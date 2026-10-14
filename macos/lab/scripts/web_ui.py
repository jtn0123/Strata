"""Serve the maintained Mac page and guard the pinned shell's HTTP intake.

The pinned handler stays unchanged; this subclass checks each request before it.
Host and Origin rules follow the current upstream server (``host_allowed`` and
``origin_allowed`` in ``serve/server.py``) without its config lists: the Mac
launcher listens on 127.0.0.1 only.
"""

import functools
import ipaddress
import json
import socket
import threading
import time
from collections.abc import Callable
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any, cast

WEB = Path(__file__).resolve().parents[1] / "web"
JAVASCRIPT = "text/javascript; charset=utf-8"
ASSETS = {
    "": ("index.html", "text/html; charset=utf-8"),
    "/web/mac.css": ("mac.css", "text/css; charset=utf-8"),
    "/web/mac.js": ("mac.js", JAVASCRIPT),
    "/web/ui-state.js": ("ui-state.js", JAVASCRIPT),
    "/web/performance.js": ("performance.js", JAVASCRIPT),
}
LOOPBACK_NAMES = frozenset(("localhost", "127.0.0.1", "::1"))
MAX_BODY_BYTES = 16 * 1024 * 1024  # Rejected before reading; the Mac profiles use a 4,096-token context.
INTAKE_SECONDS = 30.0  # Per header read, and for the whole body; answers and SSE streams have no deadline.
DRAIN_SECONDS = 2.0  # An early answer drops the unread body so the client sees it rather than a reset.
MAX_CONNECTIONS = 32  # Open connections served at once; as many more are refused with 503, then closed outright.
READ_PIECE = 1 << 16

BUSY_BODY = json.dumps({"error": {"type": "server_error", "message": "too many open requests"}}).encode()
BUSY = (
    b"HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n"
    + f"Content-Length: {len(BUSY_BODY)}\r\n\r\n".encode()
    + BUSY_BODY
)

type HandlerFactory = Callable[[Any], type[BaseHTTPRequestHandler]]


class IntakeError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def host_name(value: str | None) -> str:
    """The name in a Host header or an origin's host[:port]; "" when it is malformed."""
    text = (value or "").strip().lower()
    if text.startswith("["):
        name, closed, rest = text[1:].partition("]")
        return name if closed and (not rest or (rest.startswith(":") and rest[1:].isdigit())) else ""
    if text.count(":") == 1:
        text, port = text.split(":")
        if not port.isdigit():
            return ""
    elif ":" in text:
        return text
    text = text.rstrip(".")
    return text if text and all(c.isalnum() or c in "-._" for c in text) else ""


def is_ip(name: str) -> bool:
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


@functools.cache
def host_names(bind_host: str) -> frozenset[str]:
    """Names besides IP addresses this server answers to; beyond loopback also this Mac's name."""
    names = set(LOOPBACK_NAMES)
    bind = host_name(bind_host)
    if bind and bind not in ("0.0.0.0", "::"):
        names.add(bind)
    if bind not in LOOPBACK_NAMES:
        names.add("host.docker.internal")
        try:
            computer = socket.gethostname().lower()
            names.update((computer, computer + ".local"))
        except OSError:
            pass
    return frozenset(names)


def host_allowed(host: str | None, names: frozenset[str]) -> bool:
    """DNS rebinding needs a name: IP addresses, localhost and the server's names pass, other names do not.

    A request without Host passes (HTTP/1.0 clients; browsers always send one).
    """
    if not (host or "").strip():
        return True
    name = host_name(host)
    return bool(name) and (is_ip(name) or name == "localhost" or name.endswith(".localhost") or name in names)


