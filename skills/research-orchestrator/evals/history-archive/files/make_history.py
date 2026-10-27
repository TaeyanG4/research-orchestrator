"""Append a long synthetic history to an initialized research project (history-archive eval)."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REVIEWS = {"VERIFIED": "CLOSED — reviewer subagent:check@{date}T09:00 — recomputed the summary table",
           "HOLD": "HOLD — reviewer subagent:check@{date}T09:00 — needs the second dataset first"}


def discovery(number: int, state: str, month: int) -> str:
    finding = (f"configuration {number} changes the measured outcome by {number % 7} points under the fixed "
               "protocol; repeated runs agree within the recorded noise band and the result does not depend on "
               "the order in which inputs are read")
    date = f"2026-{month:02d}-{1 + number % 28:02d}"
    review = REVIEWS.get(state)
    reviews = f"\n  - Claude Code (A): {review.format(date=date)}" if review else ""
    return (f"## D-A-{number:03d} — configuration {number} effect\n- Source: A\n- Host: Claude Code\n"
            f"- User: operator\n- Date: {date}\n- Session: history-source:A@{date}T08:00\n"
            f"- Cross-check: {state}\n- Finding: {finding}\n- Evidence: runs/{number}/summary.csv\n"
            f"- Implication: none\n- Reviews:{reviews}\n")


def event(number: int, slot: str, key: str) -> str:
    stamp = (dt.datetime(2026, 8, 1, 9, 0) + dt.timedelta(hours=2 * number)).strftime("%Y-%m-%d %H:%M")
    return (f"### {stamp} — {slot} — {key}\n"
            f"- Host: Claude Code\n- User: operator\n- Action: ran comparison {number}\n"
            f"- Result: recorded; see D-A-{1 + number % 300:03d}\n- Artifacts: runs/{number}\n"
            f"- Discovery updates: none — synthetic history\n- Review verdict: none\n- Resource: CPU\n"
            f"- Other executor: none\n- New plan items: none — synthetic history\n")


def main(project: Path) -> None:
    states = ["VERIFIED"] * 300 + ["PENDING"] * 20 + ["HOLD"] * 10 + ["VERIFIED"]
    entries = [discovery(n, state, 8 + n // 200) for n, state in enumerate(states, 1)]
    path = project / "discoveries.md"
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + "\n".join(entries),
                    encoding="utf-8", newline="\n")
    plan = project / "plan.md"
    text = plan.read_text(encoding="utf-8")
    heading = "## Agent: A\n" if "## Agent: A\n" in text else "## Queue\n"
    claim = "- Claimed: none\n" if heading == "## Queue\n" else ""
    live = ("\n### H-A-01 — follow up the cited configuration\n" + claim + "- Sources: D-A-331\n"
            "- Hypothesis: configuration 331 generalizes\n- Evidence: D-A-331 measured it once\n"
            "- Improvement: a second dataset\n- Impact: 2\n- Information: 2\n- Confidence: 1\n- Unblock: 1\n"
            "- Diversity: 1\n- Cost: 1\n- Priority: 13\n- Resource: CPU\n- Parallel: YES\n- Other: NONE\n"
            "- Next test: rerun on the second dataset\n- Stages: s1 second dataset | s2 comparison\n")
    plan.write_text(text.replace(heading, heading + live, 1), encoding="utf-8", newline="\n")
    events = [event(n, "A" if n % 3 else "B", "H-A-01/s1" if n == 650 else "none") for n in range(700)]
    handoff = project / "handoff.md"
    text = handoff.read_text(encoding="utf-8")
    marker = "\n## Archived history"
    body = "\n".join(events)
    text = text.replace(marker, "\n" + body + marker, 1) if marker in text else text.rstrip("\n") + "\n\n" + body
    handoff.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
