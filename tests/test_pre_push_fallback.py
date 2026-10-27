"""Interpreter recovery cannot turn a publication denial into an allowed push."""

import importlib.util
import io
import json
from types import SimpleNamespace

import pytest

from conftest import ROOT


@pytest.fixture
def dispatcher():
    spec = importlib.util.spec_from_file_location("pre_push_dispatch", ROOT / "hooks/ro-pre-push.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("working", ["registered", "override", "python3", "python", "py"])
def test_interpreter_fallback_order_and_exact_input(dispatcher, monkeypatch, working):
    monkeypatch.setenv("RO_HOOK_PYTHON", "override")
    attempts, scans = [], []
    refs = b"refs/heads/main abc refs/heads/main def\r\n"

    def run(argv, **kwargs):
        if "-c" in argv:
            attempts.append(argv[0])
            if argv[0] != working:
                raise FileNotFoundError()
            return SimpleNamespace(returncode=0)
        scans.append((argv, kwargs))
        return SimpleNamespace(returncode=17)

    monkeypatch.setattr(dispatcher.subprocess, "run", run)
    assert dispatcher.dispatch({"python": "registered", "runtime": "runtime.py"}, "origin", refs, 0) == 17
    order = ["registered", "override", "python3", "python", "py"]
    assert attempts == order[:order.index(working) + 1]
    assert len(scans) == 1
    argv, kwargs = scans[0]
    assert kwargs["input"] == refs
    assert argv[-5:] == ["runtime.py", "hook", "pre-push", "--remote", "origin"]
    if working == "py":
        assert argv[:2] == ["py", "-3"]


def test_no_usable_interpreter_fails_closed(dispatcher, monkeypatch, capsys):
    monkeypatch.delenv("RO_HOOK_PYTHON", raising=False)
    attempts = []

    def unavailable(argv, **kwargs):
        attempts.append(argv[0])
        return SimpleNamespace(returncode=1)  # Installed aliases/old interpreters.

    monkeypatch.setattr(dispatcher.subprocess, "run", unavailable)
    assert dispatcher.dispatch({"python": "gone", "runtime": "runtime.py"}, "", b"", 0) == 1
    assert attempts == ["gone", "python3", "python", "py"]
    assert "no working Python 3.12+ interpreter" in capsys.readouterr().err


def test_scanner_error_is_final(dispatcher, monkeypatch):
    monkeypatch.setenv("RO_HOOK_PYTHON", "override")
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0 if "-c" in argv else 1)

    monkeypatch.setattr(dispatcher.subprocess, "run", run)
    assert dispatcher.dispatch({"python": "registered", "runtime": "missing.py"}, "", b"", 0) == 1
    assert len(calls) == 2
    assert all(argv[0] == "registered" for argv in calls)


@pytest.mark.parametrize("evidence", ["marker", "legacy-runtime", "legacy-nested-registration",
                                      "nested-separate-repository", "unrelated", "none"])
def test_missing_registration_requires_evidence_before_shared_hook_pass_through(
        dispatcher, monkeypatch, tmp_path, capsys, evidence):
    root = tmp_path / "repository"
    root.mkdir()
    gitdir = tmp_path / "git-metadata"
    gitdir.mkdir()
    registrations = tmp_path / "shared-hooks/research-orchestrator/registrations"
    registrations.mkdir(parents=True)
    if evidence == "marker":
        (gitdir / "research-orchestrator-pre-push").write_text(str(root), encoding="utf-8")
    elif evidence == "legacy-runtime":
        runtime = root / ".codex/skills/research-orchestrator/scripts/ro.py"
        runtime.parent.mkdir(parents=True)
        runtime.touch()
    elif evidence in {"legacy-nested-registration", "nested-separate-repository", "unrelated"}:
        scope = tmp_path / "other" if evidence == "unrelated" else root / "component"
        (registrations / "older.json").write_text(json.dumps({"scope": str(scope)}), encoding="utf-8")

    def git(argv, **kwargs):
        if argv[:2] == ["git", "-C"]:
            owner = scope if evidence == "nested-separate-repository" else root
            return SimpleNamespace(stdout=str(owner))
        assert argv[:2] == ["git", "rev-parse"]
        return SimpleNamespace(stdout=str(root if argv[-1] == "--show-toplevel" else gitdir))

    monkeypatch.setattr(dispatcher.subprocess, "run", git)
    monkeypatch.setattr(dispatcher, "__file__", str(registrations.parent / "pre-push.py"))
    monkeypatch.setattr(dispatcher.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"exact refs\n")))
    monkeypatch.setattr(dispatcher, "dispatch", lambda *args: pytest.fail("missing registration reached scanner"))
    expected = evidence not in {"none", "unrelated", "nested-separate-repository"}
    assert dispatcher.main() == int(expected)
    message = capsys.readouterr().err
    if expected:
        assert "repository root" in message and "install.py --project ." in message
    else:
        assert not message
