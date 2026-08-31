import unittest
import test_local_state
from src.registry import Registry
from src.skillbuilder import create_custom_skill


class DeletionTests(unittest.TestCase):
    tearDown = test_local_state.LocalStateTests.tearDown

    def setUp(self):
        test_local_state.LocalStateTests.setUp(self)
        self.doc = self.config.paths.output / 'alpha.md'
        self.doc.write_text('---\nsource_file: alpha.txt\n---\nText', encoding='utf-8')
        self.original = self.config.paths.processed_archive / 'alpha.txt'
        self.original.write_text('Original', encoding='utf-8')
        self.url = '/api/delete/doc/alpha.md'

    def delete(self, url):
        plan = self.client.get(url).get_json()
        return self.client.delete(url, json={'confirm': True, 'version': plan['version']})

    def test_deletes_doc_original_and_registry_but_preserves_other_files(self):
        registry = Registry(self.config.paths.registry_db)
        registry.mark_done(self.config.paths.inbox / 'alpha.txt', 'hash', self.doc)
        other = self.config.paths.output / 'other.md'
        other.write_text('Keep', encoding='utf-8')
        registry.mark_done(self.config.paths.inbox / 'other.txt', 'other', other)
        self.assertIn('deleteItemBtn', self.client.get('/doc/alpha.md/edit').get_data(as_text=True))
        self.assertEqual(self.delete(self.url).status_code, 200)
        self.assertFalse(self.doc.exists())
        self.assertFalse(self.original.exists())
        self.assertTrue(other.exists())
        self.assertEqual(len(registry.all_files()), 1)
        self.assertEqual(self.client.get('/doc/alpha.md').status_code, 404)

    def test_requires_confirmation_and_fresh_version(self):
        plan = self.client.get(self.url).get_json()
        self.assertEqual(self.client.delete(self.url, json=plan).status_code, 409)
        self.doc.write_text('# Changed and longer', encoding='utf-8')
        self.assertEqual(self.client.delete(self.url, json={'confirm': True, 'version': plan['version']}).status_code, 409)
        self.assertTrue(self.original.exists())
        self.assertTrue(self.doc.exists())

    def test_skill_does_not_delete_selected_documents(self):
        create_custom_skill(self.config, name='Test', description='Test', instructions='Test', document_paths=['alpha.md'])
        url = '/api/delete/skill/_custom/test/SKILL.md'
        self.assertIn('deleteItemBtn', self.client.get('/skills/edit/_custom/test/SKILL.md').get_data(as_text=True))
        self.assertEqual(self.delete(url).status_code, 200)
        self.assertTrue(self.doc.exists())
        self.assertTrue(self.original.exists())
        self.assertFalse((self.config.paths.skills / '_custom/test/SKILL.md').exists())

    def test_shared_original_blocks_deletion(self):
        (self.config.paths.output / 'other.md').write_text(self.doc.read_text(encoding='utf-8'), encoding='utf-8')
        self.assertEqual(self.client.get(self.url).status_code, 400)
        self.assertTrue(self.doc.exists())
        self.assertTrue(self.original.exists())

    def test_skill_removes_its_own_original(self):
        create_custom_skill(self.config, name='Test', description='Test', instructions='Test')
        skill = self.config.paths.skills / '_custom/test/SKILL.md'
        skill.write_text(skill.read_text(encoding='utf-8').replace('---', '---\nsource_file: skill.txt', 1), encoding='utf-8')
        original = self.config.paths.processed_archive / 'skill.txt'
        original.write_text('Skill original', encoding='utf-8')
        self.assertEqual(self.delete('/api/delete/skill/_custom/test/SKILL.md').status_code, 200)
        self.assertFalse(original.exists())
        self.assertTrue(self.original.exists())

    def test_missing_original_and_invalid_paths(self):
        self.original.unlink()
        self.assertEqual(self.delete(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get('/api/delete/doc/../config.yaml').status_code, 400)

    def test_cross_origin_deletion_is_blocked(self):
        response = self.client.delete(self.url, json={'confirm': True}, headers={'Origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.doc.exists())
