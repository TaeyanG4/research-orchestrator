"""Repository tools reuse the shipped process-start helper instead of defining their own."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_HELPER = Path(__file__).resolve().parents[2] / "skills" / "research-orchestrator" / "scripts" / "ro_proc.py"
_SPEC = importlib.util.spec_from_file_location("_ro_proc_shared", _HELPER)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
no_window_flags = _MODULE.no_window_flags
