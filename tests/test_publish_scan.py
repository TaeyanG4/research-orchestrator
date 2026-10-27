"""Outgoing publication scan: object coverage, exclusions, reporting, cost bounds and credential shapes."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import ro_evidence as evidence
import ro_settings as rs
from conftest import SCRIPTS
from test_ro_evidence import EvidenceProject, commit_content, git, refs, secret


BENIGN_CODE = [
    "password = self.config.password",
    "secret = settings.SECRET",
    "password = getpass.getpass()",
    "api_key = os.environ['API_KEY']",
    'password = os.environ.get("DB_PASSWORD")',
    "access_token = response.json()['access_token']",
    "secret = SECRET_KEY_FOR_PRODUCTION_2024",
    "api_key = load_api_key_from_vault_2024",
    'password: "${DB_PASSWORD}"',
    'password = "{password}"',
    "password = '<your password here>'",
    'API_KEY = "xxxxxxxxxxxxxxxxxxxx"',
    'secret = "changeme-please"',
    "if password == confirmation_password_field:",
    "def check_password(password, hashed_password_value):",
    "token = request.headers['Authorization']",
    "password_hash = hashlib.sha256(password.encode()).hexdigest()",
    "secret_name = f'{prefix}-secret-{index}'",
    "# Set the access_token: field in config.yaml before running.",
    'kwargs["password"] = password',
]

CREDENTIALS = [
    'password = "hunter2-staging"',
    'db_password: "Pa55word-for-prod"',
    '"api_key": "abcd1234efgh5678"',
    "API_KEY=AbCd1234EfGh5678IjKl90",
    "access_token=" + "A1" * 12,
    "secret: " + "0123456789abcdef" * 2,
    "token " + "ghp_" + "a1B2" * 6,
]


def test_benign_source_code_idioms_are_not_credentials(tmp_path):
    patterns = evidence._patterns(EvidenceProject(tmp_path))
    matched = [line for line in BENIGN_CODE if any(pattern.search(line) for pattern in patterns)]
    assert matched == []


def test_secret_shaped_values_are_credentials(tmp_path):
    patterns = evidence._patterns(EvidenceProject(tmp_path))
    missed = [line for line in CREDENTIALS if not any(pattern.search(line) for pattern in patterns)]
    assert missed == []


@pytest.fixture
def repo(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git is unavailable")
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "tag.gpgSign", "false")
    (root / "content.txt").write_text("clean\n", encoding="utf-8")
    git(root, "add", "content.txt")
    git(root, "commit", "-m", "initial")
    return EvidenceProject(root), git(root, "rev-parse", "HEAD")


def tag_refs(name, oid):
    return f"refs/tags/{name} {oid} refs/tags/{name} {'0' * 40}\n"


def test_annotated_tag_messages_are_scanned_including_nested_tags(repo):
    project, base = repo
    git(project.root, "tag", "-a", "clean-tag", "-m", "release notes")
    assert evidence.scan_publish(project, tag_refs("clean-tag", git(project.root, "rev-parse", "clean-tag")),
                                 remote="origin") == []
    git(project.root, "tag", "-a", "inner", "-m", "token " + secret())
    git(project.root, "tag", "-a", "outer", "inner", "-m", "wrapper")
    outer = git(project.root, "rev-parse", "outer")
    findings = evidence.scan_publish(project, tag_refs("outer", outer))
    inner = git(project.root, "rev-parse", "inner")
    assert any("annotated tag " + inner[:12] in finding for finding in findings)
    assert secret() not in "\n".join(findings)


def test_tag_of_a_non_commit_object_scans_its_target(repo):
    project, _ = repo
    blob = subprocess.run(["git", "-C", str(project.root), "hash-object", "-w", "--stdin"], input=secret().encode(),
                          capture_output=True, check=True).stdout.decode().strip()
    git(project.root, "tag", "-a", "blob-tag", blob, "-m", "a tagged blob")
    findings = evidence.scan_publish(project, tag_refs("blob-tag", git(project.root, "rev-parse", "blob-tag")))
    assert any("blob " + blob[:12] in finding for finding in findings)


def test_tracking_refs_never_exclude_outgoing_history(repo):
    project, base = repo
    leaked = commit_content(project, secret())
    git(project.root, "update-ref", "refs/remotes/origin/main", leaked)
    tip = commit_content(project, "clean again\n")
    new_branch = f"refs/heads/topic {tip} refs/heads/topic {'0' * 40}\n"
    # A name, URL or local tracking ref cannot establish the destination's history.
    for remote in ("origin", "public", None, "https://example.invalid/repo.git", "*"):
        assert evidence.scan_publish(project, new_branch, remote=remote), remote


def test_pre_push_destination_tip_still_excludes_already_published_history(repo):
    project, _ = repo
    published = commit_content(project, secret())
    tip = commit_content(project, "clean again\n")
    # The destination tip supplied by Git is sufficient even without tracking refs.
    assert evidence.scan_publish(project, refs(tip, published), remote="origin") == []


@pytest.mark.parametrize("configuration", ["separate-push-url", "retargeted-remote"])
def test_private_tracking_history_is_scanned_at_actual_push_destination(tmp_path, repo, configuration):
    project, _ = repo
    source, destination = tmp_path / "source.git", tmp_path / "destination.git"
    for bare in (source, destination):
        git(tmp_path, "init", "--bare", str(bare))
    leaked = commit_content(project, secret())
    tip = commit_content(project, "clean again\n")
    git(project.root, "push", str(source), "main")
    git(project.root, "remote", "add", "origin", str(source))
    git(project.root, "fetch", "origin")
    if configuration == "separate-push-url":
        git(project.root, "remote", "set-url", "--push", "origin", str(destination))
        assert git(project.root, "remote", "get-url", "origin") == str(source)
    else:
        git(project.root, "remote", "set-url", "origin", str(destination))
    assert git(project.root, "remote", "get-url", "--push", "origin") == str(destination)
    assert git(project.root, "rev-parse", "refs/remotes/origin/main") == tip
    assert git(project.root, "ls-remote", "--heads", str(destination)) == ""
    findings = evidence.scan_publish(project, refs(tip, "0" * 40), remote="origin")
    assert any(f"(commit {leaked[:12]})" in finding for finding in findings)
    assert secret() not in "\n".join(findings)

    _install_pre_push_gate(project)
    pushed = subprocess.run(["git", "-C", str(project.root), "push", "origin", "main"],
                            capture_output=True, text=True)
    diagnostic = pushed.stdout + pushed.stderr
    assert pushed.returncode != 0 and "publish.scan" in diagnostic
    assert secret() not in diagnostic
    assert git(project.root, "ls-remote", "--heads", str(destination)) == ""


def test_outgoing_findings_name_path_line_and_commit_without_content(repo):
    project, base = repo
    text = "".join(f"line {number}\n" for number in range(1, 200000)) + "key " + secret() + "\n"
    tip = commit_content(project, text)
    findings = evidence.scan_publish(project, refs(tip, base))
    assert findings == [f"publish.scan: outgoing content matched at content.txt:200000 (commit {tip[:12]}); "
                        "content redacted"]


def test_staged_findings_name_path_and_line(repo):
    project, _ = repo
    (project.root / "content.txt").write_text("clean\nsecond\nkey " + secret() + "\n", encoding="utf-8")
    git(project.root, "add", "content.txt")
    assert evidence.scan_publish(project) == ["publish.scan: staged content matched at content.txt:3; content redacted"]


def test_matching_file_names_are_never_printed(repo):
    project, base = repo
    (project.root / secret()).write_text("token " + secret(), encoding="utf-8")
    git(project.root, "add", secret())
    git(project.root, "commit", "-m", "named")
    findings = evidence.scan_publish(project, refs(git(project.root, "rev-parse", "HEAD"), base))
    assert len(findings) == 2 and secret() not in "\n".join(findings)


def test_clean_objects_are_cached_per_pattern_set(repo, monkeypatch):
    project, base = repo
    tip = commit_content(project, "clean again\n")
    assert evidence.scan_publish(project, refs(tip, base)) == []
    read = []
    original = evidence._Batch.read
    monkeypatch.setattr(evidence._Batch, "read", lambda self, oid: (read.append(oid), original(self, oid))[1])
    assert evidence.scan_publish(project, refs(tip, base)) == []
    assert read == []
    project.values["publish_scan"] = "secrets; literal:clean again"
    assert evidence.scan_publish(project, refs(tip, base))
    assert read  # A different pattern set never reuses the clean set.


def test_pre_push_deadline_is_configurable_and_bounded(repo, monkeypatch):
    project, base = repo
    assert rs.normalize("publish_scan", "secrets; deadline=2m", {}) == "secrets; deadline=2m"
    for invalid in ("deadline=0s", "deadline=61m", "deadline=soon"):
        with pytest.raises(ValueError, match="deadline"):
            rs.normalize("publish_scan", "secrets; " + invalid, {})
    project.values["publish_scan"] = "secrets; deadline=2m"
    assert evidence._scan_settings(project)[1] == 120
    tip = commit_content(project, "clean again\n")
    project.values["publish_scan"] = "secrets"
    now = [100.0]
    monkeypatch.setattr(evidence.time, "monotonic", lambda: now[0])

    def slow(patterns, chunks):
        now[0] += 1000
        evidence._remaining()
    monkeypatch.setattr(evidence, "first_match", slow)
    count = len(git(project.root, "rev-list", "--objects", tip, "--not", base, "--").splitlines())
    seconds = evidence._scan_settings(project, count)[1]
    import math
    with pytest.raises(ValueError, match=rf"{count} outgoing objects.*deadline={math.ceil(seconds * 2)}s"):
        evidence.scan_publish(project, refs(tip, base))
    assert evidence._SCAN_PROGRESS.get() is None
    assert evidence._SCAN_DEADLINE.get() is None


def test_default_deadline_scales_by_outgoing_count_but_explicit_value_wins(repo):
    project, _ = repo
    assert evidence._scan_settings(project, 0)[1] == 60
    assert evidence._scan_settings(project, 1000)[1] == 110
    assert evidence._scan_settings(project, 1_000_000)[1] == 3600
    project.values["publish_scan"] = "secrets; deadline=2m"
    assert evidence._scan_settings(project, 1000)[1] == 120


@pytest.mark.parametrize("setting", ["secrets", "secrets; deadline=2m"])
def test_enumerated_object_count_sets_batch_deadline(repo, monkeypatch, setting):
    project, base = repo
    project.values["publish_scan"] = setting
    tip = commit_content(project, "clean again\n")
    count = len(git(project.root, "rev-list", "--objects", tip, "--not", base, "--").splitlines())
    monkeypatch.setattr(evidence.time, "monotonic", lambda: 100.0)
    original = evidence._Batch.__init__
    observed = []

    def capture(self, project, oids):
        observed.append(evidence._remaining())
        return original(self, project, oids)
    monkeypatch.setattr(evidence._Batch, "__init__", capture)
    assert evidence.scan_publish(project, refs(tip, base)) == []
    assert observed == pytest.approx([evidence._scan_settings(project, count)[1]])


def test_enumeration_timeout_does_not_invent_an_object_count(repo, monkeypatch):
    project, base = repo
    tip = commit_content(project, "clean again\n")

    def timeout(*args):
        raise ValueError("publish scan deadline exceeded running git")
    monkeypatch.setattr(evidence, "_git", timeout)
    with pytest.raises(ValueError, match="object count unavailable.*deadline=120s"):
        evidence.scan_publish(project, refs(tip, base))


def _install_pre_push_gate(project):
    (project.root / "agents.md").write_text("# Probe — Agent Rules\n\n## Project settings\n- Enforcement: block\n"
                                            "- Block: publish.scan\n- Publish scan: secrets\n", encoding="utf-8")
    hook = project.root / ".git" / "hooks" / "pre-push"
    hook.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{(SCRIPTS / "ro.py").as_posix()}" '
                    'hook pre-push --remote "$1"\n', encoding="utf-8", newline="\n")
    hook.chmod(0o755)


def test_pre_push_hook_refuses_annotated_tag_with_credential_through_local_remote(tmp_path, repo):
    project, _ = repo
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    _install_pre_push_gate(project)
    git(project.root, "remote", "add", "origin", str(remote))
    git(project.root, "push", "origin", "main")
    git(project.root, "tag", "-a", "release", "-m", "token " + secret())
    pushed = subprocess.run(["git", "-C", str(project.root), "push", "origin", "release"], capture_output=True, text=True)
    assert pushed.returncode != 0 and "annotated tag" in pushed.stdout + pushed.stderr
    git(project.root, "tag", "-a", "clean", "-m", "notes")
    assert subprocess.run(["git", "-C", str(project.root), "push", "origin", "clean"],
                          capture_output=True).returncode == 0
