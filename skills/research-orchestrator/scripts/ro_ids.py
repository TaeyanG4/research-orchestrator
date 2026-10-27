"""Canonical record identifiers: padding is a minimum, never a capacity limit."""

import re


ID_WIDTHS = {"D": 3, "H": 2, "I": 2, "X": 3, "N": 2}


def id_pattern(kinds: str = "DHIXN") -> str:
    """A non-capturing pattern for whole identifiers of the requested kinds."""
    return "(?:" + "|".join(rf"{kind}-[A-Z]{{1,2}}-[0-9]{{{ID_WIDTHS[kind]},}}"
                            for kind in kinds) + ")"


def format_id(kind: str, slot: str, number: int) -> str:
    return f"{kind}-{slot}-{number:0{ID_WIDTHS[kind]}d}"


H_PATTERN = id_pattern("H")
D_PATTERN = id_pattern("D")
I_PATTERN = id_pattern("I")
X_PATTERN = id_pattern("X")
ID_RE = re.compile(rf"\b({id_pattern()})\b")
