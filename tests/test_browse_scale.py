from unittest.mock import patch
import unittest
import test_local_state
from src.docstore import list_documents, _cached_document
from urllib.parse import urlparse, parse_qs
from html import unescape
import re


class BrowseScaleTests(unittest.TestCase):
    document_count = 105
    tearDown = test_local_state.LocalStateTests.tearDown

    def setUp(self):
        test_local_state.LocalStateTests.setUp(self)
        for i in range(self.document_count):
            (self.config.paths.output / f'{i:03}.md').write_text(
                f'---\ntitle: Artikel {i:03}\ntags: [gemensam, tagg{i % 30:02}, extra, mer, sist]\nsource_type: txt\n---\nUnikt innehåll {i:03}', encoding='utf-8')

    def test_page_sizes_and_safe_bounds(self):
        for query, count in [('',24),('?page=5',9),('?per_page=48',48),('?per_page=999',24),('?page=-1',24),('?page=no',24),('?page=99999',9)]:
            html = self.client.get('/browse'+query).get_data(as_text=True)
            self.assertEqual(html.count('class="doc-card '), count)
        self.assertIn('Visar 97–105 av 105', self.client.get('/browse?page=5').get_data(as_text=True))

    def test_views_and_filters_survive_links(self):
        for view, marker in [('table','class="browse-table"'),('list','browse-list-item'),('cards','browse-cards')]:
            html = self.client.get(f'/browse?view={view}&tag=gemensam&sort=path&per_page=48&q=Artikel&type=txt').get_data(as_text=True)
            self.assertIn(marker, html)
            links = [parse_qs(urlparse(unescape(link)).query) for link in re.findall(r'href="([^"]+)"',html)]
            next_page = next(params for params in links if params.get('page') == ['2'])
            for key, value in [('view',view),('tag','gemensam'),('sort','path'),('per_page','48'),('q','Artikel'),('type','txt')]:
                self.assertEqual(next_page[key],[value])

    def test_tags_bounded_counted_searchable_and_active_visible(self):
        html = self.client.get('/browse?tag=tagg29').get_data(as_text=True)
        self.assertIn('Taggar <span class="count-badge">34</span>',html)
        self.assertIn('Ta bort taggfiltret tagg29', html)
        chips = html.split('<div class="tag-row">')[1].split('</div>')[0]
        self.assertEqual(chips.count('<a '),13)
        self.assertIn('gemensam <span class="count-badge">105</span>',chips)
        html = self.client.get('/browse?tq=tagg29').get_data(as_text=True)
        self.assertIn('#tagg29 <span class="count-badge">3</span>',html)
        self.assertIn('+2 taggar',html)

    def test_search_spans_pages_and_resets_excerpts(self):
        html = self.client.get('/browse?q=Unikt+innehåll+104').get_data(as_text=True)
        self.assertIn('Artikel 104', html)
        self.assertIn('Visar 1–1 av 1',html)
        self.assertNotIn('Unikt innehåll', self.client.get('/browse').get_data(as_text=True))

    def test_cached_files_refresh_on_edit_and_delete(self):
        _cached_document.cache_clear()
        list_documents(self.config.paths.output, cached=True)
        with patch('src.docstore.load_document', side_effect=AssertionError('Unchanged file was read again')):
            self.assertEqual(len(list_documents(self.config.paths.output,cached=True)),105)
        path = self.config.paths.output/'000.md'
        path.write_text('---\ntitle: Ny titel\ntags: [ny]\n---\nNy längre text',encoding='utf-8')
        self.assertIn('Ny titel', self.client.get('/browse?q=Ny').get_data(as_text=True))
        path.unlink()
        self.assertEqual(len(list_documents(self.config.paths.output,cached=True)),104)
