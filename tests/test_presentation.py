import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sage.presentation import render_markdown
from sage.integrations import validate_chart, generate_image, IntegrationError, search_web
from sage.config import Settings, profile_name
from sage.store import Store
from sage.agent import Agent
from sage.provider import ProviderError
from test_agent import FakeProvider


class PresentationTests(unittest.TestCase):
    def test_tables_code_and_untrusted_markup(self):
        html = render_markdown('## Comparison\n\n| Topic | Value |\n|---|---|\n| **Budget** | 50 |\n\n```python\nprint("hi")\n```\n<script>alert(1)</script>\n![tracking](https://example.com/pixel.png)\n[x](javascript:alert(1))')
        for tag in ('<table>', '<th>', '<strong>Budget</strong>', '<pre><code'):
            self.assertIn(tag, html)
        for tag in ('<script>', '<img', 'href="javascript:'):
            self.assertNotIn(tag, html)
        self.assertIn('&lt;script&gt;', html)

    def test_chart_validation(self):
        base = dict(title='Budget', type='bar', labels=['Research', 'Design'], values=[12, 24])
        self.assertEqual(validate_chart(base), base)
        for change in (dict(type=[]), dict(values=[float('nan'), 1]), dict(values=[True, 1]), dict(type='pie', values=[-1, 2]), dict(labels=[]), dict(values=[1]), dict(values=[1e30, 2])):
            with self.assertRaises(ValueError):
                validate_chart({**base, **change})

    def test_search_normalization(self):
        rows = [{'href':'https://docs.python.org/3/', 'title':'Python', 'body':'Official documentation'},
                {'href':'http://127.0.0.1/private', 'title':'Private'},
                {'href':'https://docs.python.org/3/', 'title':'Duplicate'}]
        with patch('ddgs.DDGS') as adapter:
            adapter.return_value.text.return_value = rows
            results = search_web('Python documentation')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['kind'], 'web')
        self.assertIn('retrieved_at', results[0])

    def test_image_credentials_and_provider_adapter(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(IntegrationError, 'Hugging Face token'):
                generate_image('A tree', 'test/model')
        from PIL import Image
        with patch.dict(os.environ, {'SAGE_IMAGE_API_KEY':'test-only-token'}), patch('huggingface_hub.InferenceClient') as client:
            client.return_value.text_to_image.return_value = Image.new('RGB', (8, 8), 'green')
            png = generate_image('A tree', 'test/model')
        self.assertEqual(Image.open(io.BytesIO(png)).size, (8, 8))

    def test_tool_assets_profile_permissions_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.db')
            session, other = store.session(), store.session()
            def call(name, args):
                return {'role':'assistant', 'content':None, 'tool_calls':[{'id':name, 'type':'function', 'function':{'name':name, 'arguments':json.dumps(args)}}]}
            provider = FakeProvider([call('remember_name', {'name':'Test Reader'}), call('create_chart', {'title':'Budget', 'type':'bar', 'labels':['A', 'B'], 'values':[10,20]}), {'role':'assistant','content':'## Budget\n\nTotal **30**.'}])
            result = Agent(store, provider).respond(session, 'Call me Test Reader and chart A 10 B 20')
            asset = result['assets'][0]
            self.assertIsNotNone(store.asset(session, asset['id']))
            self.assertIsNone(store.asset(other, asset['id']))
            self.assertEqual(store.history(session, rich=True)[-1]['metadata']['assets'][0]['id'], asset['id'])
            self.assertEqual(store.settings(session)['display_name'], 'Test Reader')
            self.assertEqual(profile_name(Settings(display_name='Test Reader')), 'Test Reader')
            self.assertEqual(profile_name(Settings(display_name='Test Reader', personalize=False)), '')
            for tool, args, options in [('search_web', {'query':'x'}, {'allow_web':False}), ('generate_image', {'prompt':'x'}, {'allow_images':False}), ('remember_name', {'name':'x'}, {'personalize':False})]:
                with self.assertRaises(ValueError):
                    Agent(store).execute(session, tool, args, Settings(**options))

    def test_web_sources_and_unknown_reference_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.db')
            session = store.session()
            provider = FakeProvider([{'role':'assistant','tool_calls':[{'id':'search','function':{'name':'search_web','arguments':'{"query":"public test"}'}}]}, {'role':'assistant','content':'A claim [web:ffffffffffff]'}])
            with patch('sage.agent.search_web', return_value=[{'url':'https://example.com/', 'title':'Example', 'text':'Snippet', 'kind':'web'}]):
                result = Agent(store, provider).respond(session, 'Search public test')
            self.assertTrue(result['sources'][0]['source'].startswith('web:'))
            self.assertEqual(len(result['warnings']), 1)

    def test_visible_answer_before_tool_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.db')
            provider = FakeProvider([{'role':'assistant', 'content':'Your name is Test Reader.', 'tool_calls':[{'id':'math', 'function':{'name':'calculate', 'arguments':'{"expression":"2+2"}'}}]}, {'role':'assistant', 'content':'The total is 4.'}])
            result = Agent(store, provider).respond(store.session(), 'What is my name, and what is 2+2?')
            self.assertIn('Your name is Test Reader.', result['answer'])
            self.assertIn('The total is 4.', result['answer'])

    def test_existing_history_migration_preserves_content(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.db'
            with sqlite3.connect(path) as db:
                db.executescript("CREATE TABLE messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT); INSERT INTO messages VALUES(1, 'old-session', 'assistant', 'Saved before update');")
            db.close()
            store = Store(path)
            old = store.history('old-session', rich=True)[0]
            self.assertEqual(old['content'], 'Saved before update')
            self.assertEqual(old['metadata'], {})

    def test_profile_name_from_dotenv_overrides_windows_login_name(self):
        from sage.config import load_environment
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / '.env').write_text('Username=Test Display Name\n', encoding='utf-8')
            with patch('sage.config.ROOT', Path(directory)), patch.dict(os.environ, {'Username':'WindowsLogin'}, clear=True):
                load_environment()
                self.assertEqual(profile_name(Settings()), 'Test Display Name')

    def test_short_rate_limit_retries_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.db')
            provider = FakeProvider([ProviderError('Rate limit', retry_after=12), {'role':'assistant', 'content':'Recovered answer'}])
            with patch('sage.agent.time.sleep') as sleep:
                result = Agent(store, provider).respond(store.session(), 'Hello')
            sleep.assert_called_once_with(12)
            self.assertEqual(result['answer'], 'Recovered answer')
            self.assertEqual(len(provider.requests), 2)

    def test_final_round_reserves_answer_and_limits_search(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.db')
            calls = [{'id':str(i), 'function':{'name':'search_web', 'arguments':json.dumps({'query':f'public query {i}'})}} for i in range(3)]
            provider = FakeProvider([{'role':'assistant', 'tool_calls':calls}, {'role':'assistant', 'content':'Evidence is incomplete.'}])
            with patch('sage.agent.search_web', return_value=[]) as search:
                result = Agent(store, provider).respond(store.session(), 'Research this', {'max_steps':2})
            self.assertEqual(search.call_count, 2)
            self.assertIn('two-search budget', result['steps'][-1]['result']['error'])
            self.assertEqual(provider.tool_requests[-1], [])


if __name__ == '__main__':
    unittest.main()
