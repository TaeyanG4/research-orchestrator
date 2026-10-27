"""Configuration and cleanup checks with no Codex sessions or credential access."""

import json
import os
from pathlib import Path
import stat

import pytest

from scripts.evals import isolation, run_evals as runner


def test_model_projection_never_opens_auth_or_copies_instructions(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        'model = "base-model"\nprofile = "eval"\ndeveloper_instructions = "leak"\n'
        '[profiles.eval]\nmodel = "profile-model"\nmodel_provider = "custom"\n'
        '[model_providers.custom]\nname = "Custom"\nbase_url = "https://example.invalid/v1"\n'
        'env_key = "EVAL_API_KEY"\nexperimental_bearer_token = "never-copy"\n', encoding="utf-8")
    original = Path.open
    opened = []

    def guarded_open(path, *args, **kwargs):
        assert path == tmp_path / "config.toml"
        opened.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    settings = isolation.configured_model_settings()
    assert opened == ["config.toml"]
    assert settings["model"] == "profile-model"
    command = isolation.config_arguments(settings)
    assert 'model="profile-model"' in command and "--model" not in command
    assert "never-copy" not in str(command) and "leak" not in str(command)
    assert settings["model_providers"]["custom"]["env_key"] == "EVAL_API_KEY"


@pytest.mark.parametrize("explicit_homes", [False, True])
def test_host_homes_and_sandbox_state_survive_without_host_routing(tmp_path, monkeypatch, explicit_homes):
    home = tmp_path / "host-home"
    codex_home = home / ".codex"
    for name in (".sandbox", ".sandbox-bin", ".sandbox-secrets"):
        (codex_home / name).mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    for key, value in {"CODEX_HOME": codex_home, "HOME": home, "USERPROFILE": home}.items():
        if explicit_homes:
            monkeypatch.setenv(key, str(value))
        else:
            monkeypatch.delenv(key, raising=False)
    inherited = {key: os.environ.get(key) for key in ("CODEX_HOME", "HOME", "USERPROFILE")}
    root = tmp_path / "run"
    project = root / "project"
    project.mkdir(parents=True)
    monkeypatch.setenv("CODEX_THREAD_ID", "host-session")
    monkeypatch.setenv("PYTHONPATH", "host-python-path")
    monkeypatch.setenv("CODEX_API_KEY", "synthetic-env-auth")
    environment, metadata = isolation.prepare_environment(root, project, {})
    assert "CODEX_THREAD_ID" not in environment and "PYTHONPATH" not in environment
    assert environment["CODEX_API_KEY"] == "synthetic-env-auth"
    assert environment["TMP"] == environment["TEMP"] == environment["TMPDIR"]
    assert Path(environment["TMP"]).is_relative_to(project)
    assert {key: environment.get(key) for key in inherited} == inherited
    assert all(key in environment for key in inherited) == explicit_homes
    assert Path(environment["RESEARCH_ORCHESTRATOR_HOME"]).is_relative_to(project)
    assert metadata["writable_roots"] == [str(project)]
    assert metadata["fresh_codex_home"] is metadata["fresh_user_home"] is False
    # Host roots are recorded resolved (8.3 short names, /var -> /private/var).
    assert metadata["host_context"]["codex_home"] == str(codex_home.resolve())
    assert {path.name for path in root.iterdir()} == {"project"}
    assert isolation.cleanup(root) == []
    assert all((codex_home / name).is_dir() for name in (".sandbox", ".sandbox-bin", ".sandbox-secrets"))


