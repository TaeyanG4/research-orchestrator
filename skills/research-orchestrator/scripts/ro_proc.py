"""Process-start options shared by every script that starts a subprocess (stdlib only, no imports)."""

import os

# subprocess.CREATE_NO_WINDOW; spelled out so importing this helper never loads subprocess.
CREATE_NO_WINDOW = 0x08000000
def no_window_flags() -> int:
    """Keep child console applications windowless; detached jobs retain their own flags."""
    return CREATE_NO_WINDOW if os.name == "nt" else 0
