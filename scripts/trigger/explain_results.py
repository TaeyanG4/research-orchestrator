#!/usr/bin/env python3
"""Add reasoned classifications to saved trigger results without rerunning models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.trigger.run_trigger_eval import summarize


def explain(report: dict) -> dict:
    # Keep protocols, original attempts, raw trace locations and measurements.
    # In particular, do not trim old traces at a newly inferred selection event.
    return {**report, "classification_only": True, "metrics": {
        part: summarize(value["results"], report["threshold"], report.get("repeats"))
        for part, value in report["metrics"].items()}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New JSON file; originals are preserved")
    args = parser.parse_args(argv)
    try:
        report = explain(json.loads(args.results.read_text(encoding="utf-8")))
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot explain results: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
