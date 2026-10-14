#!/usr/bin/env python3
"""Register the lab backend without modifying the downloaded Strata fork."""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple, Protocol, TypedDict, cast

from lab import ROOT

type HandlerFactory = Callable[[object], type[BaseHTTPRequestHandler]]
type HandlerInstaller = Callable[[HandlerFactory], HandlerFactory]


class PinnedServer(Protocol):
    Service: type[object]
    MockEngine: type[object]
    Server: type[ThreadingHTTPServer]
    make_handler: HandlerFactory

    def main(self) -> int: ...


class PerformanceSettings(TypedDict, total=False):
    model: str
    engine: str
    context: int
    cache_type: str
    spec: str
    draft: int
    draft_model: str
    lookup_profile: str
    tensor_api: str
    m5_tuning: str
    batch: int
    ubatch: int
    draft_threads: int | None
    draft_placement: str
    draft_p_min: float | None
    monitor_file: str
    initial_swap_bytes: int
    report_memory: bool


class ServerSettings(TypedDict, total=False):
    performance: PerformanceSettings | None


class StartupArguments(Protocol):
    config: Path | None
    help: bool


class ServerBootstrap(NamedTuple):
    server: PinnedServer
    config: PerformanceSettings | None


def performance_settings(argv: Sequence[str] | None = None) -> PerformanceSettings | None:
    # Match the shell's supported forms, last-value precedence and BOM handling;
    # its own parser still owns validation/help for every other option.
    preparser = argparse.ArgumentParser(add_help=False)
    preparser.add_argument("--config", type=Path)
    preparser.add_argument("-h", "--help", action="store_true")
    startup = cast(StartupArguments, preparser.parse_known_args(argv)[0])
    if startup.config and not startup.help:
        settings = cast(ServerSettings, json.loads(startup.config.read_text(encoding="utf-8-sig")))
        defaults: PerformanceSettings = {}
        return settings.get("performance", defaults)
    return {}


def setup_server(argv: Sequence[str] | None = None) -> ServerBootstrap:
    sys.path.insert(0, str(ROOT / "vendor/Strata-macOS"))
    from serve.backends import register_backend
    from native_backend import create_backend

    register_backend("metal-native", create_backend)
    from serve import server as pinned_server
    from web_ui import bounded_server, mac_handler_factory
    from performance_metrics import tracked_service

    # The downloaded shell is an explicit revision-pinned module boundary.
    server = cast(PinnedServer, pinned_server)
    config = performance_settings(argv)
    server.Service = tracked_service(server.Service, server.MockEngine, config)
    # The web adapter wraps the retained factory and returns its handler subclass.
    install_handler = cast(HandlerInstaller, mac_handler_factory)
    server.make_handler = install_handler(server.make_handler)
    server.Server = bounded_server(server.Server)
    return ServerBootstrap(server, config)


bootstrap = setup_server()
server, config = bootstrap
main = server.main

if __name__ == "__main__":
    raise SystemExit(main())
