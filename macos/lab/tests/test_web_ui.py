"""The Mac web layer: local page assets, then guarded intake before the pinned shell's handler."""
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import web_ui
from web_ui import BUSY, INTAKE_SECONDS, MAX_BODY_BYTES, WEB, bounded_server, mac_handler_factory

KEY = 'fixture-key'
CHAT = b'{"messages": [{"role": "user", "content": "hi"}]}'


class PinnedHandler(BaseHTTPRequestHandler):
    """The pinned shell's handler contract: its own key check, JSON answers and body reads."""
    protocol_version = 'HTTP/1.0'

    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if not self.svc.api_key:
            return True
        auth = self.headers.get('Authorization', '')
        given = auth[7:].strip() if auth.lower().startswith('bearer ') else self.headers.get('x-api-key', '')
        if given == self.svc.api_key:
            return True
        self._json(401, {'error': {'type': 'authentication_error'}})
        return False

    def do_GET(self):
        self.svc.calls.append(('GET', self.path))
        if self.path == '/metrics' and not self._authorized():
            return
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(b'data: [DONE]\n\n')
            return
        self._json(200, {'path': self.path})

    def do_POST(self):
        if not self._authorized():
            return
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.svc.calls.append(('POST', self.path, body))
        self._json(200, {'received': len(body)})


def pinned_factory(service):
    class Pinned(PinnedHandler):
        svc = service
    return Pinned


class Reader(BytesIO):
    """The socket's read side; stays inspectable after the handler closes it."""
    def close(self):
        self.closed_by_handler = True


class SlowReader(Reader):
    def read1(self, size=-1):
        raise TimeoutError('fixture body never arrived')


class Socket:
    def __init__(self, raw, reader=Reader):
        self.reader = reader(raw)
        self.sent = bytearray()
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def makefile(self, mode, buffering=None):
        return self.reader

    def sendall(self, data):
        self.sent += data


def raw_request(method='GET', path='/health', headers=None, body=b'', host='127.0.0.1:8095'):
    lines = [f'{method} {path} HTTP/1.1']
    if host is not None:
        lines.append(f'Host: {host}')
    if body and not any(name.lower() in ('content-length', 'transfer-encoding') for name, _ in headers or ()):
        lines.append(f'Content-Length: {len(body)}')
    lines += [f'{name}: {value}' for name, value in headers or ()]
    return ('\r\n'.join(lines) + '\r\n\r\n').encode() + body


class Reply:
    def __init__(self, sock, service, handler):
        head, _, self.body = bytes(sock.sent).partition(b'\r\n\r\n')
        status, *fields = head.decode().split('\r\n')
        self.code = int(status.split()[1])
        self.headers = {}
        for field in fields:
            name, _, value = field.partition(':')
            self.headers.setdefault(name.lower(), []).append(value.strip())
        self.calls, self.sock, self.handler = service.calls, sock, handler

    def json(self):
        return json.loads(self.body)


class WebLayerCase(unittest.TestCase):
    def setUp(self):
        web_ui.host_names.cache_clear()
        self.addCleanup(web_ui.host_names.cache_clear)

    def exchange(self, raw, api_key='', address='127.0.0.1', reader=Reader):
        service = SimpleNamespace(api_key=api_key, calls=[])
        sock = Socket(raw, reader)
        handler = mac_handler_factory(pinned_factory)(service)(sock, ('127.0.0.1', 50000),
                                                               SimpleNamespace(server_address=(address, 8095)))
        return Reply(sock, service, handler)

    def send(self, *args, api_key='', address='127.0.0.1', **kwargs):
        return self.exchange(raw_request(*args, **kwargs), api_key, address)

    def post(self, path='/v1/chat/completions', origin=None, content_type='application/json', body=CHAT, **kwargs):
        headers = [*kwargs.pop('headers', [])]
        if origin is not None:
            headers.append(('Origin', origin))
        if content_type is not None:
            headers.append(('Content-Type', content_type))
        return self.send('POST', path, headers, body, **kwargs)

    def assert_refused(self, reply, code):
        self.assertEqual(reply.code, code, reply.body)
        self.assertEqual(reply.calls, [])
        self.assertEqual(reply.headers['cache-control'], ['no-store'])