def origin_allowed(origin: str, host: str | None, names: frozenset[str]) -> bool:
    """A browser page that may send API requests: this server's own page or a local page.

    No IP passes on trust, and "null" (sandboxed frames, file:// pages) does not pass. Other
    schemes (browser extensions, desktop apps) do: no web site can send one.
    """
    scheme, separator, rest = origin.strip().rstrip("/").lower().partition("://")
    if not separator or not scheme:
        return False
    if scheme not in ("http", "https"):
        return True
    if host and rest == host.strip().lower():
        return True
    name = host_name(rest)
    return bool(name) and (name in LOOPBACK_NAMES or name.endswith(".localhost") or name in names)


def declared_length(headers: Message) -> int:
    """One exact Content-Length (none means an empty body); no other body framing."""
    if headers.get_all("Transfer-Encoding"):
        raise IntakeError(400, "send the request body with Content-Length; Transfer-Encoding is not supported")
    values = headers.get_all("Content-Length") or []
    if len(values) > 1:
        raise IntakeError(400, "send one Content-Length header")
    value = values[0].strip() if values else "0"
    if not (value.isascii() and value.isdigit()):
        raise IntakeError(400, "Content-Length must be a nonnegative integer")
    return int(value)


class MacRequestHandler(BaseHTTPRequestHandler):
    """Checks placed before the pinned handler; ``mac_handler_factory`` puts it first in the MRO."""

    timeout = INTAKE_SECONDS
    pinned_service: Any
    pinned_get: Callable[[], None]
    pinned_post: Callable[[], None]
    # The pinned handler's own authorization and JSON answer, found later in the MRO.
    _authorized: Callable[[], bool]
    _json: Callable[[int, object], None]

    def setup(self) -> None:
        super().setup()
        self.intake = self.rfile

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            if self.intake is not self.rfile:
                self.intake.close()

    def handle_one_request(self) -> None:
        self.body_read = False
        self.cache_policy = False
        super().handle_one_request()
        self.discard_unread()

    def keyed(self) -> bool:
        # With an API key a rebinding or foreign page cannot authenticate, so the key decides (as upstream).
        return bool(getattr(self.pinned_service, "api_key", ""))

    def names(self) -> frozenset[str]:
        address = self.server.server_address
        return host_names(str(address[0]) if isinstance(address, tuple) else "")

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        if self.keyed() or host_allowed(self.headers.get("Host"), self.names()):
            return True
        self.reject(403, f"Host {self.headers.get('Host')!r} is not allowed (DNS rebinding protection)")
        return False

    def send_header(self, keyword: str, value: str) -> None:
        if keyword.lower() == "cache-control":
            self.cache_policy = True
        super().send_header(keyword, value)

    def end_headers(self) -> None:
        # API answers carry live status, metrics, settings and replies.
        if not self.cache_policy:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reject(self, code: int, message: str) -> None:
        kind = "forbidden" if code == 403 else "invalid_request_error"
        try:
            self._json(code, {"error": {"type": kind, "message": message}})
        except OSError:
            self.close_connection = True

    def discard_unread(self) -> None:
        """Drop a body an early answer did not read, bounded by size and time.

        Closing on unread bytes can reset the connection before the client reads the answer.
        """
        headers = getattr(self, "headers", None)
        if self.body_read or headers is None:
            return
        try:
            left = min(declared_length(headers), MAX_BODY_BYTES)
        except IntakeError:
            return  # Unknown framing: close without reading.
        deadline = time.monotonic() + DRAIN_SECONDS
        try:
            while left > 0 and (wait := deadline - time.monotonic()) > 0:
                self.connection.settimeout(wait)
                piece = self.rfile.read1(min(left, READ_PIECE))
                if not piece:
                    return
                left -= len(piece)
        except OSError:
            return

    def read_body(self, length: int) -> bytes:
        self.body_read = True  # A partial body is not drained further.
        deadline = time.monotonic() + INTAKE_SECONDS
        pieces: list[bytes] = []
        while length:
            wait = deadline - time.monotonic()
            try:
                if wait <= 0:
                    raise TimeoutError
                self.connection.settimeout(wait)
                piece = self.rfile.read1(min(length, READ_PIECE))
            except TimeoutError:
                raise IntakeError(408, "the request body did not arrive in time") from None
            except OSError:
                piece = b""
            if not piece:
                raise IntakeError(400, "the request body ended before its Content-Length")
            pieces.append(piece)
            length -= len(piece)
        return b"".join(pieces)

    def check_page(self) -> None:
        """Without an API key, a browser page must be local and send JSON (no simple cross-site POST)."""
        origin = self.headers.get("Origin")
        if self.keyed() or origin is None:
            return
        if not origin_allowed(origin, self.headers.get("Host"), self.names()):
            raise IntakeError(403, f"web pages of {origin} may not use this server without an API key")
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise IntakeError(415, "send application/json")

    def do_POST(self) -> None:
        try:
            length = declared_length(self.headers)
            if length > MAX_BODY_BYTES:
                raise IntakeError(413, f"the request body is limited to {MAX_BODY_BYTES // 2**20} MiB")
            self.check_page()
            if not self._authorized():
                return
            body = self.read_body(length)
        except IntakeError as error:
            self.reject(error.code, str(error))
            return
        self.rfile = BytesIO(body)
        self.connection.settimeout(None)
        self.pinned_post()

    def do_GET(self) -> None:
        self.connection.settimeout(None)
        path = self.path.split("?", 1)[0].rstrip("/")
        # Live status includes the reply's last characters; protect it like /metrics.
        if path == "/status" and not self._authorized():
            return
        asset = ASSETS.get(path)
        if asset is None:
            self.pinned_get()
            return
        name, mime = asset
        body = (WEB / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def mac_handler_factory(original_factory: HandlerFactory) -> HandlerFactory:
    def make_handler(service: Any) -> type[BaseHTTPRequestHandler]:
        pinned: Any = original_factory(service)

        class MacHandler(MacRequestHandler, pinned):
            pinned_service = service
            pinned_get = pinned.do_GET
            pinned_post = pinned.do_POST

        return MacHandler

    return make_handler


class ConnectionLimit(ThreadingHTTPServer):
    """Bound concurrent connections, each with its own thread and request body."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.refusals = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def server_bind(self) -> None:
        """Bind and record the bound address, as HTTPServer does, without looking up its DNS name.

        HTTPServer.server_bind calls socket.getfqdn; on the hosted macOS runner that lookup of 127.0.0.1
        blocked startup for over 30 s, and nothing uses the name. The pinned server only sets
        allow_reuse_address among TCPServer's binding options.
        """
        if self.allow_reuse_address:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        host, port = cast(tuple[str, int], self.server_address)[:2]
        self.server_name, self.server_port = host, port

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.slots.acquire(blocking=False):
            # The refusal waits for the client, so it gets its own bounded thread, not the accept loop.
            if self.refusals.acquire(blocking=False):
                threading.Thread(target=self.refuse, args=(request,), daemon=True).start()
            else:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def refuse(self, request: Any) -> None:
        """Answer 503 without reading the request.

        Closing with the request unread makes the kernel reset the connection, which can discard the
        answer before the client reads it; so stop sending, then read what the client sends for a while.
        """
        try:
            request.settimeout(DRAIN_SECONDS)
            request.sendall(BUSY)
            request.shutdown(socket.SHUT_WR)
            deadline = time.monotonic() + DRAIN_SECONDS
            while (wait := deadline - time.monotonic()) > 0:
                request.settimeout(wait)
                if not request.recv(READ_PIECE):
                    break
        except OSError:
            pass
        finally:
            self.shutdown_request(request)
            self.refusals.release()


def bounded_server(original: type[ThreadingHTTPServer]) -> type[ThreadingHTTPServer]:
    pinned: Any = original

    class BoundedServer(ConnectionLimit, pinned):
        pass

    return BoundedServer
