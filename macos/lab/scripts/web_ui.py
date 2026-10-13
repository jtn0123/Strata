"""Serve the maintained Mac page while retaining the pinned shell's API and assets."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / 'web'
ASSETS = {
    '': ('index.html', 'text/html; charset=utf-8'),
    '/web/mac.css': ('mac.css', 'text/css; charset=utf-8'),
    '/web/mac.js': ('mac.js', 'text/javascript; charset=utf-8'),
    '/web/ui-state.js': ('ui-state.js', 'text/javascript; charset=utf-8'),
}


def mac_handler_factory(original_factory):
    def make_handler(service):
        class MacHandler(original_factory(service)):
            def do_GET(self):
                path = self.path.split('?', 1)[0].rstrip('/')
                asset = ASSETS.get(path)
                if asset is None:
                    return super().do_GET()
                name, mime = asset
                body = (WEB / name).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(body)
        return MacHandler
    return make_handler
