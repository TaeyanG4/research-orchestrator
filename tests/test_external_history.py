"""Durable outward-action identities survive edits to the visible ledger."""

import contextlib
import datetime as dt
import subprocess
from types import SimpleNamespace

import pytest

import ro_evidence as evidence
from test_external_safety import ready
from test_ro_evidence import action_args, prepared


@pytest.fixture(autouse=True)
def fixed_runtime(monkeypatch):
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 5, 12, tzinfo=tz)

    monkeypatch.setattr(evidence, "dt", SimpleNamespace(datetime=Clock, timezone=dt.timezone))
    monkeypatch.setattr(evidence, "process_start", lambda pid: "fixed-start")
    monkeypatch.setattr(evidence, "same_process", lambda pid, start: False)


def attempted(project, status="unknown", action="X-A-001"):
    value = {"action": action, "status": status,
             "sha256": evidence.hash_artifact(project, "artifact.txt")["sha256"],
             "destination": "release endpoint", "idempotency_key": "stable-service-key",
             "owner_pid": 123, "owner_start": "fixed-start",
             "started_at": "2020-01-01T08:01:00+00:00"}
    project.write_json(f"external-attempts/{action}.json", value)
    return value


def next_preparation(project, *, retry=False, destination="release endpoint"):
    prepared(project, "artifact.txt", action="X-A-002", expected="2020-01-02 08:00",
             destination=destination)
    if retry:
        path = project.root / "handoff.md"
        path.write_text(path.read_text(encoding="utf-8") + "- Retry of: X-A-001\n", encoding="utf-8")
    evidence.receipt_add(project, "artifact.txt", "reviewer", "PASS", "X-A-002", destination)


@pytest.mark.parametrize("status", ["unknown", "done", "in-flight"])
@pytest.mark.parametrize("edit", ["withdrawn", "omitted", "changed-identity"])
def test_attempt_identity_survives_ledger_edits(tmp_path, monkeypatch, status, edit):
    project = ready(tmp_path)
    original_attempt = attempted(project, status)
    path = tmp_path / "handoff.md"
    if edit == "omitted":
        path.write_text("## External actions\n", encoding="utf-8")
    else:
        evidence._action_status(project, "X-A-001", "withdrawn")
        if edit == "changed-identity":
            path.write_text(path.read_text(encoding="utf-8").replace("release endpoint", "different endpoint"),
                            encoding="utf-8")
    next_preparation(project)
    before = path.read_bytes()
    held = set()

    @contextlib.contextmanager
    def lock(name="state"):
        held.add(name)
        try:
            yield
        finally:
            held.remove(name)

    original_read = project.read_json

    def read(name, default):
        if name == "external-attempts/X-A-001.json":
            assert "external" in held
        return original_read(name, default)

    monkeypatch.setattr(project, "lock", lock)
    monkeypatch.setattr(project, "read_json", read)
    monkeypatch.setattr(evidence, "_run_external", lambda *a: pytest.fail("duplicate executed"))
    with pytest.raises(ValueError, match="already attempted.*reconcile.*Retry of"):
        evidence.external(project, action_args(action="X-A-002"))
    assert path.read_bytes() == before
    assert original_read("external-attempts/X-A-001.json", {}) == original_attempt
    assert not (project.state / "external-attempts/X-A-002.json").exists()


@pytest.mark.parametrize("status", ["unknown", "done", "in-flight"])
@pytest.mark.parametrize("reconciled", [False, True])
def test_withdrawn_attempt_requires_reconciled_explicit_retry(tmp_path, monkeypatch, status, reconciled):
    project = ready(tmp_path)
    attempted(project, status)
    evidence._action_status(project, "X-A-001", "withdrawn")
    path = tmp_path / "handoff.md"
    if reconciled:
        path.write_text(path.read_text(encoding="utf-8")
                        + "- Reconciled: not-accepted (observed 2020-01-01 09:00); service audit\n",
                        encoding="utf-8")
    next_preparation(project, retry=True)
    executions = []

    def execute(command, root, deadline, key):
        executions.append(key)
        return subprocess.CompletedProcess(command, 0, "accepted", "")

    monkeypatch.setattr(evidence, "_run_external", execute)
    if reconciled:
        assert "done" in evidence.external(project, action_args(action="X-A-002"))
        assert executions == ["stable-service-key"]
    else:
        with pytest.raises(ValueError, match="Reconciled"):
            evidence.external(project, action_args(action="X-A-002"))
        assert executions == []


def test_live_attempt_cannot_retry_even_when_withdrawn_and_reconciled(tmp_path, monkeypatch):
    project = ready(tmp_path)
    attempted(project, "in-flight")
    evidence._action_status(project, "X-A-001", "withdrawn")
    path = tmp_path / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8")
                    + "- Reconciled: not-accepted (observed 2020-01-01 09:00); service audit\n", encoding="utf-8")
    next_preparation(project, retry=True)
    monkeypatch.setattr(evidence, "same_process", lambda pid, start: True)
    monkeypatch.setattr(evidence, "_run_external", lambda *a: pytest.fail("live predecessor replayed"))
    with pytest.raises(ValueError, match="still in-flight"):
        evidence.external(project, action_args(action="X-A-002"))


def test_retry_chain_cannot_skip_an_omitted_attempt(tmp_path, monkeypatch):
    project = ready(tmp_path)
    attempted(project, "unknown", "X-A-003")
    path = tmp_path / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8")
                    + "- Reconciled: not-accepted (observed 2020-01-01 09:00); service audit\n", encoding="utf-8")
    next_preparation(project, retry=True)
    monkeypatch.setattr(evidence, "_run_external", lambda *a: pytest.fail("omitted branch replayed"))
    with pytest.raises(ValueError, match="restore its ledger history"):
        evidence.external(project, action_args(action="X-A-002"))


@pytest.mark.parametrize("prior", ["never-attempted", "other-destination", "other-hash"])
def test_unattempted_withdrawals_and_unrelated_identities_do_not_block(tmp_path, monkeypatch, prior):
    project = ready(tmp_path)
    evidence._action_status(project, "X-A-001", "withdrawn")
    if prior != "never-attempted":
        value = attempted(project)
        value["destination" if prior == "other-destination" else "sha256"] = (
            "other endpoint" if prior == "other-destination" else "f" * 64)
        project.write_json("external-attempts/X-A-001.json", value)
    next_preparation(project)
    monkeypatch.setattr(evidence, "_run_external", lambda command, *a: subprocess.CompletedProcess(command, 0, "ok", ""))
    assert "done" in evidence.external(project, action_args(action="X-A-002"))


@pytest.mark.parametrize("bad", [None, {}, {"action": "X-A-001", "sha256": "not-a-hash"}])
def test_damaged_attempt_history_fails_closed(tmp_path, monkeypatch, bad):
    project = ready(tmp_path)
    evidence._action_status(project, "X-A-001", "withdrawn")
    project.write_json("external-attempts/X-A-001.json", bad)
    next_preparation(project)
    monkeypatch.setattr(evidence, "_run_external", lambda *a: pytest.fail("damaged history ignored"))
    with pytest.raises(ValueError, match="invalid external attempt history"):
        evidence.external(project, action_args(action="X-A-002"))
