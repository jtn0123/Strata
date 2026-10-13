#!/usr/bin/env python3
"""Register the lab backend without modifying the downloaded Strata fork."""
import sys
from lab import ROOT
sys.path.insert(0, str(ROOT / "vendor/Strata-macOS"))
from serve.backends import register_backend
from native_backend import create_backend
register_backend("metal-native", create_backend)
from serve import server
from web_ui import mac_handler_factory
from performance_metrics import tracked_service
import json
from pathlib import Path
config = {}
if '--config' in sys.argv:
    config = json.loads(Path(sys.argv[sys.argv.index('--config') + 1]).read_text()).get('performance', {})
server.Service = tracked_service(server.Service, server.MockEngine, config)
server.make_handler = mac_handler_factory(server.make_handler)
main = server.main

if __name__ == "__main__":
    raise SystemExit(main())
