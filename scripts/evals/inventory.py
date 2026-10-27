"""Render the README's case inventory from the strict case folders."""

from __future__ import annotations

import argparse
from pathlib import Path

from .grade_evals import assertion_modes
from .run_evals import DEFAULT_SKILL, load_cases


START = "<!-- generated case inventory -->"
END = "<!-- end case inventory -->"


def render_inventory(skill: Path = DEFAULT_SKILL) -> str:
    rows = []
    scripted = judged = 0
    for case in load_cases(skill):
        modes = list(assertion_modes(case).values())
        counts = modes.count("scripted"), modes.count("judged")
        scripted += counts[0]
        judged += counts[1]
        inputs = len([path for path in (case.path / "files").rglob("*") if path.is_file()])
        rows.append(f"| {case.name} | {counts[0]} | {counts[1]} | {inputs} |")
    return "\n".join([
        START,
        f"{len(rows)} case folders; {scripted + judged} assertions ({scripted} scripted, {judged} judged).",
        "Counts and rows come from the case folders and explicit grader routing; direct artifact predicates are scripted, while judgments review qualitative or multi-step trace evidence.",
        "", "| Case | Scripted | Judged | Input files |", "| --- | ---: | ---: | ---: |",
        *rows, END,
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check the README instead of printing the inventory")
    args = parser.parse_args(argv)
    inventory = render_inventory()
    if not args.check:
        print(inventory)
        return 0
    readme = Path(__file__).with_name("README.md").read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        print("README case inventory is missing; regenerate with python -m scripts.evals.inventory")
        return 1
    actual = START + readme.split(START, 1)[1].split(END, 1)[0] + END
    if actual != inventory:
        print("README case inventory is stale; regenerate with python -m scripts.evals.inventory")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