class PageTests(WebLayerCase):
    def test_page_is_local_and_preserves_api_shell_controls(self):
        reply = self.send(path='/')
        body = reply.body.decode()
        self.assertEqual(reply.code, 200)
        self.assertIn('text/html', reply.headers['content-type'][0])
        self.assertEqual(reply.headers['cache-control'], ['no-cache'])
        self.assertIn('id="composer"', body)
        self.assertIn('id="stop-btn"', body)
        self.assertIn('id="api-key"', body)
        self.assertIn('/web/mac.js', body)
        self.assertLess(body.index('/web/ui-state.js'), body.index('/web/app.js'))
        self.assertLess(body.index('/web/ui-state.js'), body.index('/web/mac.js'))
        self.assertIn('/web/performance.js', body)
        self.assertNotIn('https://cdn', body)
        self.assertEqual(int(reply.headers['content-length'][0]), len(reply.body))
        self.assertEqual(reply.calls, [])

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
        for path, mime in [('/web/mac.css?v=2', 'text/css'), ('/web/mac.js', 'text/javascript'),
                           ('/web/ui-state.js', 'text/javascript'), ('/web/performance.js', 'text/javascript')]:
            with self.subTest(path=path):
                reply = self.send(path=path)
                self.assertEqual(reply.code, 200)
                self.assertTrue(reply.headers['content-type'][0].startswith(mime))
                self.assertEqual(reply.headers['cache-control'], ['no-cache'])
                self.assertGreater(len(reply.body), 50)

    def test_protected_api_and_original_assets_stay_with_original_handler(self):
        for path in ['/health', '/metrics', '/settings', '/status', '/web/app.js', '/web/sprite.svg',
                     '/fonts/outfit-latin-wght.woff2']:
            with self.subTest(path=path):
                reply = self.send(path=path)
                self.assertEqual(reply.calls, [('GET', path)])
                self.assertEqual(reply.json(), {'path': path})

    def test_traversal_is_not_a_local_asset(self):
        for path in ['/web/../scripts/run.py', '/web/%2e%2e/index.html', '/web/mac.js/../index.html',
                     '/web/mac.js%00', '/web/secret.json']:
            with self.subTest(path=path):
                self.assertEqual(self.send(path=path).calls, [('GET', path)])

    def test_post_keeps_original_request_behavior(self):
        for path in ('/v1/chat/completions', '/v1/messages', '/settings'):
            with self.subTest(path=path):
                reply = self.post(path)
                self.assertEqual(reply.code, 200)
                self.assertEqual(reply.calls, [('POST', path, CHAT)])

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


class HostTests(WebLayerCase):
    ALLOWED = ['127.0.0.1:8095', 'localhost:8095', 'LOCALHOST:8095', '[::1]:8095', 'app.localhost:8095',
               '127.0.0.1', '192.168.1.5:8095', None]
    REFUSED = ['evil.example:8095', 'evil.example', '127.0.0.1.nip.io:8095', 'localhost:http', '[::1]x',
               'my mac:8095', 'mymac.local:8095']

    def test_loopback_names_and_addresses_reach_the_pinned_handler(self):
        for host in self.ALLOWED:
            with self.subTest(host=host):
                self.assertEqual(self.send(host=host).calls, [('GET', '/health')])
                self.assertEqual(self.post(host=host).calls, [('POST', '/v1/chat/completions', CHAT)])

    def test_rebinding_names_are_refused_before_any_route(self):
        for host in self.REFUSED:
            for method in ('GET', 'POST'):
                with self.subTest(host=host, method=method):
                    reply = self.send(host=host) if method == 'GET' else self.post(host=host)
                    self.assert_refused(reply, 403)
                    self.assertIn('DNS rebinding', reply.json()['error']['message'])
                    # The unread body is dropped so the client receives the answer, not a reset.
                    self.assertEqual(reply.sock.reader.tell(), len(reply.sock.reader.getvalue()))

    def test_listening_beyond_loopback_also_answers_to_this_mac_name(self):
        with patch.object(web_ui.socket, 'gethostname', return_value='MyMac'):
            for host in ('mymac:8095', 'mymac.local:8095', 'host.docker.internal:8095', '0.0.0.0:8095'):
                with self.subTest(host=host):
                    self.assertEqual(self.send(host=host, address='0.0.0.0').calls, [('GET', '/health')])
            self.assert_refused(self.send(host='evil.example:8095', address='0.0.0.0'), 403)
            self.assert_refused(self.send(host='mymac.local:8095'), 403)
        web_ui.host_names.cache_clear()
        with patch.object(web_ui.socket, 'gethostname', side_effect=OSError('no name')):
            self.assertEqual(self.send(host='strata.lan:8095', address='strata.lan').calls, [('GET', '/health')])
            self.assert_refused(self.send(host='other.lan:8095', address='strata.lan'), 403)

    def test_api_key_decides_instead_of_the_host_name(self):
        reply = self.send(host='evil.example:8095', api_key=KEY)
        self.assertEqual(reply.calls, [('GET', '/health')])
        refused = self.post(host='evil.example:8095', api_key=KEY)
        self.assert_refused(refused, 401)
        self.assertEqual(refused.sock.reader.tell(), len(refused.sock.reader.getvalue()))
        accepted = self.post(host='evil.example:8095', api_key=KEY, headers=[('Authorization', 'Bearer ' + KEY)])
        self.assertEqual(accepted.calls, [('POST', '/v1/chat/completions', CHAT)])


