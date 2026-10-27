"""Find the checkout-scoped publication gate without inspecting host registrations."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

from ro_proc import no_window_flags


DISPATCH_MARK = "# research-orchestrator scoped pre-push dispatcher v1 (install.py)"


def _dispatcher_installed(hook: Path) -> bool:
    try:
        with hook.open("r", encoding="utf-8", errors="replace") as handle:
            return DISPATCH_MARK in handle.read(4096)
    except OSError:
        return False


def registration(root: Path) -> tuple[Path | None, bool]:
    """Return the nearest Git checkout and whether its active hook path registers it."""
    checkout = next((path for path in (root, *root.parents) if (path / ".git").exists()), None)
    if checkout is None:
        return None, False
    try:
        result = subprocess.run(["git", "-C", str(checkout), "rev-parse", "--git-path", "hooks"],
                                capture_output=True, text=True, check=True, timeout=1,
                                creationflags=no_window_flags())
        scope = os.path.normcase(str(checkout.resolve()))
        key = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        hooks = result.stdout.strip()
        if not hooks:
            return checkout, False
        hook_dir = checkout / hooks
        registered = (hook_dir / "research-orchestrator" / "registrations" / (key + ".json")).is_file()
        # A registration left behind after the pre-push hook was removed or replaced
        # does not protect pushes; only the installed dispatcher runs the scan.
        return checkout, registered and _dispatcher_installed(hook_dir / "pre-push")
    except (OSError, subprocess.SubprocessError):
        return checkout, False
