import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import test_local_state
from src.citations import source_id, sources_for, citation_footer


class CitationTests(unittest.TestCase):
    tearDown = test_local_state.LocalStateTests.tearDown

    def setUp(self):
        test_local_state.LocalStateTests.setUp(self)
        self.doc = self.config.paths.output / 'källa ett.md'
        self.doc.write_text('---\ntitle: Källa\nsource_file: underlag.txt\n---\nFakta', encoding='utf-8')
        (self.config.paths.processed_archive / 'underlag.txt').write_text('Originalfakta', encoding='utf-8')
        self.key = source_id(self.doc.name)

    def test_streamed_citations_and_custom_prompt(self):
        fake = MagicMock()
        fake.chat.completions.create.return_value = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])
            for part in ['Fakta [', self.key, '].']]
        self.config.ai.system_prompt = 'Svara kort.'
        with patch('src.webapp.build_openai_client', return_value=fake):
            response = self.client.post('/api/chat', json={
                'messages': [{'role': 'user', 'content': 'Vad vet du?'}],
                'context_paths': [self.doc.name]})
            body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('### Källhänvisningar', body)
        self.assertIn('[Öppna .md](</doc/k%C3%A4lla%20ett.md>)', body)
        self.assertIn('/doc/k%C3%A4lla%20ett.md/original', body)
        prompt = fake.chat.completions.create.call_args.kwargs['messages'][0]['content']
        self.assertIn('KÄLLHÄNVISNINGAR', prompt)
        self.assertIn('Käll-ID: ' + self.key, prompt)

    def test_original_and_article_links(self):
        result = self.client.get('/doc/källa ett.md/original')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_data(as_text=True), 'Originalfakta')
        self.assertIn('inline', result.headers['Content-Disposition'])
        self.assertIn('sandbox', result.headers['Content-Security-Policy'])
        self.assertIn('Öppna original', self.client.get('/doc/källa ett.md').get_data(as_text=True))
        self.assertEqual(self.client.get('/doc/källa ett.md/download').status_code, 200)

    def test_missing_and_unsafe_originals(self):
        for source in ['missing.txt', '../outside.txt', 'C:/Windows/win.ini', '/absolute.txt']:
            self.doc.write_text(f'---\nsource_file: {source}\n---\nText', encoding='utf-8')
            self.assertEqual(self.client.get('/doc/källa ett.md/original').status_code, 404)
            footer = citation_footer('Svar', sources_for(self.config, [self.doc.name]))
            self.assertIn('Original saknas', footer)
            self.assertNotIn('/original', footer)

    def test_active_content_downloads(self):
        self.doc.write_text('---\nsource_file: active.html\n---\nText', encoding='utf-8')
        (self.config.paths.processed_archive / 'active.html').write_text('<script>alert(1)</script>')
        result = self.client.get('/doc/källa ett.md/original')
        self.assertIn('attachment', result.headers['Content-Disposition'])
        self.assertEqual(result.mimetype, 'application/octet-stream')

    def test_only_known_citations_and_honest_fallback(self):
        sources = sources_for(self.config, [self.doc.name, '../outside.md'])
        self.assertEqual(len(sources), 1)
        self.assertIn('AI:n angav inga', citation_footer('[Kunknown]', sources))
        self.assertIn('AI:n angav inga', citation_footer(f'```\n[{self.key}]\n```', sources))
        self.assertEqual(citation_footer('Svar', {}), '')
        (self.config.paths.output / 'second.md').write_text('# Second', encoding='utf-8')
        sources = sources_for(self.config, [self.doc.name, 'second.md'])
        self.assertNotIn('/doc/second.md', citation_footer(f'[{self.key}]', sources))