class OriginTests(WebLayerCase):
    PATHS = ('/v1/chat/completions', '/v1/messages', '/settings')
    ALLOWED = [None, 'http://127.0.0.1:8095', 'http://localhost:5173', 'http://app.localhost:8080/',
               'chrome-extension://abcdef', 'app://strata']
    REFUSED = ['http://evil.example', 'null', '', 'http://192.168.1.9:8095', 'https://localhost.evil.example',
               'http://127.0.0.1.evil.example:8095', 'http://[::1]x']

    def test_local_pages_and_clients_without_origin_are_accepted(self):
        for path in self.PATHS:
            for origin in self.ALLOWED:
                with self.subTest(path=path, origin=origin):
                    self.assertEqual(self.post(path, origin).calls, [('POST', path, CHAT)])

    def test_foreign_pages_cannot_start_inference_or_change_settings(self):
        for path in self.PATHS:
            for origin in self.REFUSED:
                with self.subTest(path=path, origin=origin):
                    reply = self.post(path, origin)
                    self.assert_refused(reply, 403)
                    self.assertEqual(reply.json()['error']['type'], 'forbidden')

    def test_browser_pages_must_send_json_but_command_line_clients_need_not(self):
        for content_type in ('text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data', None):
            with self.subTest(content_type=content_type):
                self.assert_refused(self.post(origin='http://127.0.0.1:8095', content_type=content_type), 415)
                self.assertEqual(len(self.post(content_type=content_type).calls), 1)

    def test_with_an_api_key_the_key_decides_for_every_page(self):
        self.assert_refused(self.post(origin='http://evil.example', content_type='text/plain', api_key=KEY), 401)
        reply = self.post(origin='http://evil.example', content_type='text/plain', api_key=KEY,
                          headers=[('x-api-key', KEY)])
        self.assertEqual(reply.calls, [('POST', '/v1/chat/completions', CHAT)])


