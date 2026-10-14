"""The Mac static layer must never take over API routes or serve arbitrary files."""
from io import BytesIO
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from web_ui import WEB, mac_handler_factory


class OriginalHandler:
    def do_GET(self):
        self.delegated = self.path

    def do_POST(self):
        self.delegated = 'POST ' + self.path

    def send_response(self, code):
        self.code = code

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass


class WebUITests(unittest.TestCase):
    def handler(self, path):
        cls = mac_handler_factory(lambda service: OriginalHandler)(object())
        h = object.__new__(cls)
        h.path, h.headers, h.wfile, h.delegated = path, {}, BytesIO(), None
        return h

    def test_page_is_local_and_preserves_api_shell_controls(self):
        h = self.handler('/')
        h.do_GET()
        body = h.wfile.getvalue().decode()
        self.assertEqual(h.code, 200)
        self.assertIn('text/html', h.headers['Content-Type'])
        self.assertIn('id="composer"', body)
        self.assertIn('id="stop-btn"', body)
        self.assertIn('id="api-key"', body)
        self.assertIn('/web/mac.js', body)
        self.assertLess(body.index('/web/ui-state.js'), body.index('/web/app.js'))
        self.assertLess(body.index('/web/ui-state.js'), body.index('/web/mac.js'))
        self.assertIn('/web/performance.js', body)
        self.assertNotIn('https://cdn', body)
        self.assertEqual(int(h.headers['Content-Length']), len(h.wfile.getvalue()))

    def test_form_controls_keep_visible_and_explicit_accessible_names(self):
        class Names(HTMLParser):
            def __init__(self):
                super().__init__()
                self.controls = {}
                self.labels = set()

            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag in ('input', 'textarea'):
                    self.controls[values.get('id')] = values.get('aria-label')
                if tag == 'label':
                    self.labels.add(values.get('for'))

        names = Names()
        names.feed((WEB / 'index.html').read_text())
        for control, label in [('input', 'Your message'), ('s-temp', 'Temperature'),
                               ('s-topp', 'Top-p'), ('s-topk', 'Top-k'),
                               ('s-max', 'Max tokens'), ('s-seed', 'Seed')]:
            with self.subTest(control=control):
                self.assertEqual(names.controls[control], label)
                self.assertIn(control, names.labels)

    def test_shared_settings_status_uses_a_live_semantic_output(self):
        class Status(HTMLParser):
            def __init__(self):
                super().__init__()
                self.element = None

            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if values.get('id') == 'shared-status':
                    self.element = (tag, values)

        status = Status()
        status.feed((WEB / 'index.html').read_text())
        tag, attrs = status.element
        self.assertEqual(tag, 'output')
        self.assertEqual(attrs['aria-live'], 'polite')
        self.assertEqual(attrs['aria-atomic'], 'true')
        self.assertIn('shared-status', attrs['class'].split())
        self.assertNotIn('role', attrs)

    def test_css_and_js_mime_and_cache_allow_refresh(self):
        for path, mime in [('/web/mac.css?v=2', 'text/css'), ('/web/mac.js', 'text/javascript'), ('/web/ui-state.js', 'text/javascript'), ('/web/performance.js', 'text/javascript')]:
            with self.subTest(path=path):
                h = self.handler(path)
                h.do_GET()
                self.assertEqual(h.code, 200)
                self.assertTrue(h.headers['Content-Type'].startswith(mime))
                self.assertEqual(h.headers['Cache-Control'], 'no-cache')
                self.assertGreater(len(h.wfile.getvalue()), 50)

    def test_protected_api_and_original_assets_stay_with_original_handler(self):
        for path in ['/health', '/metrics', '/settings', '/status', '/web/app.js', '/web/sprite.svg', '/fonts/outfit-latin-wght.woff2']:
            with self.subTest(path=path):
                h = self.handler(path)
                h.do_GET()
                self.assertEqual(h.delegated, path)
                self.assertEqual(h.wfile.getvalue(), b'')

    def test_traversal_is_not_a_local_asset(self):
        for path in ['/web/../scripts/run.py', '/web/%2e%2e/index.html', '/web/mac.js/../index.html', '/web/mac.js%00', '/web/secret.json']:
            with self.subTest(path=path):
                h = self.handler(path)
                h.do_GET()
                self.assertEqual(h.delegated, path)
                self.assertEqual(h.wfile.getvalue(), b'')

    def test_post_keeps_original_request_behavior(self):
        h = self.handler('/v1/chat/completions')
        h.do_POST()
        self.assertEqual(h.delegated, 'POST /v1/chat/completions')

    def test_pinned_script_keeps_every_existing_control_id(self):
        class Controls(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = []

            def handle_starttag(self, tag, attrs):
                self.ids.extend(value for key, value in attrs if key == 'id')

        original, maintained = Controls(), Controls()
        original.feed((WEB.parent / 'vendor/Strata-macOS/serve/web/index.html').read_text())
        maintained.feed((WEB / 'index.html').read_text())
        self.assertTrue(set(original.ids).issubset(maintained.ids))
        self.assertEqual(len(maintained.ids), len(set(maintained.ids)))


if __name__ == '__main__':
    unittest.main()
