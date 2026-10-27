"""Receipt policy changes authorship requirements, never execution prerequisites."""
import datetime as dt

import pytest

import ro_evidence as evidence
import ro_settings as settings
from test_ro_evidence import EvidenceProject, artifact, prepared, action_args


@pytest.mark.parametrize("preset,expected", [("competition-solo", "self"), ("competition-team", "independent")])
def test_competition_receipt_default_and_explicit_override(preset, expected):
    data = settings.load_preset(preset)
    assert settings.resolve({"preset": preset}, data, {})["receipt_policy"] == expected
    assert settings.resolve({"receipt_policy": "independent"}, data, {})["receipt_policy"] == "independent"


def test_self_receipt_is_revoked_by_policy_or_latest_failure(tmp_path):
    project = EvidenceProject(tmp_path)
    project.values["receipt_policy"] = "self"
    name = artifact(project)
    evidence.receipt_add(project, name, project.session, "PASS", "contract")
    assert "PASS" in evidence.receipt_check(project, name, "contract")
    project.values["receipt_policy"] = "independent"
    with pytest.raises(ValueError, match="independent PASS"):
        evidence.receipt_check(project, name, "contract")
    project.values["receipt_policy"] = "self"
    evidence.receipt_add(project, name, project.session, "FAIL", "contract")
    with pytest.raises(ValueError, match="self PASS"):
        evidence.receipt_check(project, name, "contract")


@pytest.mark.parametrize("defect", ["expectation", "duplicate", "journal", "ledger", "hash"])
def test_self_policy_keeps_external_validation_unconditional(tmp_path, monkeypatch, defect):
    project = EvidenceProject(tmp_path)
    project.values["receipt_policy"] = "self"
    name = artifact(project)
    future = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    prepared(project, name, expected=future if defect == "expectation" else None)
    evidence.receipt_add(project, name, project.session, "PASS", "X-A-001", "release endpoint")
    if defect == "duplicate":
        prepared(project, name, action="X-A-002")
    elif defect == "journal":
        project.write_json("external-attempts/X-A-001.json", {"status": "done"})
    elif defect == "ledger":
        path = tmp_path / "handoff.md"
        path.write_text(path.read_text(encoding="utf-8") + "- Destination: other\n", encoding="utf-8")
    elif defect == "hash":
        artifact(project, "changed\n")
    monkeypatch.setattr(evidence.subprocess, "Popen", lambda *a, **k: pytest.fail("invalid action spawned"))
    before = (tmp_path / "handoff.md").read_bytes()
    with pytest.raises(ValueError):
        evidence.external(project, action_args())
    assert (tmp_path / "handoff.md").read_bytes() == before


def test_self_receipt_executes_once_and_journal_blocks_replay(tmp_path):
    project = EvidenceProject(tmp_path)
    project.values["receipt_policy"] = "self"
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, project.session, "PASS", "X-A-001", "release endpoint")
    evidence.external(project, action_args())
    assert project.read_json("external-attempts/X-A-001.json", {})["status"] == "done"
    with pytest.raises(ValueError):
        evidence.external(project, action_args())
