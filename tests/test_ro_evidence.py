"""Behavioural evidence tests: receipts, ledger gates and complete outgoing-history scans."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

import ro_evidence as evidence
import ro_state as state
from conftest import SCRIPTS, concurrent_results


class EvidenceProject:
    """Small protocol fixture independent of job and hook implementations."""

    def __init__(self, root: Path):
        self.root = root
        self.state = root / ".ro"
        self.state.mkdir(exist_ok=True)
        self.session = "author-session"
        self.values = {"publish_scan": "secrets"}

    def settings(self):
        return self.values

    def read_json(self, name, default):
        path = self.state / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def write_json(self, name, value):
        self.atomic_text(self.state / name, json.dumps(value))

    def atomic_text(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def lock(self, name="state"):
        return contextlib.nullcontext()


def artifact(project, text="reviewed bytes\n"):
    path = project.root / "artifact.txt"
    path.write_bytes(text.encode("utf-8"))
    return "artifact.txt"


def prepared(project, name, *, action="X-A-001", destination="release endpoint", expected=None, scope=None):
    digest = evidence.hash_artifact(project, name)["sha256"]
    written = expected or (dt.datetime.now() - dt.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
    contract = f"- Scope: {scope}\n" if scope else ""
    body = (f"### {action} — delivery\n- Kind: release\n- Candidate: {name}, hash {digest}\n"
            f"- Destination: {destination}\n{contract}- Expected: success (written {written})\n"
            "- Result: pending\n- Final: pending\n- Status: prepared\n")
    path = project.root / "handoff.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "## External actions\n\n"
    path.write_text(existing + body, encoding="utf-8", newline="\n")
    return digest


def action_args(name="artifact.txt", action="X-A-001", exit_code=0):
    return argparse.Namespace(artifact=name, action=action, command=[sys.executable, "-c", f"raise SystemExit({exit_code})"])


def test_receipt_latest_fail_supersedes_pass(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "contract")
    assert "PASS" in evidence.receipt_check(project, name, "contract")
    evidence.receipt_add(project, name, "reviewer-session", "FAIL", "contract")
    with pytest.raises(ValueError, match="no current"):
        evidence.receipt_check(project, name, "contract")


def test_receipt_changed_artifact_refuses_execution(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "contract")
    artifact(project, "changed bytes\n")
    with pytest.raises(ValueError, match="no current"):
        evidence.receipt_check(project, name, "contract")


def test_receipt_independent_identity_and_provenance(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    with pytest.raises(ValueError, match="reviewer must differ"):
        evidence.receipt_add(project, name, project.session, "PASS", "contract")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "contract")
    receipt = project.read_json("receipts.json", {})["receipts"][0]
    assert receipt["author_session"] == project.session
    assert receipt["author_source"]


def test_text_file_sha256_stable_between_lf_and_crlf(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project, "first\nsecond\n")
    first = evidence.hash_artifact(project, name)["sha256"]
    artifact(project, "first\r\nsecond\r\n")
    assert evidence.hash_artifact(project, name)["sha256"] == first


def test_directory_manifest_sorts_paths_excludes_state_and_hashes_raw_bytes(tmp_path):
    project = EvidenceProject(tmp_path)
    directory = tmp_path / "bundle"
    directory.mkdir()
    (directory / "z.txt").write_bytes(b"line\n")
    (directory / "a.txt").write_bytes(b"first\n")
    for name in evidence.EXCLUDED:
        (directory / name).mkdir()
        (directory / name / "ignored.txt").write_text("ignored", encoding="utf-8")
    first = evidence.hash_artifact(project, "bundle")
    assert [entry["path"] for entry in first["manifest"]] == ["a.txt", "z.txt"]
    (directory / "z.txt").write_bytes(b"line\r\n")
    assert evidence.hash_artifact(project, "bundle")["sha256"] != first["sha256"]


def test_directory_manifest_cap_records_unhashed_and_refuses(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    (tmp_path / "bundle").mkdir()
    (tmp_path / "bundle" / "payload").write_bytes(b"12345")
    monkeypatch.setattr(evidence, "MANIFEST_CAP", 0)
    evidence.receipt_add(project, "bundle", "reviewer-session", "PASS", "contract")
    assert project.read_json("receipts.json", {})["receipts"][0]["sha256"] == "unhashed"
    with pytest.raises(ValueError, match="unhashed"):
        evidence.receipt_check(project, "bundle", "contract")


@pytest.mark.parametrize("operation", ["add", "check", "external"])
@pytest.mark.parametrize("denied_name", ["bundle", "bundle/references"])
@pytest.mark.parametrize("error_type", [PermissionError, FileNotFoundError])
def test_directory_enumeration_failure_refuses_without_state_changes(
        tmp_path, monkeypatch, operation, denied_name, error_type):
    project = EvidenceProject(tmp_path)
    bundle = tmp_path / "bundle"
    (bundle / "references").mkdir(parents=True)
    (bundle / "visible.txt").write_bytes(b"reviewed visible bytes\n")
    (bundle / "references" / "hidden.txt").write_bytes(b"reviewed hidden bytes\n")
    prepared(project, "bundle")
    evidence.receipt_add(project, "bundle", "reviewer-session", "PASS", "X-A-001", "release endpoint")
    receipts = project.state / "receipts.json"
    ledger = tmp_path / "handoff.md"
    before = (receipts.read_bytes(), ledger.read_bytes())
    scandir = evidence.os.scandir

    def deny_directory(path):
        if Path(path).resolve() == (tmp_path / denied_name).resolve():
            raise error_type(errno.EACCES, "directory enumeration denied", str(path))
        return scandir(path)

    monkeypatch.setattr(evidence.os, "scandir", deny_directory)
    args = action_args(name="bundle")
    args.command = [sys.executable, "-c", "from pathlib import Path; Path('executed').touch()"]
    operations = {
        "add": lambda: evidence.receipt_add(project, "bundle", "reviewer-session", "PASS", "X-A-001"),
        "check": lambda: evidence.receipt_check(project, "bundle", "X-A-001", "release endpoint"),
        "external": lambda: evidence.external(project, args),
    }
    with pytest.raises(error_type, match="directory enumeration denied"):
        operations[operation]()
    assert (receipts.read_bytes(), ledger.read_bytes()) == before
    assert not (tmp_path / "executed").exists()
    assert not (project.state / "external-results").exists()


def test_first_receipt_is_not_created_when_directory_cannot_be_enumerated(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    (tmp_path / "bundle").mkdir()

    def deny_directory(path):
        raise PermissionError(errno.EACCES, "directory enumeration denied", str(path))

    monkeypatch.setattr(evidence.os, "scandir", deny_directory)
    with pytest.raises(PermissionError, match="directory enumeration denied"):
        evidence.receipt_add(project, "bundle", "reviewer-session", "PASS", "contract")
    assert not (project.state / "receipts.json").exists()


@pytest.mark.parametrize("failed_scan", [2, 3])
def test_directory_becoming_unreadable_during_external_validation_never_executes(
        tmp_path, monkeypatch, failed_scan):
    project = EvidenceProject(tmp_path)
    bundle = tmp_path / "bundle"
    (bundle / "references").mkdir(parents=True)
    (bundle / "references" / "source.txt").write_bytes(b"reviewed bytes\n")
    prepared(project, "bundle")
    evidence.receipt_add(project, "bundle", "reviewer-session", "PASS", "X-A-001", "release endpoint")
    receipts = project.state / "receipts.json"
    ledger = tmp_path / "handoff.md"
    before = (receipts.read_bytes(), ledger.read_bytes())
    scandir = evidence.os.scandir
    scans = 0

    def deny_later_scan(path):
        nonlocal scans
        if Path(path).resolve() == bundle.resolve():
            scans += 1
        if scans == failed_scan and Path(path).resolve() == (bundle / "references").resolve():
            raise PermissionError(errno.EACCES, "directory became unreadable", str(path))
        return scandir(path)

    monkeypatch.setattr(evidence.os, "scandir", deny_later_scan)
    args = action_args(name="bundle")
    args.command = [sys.executable, "-c", "from pathlib import Path; Path('executed').touch()"]
    with pytest.raises(PermissionError, match="directory became unreadable"):
        evidence.external(project, args)
    assert scans == failed_scan
    assert (receipts.read_bytes(), ledger.read_bytes()) == before
    assert not (tmp_path / "executed").exists()
    assert not (project.state / "external-results").exists()


@pytest.mark.parametrize("wrong", ["scope", "destination", "hash"])
def test_external_requires_matching_current_receipt(tmp_path, wrong):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "other" if wrong == "scope" else "X-A-001",
                         "other" if wrong == "destination" else "release endpoint")
    if wrong == "hash":
        artifact(project, "changed artifact\n")
    prepared(project, name)
    with pytest.raises(ValueError, match="no current"):
        evidence.external(project, action_args())
    assert "Status: prepared" in (tmp_path / "handoff.md").read_text(encoding="utf-8")


def test_external_prepared_becomes_done_and_cannot_repeat(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    assert evidence.external(project, action_args()).startswith("external X-A-001: done; result: ")
    assert "Status: done" in (tmp_path / "handoff.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="prepared"):
        evidence.external(project, action_args())


def test_external_failed_command_sets_error(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    with pytest.raises(ValueError, match="exit 7"):
        evidence.external(project, action_args(exit_code=7))
    assert "Status: error" in (tmp_path / "handoff.md").read_text(encoding="utf-8")


def test_external_future_expectation_refuses(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    future = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    prepared(project, name, expected=future)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    with pytest.raises(ValueError, match="before"):
        evidence.external(project, action_args())


def test_external_contract_scope_and_inferred_artifact(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, scope="release-contract")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "release-contract", "release endpoint")
    assert evidence.external(project, action_args(name=None)).startswith("external X-A-001: done; result: ")


def test_external_candidate_name_can_be_descriptive_with_explicit_artifact(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    path = tmp_path / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Candidate: artifact.txt,", "Candidate: reviewed release,"),
                    encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    assert evidence.external(project, action_args()).startswith("external X-A-001: done; result: ")


def test_external_duplicate_requires_deliberate_retry(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    prepared(project, name, action="X-A-002", expected="2020-01-02 08:00")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-002", "release endpoint")
    with pytest.raises(ValueError, match="duplicate"):
        evidence.external(project, action_args(action="X-A-002"))
    path = tmp_path / "handoff.md"
    text = path.read_text(encoding="utf-8")
    position = text.index("### X-A-002")
    path.write_text(text[:position] + "- Reconciled: not-accepted (observed 2020-01-01 09:00); service log\n"
                    + text[position:] + "- Retry of: X-A-001\n", encoding="utf-8")
    assert "done" in evidence.external(project, action_args(action="X-A-002"))


@pytest.mark.parametrize("padded", ["X-A-001", "X-A-002"])
def test_external_candidate_whitespace_does_not_hide_duplicate_identity(tmp_path, padded):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    prepared(project, name, action="X-A-002", expected="2020-01-02 08:00")
    path = tmp_path / "handoff.md"
    text = path.read_text(encoding="utf-8")
    position = text.index(f"### {padded}")
    tail = text[position:]
    candidate_end = tail.index("\n", tail.index("- Candidate:"))
    path.write_text(text[:position] + tail[:candidate_end] + "  " + tail[candidate_end:], encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-002", "release endpoint")
    args = action_args(action="X-A-002")
    args.command = [sys.executable, "-c", "from pathlib import Path; Path('executed').touch()"]
    before = path.read_bytes()
    with pytest.raises(ValueError, match="duplicate"):
        evidence.external(project, args)
    assert not (tmp_path / "executed").exists()
    assert path.read_bytes() == before


@pytest.mark.parametrize("selected", ["X-A-001", "X-A-002"])
def test_external_earlier_prepared_cannot_execute_after_later_attempt(tmp_path, selected):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    prepared(project, name, action="X-A-002", expected="2020-01-02 08:00")
    path = tmp_path / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8") + "- Retry of: X-A-001\n", encoding="utf-8")
    prepared(project, name, action="X-A-003", expected="2020-01-03 08:00")
    evidence._action_status(project, "X-A-003", "done")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", selected, "release endpoint")
    with pytest.raises(ValueError, match="duplicate"):
        evidence.external(project, action_args(action=selected))


def test_external_duplicate_ancestor_cannot_authorize_retry(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    prepared(project, name, expected="2020-01-01 08:00")
    prepared(project, name, action="X-A-002", expected="2020-01-02 08:00")
    path = tmp_path / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8") + "- Retry of: X-A-001\n", encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-002", "release endpoint")
    with pytest.raises(ValueError, match="exactly one heading"):
        evidence.external(project, action_args(action="X-A-002"))


def test_external_retry_chain_executes_third_attempt_once(tmp_path):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    path = tmp_path / "handoff.md"
    for number in range(1, 4):
        key = f"X-A-{number:03}"
        prepared(project, name, action=key, expected=f"2020-01-0{number} 08:00")
        if number > 1:
            path.write_text(path.read_text(encoding="utf-8") + f"- Retry of: X-A-{number - 1:03}\n",
                            encoding="utf-8")
        evidence.receipt_add(project, name, "reviewer-session", "PASS", key, "release endpoint")
        args = action_args(action=key, exit_code=7 if number < 3 else 0)
        if number < 3:
            with pytest.raises(ValueError, match="exit 7"):
                evidence.external(project, args)
            text = path.read_text(encoding="utf-8")
            position = text.index(f"### {key}")
            path.write_text(text[:position] + text[position:].replace(
                "Result: pending", f"Result: reconciled failure (observed 2020-01-0{number} 09:00)")
                + f"- Reconciled: not-accepted (observed 2020-01-0{number} 09:00); service log\n",
                encoding="utf-8")
        else:
            args.command = [sys.executable, "-c", "from pathlib import Path; p=Path('count'); "
                            "p.write_text(p.read_text()+'x' if p.exists() else 'x')"]
            assert "done" in evidence.external(project, args)
            with pytest.raises(ValueError, match="prepared"):
                evidence.external(project, args)
    assert (tmp_path / "count").read_text() == "x"
    actions = evidence._actions(path.read_text(encoding="utf-8"))
    assert [a["fields"]["Status"] for a in actions] == ["error", "error", "done"]


@pytest.mark.parametrize("invalid", ["missing", "self", "forward", "equal-time", "identity", "cycle", "ancestor"])
def test_external_invalid_retry_never_executes(tmp_path, invalid):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    prepared(project, name, action="X-A-002", expected=(
        "2020-01-01 08:00" if invalid == "equal-time" else "2020-01-02 08:00"))
    path = tmp_path / "handoff.md"
    text = path.read_text(encoding="utf-8")
    if invalid in {"cycle", "ancestor"}:
        text = text.replace("### X-A-002", "- Retry of: " + (
            "X-A-002" if invalid == "cycle" else "X-A-999") + "\n### X-A-002")
    if invalid == "identity":
        text = text.replace("Destination: release endpoint", "Destination: another endpoint", 1)
    if invalid == "forward":
        text = text.replace("written 2020-01-01", "written 2020-01-03")
    retry = {"missing": "X-A-999", "self": "X-A-002"}.get(invalid, "X-A-001")
    path.write_text(text + f"- Retry of: {retry}\n", encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-002", "release endpoint")
    before = path.read_bytes()
    args = action_args(action="X-A-002")
    args.command = [sys.executable, "-c", "from pathlib import Path; Path('executed').touch()"]
    with pytest.raises(ValueError, match="earlier matching"):
        evidence.external(project, args)
    assert not (tmp_path / "executed").exists()
    assert path.read_bytes() == before


def test_external_two_processes_execute_prepared_action_once(tmp_path):
    from ro_state import Project

    project = Project(tmp_path, session="author-session")
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    code = ("import argparse,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
            "from ro_state import Project; from ro_evidence import external; "
            "p=Project(Path(sys.argv[2]),session='author-session'); "
            "a=argparse.Namespace(artifact='artifact.txt',action='X-A-001',command="
            "[sys.executable,'-c',\"from pathlib import Path; import time; "
            "p=Path('executions.txt'); p.write_text(p.read_text()+'x' if p.exists() else 'x'); time.sleep(.4)\"]);"
            "print('ready',flush=True);sys.stdin.readline();\n"
            "try: print(external(p,a))\nexcept ValueError: raise SystemExit(3)\n")
    results = concurrent_results([[sys.executable, "-c", code, str(SCRIPTS), str(tmp_path)]] * 2)
    assert sorted(code for code, _, _ in results) == [0, 3], results
    assert (tmp_path / "executions.txt").read_text(encoding="utf-8") == "x"


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def history(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git is unavailable")
    git(tmp_path, "init", "--initial-branch=main")
    git(tmp_path, "config", "user.name", "fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    (tmp_path / "content.txt").write_text("clean\n", encoding="utf-8")
    git(tmp_path, "add", "content.txt")
    git(tmp_path, "commit", "-m", "initial")
    return EvidenceProject(tmp_path), git(tmp_path, "rev-parse", "HEAD")


def commit_content(project, content, message="change"):
    (project.root / "content.txt").write_text(content, encoding="utf-8")
    git(project.root, "add", "content.txt")
    git(project.root, "commit", "-m", message)
    return git(project.root, "rev-parse", "HEAD")


def refs(local, remote):
    return f"refs/heads/main {local} refs/heads/main {remote}\n"


def secret():
    return "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4"


def test_publish_intermediate_commit_cannot_hide_deleted_secret(history):
    project, old = history
    commit_content(project, secret())
    tip = commit_content(project, "clean again\n")
    findings = evidence.scan_publish(project, refs(tip, old))
    assert findings and all("redacted" in finding for finding in findings)
    assert secret() not in "\n".join(findings)


def test_publish_new_branch_scans_reachable_history(history):
    project, _ = history
    commit_content(project, secret())
    tip = commit_content(project, "clean again\n")
    assert evidence.scan_publish(project, refs(tip, "0" * 40))


def test_publish_force_push_scans_divergent_intermediate_commits(history):
    project, base = history
    previous = commit_content(project, "previous branch\n")
    git(project.root, "reset", "--hard", base)
    commit_content(project, secret())
    tip = commit_content(project, "clean replacement\n")
    assert evidence.scan_publish(project, refs(tip, previous))


def test_publish_exact_refs_excludes_unrelated_local_branch(history):
    project, base = history
    git(project.root, "checkout", "-b", "private")
    commit_content(project, secret())
    git(project.root, "checkout", "main")
    tip = commit_content(project, "clean outgoing\n")
    assert not evidence.scan_publish(project, refs(tip, base))


@pytest.mark.parametrize("location", ["message", "path"])
def test_publish_commit_message_and_file_names_are_redacted(history, location):
    project, old = history
    if location == "path":
        (project.root / secret()).write_text("ordinary content", encoding="utf-8")
        git(project.root, "add", secret())
    tip = commit_content(project, "clean outgoing\n", secret() if location == "message" else "change")
    findings = evidence.scan_publish(project, refs(tip, old))
    assert findings and secret() not in "\n".join(findings)


def test_publish_staged_precheck_scans_additions_not_secret_removals(history):
    project, _ = history
    commit_content(project, secret())
    (project.root / "content.txt").write_text("clean\n", encoding="utf-8")
    git(project.root, "add", "content.txt")
    assert not evidence.scan_publish(project)
    (project.root / "content.txt").write_text(secret(), encoding="utf-8")
    git(project.root, "add", "content.txt")
    # Change the index relative to a clean parent, so this is an added secret.
    git(project.root, "reset", "--soft", "HEAD^")
    assert evidence.scan_publish(project)


@pytest.mark.parametrize("setting", ["secrets; literal:restricted text", "secrets, regex:restricted[ ]text"])
def test_publish_configured_patterns_are_redacted(history, setting):
    project, old = history
    project.values["publish_scan"] = setting
    tip = commit_content(project, "restricted text\n")
    findings = evidence.scan_publish(project, refs(tip, old))
    assert findings and "restricted" not in "\n".join(findings)


@pytest.mark.parametrize("pattern", ["(a+)+$", "a" * 257, "(?:a|aa)" * 31 + "b", "a{1,2}{1,2}"])
def test_publish_unsafe_regex_refuses_before_execution(pattern):
    with pytest.raises(ValueError, match="use literals, character classes, anchors"):
        evidence.safe_regex(pattern)


def test_publish_regex_accepts_flat_branches_and_literal_group_characters():
    pattern = evidence.safe_regex(r"^token_[a-z]{8,16}$|^key_[()|]{2}$|^\(literal\)$")
    assert all(pattern.fullmatch(value) for value in ("token_abcdefgh", "key_(|", "(literal)"))


def test_publish_deleted_ref_has_no_outgoing_content(history):
    project, old = history
    assert not evidence.scan_publish(project, refs("0" * 40, old))


def test_publish_malformed_refs_fail_closed(history):
    project, _ = history
    with pytest.raises(ValueError, match="malformed"):
        evidence.scan_publish(project, "refs/heads/main --all refs/heads/main not-an-oid")


def test_publish_none_has_no_patterns(history):
    project, old = history
    project.values["publish_scan"] = "none"
    tip = commit_content(project, secret())
    assert not evidence.scan_publish(project, refs(tip, old))


def test_receipt_process_identity_is_not_an_author_assertion(tmp_path, monkeypatch):
    monkeypatch.delenv("RO_SESSION", raising=False)
    project = state.Project(tmp_path)
    assert project.session.startswith("local:") and project.explicit_session == ""
    artifact(project)
    with pytest.raises(ValueError, match="explicit stable author session"):
        evidence.receipt_add(project, "artifact.txt", "reviewer-session", "PASS", "contract")


@pytest.mark.parametrize("status", ["prepared", "done", "withdrawn"])
@pytest.mark.parametrize("selected", ["X-A-001", None])
def test_external_duplicate_selected_id_never_executes(tmp_path, monkeypatch, status, selected):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    path = tmp_path / "handoff.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace("Status: prepared", f"Status: {status}") +
                    original.split("## External actions\n", 1)[1], encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    executions = []
    monkeypatch.setattr(evidence.subprocess, "run", lambda *args, **kwargs: executions.append(args))
    with pytest.raises(ValueError, match="exactly one"):
        evidence.external(project, action_args(action=selected))
    assert executions == []
    assert path.read_text(encoding="utf-8").count("Status: prepared") == (2 if status == "prepared" else 1)


@pytest.mark.parametrize("selected", ["X-A-002", None])
@pytest.mark.parametrize("retry", [False, True])
def test_external_duplicate_historical_ids_refuse_before_selection_and_retry(tmp_path, monkeypatch, selected, retry):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    digest = prepared(project, name, expected="2020-01-01 08:00")
    path = project.root / "handoff.md"
    first = path.read_text(encoding="utf-8").replace("Status: prepared", "Status: done")
    duplicate = first.split("## External actions\n", 1)[1].replace(digest, "f" * 64)
    path.write_text(first + duplicate, encoding="utf-8")
    prepared(project, name, action="X-A-002", expected="2020-01-02 08:00")
    if retry:
        path.write_text(path.read_text(encoding="utf-8") + "- Retry of: X-A-001\n", encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-002", "release endpoint")
    calls = []
    monkeypatch.setattr(evidence, "_run_external", lambda *a, **k: calls.append("execute"))
    monkeypatch.setattr(evidence, "external_retry_checks", lambda *a, **k: calls.append("retry"))
    monkeypatch.setattr(evidence, "hash_artifact", lambda *a, **k: calls.append("select"))
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    for _ in range(2):
        with pytest.raises(ValueError, match="X-A-001 must have exactly one heading"):
            evidence.external(project, action_args(action=selected))
        assert calls == []
        assert before == {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert not (project.state / "external-attempts").exists()
    assert not (project.state / "external-results").exists()


@pytest.mark.parametrize("copies", [0, 2])
def test_external_status_update_requires_exactly_one_heading(tmp_path, copies):
    project = EvidenceProject(tmp_path)
    path = tmp_path / "handoff.md"
    text = "## External actions\n" + "### X-A-001 action\n- Status: prepared\n" * copies
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one heading"):
        evidence._action_status(project, "X-A-001", "done")
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("field", ["Status", "Candidate", "Destination", "Expected", "Result",
                                   "Scope", "Contract", "Retry of"])
@pytest.mark.parametrize("selected", ["X-A-001", None])
def test_external_duplicate_fields_never_execute_even_on_repeat(tmp_path, monkeypatch, field, selected):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    path = tmp_path / "handoff.md"
    text = path.read_text(encoding="utf-8")
    values = evidence._actions(text)[0]["fields"]
    if field not in values:
        values[field] = "X-A-001"
        text += f"- {field}: {values[field]}\n"
    path.write_text(text + f"- {field}: {values[field]}\n", encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    executions = []
    def execute(*args, **kwargs):
        executions.append(args)
        return subprocess.CompletedProcess(args[0], 0, "remote-123", "")
    monkeypatch.setattr(evidence.subprocess, "run", execute)
    before = path.read_bytes()
    for _ in range(2):
        with pytest.raises(ValueError, match=f"duplicate {field}"):
            evidence.external(project, action_args(action=selected))
        assert executions == []
        assert path.read_bytes() == before
    assert not (project.state / "external-results").exists()


@pytest.mark.parametrize("field", ["Status", "Candidate", "Destination", "Expected"])
def test_external_missing_required_field_in_history_refuses_before_execution(tmp_path, monkeypatch, field):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    path = tmp_path / "handoff.md"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(line for line in lines if not line.startswith(f"- {field}:")), encoding="utf-8")
    prepared(project, name, action="X-A-002", expected="2020-01-02 08:00")
    path.write_text(path.read_text(encoding="utf-8") + "- Retry of: X-A-001\n", encoding="utf-8")
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-002", "release endpoint")
    executions = []
    monkeypatch.setattr(evidence.subprocess, "run", lambda *args, **kwargs: executions.append(args))
    before = path.read_bytes()
    with pytest.raises(ValueError, match=f"exactly one {field}"):
        evidence.external(project, action_args(action="X-A-002"))
    assert executions == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("malformed", ["scope-alias", "duplicate-history-field", "two-sections"])
def test_external_ambiguous_ledger_refuses_before_execution(tmp_path, monkeypatch, malformed):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name, expected="2020-01-01 08:00")
    path = tmp_path / "handoff.md"
    if malformed == "scope-alias":
        path.write_text(path.read_text(encoding="utf-8") + "- Scope: X-A-001\n- Contract: other\n", encoding="utf-8")
        selected = "X-A-001"
    else:
        addition = "- Status: withdrawn\n" if malformed == "duplicate-history-field" else "## External actions\n"
        path.write_text(path.read_text(encoding="utf-8") + addition, encoding="utf-8")
        prepared(project, name, action="X-A-002", destination="second endpoint", expected="2020-01-02 08:00")
        selected = "X-A-002"
    evidence.receipt_add(project, name, "reviewer-session", "PASS", selected,
                         "release endpoint" if selected == "X-A-001" else "second endpoint")
    executions = []
    monkeypatch.setattr(evidence.subprocess, "run", lambda *args, **kwargs: executions.append(args))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="external ledger"):
        evidence.external(project, action_args(action=selected))
    assert executions == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("exit_code", [0, 7])
def test_external_retains_remote_identity_and_diagnostics(tmp_path, exit_code):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    args = action_args()
    args.command = [sys.executable, "-c", "import sys; print('remote-id: archive-482'); "
                    "print('request accepted; reconciliation required', file=sys.stderr); "
                    f"raise SystemExit({exit_code})"]
    if exit_code:
        with pytest.raises(ValueError) as exc:
            evidence.external(project, args)
        message = str(exc.value)
    else:
        message = evidence.external(project, args)
    result_path = ".ro/external-results/X-A-001.json"
    assert result_path in message
    result = json.loads((tmp_path / result_path).read_text(encoding="utf-8"))
    assert result["action"] == "X-A-001" and result["returncode"] == exit_code
    assert result["stdout"] == "remote-id: archive-482\n"
    assert result["stderr"] == "request accepted; reconciliation required\n"
    assert result["stdout_omitted_chars"] == result["stderr_omitted_chars"] == 0
    assert result["start_error"] == ""
    assert dt.datetime.fromisoformat(result["recorded_at"]).tzinfo is not None
    expected_status = "done" if exit_code == 0 else "error"
    assert f"Status: {expected_status}" in (tmp_path / "handoff.md").read_text(encoding="utf-8")


def test_external_start_failure_retains_diagnostic(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    def fail(*args, **kwargs):
        raise OSError("release executable unavailable")
    monkeypatch.setattr(evidence, "_run_external", fail)
    with pytest.raises(ValueError, match=r"could not start; result: \.ro/external-results/X-A-001.json"):
        evidence.external(project, action_args())
    result = project.read_json("external-results/X-A-001.json", {})
    assert result["returncode"] is None
    assert result["start_error"] == "release executable unavailable"
    assert "Status: error" in (tmp_path / "handoff.md").read_text(encoding="utf-8")


def test_external_retained_output_is_bounded_and_redacted(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    output = "remote-id: archive-482\npassword=do-not-retain\n" + "x" * 100000 + "\nfinal diagnostic"
    monkeypatch.setattr(evidence, "_run_external", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 0, output, output))
    evidence.external(project, action_args())
    result = project.read_json("external-results/X-A-001.json", {})
    for stream in ("stdout", "stderr"):
        assert result[stream].startswith("remote-id: archive-482\npassword=[REDACTED]")
        assert result[stream].endswith("final diagnostic")
        assert "do-not-retain" not in result[stream]
        assert len(result[stream]) <= evidence.EXTERNAL_OUTPUT_CAP + len("\n[output truncated]\n")
        assert result[stream + "_omitted_chars"] > 0


def test_external_storage_removes_github_fine_grained_and_temporary_aws_tokens(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    secrets = ["github_pat_" + "aB9_" * 20, "ASIA" + "A1" * 8]
    output = "remote-id: archive-482\n" + "\n".join(secrets) + "\naccepted"
    monkeypatch.setattr(evidence, "_run_external", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 0, output, output))
    evidence.external(project, action_args())
    result = project.read_json("external-results/X-A-001.json", {})
    for stream in ("stdout", "stderr"):
        assert result[stream] == "remote-id: archive-482\n[REDACTED]\n[REDACTED]\naccepted"
    assert all(secret not in json.dumps(result) for secret in secrets)


def test_external_result_write_failure_does_not_make_action_reusable(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    executions = []
    def execute(*args, **kwargs):
        executions.append(args)
        return subprocess.CompletedProcess(args[0], 0, "remote-id: archive-482", "")
    write_json = project.write_json
    def failed_write(name, value):
        if name.startswith("external-results/"):
            raise OSError("result disk unavailable")
        return write_json(name, value)
    monkeypatch.setattr(evidence, "_run_external", execute)
    monkeypatch.setattr(project, "write_json", failed_write)
    with pytest.raises(OSError, match="result disk unavailable"):
        evidence.external(project, action_args())
    assert "Status: done" in (tmp_path / "handoff.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="prepared"):
        evidence.external(project, action_args())
    assert len(executions) == 1


def test_publish_original_outgoing_commit_ignores_clean_replacement(history):
    project, base = history
    original = commit_content(project, secret(), "original outgoing")
    git(project.root, "checkout", "--detach", base)
    replacement = commit_content(project, "clean replacement\n", "replacement")
    git(project.root, "replace", original, replacement)
    assert secret() not in git(project.root, "show", f"{original}:content.txt")
    findings = evidence.scan_publish(project, refs(original, base))
    # The original blob (not the replacement's) is reported by path, line and introducing commit.
    assert any("content.txt:1 (commit " + original[:12] in finding for finding in findings)
    assert secret() not in "\n".join(findings)


def test_publish_staged_scan_uses_original_parent_despite_replacement(history):
    project, clean = history
    secret_parent = commit_content(project, secret())
    # A replacement hides the addition from an ordinary staged diff.
    git(project.root, "reset", "--hard", clean)
    git(project.root, "replace", clean, secret_parent)
    (project.root / "content.txt").write_text(secret(), encoding="utf-8")
    git(project.root, "add", "content.txt")
    assert not git(project.root, "diff", "--cached", "--", "content.txt")
    assert evidence.scan_publish(project)


def test_scan_deadline_applies_across_windows_and_restores_context(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    monkeypatch.setattr(evidence, "_staged_diff", lambda *_: b"+" + b"a" * 1000000)
    monkeypatch.setattr(evidence, "SCAN_SECONDS", .001)
    original = evidence._remaining
    def slow_check():
        time.sleep(.002)
        return original()
    monkeypatch.setattr(evidence, "_remaining", slow_check)
    with pytest.raises(ValueError, match="deadline"):
        evidence.scan_publish(project)
    assert evidence._SCAN_DEADLINE.get() is None


def test_publish_literal_crossing_scan_window_is_detected(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    monkeypatch.setattr(project, "settings", lambda: {"publish_scan": "literal:restricted-content"})
    monkeypatch.setattr(evidence, "_staged_diff", lambda *_: b"+" + b"a" * 65530 + b"restricted-content")
    assert evidence.scan_publish(project)


def test_staged_pipe_read_respects_deadline_and_reaps_only_owned_process(tmp_path, monkeypatch):
    project = EvidenceProject(tmp_path)
    started = []
    popen = subprocess.Popen
    def slow_git(*args, **kwargs):
        child = popen([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)
        started.append(child)
        return child
    monkeypatch.setattr(evidence.subprocess, "Popen", slow_git)
    monkeypatch.setattr(evidence, "SCAN_SECONDS", .2)
    before = time.monotonic()
    with pytest.raises(ValueError, match="deadline"):
        evidence.scan_publish(project)
    assert time.monotonic() - before < 2
    assert len(started) == 1 and started[0].poll() is not None


@pytest.mark.parametrize("chunk_size", [1, 7, 127, 4096, 65536])
@pytest.mark.parametrize("closed", [False, True])
def test_stream_redaction_suppresses_long_pem_bodies_before_retention(chunk_size, closed):
    body = "SensitiveBody9876543210" * 5 + "\n"
    raw = ("remote-id: accepted\n" + "safe diagnostic\n" * 800
           + "-----BEGIN RSA PRIVATE KEY-----\n" + body * 400
           + ("-----END RSA PRIVATE KEY-----\nfinal receipt\n" if closed else ""))
    output = evidence._RedactedOutput()
    for offset in range(0, len(raw), chunk_size):
        output.add(raw[offset:offset + chunk_size])
        assert len(output.pending) <= output.RECORD_CAP
    retained, _ = output.result()
    assert "SensitiveBody" not in retained
    assert "9876543210" not in retained
    assert retained.startswith("remote-id: accepted\n")
    if closed:
        assert retained.endswith("final receipt\n")


@pytest.mark.parametrize("prefix", ["github_pat_", "ghp_", "sk-proj-", 'password="'])
def test_stream_redaction_never_retains_split_token_fragments(prefix):
    body = "FragmentValue9753" * 3000
    raw = "remote-id: accepted\n" + prefix + body + ('"' if prefix.endswith('"') else '') + "\nfinal receipt\n"
    output = evidence._RedactedOutput()
    for offset in range(0, len(raw), 13):
        output.add(raw[offset:offset + 13])
    retained, omitted = output.result()
    assert "FragmentValue" not in retained and "9753" not in retained
    assert retained.startswith("remote-id: accepted\n") and retained.endswith("final receipt\n")
    assert omitted > 40000


@pytest.mark.parametrize("raw", [
    'password="first-fragment\nsecond-fragment"\nreceipt\n',
    'authorization: Bearer\nfirst-fragment\nreceipt\n',
    '-----BEGIN PRIVATE KEY-----' + 'first-fragment' * 2000 + '\nsecond-fragment\n'
    '-----END PRIVATE KEY-----\nreceipt\n',
])
def test_stream_redaction_retains_recognition_across_lines_and_unbounded_records(raw):
    output = evidence._RedactedOutput()
    for offset in range(0, len(raw), 3):
        output.add(raw[offset:offset + 3])
    retained, _ = output.result()
    assert "first-fragment" not in retained and "second-fragment" not in retained
    assert retained.endswith("receipt\n")


def test_external_streams_redact_pem_and_tokens_across_both_retention_boundaries(tmp_path):
    command = [sys.executable, "-c",
        "import sys; "
        "body='PrivateBody6543210'*9+'\\n'; "
        "payload='remote-id: accepted\\n'+'safe line\\n'*800+"
        "'-----BEGIN PRIVATE KEY-----\\n'+body*500+'-----END PRIVATE KEY-----\\n'+"
        "'github_pat_'+'SplitToken9753'*8000+'\\n'+'final receipt\\n'; "
        "sys.stdout.write(payload); sys.stderr.write(payload)"]
    result = evidence._run_external(command, tmp_path, 10, "key")
    assert result.returncode == 0 and not result.timed_out
    project = EvidenceProject(tmp_path)
    evidence._external_result(project, "X-A-001", stdout=result.stdout, stderr=result.stderr,
                              stdout_omitted=result.stdout_omitted, stderr_omitted=result.stderr_omitted)
    stored = project.read_json("external-results/X-A-001.json", {})
    for stream in ("stdout", "stderr"):
        assert "PrivateBody" not in stored[stream] and "6543210" not in stored[stream]
        assert "SplitToken" not in stored[stream] and "9753" not in stored[stream]
        assert stored[stream].startswith("remote-id: accepted\n")
        assert stored[stream].endswith("final receipt\n")
        assert "REDACTED" in stored[stream]
        assert stored[stream + "_omitted_chars"] > 90000


@pytest.mark.parametrize("launcher_exits", [False, True])
def test_external_deadline_terminates_owned_grandchild_and_prevents_delayed_effect(tmp_path, launcher_exits):
    # Two generations below the actual command, with inherited pipes and a
    # delayed local effect, discriminate tree cleanup from killing one PID.
    (tmp_path / "grandchild.py").write_text(
        "import os,time\nfrom pathlib import Path\n"
        "Path('grandchild.pid').write_text(str(os.getpid()))\n"
        "time.sleep(2)\nPath('late-effect.txt').write_text('unexpected')\n", encoding="utf-8")
    (tmp_path / "child.py").write_text(
        "import subprocess,sys,time\nsubprocess.Popen([sys.executable,'grandchild.py'])\ntime.sleep(10)\n",
        encoding="utf-8")
    command = [sys.executable, "-c", "import subprocess,sys,time; "
               "subprocess.Popen([sys.executable,'child.py']); "
               + ("time.sleep(.3)" if launcher_exits else "time.sleep(10)")]
    result = evidence._run_external(command, tmp_path, .8, "key")
    assert result.timed_out and result.termination_verified is True
    pid = int((tmp_path / "grandchild.pid").read_text(encoding="utf-8"))
    assert state.process_start(pid) is None
    time.sleep(1.5)
    assert not (tmp_path / "late-effect.txt").exists()


def test_external_interruption_terminates_descendants_before_returning(tmp_path, monkeypatch):
    real_wait = subprocess.Popen.wait
    triggered = []

    def interrupted(process, timeout=None):
        if timeout == 10 and not triggered:
            until = time.monotonic() + 3
            while not (tmp_path / "child.pid").exists() and time.monotonic() < until:
                time.sleep(.02)
            triggered.append(True)
            raise KeyboardInterrupt
        return real_wait(process, timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", interrupted)
    child = "import os,time; from pathlib import Path; Path('child.pid').write_text(str(os.getpid())); time.sleep(20)"
    command = [sys.executable, "-c", "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
               + repr(child) + "]); time.sleep(20)"]
    with pytest.raises(KeyboardInterrupt):
        evidence._run_external(command, tmp_path, 10, "key")
    assert triggered
    pid = int((tmp_path / "child.pid").read_text(encoding="utf-8"))
    assert state.process_start(pid) is None


def test_external_unproven_tree_termination_preserves_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence.OwnedTree, "alive", lambda self: None)
    result = evidence._run_external([sys.executable, "-c", "pass"], tmp_path, 2, "key")
    assert result.timed_out and result.termination_verified is False
