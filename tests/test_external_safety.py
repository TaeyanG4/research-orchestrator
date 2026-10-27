"""Crash-safe external attempts and bounded-memory artifact/response processing."""

import contextlib
import hashlib
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

import ro_evidence as evidence
import ro_state as state
from test_ro_evidence import EvidenceProject, action_args, artifact, prepared


def ready(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    evidence.receipt_add(project, name, "reviewer", "PASS", "X-A-001", "release endpoint")
    return project


def test_artifact_larger_than_64_mib_streams_without_read_bytes(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    chunk = b"\0" + b"a" * (1024 * 1024 - 1)
    digest = hashlib.sha256()
    with (tmp_path / "large.bin").open("wb") as output:
        for _ in range(65):
            output.write(chunk)
            digest.update(chunk)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded artifact read"))
    value = evidence.hash_artifact(project, "large.bin")
    assert value["sha256"] == digest.hexdigest()
    assert value["bytes"] == 65 * 1024 * 1024


@pytest.mark.parametrize("suffix", [b"", b"\0", b"\xff", b"\xe2\x82", b"\r"])
def test_streamed_text_hash_preserves_crlf_utf8_and_late_binary(tmp_path, monkeypatch, suffix):
    project = EvidenceProject(tmp_path)
    data = "ab\r\n문자\r\n".encode() + suffix
    (tmp_path / "artifact").write_bytes(data)
    monkeypatch.setattr(evidence, "WINDOW", 3)
    try:
        data.decode("utf-8")
        expected = data if b"\0" in data else data.replace(b"\r\n", b"\n")
    except UnicodeDecodeError:
        expected = data
    value = evidence.hash_artifact(project, "artifact")
    assert value["sha256"] == hashlib.sha256(expected).hexdigest()
    assert value["bytes"] == len(expected)


def test_external_journals_before_spawn_and_releases_shared_lock(tmp_path, monkeypatch):
    project = ready(tmp_path)
    held = set()

    @contextlib.contextmanager
    def lock(name="state"):
        held.add(name)
        try:
            yield
        finally:
            held.remove(name)

    monkeypatch.setattr(project, "lock", lock)

    def execute(command, root, deadline, key):
        attempt = project.read_json("external-attempts/X-A-001.json", {})
        assert attempt["status"] == "in-flight"
        assert attempt["idempotency_key"] == key and len(key) == 64
        assert "Status: in-flight" in (tmp_path / "handoff.md").read_text(encoding="utf-8")
        assert held == {"external-X-A-001"}
        return subprocess.CompletedProcess(command, 0, "accepted", "")

    monkeypatch.setattr(evidence, "_run_external", execute)
    evidence.external(project, action_args())
    assert project.read_json("external-attempts/X-A-001.json", {})["status"] == "done"


def test_independent_external_actions_execute_concurrently(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    ready(tmp_path)
    project = state.Project(tmp_path, session="author")
    prepared(project, "artifact.txt", action="X-A-002", destination="other endpoint")
    evidence.receipt_add(project, "artifact.txt", "reviewer", "PASS", "X-A-002", "other endpoint")
    both_running = threading.Barrier(2)

    def execute(command, *args):
        both_running.wait(timeout=5)
        return subprocess.CompletedProcess(command, 0, "accepted", "")

    monkeypatch.setattr(evidence, "_run_external", execute)
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [pool.submit(evidence.external, project, action_args(action=key))
                for key in ("X-A-001", "X-A-002")]
        assert all("done" in run.result(timeout=10) for run in runs)


def test_remote_acceptance_then_interruption_never_replays_even_if_prepared_restored(tmp_path, monkeypatch):
    project = ready(tmp_path)
    executions = []

    def accepted_then_crashed(*args):
        executions.append(True)
        raise KeyboardInterrupt()

    monkeypatch.setattr(evidence, "_run_external", accepted_then_crashed)
    with pytest.raises(KeyboardInterrupt):
        evidence.external(project, action_args())
    assert project.read_json("external-attempts/X-A-001.json", {})["status"] == "unknown"
    evidence._action_status(project, "X-A-001", "prepared")
    with pytest.raises(ValueError, match="already attempted"):
        evidence.external(project, action_args())
    assert len(executions) == 1


@pytest.mark.parametrize("fail_at", ["journal-before", "ledger-before", "journal-after", "ledger-after"])
def test_status_write_failures_never_allow_replay(tmp_path, monkeypatch, fail_at):
    project = ready(tmp_path)
    executions = []
    original_json, original_status = project.write_json, evidence._action_status

    def write(name, value):
        if name.startswith("external-attempts/") and (
                fail_at == "journal-before" and value["status"] == "in-flight" or
                fail_at == "journal-after" and value["status"] == "done"):
            raise OSError("journal unavailable")
        original_json(name, value)

    def status(project, action, value):
        if (fail_at == "ledger-before" and value == "in-flight" or
                fail_at == "ledger-after" and value == "done"):
            raise OSError("ledger unavailable")
        original_status(project, action, value)

    def execute(*args):
        executions.append(True)
        return subprocess.CompletedProcess(args[0], 0, "accepted", "")

    monkeypatch.setattr(project, "write_json", write)
    monkeypatch.setattr(evidence, "_action_status", status)
    monkeypatch.setattr(evidence, "_run_external", execute)
    with pytest.raises(OSError, match="unavailable"):
        evidence.external(project, action_args())
    assert len(executions) == (1 if fail_at.endswith("after") else 0)
    if fail_at.endswith("after"):
        assert project.read_json("external-results/X-A-001.json", {})["stdout"] == "accepted"
    if fail_at != "journal-before":
        original_status(project, "X-A-001", "prepared")
        with pytest.raises(ValueError, match="already attempted"):
            evidence.external(project, action_args())
    else:
        assert not (project.state / "external-attempts/X-A-001.json").exists()


@pytest.mark.parametrize("reconciled", ["", "accepted (observed 2020-01-01 09:00); service receipt",
                                      "not-accepted (observed 2019-12-31 09:00); stale service log",
                                      "not-accepted (observed 2020-01-03 09:00); service log",
                                      "not-accepted (observed 2020-01-01 09:00);"])
def test_retry_needs_prior_not_accepted_reconciliation(tmp_path, monkeypatch, reconciled):
    project = ready(tmp_path)
    ledger = tmp_path / "handoff.md"
    ledger.write_text(ledger.read_text(encoding="utf-8") + "- Reconciled: " + reconciled + "\n", encoding="utf-8")
    prepared(project, "artifact.txt", action="X-A-002", expected="2020-01-02 08:00")
    ledger.write_text(ledger.read_text(encoding="utf-8") + "- Retry of: X-A-001\n", encoding="utf-8")
    evidence.receipt_add(project, "artifact.txt", "reviewer", "PASS", "X-A-002", "release endpoint")
    monkeypatch.setattr(evidence, "_run_external", lambda *a: pytest.fail("unreconciled retry executed"))
    with pytest.raises(ValueError, match="Reconciled"):
        evidence.external(project, action_args(action="X-A-002"))


def test_reconciled_retry_preserves_service_idempotency_key(tmp_path):
    project = ready(tmp_path)
    args = action_args(exit_code=7)
    args.command = [sys.executable, "-c", "import os; print(os.environ['RO_IDEMPOTENCY_KEY']); raise SystemExit(7)"]
    with pytest.raises(ValueError, match="exit 7"):
        evidence.external(project, args)
    ledger = tmp_path / "handoff.md"
    ledger.write_text(ledger.read_text(encoding="utf-8")
                      + "- Reconciled: not-accepted (observed 2020-01-01 09:00); service log\n", encoding="utf-8")
    prepared(project, "artifact.txt", action="X-A-002", expected="2020-01-02 08:00")
    ledger.write_text(ledger.read_text(encoding="utf-8") + "- Retry of: X-A-001\n", encoding="utf-8")
    evidence.receipt_add(project, "artifact.txt", "reviewer", "PASS", "X-A-002", "release endpoint")
    args = action_args(action="X-A-002")
    args.command = [sys.executable, "-c", "import os; print(os.environ['RO_IDEMPOTENCY_KEY'])"]
    evidence.external(project, args)
    one = project.read_json("external-attempts/X-A-001.json", {})["idempotency_key"]
    two = project.read_json("external-attempts/X-A-002.json", {})["idempotency_key"]
    assert one == two
    assert project.read_json("external-results/X-A-002.json", {})["stdout"].strip() == one


def test_deadline_bounds_child_and_retains_unknown_outcome(tmp_path):
    project = ready(tmp_path)
    args = action_args()
    args.deadline = 0.2
    args.command = [sys.executable, "-c", "import time; print('accepted remote-7', flush=True); time.sleep(10)"]
    start = time.monotonic()
    with pytest.raises(ValueError, match="outcome unknown"):
        evidence.external(project, args)
    assert time.monotonic() - start < 5
    result = project.read_json("external-results/X-A-001.json", {})
    assert result["stdout"] == "accepted remote-7\n"
    assert project.read_json("external-attempts/X-A-001.json", {})["status"] == "unknown"
    with pytest.raises(ValueError, match="prepared"):
        evidence.external(project, args)


def test_external_streams_both_large_outputs_in_bounded_memory(tmp_path):
    result = evidence._run_external([sys.executable, "-c",
        "import sys; print('remote-id: 7'); print('password=hidden'); "
        "sys.stdout.write('x'*3000000); sys.stderr.write('y'*3000000); print('last')"], tmp_path, 10, "key")
    assert result.returncode == 0 and not result.timed_out
    assert len(result.stdout) <= evidence.EXTERNAL_OUTPUT_CAP + 30
    assert len(result.stderr) <= evidence.EXTERNAL_OUTPUT_CAP + 30
    assert result.stdout_omitted > 2_000_000 and result.stderr_omitted > 2_000_000
    project = EvidenceProject(tmp_path)
    evidence._external_result(project, "X-A-001", stdout=result.stdout, stderr=result.stderr,
                              stdout_omitted=result.stdout_omitted, stderr_omitted=result.stderr_omitted)
    stored = project.read_json("external-results/X-A-001.json", {})
    assert "hidden" not in stored["stdout"] and "remote-id: 7" in stored["stdout"]


@pytest.mark.parametrize("deadline", [0, -1, float("inf"), float("nan")])
def test_invalid_external_deadline_refuses_before_journal(tmp_path, deadline):
    project = ready(tmp_path)
    args = action_args()
    args.deadline = deadline
    with pytest.raises(ValueError, match="positive finite"):
        evidence.external(project, args)
    assert not (project.state / "external-attempts").exists()


def test_git_startup_timeout_reports_the_scan_deadline(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(evidence.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="deadline exceeded"):
        evidence._git(EvidenceProject(tmp_path), "rev-parse", "HEAD")


def test_batch_timer_expiry_is_reported_even_before_clock_ticks():
    batch = evidence._Batch.__new__(evidence._Batch)
    batch.expired = threading.Event()
    batch.expired.set()
    with pytest.raises(ValueError, match="deadline exceeded"):
        batch._failed()


def test_external_subprocess_passes_shared_no_window_flag(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(evidence, "no_window_flags", lambda: 0x08000000)

    def unavailable(command, **kwargs):
        seen.append(kwargs["creationflags"])
        raise OSError("unavailable")

    monkeypatch.setattr(evidence.subprocess, "Popen", unavailable)
    with pytest.raises(OSError, match="unavailable"):
        evidence._run_external(["external-tool"], tmp_path, 1, "key")
    assert seen == [0x08000000]


def test_publish_cache_oversized_read_is_discarded_before_json_parsing(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    (project.state / evidence.SCAN_CACHE).write_bytes(b"x" * 100)
    monkeypatch.setattr(evidence, "SCAN_CACHE_BYTES", 32)
    monkeypatch.setattr(evidence.json, "loads", lambda *a: pytest.fail("oversized cache parsed"))
    assert evidence._cache(project, [])[1] == []


def test_publish_cache_caps_oid_count_and_ignores_malformed_entries(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    key, _ = evidence._cache(project, [])
    project.write_json(evidence.SCAN_CACHE, {"patterns": key, "objects": ["a" * 40, "b" * 40, "invalid", "c" * 64]})
    monkeypatch.setattr(evidence, "SCAN_CACHE_LIMIT", 3)
    assert evidence._cache(project, [])[1] == ["b" * 40, "c" * 64]
