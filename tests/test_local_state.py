import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch, MagicMock
from src.registry import Registry
from src.config import AIConfig, Config, FrontmatterConfig, PathsConfig
from src.webapp import create_app, _build_chat_context


class LocalStateTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = Config(PathsConfig(inbox=root/'inbox', processed_archive=root/'processed',
            output=root/'kb', images=root/'kb/images', skills=root/'skills',
            registry_db=root/'data/registry.json', logs=root/'logs'), AIConfig(), FrontmatterConfig())
        self.client = create_app(self.config).test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_persistence_and_multiple_instances(self):
        path = self.config.paths.registry_db
        first, second = Registry(path), Registry(path)
        first.mark_pending(Path('one.txt'), 'hash')
        second.mark_pending(Path('two.txt'), 'hash2')
        first.mark_done(Path('one.txt'), 'hash', Path('one.md'))
        second.mark_error(Path('two.txt'), 'hash2', 'test error')
        self.assertEqual(Registry(path).counts(), {'done': 1, 'error': 1})
        self.assertTrue(second.already_processed(Path('one.txt'), 'hash'))
        self.assertEqual(len(first.list_by_status('error')), 1)
        self.assertFalse(path.with_suffix('.db').exists())

    def test_help_guide_and_dialog(self):
        html = self.client.get('/browse').get_data(as_text=True)
        self.assertIn('id="helpDialog"', html)
        self.assertIn('aria-label="Hjälp"', html)
        self.assertIn('sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"', html)
        self.assertNotIn('id="helpFrame" src=', html)
        guide = self.client.get('/help/guide')
        self.assertEqual(guide.status_code, 200)
        self.assertIn('text/html', guide.content_type)
        self.assertIn('data/MEMORY.md', guide.get_data(as_text=True))
        self.assertEqual(self.client.get('/help/config.yaml').status_code, 404)

    def test_missing_help_file_has_clear_error(self):
        with patch('src.webapp.Path.is_file', return_value=False):
            response = self.client.get('/help/guide')
        self.assertEqual(response.status_code, 404)
        self.assertIn('Hjälpguiden saknas', response.get_data(as_text=True))

    def test_sqlite_migration_preserves_rows_and_backup(self):
        path = self.config.paths.registry_db.with_suffix('.db')
        conn = sqlite3.connect(path)
        conn.execute('CREATE TABLE files (id INTEGER, source_path TEXT, content_hash TEXT, status TEXT, output_path TEXT, error_message TEXT, discovered_at TEXT, processed_at TEXT)')
        conn.execute("INSERT INTO files VALUES (1,'old.txt','abc','done','old.md',NULL,'2026-01-01','2026-01-02')")
        conn.commit()
        conn.close()
        registry = Registry(path)
        self.assertTrue(registry.already_processed(Path('old.txt'), 'abc'))
        self.assertFalse(path.exists())
        self.assertTrue(path.with_suffix('.db.bak').exists())
        self.assertEqual(Registry(path).all_files(), registry.all_files())

    def test_corrupt_registry_is_not_overwritten(self):
        path = self.config.paths.registry_db
        path.write_text('broken', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            Registry(path).mark_pending(Path('a'), 'a')
        self.assertEqual(path.read_text(), 'broken')

    def test_settings_roundtrip_memory_and_secret(self):
        payload = {'title':'Demo1', 'memory':'Kom ihåg Älg.', 'preview_enabled':True, 'ai':{'api_key':'secret', 'temperature':0.6}}
        self.assertEqual(self.client.post('/api/settings', json=payload).status_code, 200)
        response = self.client.get('/api/settings').get_json()
        self.assertNotIn('api_key', response['ai'])
        self.assertTrue(response['ai']['has_api_key'])
        self.assertEqual(self.config.memory(), 'Kom ihåg Älg.')
        self.assertTrue(response['preview_enabled'])
        self.assertIn('Kom ihåg Älg.', _build_chat_context(self.config, []))
        fresh = Config(self.config.paths, AIConfig(), FrontmatterConfig())
        client = create_app(fresh).test_client()
        self.assertEqual(fresh.ai.api_key, 'secret')
        self.assertEqual(fresh.ai.temperature, 0.6)
        self.assertTrue(fresh.gui.preview_enabled)
        self.assertIn('Demo1', client.get('/chat').get_data(as_text=True))
        payload['ai'] = {'base_url':'http://other-server:1234/v1'}
        client.post('/api/settings', json=payload)
        self.assertEqual(fresh.ai.api_key, '')

    def test_settings_validation_and_origin(self):
        for ai in ({'temperature':9}, {'base_url':'file:///secret'}, {'context_window':-1}):
            self.assertEqual(self.client.post('/api/settings', json={'title':'X', 'ai':ai}).status_code, 400)
        self.assertFalse(self.config.settings_path.exists())
        self.assertEqual(self.client.post('/api/settings', json={}, headers={'Origin':'https://evil.example'}).status_code, 403)

    def test_models_and_connection_use_draft_without_saving(self):
        fake = MagicMock()
        fake.models.list.return_value = [MagicMock(id='gemma4:26b')]
        with patch('src.settings.build_openai_client', return_value=fake):
            response = self.client.post('/api/settings/models', json={'ai':{'model':''}})
            self.assertEqual(response.get_json()['models'], ['gemma4:26b'])
            self.assertEqual(self.client.post('/api/settings/test', json={'ai':{}}).status_code, 200)
        self.assertFalse(self.config.settings_path.exists())

    def test_chat_receives_memory_prompt_and_temperature(self):
        self.client.post('/api/settings', json={'title':'Demo', 'memory':'Globalt minne', 'ai':{'system_prompt':'Svara kort.', 'temperature':0.65}})
        fake = MagicMock()
        fake.chat.completions.create.return_value = []
        with patch('src.webapp.build_openai_client', return_value=fake):
            response = self.client.post('/api/chat', json={'messages':[{'role':'user','content':'Hej'}]})
            response.get_data()
        arguments = fake.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments['temperature'], 0.65)
        self.assertIn('Globalt minne', arguments['messages'][0]['content'])
        self.assertIn('Svara kort.', arguments['messages'][0]['content'])

    def test_export_is_markdown_and_never_overwrites(self):
        payload = {'title':'../Demo', 'messages':[{'role':'user','content':'Hej'}, {'role':'assistant','content':'# Svar'}]}
        first = self.client.post('/api/chat/export', json=payload)
        second = self.client.post('/api/chat/export', json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.get_json()['url'], second.get_json()['url'])
        files = list((self.config.paths.output/'chattar').glob('*.md'))
        self.assertEqual(len(files), 2)
        self.assertIn('## Assistent\n\n# Svar', files[0].read_text(encoding='utf-8'))
        self.assertEqual(self.client.post('/api/chat/export', json={'title':'X','messages':[{'role':'system','content':'no'}]}).status_code, 400)
