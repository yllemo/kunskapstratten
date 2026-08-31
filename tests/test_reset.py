import unittest
from unittest.mock import patch
import test_local_state
from src.reset import reset_plan


class ResetTests(unittest.TestCase):
    tearDown = test_local_state.LocalStateTests.tearDown

    def setUp(self):
        test_local_state.LocalStateTests.setUp(self)
        paths = self.config.paths
        for path, content in [(paths.output/'article.md','# Article'),
                              (paths.skills/'SKILL.md','# Skill'),
                              (paths.processed_archive/'original.pdf','original'),
                              (paths.registry_db.parent/'settings.json','{}'),
                              (paths.registry_db.parent/'MEMORY.md','memory'),
                              (paths.inbox/'keep.md','inbox'),
                              (paths.images/'keep.png','image'),
                              (paths.logs/'keep.log','log')]:
            path.write_text(content,encoding='utf-8')

    def challenge(self):
        response = self.client.post('/api/reset/challenge',json={})
        self.assertEqual(response.status_code,200)
        data = response.get_json()
        a,b = data['question'].replace('=','').split('+')
        return {'token':data['token'],'answer':str(int(a)+int(b)),'confirmed':True}

    def test_both_confirmations_required_and_token_single_use(self):
        payload = self.challenge()
        self.assertEqual(self.client.post('/api/reset',json={**payload,'confirmed':False}).status_code,400)
        self.assertEqual(self.client.post('/api/reset',json={**payload,'answer':'999'}).status_code,400)
        self.assertEqual(self.client.post('/api/reset',json=payload).status_code,400)
        self.assertTrue((self.config.paths.output/'article.md').exists())

    def test_reset_exact_scope(self):
        response = self.client.post('/api/reset',json=self.challenge())
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()['removed'],5)
        self.assertEqual(list(self.config.paths.output.rglob('*.md')),[])
        for folder in (self.config.paths.skills,self.config.paths.processed_archive,self.config.paths.registry_db.parent):
            self.assertEqual(list(folder.iterdir()),[])
        for path in (self.config.paths.inbox/'keep.md',self.config.paths.images/'keep.png',self.config.paths.logs/'keep.log'):
            self.assertTrue(path.exists())

    def test_expired_and_other_session_rejected(self):
        payload = self.challenge()
        other = self.client.application.test_client()
        self.assertEqual(other.post('/api/reset',json=payload).status_code,400)
        with patch('src.reset.time.monotonic',return_value=10**20):
            self.assertEqual(self.client.post('/api/reset',json=payload).status_code,400)

    def test_changed_files_require_new_review(self):
        payload = self.challenge()
        (self.config.paths.output/'new.md').write_text('new',encoding='utf-8')
        self.assertEqual(self.client.post('/api/reset',json=payload).status_code,409)
        self.assertTrue((self.config.paths.output/'article.md').exists())

    def test_broad_or_overlapping_targets_rejected(self):
        self.config.paths.skills = self.config.paths.output
        with self.assertRaises(ValueError):
            reset_plan(self.config)
        self.config.paths.skills = self.config.paths.output.parent
        with self.assertRaises(ValueError):
            reset_plan(self.config)

    def test_cross_origin_rejected(self):
        self.assertEqual(self.client.post('/api/reset/challenge',json={},headers={'Origin':'https://other.example'}).status_code,403)

    def test_links_block_deletion(self):
        with patch('src.reset._is_link',side_effect=lambda p: p.name == 'article.md'):
            self.assertEqual(self.client.post('/api/reset/challenge',json={}).status_code,400)
        self.assertTrue((self.config.paths.output/'article.md').exists())

    def test_runtime_settings_return_to_initial_values(self):
        self.client.post('/api/settings',json={'title':'Testtitel','memory':'Testminne','ai':{'model':'testmodell'}})
        self.assertEqual(self.client.post('/api/reset',json=self.challenge()).status_code,200)
        self.assertEqual(self.config.title,'Kunskapstratten')
        self.assertEqual(self.config.ai.model,'gemma4:26b')
        self.assertEqual(self.config.memory(),'')

    def test_busy_stream_blocks_reset(self):
        from types import SimpleNamespace
        fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: iter([
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='hello'))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='world'))])]))))
        with patch('src.webapp.build_openai_client',return_value=fake):
            response = self.client.post('/api/chat',json={'messages':[{'role':'user','content':'Hej'}]},buffered=False)
            self.assertEqual(self.client.post('/api/reset/challenge',json={}).status_code,409)
            response.close()
        self.assertEqual(self.client.post('/api/reset/challenge',json={}).status_code,200)
