#!/usr/bin/env python3
"""Generate the SMDPIS synthetic sample dataset.

Thin wrapper around ``backend/scripts/generate_sample_data.py`` so the
documented root-level command works as specified:

    python scripts/generate_sample_data.py

ALL output is synthetic. No real people, organizations, or private data are
represented. Safe to commit and share.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "backend" / "scripts" / "generate_sample_data.py"

# Default output resolves against the repo root, not the caller's CWD.
DEFAULT_OUTPUT = ROOT / "data" / "sample"

if __name__ == "__main__":
    if not GENERATOR.exists():
        sys.exit(f"Generator not found: {GENERATOR}")

    argv = list(sys.argv[1:])
    if "--output" not in argv:
        argv = ["--output", str(DEFAULT_OUTPUT), *argv]

    sys.argv = [str(GENERATOR), *argv]
    runpy.run_path(str(GENERATOR), run_name="__main__")
