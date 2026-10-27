"""Direction and final-pair snapshots from preserved, anonymised record excerpts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re

import pytest

from conftest import FIXTURES, append_discovery, check, item
from guard_helpers import discovery, instrument, plan, project, section, shared
from test_guards import guard_issues
from test_real_record_replays import corpus

SOURCE = FIXTURES / "real-record-corpus" / "direction-selection.json"
REPLAYS = FIXTURES / "real-record-replays"
PROVENANCE = "anonymised from a past project's records"
NUMERIC_DIGESTS = {
    "strategy-review": "0b82122ee1a5e3a56287aef1f0c040bfe40e5247b77f7aa1ac4ab6bffb5d2244",
    "direction-debate": "4831b023c05507209b1a51f31a9865eece64203f7f6a8f704b2f009a1ecce96e",
    "intake": "20b48118a8834af375a380c350e2858e816d422ab69a186378fbe7441d924a02",
    "final-selection": "0217ae136bc28626a04620517be2f63bacbd57e0ebeb8fbd0ca9ea53a49c87cf",
}


def excerpts() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def receipt_lines(key: str, first: int = 1, last: int | None = None) -> str:
    source = next(source for source in excerpts()["excerpts"] if source["key"] == key)
    lines = []
    for line in source["lines"][first - 1:last]:
        # Shape tags preserve blank/heading/field/row positions without creating new checker records.
        parts = [f"> {key} line {line['line']:02} [{line['shape']}:{line['name']}]: {line['text']}"]
        if line["dates"]:
            parts.append("dates: " + ", ".join(line["dates"]))
        if line["numbers"]:
            parts.append("numeric receipt: " + " ".join(line["numbers"]))
        if line["states"]:
            parts.append("states: " + ", ".join(line["states"]))
        lines.append("; ".join(parts))
    return "\n".join(lines) + "\n"


def real_direction_selection_replay(parent: Path, name: str, *, repair: bool = False,
                                    workflow: str = "unified") -> tuple[Path, dict]:
    manifest = json.loads((REPLAYS / name / "replay.json").read_text(encoding="utf-8"))
    guards = "G6, GD" if name == "replay-direction-review" else "G11"
    target = project(parent, guards, workflow=workflow, name=name)
    if name == "replay-direction-review":
        append_discovery(target, discovery(manifest["insight"], date="2026-10-13",
            finding="structural gap: ours 0.957 vs reference 0.962-0.966; stronger standalone family remains unbuilt",
            implication="a different standalone family is needed; the diagnosis has no live action",
            Kind="insight", Status="planned H-A-31" if repair else "open", Due="2026-10-15 00:00")
            + "\n" + receipt_lines("strategy-review"))
        append_discovery(target, discovery(manifest["pivot"], date="2026-10-16",
            finding="pivot proposed at 01:43; withdrawn at 01:59 as redundant on proxy evidence",
            Kind="insight", Status=f"rejected — {manifest['rejection']} share tests show no gain",
            Due="2026-10-18 00:00") + "\n" + receipt_lines("direction-debate", 1, 36))
        append_discovery(target, discovery(manifest["rejection"], date="2026-10-16",
            finding="the proposed pivot does not hold: 0 % −0.0069, 50 % flat, 60 % dropped, 100 % −0.0058",
            Decision_class="target-change", Instrument="I-A-03" if repair else "I-A-01",
            Rejected_on=("I-A-03" if repair else "I-A-01") + "; fired: D-Z-990 confirms execution")
            + "\n" + receipt_lines("direction-debate", 37, 48))
        fields = {
            "Kind": "direction-review",
            "Gap": "ours 0.957 vs reference 0.966 on I-A-02 (2026-10-13)",
            "Decomposition": "own standalone 0.946 vs stronger singles 0.951-0.959; own contribution about +0.001",
            "Core_families": f"family-a built standalone {manifest['insight']}; family-b not built",
            "Data_audit": "supervision lineage and own-source correlation diagnosed; held-out versus proxy distinction recorded",
            "Rejected_consistent_gains": "none",
            "Decisions": ("H-A-31 created to build standalone family-b and test the structural gap" if repair
                          else "no change — retain daily small changes and a recipe fix; structural pivot withdrawn"),
        }
        if repair:
            fields["Intake"] = ("iterative supervision and standalone recipes reported at 0.949, 0.960 and 0.952; "
                                "agreement claims 0.66 versus 0.87 unreplicated; claims assessed as methods, not asset availability")
            plan(target, item("H-A-31", extra=[("Family", "family-b")]).replace(
                "- Sources: none", f"- Sources: {manifest['insight']}"))
        append_discovery(target, discovery(manifest["review"], date="2026-10-16",
            finding="debate concluded at 02:12 on daily small changes; intake was closed for lack of usable assets",
            **fields) + "\n" + receipt_lines("direction-debate", 49) + receipt_lines("intake"))
        shared(target, "Last direction review", f"{manifest['review']} (2026-10-16)")
        section(target, "Instruments", instrument("I-A-01", provenance="derived-from-targets",
                not_for="target-change") + instrument("I-A-02", provenance="external-feedback", coverage="external",
                agreement="unmeasured", resolution="±0.002 (D-Z-991)", dynamics="rounded display with changing cohort"))
        if repair:
            section(target, "Instruments", instrument("I-A-03"))
    else:
        selected = [row for row in corpus()["external_actions"] if row["ref"] in manifest["action_refs"]]
        for index, row in enumerate(selected, 1):
            stamp = dt.datetime.fromisoformat(row["date"]).strftime("%Y-%m-%d %H:%M")
            section(target, "External actions", f"### X-A-{index:03} — item {row['ref']}\n"
                    f"- Kind: release\n- Candidate: item {row['ref']}, hash neutral-{row['ref']}\n"
                    f"- Destination: external board\n- Family: {manifest['family']}\n"
                    "- Expected: not retained in source\n"
                    f"- Result: quality={row['visible score']} (observed {stamp})\n- Final: pending\n- Status: complete\n")
        rationale = "; rationale: retain a flat-weight hedge against the anchor's tuned weights" if repair else ""
        shared(target, "Final picks", f"X-A-001, X-A-002 (families: {manifest['family']}{rationale})")
        section(target, "Record receipts", receipt_lines("final-selection"))
    return target, manifest


@pytest.mark.parametrize("key,count", [("strategy-review", 55), ("direction-debate", 72),
                                       ("intake", 17), ("final-selection", 13)])
def test_real_direction_selection_corpus_preserves_source_structure_dates_numbers_and_states(key, count) -> None:
    data = excerpts()
    lines = next(source["lines"] for source in data["excerpts"] if source["key"] == key)
    assert len(lines) == count == data["integrity"][key]["line_count"]
    assert [line["line"] for line in lines] == list(range(1, count + 1))
    assert digest([line["numbers"] for line in lines]) == NUMERIC_DIGESTS[key]
    streams = {"structure": [[line["shape"], line["name"]] for line in lines],
               "numbers": [line["numbers"] for line in lines], "dates": [line["dates"] for line in lines],
               "states": [line["states"] for line in lines]}
    for stream, values in streams.items():
        assert digest(values) == data["integrity"][key][stream + "_sha256"]
    if key == "direction-debate":
        assert [line["dates"][0] for line in lines if line["shape"] == "heading"] == [
            f"2026-10-16 {stamp} KST" for stamp in ("01:43", "01:51", "01:57", "01:59", "02:11", "02:12")]
        assert [line["name"] for line in lines[1:11]] == ["Agent", "Host", "User", "Heading", "Action",
            "Discovery updates", "Review verdict", "Resource", "Other executor", "New plan items"]
        assert "WITHDRAWN" in lines[36]["states"] and "CHALLENGED" in lines[65]["states"]
    if key == "final-selection":
        assert "10-23 00:3x" in lines[1]["dates"]
        assert "57415972" in lines[1]["numbers"] and "57475409" in lines[1]["numbers"]
        # Preserve reverse update order, including the older update below the newer one.
        assert lines[1]["numbers"][0] == "12" and lines[2]["numbers"][0] == "11"


def test_real_direction_selection_excerpts_are_neutral_and_have_no_names_or_source_paths() -> None:
    data = excerpts()
    assert data["provenance"] == PROVENANCE
    # Pin the manually reviewed neutral summaries as well as the original numeric streams.
    assert digest([[line["text"] for line in source["lines"]] for source in data["excerpts"]]) == \
        "917f6e37654538005d94c6180b1984352896577050246d1219e40e3488f70d00"
    assert [source["key"] for source in data["excerpts"]] == [
        "strategy-review", "direction-debate", "intake", "final-selection"]
    allowed_fields = {"", "Agent", "Host", "User", "Heading", "Action", "Reference today", "Discovery updates", "Review verdict",
                      "Resource", "Other executor", "New plan items"}
    for source in data["excerpts"]:
        for line in source["lines"]:
            assert set(line) == {"line", "shape", "name", "text", "dates", "numbers", "states"}
            assert line["name"] in allowed_fields
            assert re.fullmatch(r"[a-z ,;:-]*", line["text"]), line["text"]
            assert not re.search(r"https?:|[/\\]|[A-Z]", line["text"])
            assert all(re.fullmatch(r"[-+−]?(?:\d+(?:[.,]\d+)*|\.\d+)(?:%|h)?", token)
                       for token in line["numbers"])
            assert all(re.fullmatch(r"[\d x:KST/-]+", stamp) for stamp in line["dates"])
    for name in ("replay-direction-review", "replay-final-selection"):
        manifest = json.loads((REPLAYS / name / "replay.json").read_text(encoding="utf-8"))
        assert manifest["provenance"] == PROVENANCE
        assert (REPLAYS / name / "README.md").read_text(encoding="utf-8").splitlines()[0] == "Provenance: " + PROVENANCE


@pytest.mark.parametrize("name", ["replay-direction-review", "replay-final-selection"])
@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_real_direction_selection_failure_replays_detect_the_recorded_gaps(tmp_path, capsys, name, workflow) -> None:
    target, manifest = real_direction_selection_replay(tmp_path, name, workflow=workflow)
    checker = check(target, now=dt.datetime.fromisoformat(manifest["snapshot"]))
    warnings = [issue for issue in guard_issues(checker) if issue.severity == "WARN"]
    expected = set(manifest["checks"])
    if name == "replay-direction-review":
        expected.discard("guard.direction.incomplete")
        assert any(issue.check == "guard.direction.advice" and issue.severity == "INFO" for issue in checker.issues)
    assert {issue.check for issue in warnings} == expected, [i.render() for i in checker.issues]
    assert not [issue for issue in checker.issues if issue.severity == "ERROR"], [i.render() for i in checker.issues]
    added = [len(set(checker.discoveries[key].fields) - {
        "Source", "Host", "User", "Date", "Cross-check", "Finding", "Evidence", "Implication", "Reviews"})
        for key in manifest["records"]]
    with capsys.disabled():
        print(f"\nBURDEN real {name} ({workflow}): added fields per discovery={added}; "
              f"guard warning volume={len(warnings)}; distinct warning checks={len(set(i.check for i in warnings))}")


@pytest.mark.parametrize("name", ["replay-direction-review", "replay-final-selection"])
@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_real_direction_selection_counter_replays_record_repairs_and_raise_nothing(tmp_path, name, workflow) -> None:
    target, manifest = real_direction_selection_replay(tmp_path, name, repair=True, workflow=workflow)
    checker = check(target, now=dt.datetime.fromisoformat(manifest["snapshot"]))
    assert not [issue for issue in guard_issues(checker) if issue.severity in {"WARN", "ERROR"}], \
        [issue.render() for issue in checker.issues]
    assert not [issue for issue in checker.issues if issue.severity in {"WARN", "ERROR"}], \
        [issue.render() for issue in checker.issues]
    if name == "replay-direction-review":
        assert checker.discoveries[manifest["insight"]].fields["Status"] == "planned H-A-31"
        assert checker.plan_items["H-A-31"].fields["Family"] == "family-b"
        assert "family-b not built" in checker.discoveries[manifest["review"]].fields["Core families"]
        assert "0.66 versus 0.87 unreplicated" in checker.discoveries[manifest["review"]].fields["Intake"]
        assert checker.discoveries[manifest["rejection"]].fields["Instrument"] == "I-A-03"
    else:
        assert "rationale:" in checker.shared["Final picks"]
        assert {row.fields["Family"] for row in checker.external_actions.values()} == {"family-a"}


def test_real_direction_replay_retains_unacted_diagnosis_withdrawal_debate_and_asset_closures(tmp_path) -> None:
    target, manifest = real_direction_selection_replay(tmp_path, "replay-direction-review")
    text = (target / "discoveries.md").read_text(encoding="utf-8")
    assert text.index("strategy-review line 01") < text.index("direction-debate line 01")
    assert text.index("direction-debate line 37") < text.index("direction-debate line 61")
    assert text.index("direction-debate line 72") < text.index("intake line 01")
    for key in manifest["excerpts"]:
        for line in receipt_lines(key).splitlines():
            assert line in text
    checker = check(target, now=dt.datetime.fromisoformat(manifest["snapshot"]))
    assert checker.discoveries[manifest["insight"]].fields["Date"] == "2026-10-13"
    assert checker.discoveries[manifest["insight"]].fields["Due"] == "2026-10-15 00:00"
    assert checker.discoveries[manifest["insight"]].fields["Status"] == "open"
    review = checker.discoveries[manifest["review"]]
    assert "Intake" not in review.fields and "family-b not built" in review.fields["Core families"]


def test_real_final_selection_replay_retains_actual_pair_receipts_and_no_invented_forecasts(tmp_path) -> None:
    target, manifest = real_direction_selection_replay(tmp_path, "replay-final-selection")
    checker = check(target, now=dt.datetime.fromisoformat(manifest["snapshot"]))
    rows = sorted(checker.external_actions.values(), key=lambda row: row.key)
    assert [row.fields["Candidate"] for row in rows] == [
        f"item {ref}, hash neutral-{ref}" for ref in manifest["action_refs"]]
    assert [row.fields["Result"].split()[0] for row in rows] == ["quality=0.958", "quality=0.957"]
    assert all(row.fields["Expected"] == "not retained in source" for row in rows)
    assert all(row.fields["Final"] == "pending" for row in rows)
    assert receipt_lines("final-selection") in (target / "handoff.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["replay-own-lineage-panel", "replay-in-sample-validation"])
def test_recordless_replay_readmes_explicitly_identify_postmortem_reconstructions(name) -> None:
    text = (FIXTURES / name / "README.md").read_text(encoding="utf-8")
    assert "post-mortem-derived reconstruction" in text
    assert "did not keep records in this" in text