class BodyTests(WebLayerCase):
    def framed(self, *headers, body=CHAT):
        return self.exchange(raw_request('POST', '/v1/chat/completions', [*headers], body))

    def test_ambiguous_or_malformed_framing_is_refused_without_reading(self):
        for headers in ([('Content-Length', '-1')], [('Content-Length', '+5')], [('Content-Length', '0x10')],
                        [('Content-Length', '1e3')], [('Content-Length', '')], [('Content-Length', '５')],
                        [('Content-Length', str(len(CHAT)))] * 2, [('Transfer-Encoding', 'chunked')],
                        [('Transfer-Encoding', 'chunked'), ('Content-Length', str(len(CHAT)))]):
            with self.subTest(headers=headers):
                reply = self.framed(*headers)
                self.assert_refused(reply, 400)
                self.assertEqual(reply.sock.reader.tell(), len(reply.sock.reader.getvalue()) - len(CHAT))

    def test_oversized_body_is_refused_before_it_is_read(self):
        reply = self.framed(('Content-Length', str(MAX_BODY_BYTES + 1)))
        self.assert_refused(reply, 413)
        self.assertIn('16 MiB', reply.json()['error']['message'])
        reads = []
        original = Reader.read1
        with patch.object(Reader, 'read1', lambda self, size=-1: reads.append(size) or original(self, size)):
            self.framed(('Content-Length', str(10**12)))
        self.assertTrue(reads and max(reads) <= web_ui.READ_PIECE)

    def test_largest_allowed_body_and_missing_length_reach_the_pinned_handler(self):
        body = b'x' * MAX_BODY_BYTES
        self.assertEqual(self.framed(body=body).calls, [('POST', '/v1/chat/completions', body)])
        self.assertEqual(self.framed(body=b'').calls, [('POST', '/v1/chat/completions', b'')])

    def test_short_or_slow_bodies_end_with_an_answer(self):
        short = self.framed(('Content-Length', '200'))
        self.assert_refused(short, 400)
        self.assertIn('ended before', short.json()['error']['message'])
        slow = self.exchange(raw_request('POST', '/v1/chat/completions', body=CHAT), reader=SlowReader)
        self.assert_refused(slow, 408)
        clock = iter([0.0, INTAKE_SECONDS + 1])
        with patch.object(web_ui.time, 'monotonic', side_effect=lambda: next(clock)):
            self.assert_refused(self.framed(), 408)

    def test_intake_has_a_deadline_but_answers_and_streams_do_not(self):
        post = self.post()
        self.assertEqual(post.sock.timeouts[0], INTAKE_SECONDS)
        self.assertTrue(0 < post.sock.timeouts[1] <= INTAKE_SECONDS)
        self.assertIsNone(post.sock.timeouts[-1])
        stream = self.send(path='/stream')
        self.assertEqual(stream.sock.timeouts, [INTAKE_SECONDS, None])
        self.assertEqual(stream.headers['cache-control'], ['no-cache'])
        self.assertEqual(stream.body, b'data: [DONE]\n\n')

    def test_private_answers_are_not_cached(self):
        for reply in (self.send(path='/metrics'), self.send(path='/status'), self.post()):
            with self.subTest(path=reply.calls[0][1]):
                self.assertEqual(reply.headers['cache-control'], ['no-store'])

    def test_finish_closes_the_socket_reader_after_replacing_it(self):
        reply = self.post()
        self.assertTrue(reply.sock.reader.closed_by_handler)
        self.assertIsNot(reply.handler.rfile, reply.sock.reader)
        self.assertTrue(reply.handler.rfile.closed)

    def test_failed_answer_write_closes_the_connection(self):
        class Broken(Socket):
            def sendall(self, data):
                raise BrokenPipeError('client left')
        service = SimpleNamespace(api_key='', calls=[])
        handler_type = mac_handler_factory(pinned_factory)(service)
        handler = handler_type(Broken(raw_request(host='evil.example')), ('127.0.0.1', 1),
                               SimpleNamespace(server_address=('127.0.0.1', 8095)))
        self.assertTrue(handler.close_connection)
        self.assertEqual(service.calls, [])


class StatusTests(WebLayerCase):
    def test_status_needs_the_api_key_when_one_is_set(self):
        self.assertEqual(self.send(path='/status').calls, [('GET', '/status')])
        refused = self.send(path='/status', api_key=KEY)
        self.assert_refused(refused, 401)
        for header in (('Authorization', 'Bearer ' + KEY), ('x-api-key', KEY)):
            with self.subTest(header=header[0]):
                reply = self.send(path='/status', api_key=KEY, headers=[header])
                self.assertEqual(reply.calls, [('GET', '/status')])
        self.assert_refused(self.send(path='/status', api_key=KEY, headers=[('x-api-key', 'wrong')]), 401)
        self.assertEqual(self.send(path='/health', api_key=KEY).calls, [('GET', '/health')])


