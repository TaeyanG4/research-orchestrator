#!/usr/bin/env python3
"""Probe the installed Codex sample; exit nonzero when enforcement is unverified.

Running without --dry-print launches Codex. Runner decisions, bound-file state
and tool results are checked together, so a completed exec session alone cannot
pass the probe.
"""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.host.dryrun import main


if __name__ == "__main__":
    raise SystemExit(main("codex"))
