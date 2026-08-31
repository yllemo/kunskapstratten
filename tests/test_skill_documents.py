import hashlib
import unittest
from unittest.mock import MagicMock, patch
import test_local_state
from src.skillbuilder import create_custom_skill, list_custom_skills


class SkillDocumentTests(unittest.TestCase):
    tearDown = test_local_state.LocalStateTests.tearDown

    def setUp(self):
        test_local_state.LocalStateTests.setUp(self)
        (self.config.paths.output/'alpha.md').write_text('# Alpha\nUnikt underlag',encoding='utf-8')
        create_custom_skill(self.config,name='Test',description='Beskrivning',instructions='Instruktion',document_paths=['alpha.md'])
        self.path = self.config.paths.skills/'_custom/test/SKILL.md'

    def test_document_gui_preserves_instructions_and_metadata(self):
        raw = self.path.read_text(encoding='utf-8').replace('custom: true','custom: true\nextra: bevara')
        self.path.write_text(raw,encoding='utf-8')
        html = self.client.get('/skills/documents/test').get_data(as_text=True)
        self.assertIn('value="alpha.md" checked',html)
        version = hashlib.sha256(raw.encode()).hexdigest()
        response = self.client.post('/skills/documents/test', data={'version':version})
        self.assertEqual(response.status_code,302)
        updated = self.path.read_text(encoding='utf-8')
        self.assertIn('extra: bevara',updated)
        self.assertEqual(updated.split('---',2)[2],raw.split('---',2)[2])
        self.assertEqual(list_custom_skills(self.config)[0]['document_paths'],[])
        self.assertEqual(self.client.post('/skills/documents/test',data={'version':version}).status_code,400)

    def test_reject_unsafe_metadata_and_new_skill_documents(self):
        raw = self.path.read_text(encoding='utf-8')
        for invalid in ['../outside.md','/absolute.md','alpha.txt']:
            response = self.client.post('/api/skill/_custom/test/SKILL.md',json={'content':raw.replace('alpha.md',invalid)})
            self.assertEqual(response.status_code,400)
        response = self.client.post('/skills/new',data={'name':'Bad','description':'Bad','documents':['missing.md']})
        self.assertNotEqual(response.status_code,302)

    def test_autorun_reads_server_metadata_and_blocks_missing(self):
        fake = MagicMock()
        fake.chat.completions.create.return_value = []
        payload = {'skill':'test','autorun_skill':True,'context_paths':[], 'messages':[{'role':'user','content':'Kör'}]}
        with patch('src.webapp.build_openai_client',return_value=fake):
            response = self.client.post('/api/chat',json=payload)
            response.get_data()
        self.assertIn('Unikt underlag',fake.chat.completions.create.call_args.kwargs['messages'][0]['content'])
        (self.config.paths.output/'alpha.md').unlink()
        with patch('src.webapp.build_openai_client') as build:
            response = self.client.post('/api/chat',json=payload)
            self.assertEqual(response.status_code,400)
            build.assert_not_called()
        self.assertIn('Saknas',self.client.get('/skills/documents/test').get_data(as_text=True))

    def test_chat_exports_presets_and_run_page_preselects(self):
        html = self.client.get('/chat').get_data(as_text=True)
        self.assertIn('"document_paths": ["alpha.md"]',html)
        self.assertIn('value="alpha.md" checked',self.client.get('/skills/run/test').get_data(as_text=True))
