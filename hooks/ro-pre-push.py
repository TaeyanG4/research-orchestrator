#!/usr/bin/env python3
"""Dispatch a shared Git hook to the current checkout's registered runtime."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def dispatch(data: dict, remote: str, refs: bytes, flags: int) -> int:
    """Try launchable interpreters, never retry a scanner's nonzero verdict."""
    candidates = [[data["python"]]]
    if os.environ.get("RO_HOOK_PYTHON"):
        candidates.append([os.environ["RO_HOOK_PYTHON"]])
    candidates.extend([["python3"], ["python"], ["py", "-3"]])
    tried = set()
    for interpreter in candidates:
        key = tuple(interpreter)
        if key in tried:
            continue
        tried.add(key)
        try:
            # A launcher or store alias can exist without a usable Python. Probe
            # separately so an actual scanner failure never selects another gate.
            probe = subprocess.run(interpreter + ["-E", "-S", "-c",
                                   "import sys; sys.exit(sys.version_info < (3, 12))"],
                                   capture_output=True, timeout=5, creationflags=flags)
            if probe.returncode:
                continue
        except (OSError, subprocess.TimeoutExpired):
            continue
        try:
            return subprocess.run(interpreter + ["-E", "-S", data["runtime"], "hook", "pre-push",
                                  "--remote", remote], input=refs, creationflags=flags).returncode
        except FileNotFoundError:
            continue  # Interpreter disappeared between probe and launch.
    print("research-orchestrator pre-push failed: no working Python 3.12+ interpreter; "
          "set RO_HOOK_PYTHON or install python3, python, or py -3", file=sys.stderr)
    return 1


def registration_expected(root: Path, registrations: Path, flags: int) -> bool:
    """Distinguish an uninstalled shared-hook user from a damaged installation."""
    gitdir = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], check=True,
                            capture_output=True, text=True, creationflags=flags).stdout.strip()
    if (Path(gitdir) / "research-orchestrator-pre-push").exists():
        return True
    # Older installers had no expectation marker. Installed runtimes and nested
    # registrations still identify their checkout, including the former subdir bug.
    if any((root / host / "skills/research-orchestrator/scripts/ro.py").is_file()
           for host in (".claude", ".codex", ".agents")):
        return True
    for path in registrations.glob("*.json"):
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            candidate = Path(saved["scope"]).resolve()
        except (ValueError, KeyError, TypeError):
            continue  # A malformed unrelated registration does not identify this checkout.
        if candidate == root:
            return True
        if root in candidate.parents:
            try:
                owner = subprocess.run(["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
                                       check=True, capture_output=True, text=True, creationflags=flags)
            except (OSError, subprocess.CalledProcessError):
                return True  # A damaged former nested installation needs repair, not a silent pass.
            if Path(owner.stdout.strip()).resolve() == root:
                return True
    return False


def main() -> int:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        refs = sys.stdin.buffer.read()
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True,
                                capture_output=True, text=True, creationflags=flags)
        scope = os.path.normcase(str(Path(result.stdout.strip()).resolve()))
        key = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        registrations = Path(__file__).resolve().parent / "registrations"
        path = registrations / (key + ".json")
        if not path.exists():
            if registration_expected(Path(scope), registrations, flags):
                raise ValueError("this repository's pre-push registration is missing; "
                                 "from the Git repository root, rerun python install.py --project .")
            return 0  # Shared hooksPath also serves repositories with no installation.
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["scope"] != scope:
            raise ValueError("registration scope does not match this checkout")
        remote = sys.argv[1] if len(sys.argv) > 1 else ""
        # A fresh pipe preserves the bytes and closes EOF explicitly on Windows.
        return dispatch(data, remote, refs, flags)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"research-orchestrator pre-push failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
