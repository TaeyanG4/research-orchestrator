"""Record one upload per candidate file in uploads.log (a local stand-in for a remote service)."""

from __future__ import annotations

import argparse
from pathlib import Path

from submit_common import digest

VERSION = "1.3.0"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    log = Path("uploads.log")
    sha = digest(args.file)
    if log.exists() and sha in log.read_text(encoding="utf-8"):
        print(f"already uploaded: {sha}")
        return 1
    with log.open("a", encoding="utf-8") as output:
        output.write(f"{sha} {args.message}\n")
    print(f"uploaded {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
