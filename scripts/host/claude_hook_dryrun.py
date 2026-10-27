#!/usr/bin/env python3
"""Exercise this checkout's plugin hooks through an installed Claude Code."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.host.dryrun import main


if __name__ == "__main__":
    raise SystemExit(main("claude"))
