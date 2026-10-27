"""Scope-bound independent reviews for designated launch stages and changed decisions."""

from __future__ import annotations

import datetime as dt
import json
import re
from types import SimpleNamespace

from ro_evidence import _valid_receipt, receipt_check
from ro_ids import H_PATTERN
from ro_markdown import mask_fences


STAGE = re.compile(rf"\b({H_PATTERN}/s\d+)\b")


def _text(project, name: str) -> str:
    path = project.root / name
    return mask_fences(path.read_text(encoding="utf-8")) if path.is_file() else ""


def _fields(body: str) -> dict[str, str]:
    result = {}
    for key, value in re.findall(r"^- ([\w /-]+):[ \t]*([^\n]*)", body, re.M):
        if key in result:
            raise ValueError(f"stage record has duplicate {key} fields")
        result[key] = value.strip()
    return result


def important_stages(fields: dict[str, str]) -> set[str]:
    value = fields.get("Important stages", "")
    if not value:
        return set()
    stages = [stage.strip() for stage in value.split("|")]
    declared = set(re.findall(r"(?:^|\|)\s*(s\d+)\s+", fields.get("Stages", "")))
    if (any(not re.fullmatch(r"s\d+", stage) for stage in stages)
            or len(stages) != len(set(stages)) or not set(stages) <= declared):
        raise ValueError("Important stages must name distinct declared stages, e.g. s2 | s3")
    return set(stages)


def result_review(project, heading: str, fields: dict[str, str], stamp: str = "") -> None:
    """Review each dated stage event, independently of an editable completion summary.

    Action-based identity remains supported for earlier single-stage work summaries.
    New work records use the same immutable stage headings as research records.
    """
    if fields.get("Decision") != "changed":
        return
    stages = set(STAGE.findall(heading)) or set(STAGE.findall(fields.get("Action", "")))
    if not stages:
        return
    artifact = fields.get("Review artifact", "")
    if len(stages) != 1 or not artifact:
        raise ValueError("decision-changing stage result needs one stage ID and Review artifact; "
                         "preserve each changed stage in its own dated event alongside the session summary")
    stage = stages.pop()
    entry = _valid_receipt(project, artifact, stage + ":after", independent=True)
    if stamp:
        observed = dt.datetime.fromisoformat(stamp).timestamp()
        if entry.get("created_at", 0) < observed:
            raise ValueError("stage result receipt predates the decision-changing result")


def result_review_issue(root, heading: str, fields: dict[str, str], stamp: str = "") -> str | None:
    """Read-only checker adapter: no slot registration, locks, or state creation."""
    def read_json(name, default):
        path = root / ".ro" / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    try:
        result_review(SimpleNamespace(root=root, read_json=read_json), heading, fields, stamp)
    except (ValueError, OSError, TypeError) as exc:
        return str(exc)
    return None


def launch_fields(project, item: str) -> dict[str, str]:
    """Resolve one active record and its stage before applying any launch policy."""
    if not re.fullmatch(rf"{H_PATTERN}(?:/s\d+)?", item):
        raise ValueError("launch needs an H-id item")
    base, _, stage = item.partition("/")
    workflow = project.settings().get("workflow", "classic")
    blocks = []
    # Only the configured workflow's live sections own queue records. A heading
    # in archived notes, a fenced sample, or a bare legacy-looking block is not
    # a runnable item. Use the checker's canonical ID/title separator as well.
    for section in re.finditer(r"^## ([^\n]+)\n(.*?)(?=^#{1,2} |\Z)",
                               _text(project, "plan.md"), re.M | re.S):
        heading = section[1].strip()
        active = heading == "Queue" if workflow == "unified" else bool(
            re.fullmatch(r"Agent: [A-Z]{1,2}", heading) and base.startswith(f"H-{heading[7:]}-"))
        if active:
            blocks.extend(re.findall(rf"^### {re.escape(base)}(?: — [^\n]*)?[ \t]*\n(.*?)(?=^#{{1,3}} |\Z)",
                                     section[2], re.M | re.S))
    if len(blocks) != 1:
        raise ValueError("launch item needs exactly one active plan record "
                         "(missing or duplicate plan records)")
    lines = []
    for line in blocks[0].splitlines():
        if not line.startswith(("- ", "  - ")):
            break
        lines.append(line)
    fields = _fields("\n".join(lines))
    declared = set(re.findall(r"(?:^|\|)\s*(s\d+)\s+", fields.get("Stages", "")))
    if stage and stage not in declared:
        raise ValueError(f"launch stage {stage} is not declared in {base} Stages")
    return fields


def launch_review(project, item: str, artifact: str | None) -> None:
    """Validate before any job ID, registry entry, or subprocess is created."""
    base, _, stage = item.partition("/")
    important = important_stages(launch_fields(project, item))
    if important and not stage:
        raise ValueError("item has important stages; launch an explicit item/sN stage")
    if stage in important:
        if not artifact:
            raise ValueError("important stage requires --require-receipt with independent scope " + item + ":before")
        _valid_receipt(project, artifact, item + ":before", independent=True)
    elif artifact:
        receipt_check(project, artifact)
    for event in re.finditer(r"^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2})[^\n]*\n(.*?)(?=^#{1,3} |\Z)",
                             _text(project, "handoff.md"), re.M | re.S):
        fields = _fields(event[2])
        heading = event[0].split("\n", 1)[0]
        stages = set(STAGE.findall(heading)) or set(STAGE.findall(fields.get("Action", "")))
        if any(value.partition("/")[0] == base for value in stages):
            result_review(project, heading, fields, event[1])
