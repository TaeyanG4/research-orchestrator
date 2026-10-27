"""Literal host-shell commands for trusted runtime paths."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import sys


def literal(value: str, shell: str = "sh") -> str:
    if shell == "powershell":
        return "'" + value.replace("'", "''") + "'"
    if shell == "cmd":
        # Batch expansion happens even in double quotes. Delayed expansion is
        # disabled by the shim, and a quote is not a legal Windows path byte.
        if '"' in value or "\n" in value or "\r" in value:
            raise ValueError("invalid batch path")
        return '"' + value.replace("%", "%%") + '"'
    return shlex.quote(value)


def command_prefix(script: Path | None = None, shell: str | None = None) -> str:
    shell = shell or ("powershell" if os.name == "nt" else "sh")
    script = script or Path(__file__).with_name("ro.py")
    parts = [literal(str(Path(sys.executable).resolve()), shell), "-E", "-S",
             literal(str(script.resolve()), shell)]
    return ("& " if shell == "powershell" else "") + " ".join(parts)


def install_command(shell: str, arguments: str) -> str | None:
    """Resolve the plugin installer from this runtime, including marketplace layouts."""
    root = Path(__file__).resolve().parents[3]
    installer = root / "install.py"
    if not installer.is_file():
        return None  # A standalone installed skill does not include the plugin installer.
    return command_prefix(installer, shell) + " " + arguments


def shim_install_command(shell: str) -> str | None:
    return install_command(shell, "--shim-only")