@pytest.mark.parametrize("contents", [None, b"", b"Synthetic global instructions"])
def test_global_agents_snapshot_uses_only_size_and_real_home_roots(tmp_path, monkeypatch, contents):
    home = tmp_path / "real-home"
    codex_home = tmp_path / "custom-codex-home"
    codex_home.mkdir()
    agents = codex_home / "AGENTS.md"
    if contents is not None:
        agents.write_bytes(contents)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    def unexpected(*args, **kwargs):
        pytest.fail("Host instruction and credential contents must not be opened")

    monkeypatch.setattr(Path, "open", unexpected)
    project = tmp_path / "project"
    project.mkdir()
    _, metadata = isolation.prepare_environment(tmp_path, project, {})
    context = metadata["host_context"]
    # Real home roots are recorded resolved (8.3 short names, /var -> /private/var).
    assert context["global_agents"] == {
        "path": str(agents.resolve()), "exists": contents is not None,
        "size_bytes": len(contents) if contents is not None else None,
        "empty": contents == b"" if contents is not None else None,
    }
    assert context["installed_skill_roots"] == [
        str(home.resolve() / name / "skills") for name in (".codex", ".agents", ".claude")
    ] + [str(codex_home.resolve() / "skills")]


@pytest.mark.parametrize("backend", ["elevated", "unelevated", "mxc"])
def test_windows_execution_backend_survives_isolation_without_host_permissions(tmp_path, monkeypatch, backend):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        'sandbox_mode = "danger-full-access"\napproval_policy = "on-request"\n'
        '[windows]\nsandbox = "' + backend + '"\nprivate_desktop = false\n'
        '[sandbox_workspace_write]\nwritable_roots = ["/host"]\nnetwork_access = true\n', encoding="utf-8")
    settings = isolation.configured_model_settings()
    assert settings == {"windows": {"sandbox": backend}}
    command = isolation.config_arguments(settings)
    assert f'windows.sandbox="{backend}"' in command
    assert 'approval_policy="never"' in command
    assert 'sandbox_workspace_write.writable_roots=[]' in command
    assert 'sandbox_workspace_write.network_access=false' in command
    assert not any("danger-full-access" in value or "private_desktop" in value or "/host" in value for value in command)


def test_provider_key_and_auth_variable_survive_isolation(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    settings = {"model_providers": {"custom-provider": {"env_key": "CODEX_EVAL_AUTH"}}}
    monkeypatch.setenv("CODEX_EVAL_AUTH", "synthetic-auth")
    monkeypatch.setenv("CODEX_THREAD_ID", "host-session")
    environment, _ = isolation.prepare_environment(tmp_path, project, settings)
    assert environment["CODEX_EVAL_AUTH"] == "synthetic-auth"
    assert "CODEX_THREAD_ID" not in environment
    assert 'model_providers.custom-provider.env_key="CODEX_EVAL_AUTH"' in isolation.config_arguments(settings)


def test_cleanup_removes_read_only_ro_and_runtime(tmp_path):
    root = tmp_path / "run"
    for name in ("project/.ro/record", "skill/references/readme.md"):
        path = root / name
        path.parent.mkdir(parents=True)
        path.write_text("record", encoding="utf-8")
        path.chmod(stat.S_IREAD)
        path.parent.chmod(stat.S_IREAD | stat.S_IEXEC)
    assert isolation.cleanup(root) == []
    assert not root.exists()


@pytest.mark.parametrize("failures", [1, 3])
def test_cleanup_retries_and_reports_locks_without_raising(tmp_path, monkeypatch, failures):
    root = tmp_path / "run"
    root.mkdir()
    original = isolation.shutil.rmtree
    attempts = []

    def transient(path, **kwargs):
        attempts.append(path)
        if len(attempts) <= failures:
            raise PermissionError("access denied: .ro")
        original(path, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(isolation.shutil, "rmtree", transient)
        patch.setattr(isolation.time, "sleep", lambda duration: None)
        problems = isolation.cleanup(root)
    assert len(attempts) == min(failures + 1, 3)
    assert "access denied" in problems[0]
    assert root.exists() == (failures == 3)
    if root.exists():
        assert "Temporary directory remains" in problems[-1]
        original(root)


def test_model_resolution_accepts_session_metadata_not_generated_claims():
    assert runner.resolved_model(json.dumps({"type": "thread.started", "model": "resolved"})) == "resolved"
    assert runner.resolved_model(json.dumps({"type": "item.completed", "model": "invented"})) is None
    assert runner.resolved_model("", "model: configured\n") == "configured"
    assert runner.resolved_model("{}") is None
