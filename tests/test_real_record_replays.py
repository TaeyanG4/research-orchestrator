"""Guard snapshots and counterfactual repairs from an anonymised historical corpus."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re

import pytest

from conftest import FIXTURES, append_discovery, check, item
from guard_helpers import instrument, plan, project, section, setting
from test_guards import guard_issues

CORPUS = FIXTURES / "real-record-corpus" / "records.json"
REPLAYS = FIXTURES / "real-record-replays"


def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def digest(value: object, *, unicode: bool = False) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=not unicode).encode()).hexdigest()


def render_discovery(record: dict, extra: list[tuple[str, str]] = ()) -> str:
    """Keep source field/update/review order; normalize only the P1 state and review grammar."""
    rendered = [f"## {record['id']} — {record['title']}"]
    inserted, challenged = False, False

    def guard_fields() -> None:
        nonlocal inserted
        if not inserted:
            rendered.extend(f"- {name}: {value}" for name, value in extra)
            inserted = True

    for line in record["lines"]:
        shape = line["shape"]
        if shape == "blank":
            # The checker reads the first contiguous record block. Keep every later update verbatim in order.
            guard_fields()
            rendered.append("")
            continue
        value = line["text"]
        dates = "; recorded " + ", ".join(line["dates"]) if line["dates"] else ""
        receipt = "; numeric receipt: " + " ".join(line["numbers"]) if line["numbers"] else ""
        if shape == "field":
            name = line["name"]
            if name == "Host":
                value = "Claude Code" if value == "Host A" else "Codex"
            elif name == "User":
                value = "operator"
            elif name == "Cross-check" and value == "CLOSED":
                value = "VERIFIED"
            if name in {"Source", "Host", "User", "Date", "Cross-check"}:
                rendered.append(f"- {name}: {value}")
            else:
                rendered.append(f"- {name}: {value}{dates}{receipt}")
        else:
            verdict = line["states"][0]
            # Source CORRECTED means the bounded result is retained; P1 spells that CLOSED.
            verdict = "CLOSED" if verdict == "CORRECTED" else verdict
            resolves = challenged and verdict in {"CLOSED", "HOLD", "VERIFIED"}
            suffix = " after challenge" if resolves else ""
            rendered.append(f"  - Codex (B): {verdict}{suffix} — {value}{dates}{receipt}")
            challenged = verdict == "CHALLENGED" or (challenged and not resolves)
    guard_fields()
    return "\n".join(rendered) + "\n"


def real_replay(parent: Path, name: str, *, repair: str | None = None, workflow: str = "unified") -> tuple[Path, dict]:
    data = corpus()
    manifest = json.loads((REPLAYS / name / "replay.json").read_text(encoding="utf-8"))
    guards = "G1, G5, G6" if name == "replay-derived-instruments" else "G1, G3"
    target = project(parent, guards, workflow=workflow, name=name)
    setting(target, "Guards", "light since 2026-10-01")
    records = {record["id"]: record for record in data["discoveries"]}
    for key in manifest["records"]:
        extra = []
        if key == manifest.get("decision"):
            extra = [("Decision class", "target-change"), ("Instrument", "I-A-01, I-A-02, I-A-03")]
            if repair:
                extra.append(("Outcome", "inconclusive"))
        if key == manifest.get("override"):
            trigger = "; re-check: new independent-panel result" if repair else ""
            extra += [("Override", "registered rule said GO_RULE_MET; decided DROP because proxy guards fail"
                       + trigger + "; expires 2026-10-26")]
        if key == manifest.get("insight"):
            extra += [("Kind", "insight"), ("Status", "planned H-A-02" if repair else "open"),
                      ("Due", "2026-10-21 00:00")]
        append_discovery(target, render_discovery(records[key], extra))
    if name == "replay-derived-instruments":
        instruments = instrument("I-A-01", provenance="derived-from-targets", not_for="target-change",
                                 agreement="0.74–0.83 agreement, D-A-042", resolution="±0.0021 (D-A-042)")
        instruments += instrument("I-A-02", provenance="own-lineage", not_for="target-change, model-change",
                                  agreement="0.74–0.83 agreement, D-A-042", resolution="±0.0004 (D-A-042)")
        instruments += instrument("I-A-03", agreement="56/58 agreement, D-A-112" if repair else "unmeasured",
                                  resolution="unmeasured")
        if repair:
            plan(target, item("H-A-02", extra=[("Sources", "D-A-235")]))
        section(target, "Instruments", instruments)
    else:
        section(target, "Instruments", instrument(provenance="external-feedback", coverage="external",
                agreement="0.74–0.83 agreement, D-A-042", resolution="±0.007 (D-A-042)",
                dynamics="visible score may drift; refresh on a new comparable cohort"))
        selected = [action for action in data["external_actions"] if action["ref"] in manifest["action_refs"]]
        for index, action in enumerate(selected, 1):
            stamp = dt.datetime.fromisoformat(action["date"])
            observed = stamp.strftime("%Y-%m-%d %H:%M")
            cohort = f"cohort-{index}" if repair == "cohorts" else "stable"
            section(target, "External actions", f"### X-A-{index:03} — item {action['ref']}\n"
                    f"- Kind: release\n- Candidate: item {action['ref']}, hash neutral-{action['ref']}\n"
                    f"- Destination: external board\n- Family: {manifest['family']}\n"
                    f"- Expected: no forecast retained in receipt (written {observed})\n"
                    f"- Result: quality={action['visible score']} on I-A-01 cohort {cohort} (observed {observed})\n"
                    "- Final: pending\n- Status: complete\n")
        exit_field = []
        if repair == "instrument":
            section(target, "Instruments", instrument("I-A-02", agreement="unmeasured", resolution="unmeasured"))
            exit_field = [("Saturation exit", "instrument I-A-02")]
        plan(target, item("H-A-01", extra=[("Family", manifest["family"]), *exit_field]))
    return target, manifest


def test_real_corpus_preserves_all_record_counts_field_order_dates_states_and_numbers() -> None:
    data = corpus()
    assert data["provenance"] == "anonymised from a past project's records"
    assert len(data["discoveries"]) == 14
    assert len(data["external_actions"]) == 134
    numbers = [record["heading_numbers"] + [number for line in record["lines"] for number in line["numbers"]]
               for record in data["discoveries"]]
    assert digest(numbers, unicode=True) == data["integrity"]["discovery_numeric_sha256"]
    shapes = [[[line["shape"], line["name"]] for line in record["lines"]] for record in data["discoveries"]]
    assert digest(shapes) == data["integrity"]["discovery_structure_sha256"]
    dates = [record["heading_dates"] + [stamp for line in record["lines"] for stamp in line["dates"]]
             for record in data["discoveries"]]
    assert digest(dates) == data["integrity"]["discovery_dates_sha256"]
    first_finding = next(line for line in data["discoveries"][0]["lines"] if line["name"] == "Finding")
    assert first_finding["numbers"][:5] == ["5", "888", "\u22120.0021", "\u22120.0047", "\u22120.0054"]
    assert "2026-10-07 16:48 KST" in first_finding["dates"]
    base_order = ["Source", "Host", "User", "Date", "Cross-check"]
    for record in data["discoveries"]:
        fields = [line["name"] for line in record["lines"] if line["shape"] == "field"]
        assert fields[:5] == base_order
    strategy = next(record for record in data["discoveries"] if record["id"] == "D-A-235")
    assert sum(line["name"] == "Finding" for line in strategy["lines"]) == 4
    assert sum(line["name"] == "Evidence" for line in strategy["lines"]) == 4
    states = [state for record in data["discoveries"] for line in record["lines"] for state in line["states"]]
    assert {"VERIFIED", "HOLD", "CHALLENGED", "CLOSED", "PENDING", "CORRECTED", "GO_RULE_MET"} <= set(states)
    values = []
    for action in data["external_actions"]:
        assert list(action) == ["date", "visible score", "final score", "status", "ref", "description"]
        values.append([action["date"], action["visible score"], action["final score"],
                       action["status"].split(".")[-1], action["ref"]])
    assert digest(values) == data["integrity"]["action_values_sha256"]
    numeric_tokens = re.compile(r"[-+\u2212]?(?:\d+(?:[.,]\d+)*|\.\d+)(?:%|h)?")
    description_values = [numeric_tokens.findall(action["description"].partition("numeric receipt:")[2])
                          for action in data["external_actions"]]
    assert digest(description_values, unicode=True) == data["integrity"]["action_description_numeric_sha256"]
    assert {action["status"] for action in data["external_actions"]} == {"ActionStatus.COMPLETE", "ActionStatus.ERROR"}


def test_real_runtime_replays_retain_review_dates_verdict_order_and_repeated_updates() -> None:
    records = {record["id"]: record for record in corpus()["discoveries"]}
    review = render_discovery(records["D-A-042"])
    assert review.index("CHALLENGED —") < review.index("CLOSED after challenge —")
    assert "2026-10-07 23:56 KST" in review
    assert "2026-10-08 00:07 KST" in review
    strategy = render_discovery(records["D-A-235"])
    assert strategy.count("\n- Finding:") == 4
    assert strategy.count("\n- Evidence:") == 4
    assert strategy.count("\n- Reviews:") == 3
    assert strategy.index("2026-10-19 14:36 KST") < strategy.index("2026-10-19 15:20 KST")
    assert strategy.index("2026-10-19 15:20 KST") < strategy.index("2026-10-19 15:33 KST")


def test_real_corpus_field_qualifiers_are_neutral_and_have_no_artifact_paths() -> None:
    allowed = {"Source", "Host", "User", "Date", "Cross-check", "Finding", "Evidence", "Implication",
               "Reviews", "Amendment", "Update", "Panel 7 update", "Cause analysis", "Discard", "Instruments",
               "Follow-ups"}
    for record in corpus()["discoveries"]:
        for line in record["lines"]:
            if line["shape"] != "field":
                continue
            name = line["name"]
            assert name.split(" (", 1)[0] in allowed
            assert not re.search(r"[/\\]", name)
            if name.startswith(("Amendment (", "Panel 7 update (", "Cause analysis (")):
                assert "(recorded " in name
                assert not re.search(r"[A-Za-z]+-\d", name)


@pytest.mark.parametrize("name", ["replay-derived-instruments", "replay-saturated-family"])
def test_real_record_failure_replays_detect_historical_guard_gaps(tmp_path, capsys, name) -> None:
    target, manifest = real_replay(tmp_path, name)
    checker = check(target)
    warnings = [issue for issue in guard_issues(checker) if issue.severity == "WARN"]
    expected = set(manifest["checks"]) | ({"guard.outcome.missing"} if manifest.get("decision") else set())
    assert {issue.check for issue in warnings} == expected, [issue.render() for issue in checker.issues]
    assert not [issue for issue in checker.issues if issue.severity == "ERROR"], [issue.render() for issue in checker.issues]
    source_fields = {record["id"]: {line["name"] for line in record["lines"] if line["shape"] == "field"}
                     for record in corpus()["discoveries"]}
    fields = [len(set(record.fields) - source_fields[key]) for key, record in checker.discoveries.items()
              if key in manifest["records"]]
    with capsys.disabled():
        print(f"\nBURDEN real {name}: added fields per discovery={fields}; guard warning volume={len(warnings)}; "
              f"distinct warning checks={len(set(issue.check for issue in warnings))}")


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_real_derived_counter_replay_records_independent_agreement_recheck_and_live_plan(tmp_path, workflow) -> None:
    target, _ = real_replay(tmp_path, "replay-derived-instruments", repair="recorded", workflow=workflow)
    checker = check(target)
    assert not [issue for issue in guard_issues(checker) if issue.severity in {"WARN", "ERROR"}], \
        [issue.render() for issue in checker.issues]
    assert not [issue for issue in checker.issues if issue.severity == "ERROR"]


@pytest.mark.parametrize("repair", ["cohorts", "instrument"])
@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_real_saturation_counter_replays_change_comparability_or_record_an_exit(tmp_path, repair, workflow) -> None:
    target, _ = real_replay(tmp_path, "replay-saturated-family", repair=repair, workflow=workflow)
    checker = check(target)
    assert not [issue for issue in guard_issues(checker) if issue.severity in {"WARN", "ERROR"}], \
        [issue.render() for issue in checker.issues]
    assert not [issue for issue in checker.issues if issue.severity == "ERROR"]


def test_real_saturation_replay_uses_visible_ties_before_final_scores_exist(tmp_path) -> None:
    target, manifest = real_replay(tmp_path, "replay-saturated-family")
    checker = check(target, now=dt.datetime.fromisoformat(manifest["snapshot"]))
    assert len(checker.external_actions) == 5
    assert not manifest["final_available"]
    assert all(action.fields["Final"] == "pending" for action in checker.external_actions.values())
    results = [action.fields["Result"] for action in checker.external_actions.values()]
    assert all("quality=0.958 " in result for result in results)
    assert any(issue.check == "guard.family.saturated" for issue in guard_issues(checker))
    source_rows = [row for row in corpus()["external_actions"] if row["ref"] in manifest["action_refs"]]
    assert all(row["final score"] == "0.943" for row in source_rows)
    assert all(dt.datetime.fromisoformat(row["date"]) < checker.now for row in source_rows)
