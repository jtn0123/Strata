"""The real Mac server (pinned shell, mock engine, no model) over local sockets: guarded intake end to end."""
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from web_ui import MAX_CONNECTIONS

KEY = 'fixture-key'
CHAT = dict(model='flash', messages=[dict(role='user', content='hi')], max_tokens=256)


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class Server:
    """One owned mock-engine server process on a free loopback port."""

    def __init__(self, api_key=''):
        self.port = free_port()
        self.log = tempfile.TemporaryFile()
        env = dict(os.environ, STRATA_API_KEY=api_key)
        # Unbuffered, with faulthandler: a server that does not start leaves its thread stacks in the log.
        self.process = subprocess.Popen([sys.executable, '-u', '-X', 'faulthandler',
                                         str(ROOT / 'scripts/strata_server.py'), '--engine', 'mock',
                                         '--host', '127.0.0.1', '--port', str(self.port)],
                                        stdout=self.log, stderr=subprocess.STDOUT, env=env, cwd=ROOT)
        deadline, last = time.monotonic() + 30, None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail_start('exited')
            try:
                last = self.request('GET', '/health')[0]
                if last == 200:
                    return
            except OSError as error:
                last = error
            time.sleep(.1)
        self.fail_start(f'was not ready (last /health: {last!r})')

    def fail_start(self, problem):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGABRT)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        output = self.output()
        self.log.close()
        raise RuntimeError(f'Mock server {problem}: {output}')

    def output(self):
        self.log.seek(0)
        return self.log.read().decode(errors='replace')

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.log.close()

    def request(self, method, path, body=None, headers=None, host=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            connection.putrequest(method, path, skip_host=host is not None, skip_accept_encoding=True)
            if host is not None:
                connection.putheader('Host', host)
            data = json.dumps(body).encode() if isinstance(body, dict) else body
            for name, value in {**({'Content-Type': 'application/json'} if body is not None else {}),
                                **(headers or {})}.items():
                connection.putheader(name, value)
            if data is not None:
                connection.putheader('Content-Length', str(len(data)))
            connection.endheaders(data)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def raw(self, data, close_write=False):
        with socket.create_connection(('127.0.0.1', self.port), timeout=10) as client:
            client.sendall(data)
            if close_write:
                client.shutdown(socket.SHUT_WR)
            reply = b''
            while piece := client.recv(65536):
                reply += piece
        return int(reply.split(b' ', 2)[1]), reply

    def completed(self, headers=None):
        status, _, body = self.request('GET', '/metrics', headers=headers)
        if status != 200:
            raise AssertionError(body)
        return len(json.loads(body)['requests'])


class WebIntakeSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_page_and_normal_api_answers_still_work(self):
        status, headers, body = self.server.request('GET', '/')
        self.assertEqual((status, headers['Cache-Control']), (200, 'no-cache'))
        self.assertIn(b'/web/mac.js', body)
        before = self.server.completed()
        status, headers, body = self.server.request('POST', '/v1/chat/completions', CHAT)
        self.assertEqual((status, headers['Cache-Control']), (200, 'no-store'), body)
        self.assertIn('mock engine', json.loads(body)['choices'][0]['message']['content'])
        self.assertEqual(self.server.completed(), before + 1)

    def test_streaming_answer_ends_normally(self):
        status, headers, body = self.server.request('POST', '/v1/chat/completions', dict(CHAT, stream=True),
                                                    headers={'Origin': f'http://127.0.0.1:{self.server.port}'})
        self.assertEqual((status, headers['Content-Type'], headers['Cache-Control']),
                         (200, 'text/event-stream', 'no-cache'))
        self.assertTrue(body.rstrip().endswith(b'data: [DONE]'))

    def test_rebinding_hosts_and_foreign_pages_start_no_generation(self):
        before = self.server.completed()
        for host in ('evil.example:%d' % self.server.port, '127.0.0.1.nip.io'):
            with self.subTest(host=host):
                self.assertEqual(self.server.request('GET', '/health', host=host)[0], 403)
                self.assertEqual(self.server.request('POST', '/v1/chat/completions', CHAT, host=host)[0], 403)
        for origin, content_type, expected in (('http://evil.example', 'text/plain', 403), ('null', None, 403),
                                               (f'http://127.0.0.1:{self.server.port}', 'text/plain', 415)):
            with self.subTest(origin=origin):
                headers = {'Origin': origin, **({'Content-Type': content_type} if content_type else {})}
                status, _, _ = self.server.request('POST', '/v1/chat/completions', CHAT, headers=headers)
                self.assertEqual(status, expected)
        status, _, _ = self.server.request('POST', '/settings', {'defaults': {'temperature': 0.1}},
                                           headers={'Origin': 'http://evil.example'})
        self.assertEqual(status, 403)
        self.assertEqual(self.server.completed(), before)

    def test_oversized_malformed_and_partial_bodies_are_answered_promptly(self):
        head = 'POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n' % self.server.port
        started = time.monotonic()
        self.assertEqual(self.server.raw((head + 'Content-Length: 2147483647\r\n\r\n').encode())[0], 413)
        self.assertEqual(self.server.raw((head + 'Content-Length: -1\r\n\r\n').encode())[0], 400)
        chunked = head + 'Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n'
        self.assertEqual(self.server.raw(chunked.encode())[0], 400)
        status, reply = self.server.raw((head + 'Content-Length: 100\r\n\r\n{"messages":').encode(), close_write=True)
        self.assertEqual(status, 400)
        self.assertIn(b'ended before', reply)
        self.assertLess(time.monotonic() - started, 10)

    def test_connections_beyond_the_bound_are_refused(self):
        idle = [socket.create_connection(('127.0.0.1', self.server.port), timeout=10) for _ in range(MAX_CONNECTIONS)]
        try:
            time.sleep(.5)  # Let the server accept every idle connection first.
            status, reply = self.server.raw(b'GET /health HTTP/1.1\r\n\r\n')
            self.assertEqual(status, 503, reply)
        finally:
            for client in idle:
                client.close()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = self.server.raw(b'GET /health HTTP/1.1\r\n\r\n')[0]
            if status == 200:
                break
            time.sleep(.1)
        self.assertEqual(status, 200)


class KeyedWebIntakeSocketTests(unittest.TestCase):
    def test_status_and_foreign_pages_need_the_configured_key(self):
        server = Server(api_key=KEY)
        try:
            self.assertEqual(server.request('GET', '/status')[0], 401)
            status, headers, body = server.request('GET', '/status', headers={'Authorization': 'Bearer ' + KEY})
            self.assertEqual((status, headers['Cache-Control']), (200, 'no-store'))
            self.assertIn('busy', json.loads(body))
            self.assertEqual(server.request('GET', '/health')[0], 200)
            foreign = {'Origin': 'http://evil.example', 'Content-Type': 'text/plain'}
            self.assertEqual(server.request('POST', '/v1/chat/completions', CHAT, headers=foreign)[0], 401)
            keyed = dict(foreign, Authorization='Bearer ' + KEY)
            self.assertEqual(server.request('POST', '/v1/chat/completions', CHAT, headers=keyed)[0], 200)
        finally:
            server.stop()


if __name__ == '__main__':
    unittest.main()
