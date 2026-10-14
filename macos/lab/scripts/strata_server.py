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
import argparse
import json
from pathlib import Path
# Match the pinned shell's supported argument forms, last-value precedence and BOM
# handling; its own parser still owns validation/help for every other option.
preparser = argparse.ArgumentParser(add_help=False)
preparser.add_argument('--config', type=Path)
preparser.add_argument('-h', '--help', action='store_true')
startup, _ = preparser.parse_known_args()
config = (json.loads(startup.config.read_text(encoding='utf-8-sig')).get('performance', {})
          if startup.config and not startup.help else {})
server.Service = tracked_service(server.Service, server.MockEngine, config)
server.make_handler = mac_handler_factory(server.make_handler)
main = server.main

if __name__ == "__main__":
    raise SystemExit(main())
