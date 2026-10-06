#!/usr/bin/env python3
"""Register the lab backend without modifying the downloaded Strata fork."""
import sys
from lab import ROOT
sys.path.insert(0, str(ROOT / "vendor/Strata-macOS"))
from serve.backends import register_backend
from native_backend import create_backend
register_backend("metal-native", create_backend)
from serve.server import main

if __name__ == "__main__":
    raise SystemExit(main())
