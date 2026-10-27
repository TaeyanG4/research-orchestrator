"""Output encoding shared by the command-line entry points."""

from __future__ import annotations

import os
import sys


def utf8_output() -> None:
    """Write UTF-8 to pipes and files so records in any language survive capture.

    Windows otherwise encodes redirected output in the locale code page (for example
    cp949), which garbles non-ASCII records for agents that read command output as
    UTF-8. Terminals keep their own handling, an explicit PYTHONIOENCODING still wins,
    and unencodable characters are escaped rather than raising.
    """
    explicit = bool(os.environ.get("PYTHONIOENCODING")) and not sys.flags.ignore_environment
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        try:
            redirected = not stream.isatty()
        except (OSError, ValueError):
            redirected = True
        if redirected and not explicit:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        else:
            stream.reconfigure(errors="backslashreplace")