class ConnectionLimitTests(unittest.TestCase):
    class Original(ThreadingHTTPServer):
        def process_request(self, request, client_address):
            if getattr(request, 'fail', False):
                raise RuntimeError('thread start failed')
            self.started.append(request)

        def process_request_thread(self, request, client_address):
            self.finished.append(request)

        def shutdown_request(self, request):
            request.closed = True

    class Request:
        def __init__(self, fail=False, send_error=None, incoming=(b'GET / HTTP/1.1\r\n\r\n',)):
            self.fail, self.send_error, self.sent, self.closed = fail, send_error, b'', False
            self.incoming, self.events = list(incoming), []

        def settimeout(self, value):
            self.timeout = value

        def sendall(self, data):
            if self.send_error:
                raise self.send_error
            self.sent += data

        def shutdown(self, how):
            self.events.append('stop sending')

        def recv(self, size):
            self.events.append('read')
            return self.incoming.pop(0) if self.incoming else b''

    class Thread:
        """Records each refusal thread; ``run()`` stands in for the thread running later."""
        started = []

        def __init__(self, target, args, daemon):
            self.target, self.args, self.daemon = target, args, daemon

        def start(self):
            self.started.append(self)

        def run(self):
            self.target(*self.args)

    def setUp(self):
        self.Thread.started = []
        patcher = patch.object(web_ui.threading, 'Thread', self.Thread)
        patcher.start()
        self.addCleanup(patcher.stop)

    def server(self, slots=2):
        server = object.__new__(bounded_server(self.Original))
        server.slots, server.started, server.finished = threading.BoundedSemaphore(slots), [], []
        server.refusals = threading.BoundedSemaphore(slots)
        return server

    def refused(self, server, request):
        server.process_request(request, ('127.0.0.1', 1))
        thread = self.Thread.started.pop()
        self.assertTrue(thread.daemon)
        self.assertFalse(request.closed, 'The accept loop must not wait for a refused client')
        thread.run()

    def free(self, semaphore):
        count = 0
        while semaphore.acquire(blocking=False):
            count += 1
        for _ in range(count):
            semaphore.release()
        return count

    def test_requests_beyond_the_bound_get_busy_and_are_closed(self):
        server = self.server()
        first, second, third, fourth = (self.Request() for _ in range(4))
        for request in (first, second):
            server.process_request(request, ('127.0.0.1', 1))
        self.refused(server, third)
        self.assertEqual(server.started, [first, second])
        self.assertTrue(third.closed)
        self.assertEqual(third.sent, BUSY)
        # The unread request is read after the answer, so closing does not reset the connection.
        self.assertEqual(third.events, ['stop sending', 'read', 'read'])
        self.assertEqual(self.free(server.refusals), 2)
        server.process_request_thread(first, ('127.0.0.1', 1))
        server.process_request(fourth, ('127.0.0.1', 1))
        self.assertEqual(server.started, [first, second, fourth])

    def test_refusals_are_bounded_and_a_slow_client_is_not_waited_on(self):
        server = self.server(slots=1)
        server.process_request(self.Request(), ('127.0.0.1', 1))
        waiting = self.Request()
        server.process_request(waiting, ('127.0.0.1', 1))  # Its refusal thread has not run yet.
        beyond = self.Request()
        server.process_request(beyond, ('127.0.0.1', 1))
        self.assertTrue(beyond.closed)
        self.assertEqual((beyond.sent, beyond.events), (b'', []))
        self.assertEqual(len(self.Thread.started), 1)
        endless = self.Request(incoming=[b'x'] * 1000)
        clock = iter([0.0, 0.5, 1.0, 1.5, web_ui.DRAIN_SECONDS + 1])
        self.Thread.started.pop().run()
        with patch.object(web_ui.time, 'monotonic', lambda: next(clock)):
            self.refused(server, endless)
        self.assertTrue(endless.closed)
        self.assertEqual(endless.events.count('read'), 3)

    def test_failed_thread_start_or_busy_write_releases_resources(self):
        server = self.server(slots=1)
        with self.assertRaises(RuntimeError):
            server.process_request(self.Request(fail=True), ('127.0.0.1', 1))
        accepted = self.Request()
        server.process_request(accepted, ('127.0.0.1', 1))
        refused = self.Request(send_error=BrokenPipeError('client left'))
        self.refused(server, refused)
        self.assertEqual(server.started, [accepted])
        self.assertTrue(refused.closed)
        self.assertEqual(refused.events, [])
        self.assertEqual(self.free(server.refusals), 1)

    def test_binding_does_not_wait_for_a_dns_name(self):
        class Socket:
            def setsockopt(self, *args): pass
            def bind(self, address): self.address = address
            def getsockname(self): return ('127.0.0.1', 8095)
        server = self.server()
        server.socket, server.server_address = Socket(), ('127.0.0.1', 0)
        with patch('socket.getfqdn', side_effect=AssertionError('DNS lookup at startup')):
            server.server_bind()
        self.assertEqual((server.socket.address, server.server_name, server.server_port),
                         (('127.0.0.1', 0), '127.0.0.1', 8095))

    def test_busy_answer_is_complete_http(self):
        head, _, body = BUSY.partition(b'\r\n\r\n')
        self.assertTrue(head.startswith(b'HTTP/1.0 503 '))
        self.assertIn(f'Content-Length: {len(body)}'.encode(), head)
        self.assertEqual(json.loads(body)['error']['type'], 'server_error')

    def test_construction_creates_the_configured_bound(self):
        with patch.object(self.Original, '__init__', lambda self, *args, **kwargs: None):
            server = bounded_server(self.Original)(('127.0.0.1', 0), BaseHTTPRequestHandler)
        self.assertEqual((self.free(server.slots), self.free(server.refusals)),
                         (web_ui.MAX_CONNECTIONS, web_ui.MAX_CONNECTIONS))


if __name__ == '__main__':
    unittest.main()
