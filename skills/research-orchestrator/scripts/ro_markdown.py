"""Exclude Markdown fenced examples while retaining original source positions."""

from collections.abc import Iterable
import re


_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def visible_lines(text: str | Iterable[str]):
    """Yield (original line, visible) for CommonMark backtick and tilde fences.

    A closing fence uses the same delimiter, at least the opening length, and
    no trailing content. A shorter or different delimiter stays inside the block.
    A line iterator lets bounded readers stop before unrelated document bodies.
    """
    delimiter, width = "", 0
    for line in text.splitlines(keepends=True) if isinstance(text, str) else text:
        match = _OPEN.match(line.rstrip("\r\n"))
        if delimiter:
            if (match and match[1][0] == delimiter and len(match[1]) >= width
                    and not match[2].strip()):
                delimiter, width = "", 0
            yield line, False
        elif match and (match[1][0] != "`" or "`" not in match[2]):
            delimiter, width = match[1][0], len(match[1])
            yield line, False
        else:
            yield line, True


def mask_fences(text: str) -> str:
    """Blank fenced characters with spaces, preserving offsets and newlines."""
    return "".join(line if visible else re.sub(r"[^\r\n]", " ", line)
                   for line, visible in visible_lines(text))


def unfenced(text: str) -> list[str]:
    """Blank fenced lines, preserving one result per source line."""
    return [line.rstrip("\r\n") if visible else "" for line, visible in visible_lines(text)]
