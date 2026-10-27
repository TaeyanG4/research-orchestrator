"""Identifiers survive rollover; Markdown examples never become operational records."""

import argparse
import datetime as dt
import re
import sys

import pytest

from conftest import append_discovery, append_events, check, event, item, set_slot
from guard_helpers import discovery, instrument, plan, project, section
import init_research_orchestrator as init
import ro_evidence as evidence
import ro_hooks as hooks
from ro_ids import ID_WIDTHS, format_id, id_pattern
from ro_markdown import mask_fences, unfenced, visible_lines
import ro_records as records
import ro_settings as settings
from ro_state import Project


@pytest.mark.parametrize("previous", [99, 999])
def test_allocated_ids_complete_evidence_workflow_across_rollover(tmp_path, previous):
    target = project(tmp_path, "G1, G6, E1")
    set_slot(target, "A", "Claude Code")
    p = Project(target, slot="A", session="author-session")
    archive = target / "docs"
    archive.mkdir(exist_ok=True)
    (archive / "historical-ids.md").write_text(
        "\n".join(format_id(kind, "A", previous) for kind in ID_WIDTHS), encoding="utf-8")
    allocated = {kind: records.next_id(p, kind) for kind in ID_WIDTHS}
    assert allocated == {kind: format_id(kind, "A", previous + 1) for kind in ID_WIDTHS}
    hid, iid, did, xid = (allocated[kind] for kind in "HIDX")
    followup = item(hid, stages="s1 measurement | s2 follow-up").replace("- Sources: none", f"- Sources: {did}")
    plan(target, followup)
    section(target, "Instruments", instrument(iid))
    measurement = f"quality=0.85 on {iid} cohort stable"
    append_discovery(target, discovery(did, Kind="insight", Status=f"planned {hid}",
                                      Decision_class="model-change", Instrument=iid, Result=measurement))
    assert records.claim(p, hid).startswith(hid + ": A since ")
    assert records.release(p, hid) == hid + ": none"
    append_events(target, event("2026-10-24 11:00", "A", hid + "/s1", discovery=did, new_items=hid))
    (target / "candidate.txt").write_text("release candidate\n", encoding="utf-8")
    digest = evidence.hash_artifact(p, "candidate.txt")["sha256"]
    stamp = (dt.datetime.now() - dt.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
    section(target, "External actions", f"### {xid} — release\n- Kind: release\n"
            f"- Candidate: candidate.txt, hash {digest}\n- Destination: local test endpoint\n"
            f"- Expected: quality above 0.8 (written {stamp})\n- Result: pending\n"
            "- Final: pending\n- Status: prepared\n")
    evidence.receipt_add(p, "candidate.txt", "independent-review", "PASS", xid, "local test endpoint")
    evidence.external(p, argparse.Namespace(artifact="candidate.txt", action=xid,
                      command=[sys.executable, "-c", "print('recorded release')"]))
    path = target / "handoff.md"
    text = path.read_text(encoding="utf-8")
    observed = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    path.write_text(text.replace("- Result: pending", f"- Result: {measurement} (observed {observed})"),
                    encoding="utf-8")
    checker = check(target, dt.datetime.now())
    assert not [issue.render() for issue in checker.issues if issue.severity in {"ERROR", "WARN"}]
    assert checker.eligible_instrument(checker.discoveries[did])
    assert checker.insight_status(f"planned {hid}") == ("planned", hid)
    assert checker.external_actions[xid].fields["Status"] == "done"
    assert {hid, iid, did, xid} <= set(records.reconcile_ids(p))
    assert records.next_id(p, "I") == format_id("I", "A", previous + 2)
    # Reference extraction must retain the entire wide ID and still detect dangling evidence.
    path.write_text(path.read_text(encoding="utf-8").replace(f"### {iid} —", "### I-B-01 —"), encoding="utf-8")
    missing = check(target, dt.datetime.now())
    assert any(issue.check == "evidence.instrument.dangling" and iid in issue.message for issue in missing.issues)


@pytest.mark.parametrize("kind", ID_WIDTHS)
def test_identifier_grammar_keeps_minimum_width_and_accepts_larger_sequences(kind):
    width = ID_WIDTHS[kind]
    assert not re.fullmatch(id_pattern(kind), f"{kind}-A-{'1' * (width - 1)}")
    assert re.fullmatch(id_pattern(kind), format_id(kind, "ZZ", 10 ** (width + 2)))


FENCES = [("~~~markdown", "~~~", "```"), ("````markdown", "````", "```"),
          ("~~~~~", "~~~~~~", "~~~"), ("```", "```", "~~~")]


def sample(opening, closing, inner, body):
    return f"{opening}\n{body}\n{inner}\n{body}\n{closing}\n"


@pytest.mark.parametrize("opening,closing,inner", FENCES)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_fences_preserve_line_numbers_and_character_offsets(opening, closing, inner, newline):
    fake = sample(opening, closing, inner, "## D-A-999 — sample")
    text = ("prefix\n" + fake + "## D-A-001 — live\n").replace("\n", newline)
    masked = mask_fences(text)
    assert len(masked) == len(text)
    assert [i for i, char in enumerate(masked) if char in "\r\n"] == [
        i for i, char in enumerate(text) if char in "\r\n"]
    assert masked.index("## D-A-001") == text.index("## D-A-001")
    assert len(unfenced(text)) == len(text.splitlines())
    assert "D-A-999" not in masked


@pytest.mark.parametrize("opening,closing,inner", FENCES)
def test_checker_and_record_commands_ignore_fenced_records(tmp_path, opening, closing, inner):
    target = project(tmp_path, "G1")
    p = Project(target, slot="A", session="author-session")
    plan(target, sample(opening, closing, inner, item("H-A-999")) + item("H-A-01"))
    fenced = sample(opening, closing, inner, discovery("D-A-999"))
    append_discovery(target, fenced + discovery("D-A-001"))
    section(target, "Instruments", sample(opening, closing, inner, instrument("I-A-999")))
    checker = check(target)
    assert set(checker.plan_items) == {"H-A-01"}
    assert "D-A-999" not in checker.discoveries and not checker.instruments
    source = (target / "discoveries.md").read_text(encoding="utf-8")
    assert checker.discoveries["D-A-001"].line == source[:source.rindex("## D-A-001")].count("\n") + 1
    assert records.next_id(p, "H") == "H-A-02"
    assert records.next_id(p, "D") == "D-A-002"
    assert records.next_id(p, "I") == "I-A-01"
    assert "D-A-999" not in records.discovery_index(p)
    assert records.discovery_index(p, "D-A-001").startswith("## D-A-001")
    before = (target / "plan.md").read_bytes()
    with pytest.raises(ValueError, match="exactly once"):
        records.claim(p, "H-A-999")
    assert (target / "plan.md").read_bytes() == before


@pytest.mark.parametrize("opening,closing,inner", FENCES)
def test_migration_ignores_sample_items_and_preserves_fenced_fields(opening, closing, inner):
    settings_values = settings.resolve({}, None, {"workflow": "unified"})
    fenced = sample(opening, closing, inner, item("H-A-999"))
    source = "## Agent: A\n\n" + item("H-A-01", claimed=None) + fenced
    converted, count = init.plan_to_unified(source, settings_values, "sample")
    assert count == 1 and [i.item_id for i in init.parse_plan_items(converted)] == ["H-A-01"]
    assert fenced in converted
    handoff = "## Shared state\n- Active agent(s): A\n"
    classic, _, count = init.plan_to_classic(converted, handoff, settings_values, "sample")
    assert count == 1 and fenced in classic
    assert [i.item_id for i in init.parse_plan_items(classic)] == ["H-A-01"]


@pytest.mark.parametrize("opening,closing,inner", FENCES)
def test_settings_ignore_fenced_sections_markers_and_user_region(opening, closing, inner):
    fake = sample(opening, closing, inner,
                  "<!-- ro-template: v99 -->\n## Project settings\n- Workflow: classic\n## Project rules")
    generated = "# Example — Agent Rules\n" + fake + "## Project settings\n- Workflow: unified\n"
    region = "## Project rules\nKeep this region verbatim.\n"
    assert settings.split_agents(generated + region) == (generated, region)
    parsed = settings.read_settings(generated + region)
    assert parsed.values["workflow"] == "unified" and parsed.version == ""
    assert fake.rstrip() in init.comparable(generated)


@pytest.mark.parametrize("opening,closing,inner", FENCES)
@pytest.mark.parametrize("placement", ["before-settings", "inside-settings"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_runtime_and_checker_read_live_enforcement_after_fenced_examples(
        tmp_path, opening, closing, inner, placement, newline):
    target = project(tmp_path)
    path = target / "agents.md"
    live = re.sub(r"(?m)^- Block:.*$", "- Block: external.gate",
                  path.read_text(encoding="utf-8").replace("- Enforcement: off", "- Enforcement: block"))
    fake = sample(opening, closing, inner,
                  "## Project settings\n- Enforcement: off\n- Block: none\n## Project rules")
    if placement == "before-settings":
        text = live.replace("## Project settings\n", fake + "## Project settings\n", 1)
    else:
        text = live.replace("## Project settings\n", "## Project settings\n" + fake, 1)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    checker = check(target)
    runtime = Project(target).settings(required=True)
    shared = settings.read_settings(text).values
    for values in (shared, checker.values, runtime):
        assert values["enforcement"] == "block"
        assert values["block"] == "external.gate"


def test_fence_iterator_stops_without_consuming_unrelated_lines():
    def source():
        yield "~~~markdown\n"
        yield "```\n"
        yield "~~~\n"
        yield "## Project settings\n"
        raise AssertionError("reader consumed unrelated body")

    lines = visible_lines(source())
    assert [next(lines)[1] for _ in range(4)] == [False, False, False, True]


@pytest.mark.parametrize("opening,closing,inner", FENCES)
def test_hook_snapshot_ignores_fenced_dates_ids_and_reservations(tmp_path, opening, closing, inner):
    target = project(tmp_path)
    p = Project(target, slot="A")
    path = target / "discoveries.md"
    future = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    example = sample(opening, closing, inner, "## D-A-001 example\n- Date: " + future)
    path.write_text(example, encoding="utf-8")
    assert records.next_id(p, "D") == "D-A-001"
    assert hooks._snapshot(p) == []
    cached = p.read_json("records-hook.json")["discoveries.md"]
    assert cached["ids"] == cached["future"] == cached["duplicate"] == []
    assert "D-A-001" in p.read_json("ids.json")

    path.write_text(example + ("## D-A-001 live\n- Date: " + future + "\n") * 2, encoding="utf-8")
    assert {finding.check for finding in hooks._snapshot(p)} == {"records.timestamp", "records.id"}
    assert "D-A-001" not in p.read_json("ids.json")


def test_hook_snapshot_reparses_legacy_fence_cache_without_a_file_change(tmp_path):
    target = project(tmp_path)
    p = Project(target, slot="A")
    path = target / "discoveries.md"
    path.write_text("~~~~\n## D-A-999 example\n~~~\n~~~~\n## D-A-001 live\n", encoding="utf-8")
    stat = path.stat()
    p.write_json("records-hook.json", {"discoveries.md": {
        "stamp": [stat.st_mtime_ns, stat.st_size], "ids": ["D-A-999", "D-A-001"],
        "future": [], "future_records": [], "duplicate": []}})
    assert hooks._snapshot(p) == []
    assert p.read_json("records-hook.json")["discoveries.md"]["ids"] == ["D-A-001"]


@pytest.mark.parametrize("opening,closing,inner", FENCES)
def test_observe_updates_live_field_without_touching_fenced_sample(tmp_path, opening, closing, inner):
    target = project(tmp_path)
    p = Project(target, slot="A")
    path = target / "handoff.md"
    fake = sample(opening, closing, inner, "## Shared state\n- Runner: sample")
    path.write_text(fake + path.read_text(encoding="utf-8"), encoding="utf-8")
    records.observe(p, "Runner", "ready")
    updated = path.read_text(encoding="utf-8")
    assert updated.startswith(fake)
    assert "- Runner: ready (Observed at " in mask_fences(updated)


def test_old_archive_cache_is_reparsed_with_delimiter_aware_rules(tmp_path):
    target = project(tmp_path)
    p = Project(target, slot="A")
    archive = target / "docs"
    archive.mkdir(exist_ok=True)
    path = archive / "examples.md"
    path.write_text("````\n```\nD-A-999\n````\nD-A-003\n", encoding="utf-8")
    info = path.stat()
    stamp = [info.st_mtime_ns, info.st_ctime_ns, info.st_size, info.st_ino]
    p.write_json("archive-ids.json", {"version": 1, "files": {"docs/examples.md": {
        "stat": stamp, "ids": ["D-A-999", "D-A-003"]}}})
    assert records.next_id(p, "D") == "D-A-004"
    assert p.read_json("archive-ids.json")["version"] == 2
