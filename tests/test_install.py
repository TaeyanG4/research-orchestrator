"""install.py: user and project scopes, idempotence, backups instead of deletion, and dry runs."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import shlex
from types import SimpleNamespace

import pytest

from conftest import ROOT, make_project
import ro
from ro_state import Project

SPEC = importlib.util.spec_from_file_location("ro_install", ROOT / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A private home; the real one is never read or written."""
    class FixedDateTime(installer.dt.datetime):
        @classmethod
        def now(cls):
            return cls(2026, 10, 27, 12, 0)

    monkeypatch.setattr(installer, "dt", SimpleNamespace(datetime=FixedDateTime))
    folder = tmp_path / "home"
    folder.mkdir()
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(folder))
    return folder


def install(*args: str) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert installer.main(list(args)) == 0
    return output.getvalue()


def snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.parametrize("options", [[], ["--dry-run"], ["--no-hooks"], ["--shim-only"],
                                    ["--remove-hooks"], ["--uninstall"]])
def test_nested_git_project_is_refused_before_any_installer_writes(home, tmp_path, options):
    project = tmp_path / "repository"
    nested = project / "packages/component"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    (nested / "keep.txt").write_text("existing data\n", encoding="utf-8")
    before = snapshot(project), snapshot(home)
    with pytest.raises(SystemExit) as refusal:
        installer.main(["--home", str(home), "--project", str(nested), *options])
    message = str(refusal.value)
    assert "repository root" in message and "install.py --project ." in message
    # The installer reports the resolved root (8.3 short names, /var -> /private/var).
    assert project.resolve().as_posix() in message.replace("\\", "/")
    assert (snapshot(project), snapshot(home)) == before


def test_root_installed_gate_denies_forbidden_content_in_outgoing_history(home, tmp_path):
    project = make_project(tmp_path, "publication", "--preset", "quick", "--user", "operator")
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    (project / "agents.md").write_text("# Agent rules\n\n## Project settings\n- Enforcement: block\n"
                                        "- Block: publish.scan\n- Publish scan: secrets\n", encoding="utf-8")
    content = project / "payload.txt"
    secret = "ghp_" + "a1B2" * 6
    commits = []
    for text in ("clean\n", "token " + secret + "\n", "clean again\n"):
        content.write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(project), "add", "payload.txt"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(project), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgSign=false",
                        "commit", "-qm", "fixture content"], check=True, capture_output=True)
        commits.append(subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"],
                                      check=True, capture_output=True, text=True).stdout.strip())
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    refs = f"refs/heads/main {commits[-1]} refs/heads/main {commits[0]}\n"
    result = subprocess.run([shutil.which("sh"), ".git/hooks/pre-push", "origin"],
                            cwd=project, input=refs, text=True, capture_output=True, timeout=15)
    assert result.returncode == 1, (result.stdout, result.stderr)
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "payload.txt" in output["permissionDecisionReason"]
    assert commits[1][:12] in output["permissionDecisionReason"]
    assert secret not in result.stdout + result.stderr


@pytest.mark.parametrize("layout", ["ordinary", "linked-worktree", "shared-hooks-path"])
def test_lost_gate_registration_fails_closed_until_explicit_uninstall(home, tmp_path, layout):
    project = tmp_path / "repository"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    hookdir = project / ".git/hooks"
    if layout == "linked-worktree":
        subprocess.run(["git", "-C", str(project), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgSign=false",
                        "commit", "--allow-empty", "-qm", "fixture"], check=True, capture_output=True)
        linked = tmp_path / "linked"
        subprocess.run(["git", "-C", str(project), "worktree", "add", "-qb", "linked", str(linked)],
                       check=True, capture_output=True)
        project = linked
    elif layout == "shared-hooks-path":
        hookdir = tmp_path / "shared-hooks"
        subprocess.run(["git", "-C", str(project), "config", "core.hooksPath", str(hookdir)],
                       check=True, capture_output=True)
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    next((hookdir / "research-orchestrator/registrations").glob("*.json")).unlink()
    # Losing the runtime too must not erase the expectation that scanning is required.
    (project / ".claude/skills/research-orchestrator/scripts/ro.py").unlink()
    result = subprocess.run([shutil.which("sh"), (hookdir / "pre-push").as_posix(), "origin"],
                            cwd=project, input="", text=True, capture_output=True, timeout=15)
    assert result.returncode != 0
    assert "registration" in result.stderr and "install.py --project ." in result.stderr
    install("--home", str(home), "--project", str(project), "--host", "claude-code", "--uninstall")
    result = subprocess.run([shutil.which("sh"), (hookdir / "pre-push").as_posix(), "origin"],
                            cwd=project, input="", text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_hooks_only_removal_preserves_skill_git_gate_and_foreign_hooks(home, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", str(project)], check=True, capture_output=True)
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    skill = project / ".claude/skills/research-orchestrator"
    before = snapshot(skill)
    gate = project / ".git/hooks/pre-push"
    gate_before = gate.read_bytes()
    settings = project / ".claude/settings.json"
    document = json.loads(settings.read_text(encoding="utf-8"))
    document["hooks"]["Stop"].append({"hooks": [{"command": "unrelated-check", "type": "command"}]})
    settings.write_text(json.dumps(document), encoding="utf-8")
    install("--home", str(home), "--project", str(project), "--host", "claude-code", "--remove-hooks")
    assert snapshot(skill) == before and gate.read_bytes() == gate_before
    assert commands(json.loads(settings.read_text(encoding="utf-8"))) == ["unrelated-check"]


def test_install_then_active_plugin_keeps_exactly_one_registration(home):
    install("--home", str(home), "--host", "claude-code")
    settings = home / ".claude/settings.json"
    document = json.loads(settings.read_text(encoding="utf-8"))
    document["enabledPlugins"] = {"research-orchestrator@research-orchestrator": True}
    settings.write_text(json.dumps(document), encoding="utf-8")
    output = install("--home", str(home), "--host", "claude-code")
    result = json.loads(settings.read_text(encoding="utf-8"))
    assert result["enabledPlugins"] == document["enabledPlugins"]
    assert commands(result) == []
    assert "active plugin supplies hooks" in output
    assert (home / ".claude/skills/research-orchestrator/SKILL.md").exists()


def test_declared_python_minimum_matches_ci_and_runtime_features():
    import ast
    assert installer.MIN_PYTHON == (3, 12)
    installer.require_python((3, 12))
    with pytest.raises(SystemExit, match=r"Python 3\.12\+"):
        installer.require_python((3, 11))
    assert "Python 3.12+" in installer.parser().format_help()
    for path in ROOT.glob("README*.md"):
        assert "Python 3.12+" in path.read_text(encoding="utf-8")
    assert '3.12' in (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    # Parse every shipped source with the declared grammar; the two known runtime
    # feature floors remain covered by an executing 3.12 interpreter in CI.
    for path in (ROOT / "skills/research-orchestrator/scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), feature_version=installer.MIN_PYTHON)
    assert hasattr(Path, "is_junction")
    from re import _parser
    assert _parser.parse("a", 0)


def commands(document: dict) -> list[str]:
    return [hook["command"] for entries in document["hooks"].values() for entry in entries for hook in entry["hooks"]]


def test_user_install_copies_skill_and_wires_absolute_hooks_for_both_hosts(home):
    output = install("--home", str(home))
    skills = [home / ".claude/skills/research-orchestrator", home / ".codex/skills/research-orchestrator",
              home / ".agents/skills/research-orchestrator"]
    for skill in skills:
        assert (skill / "SKILL.md").is_file() and (skill / "scripts/ro_hook_runner.py").is_file()
        assert (skill / "hooks/ro-hook.sh").is_file() and (skill / "hooks/ro-hook.cmd").is_file()
        assert not (skill / "evals").exists()
    claude = json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))
    assert set(claude["hooks"]) == {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
    assert all(shlex.split(command)[:2] == ['sh', skills[0].resolve().as_posix() + '/hooks/ro-hook.sh']
               for command in commands(claude))
    codex = json.loads((home / ".codex/hooks.json").read_text(encoding="utf-8"))
    assert all(f'{skills[1].resolve().as_posix()}/hooks/ro-hook.' in command for command in commands(codex))
    assert "/hooks" in output and "trust" in output


def test_reinstall_is_idempotent_and_keeps_foreign_hooks_with_a_backup(home):
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    foreign = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-linter"}]}
    settings.write_text(json.dumps({"model": "x", "hooks": {"PreToolUse": [foreign]}}), encoding="utf-8")
    original = settings.read_text(encoding="utf-8")
    install("--home", str(home), "--host", "claude-code")
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["model"] == "x" and merged["hooks"]["PreToolUse"][0] == foreign
    assert [entry["matcher"] for entry in merged["hooks"]["PreToolUse"]] == [
        "Bash", "Bash|PowerShell", "Edit|Write|NotebookEdit", "AskUserQuestion", "Agent"]
    backups = list(settings.parent.glob("settings.json.bak-*"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == original
    before = snapshot(home)
    output = install("--home", str(home), "--host", "claude-code")
    assert snapshot(home) == before
    assert "skill unchanged" in output and "hooks unchanged" in output


def test_old_name_install_and_changed_install_move_to_backups_never_deleted(home):
    old = home / ".claude/skills" / installer.OLD_NAME
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text("old skill\n", encoding="utf-8")
    settings = home / ".claude/settings.json"
    stale = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": f'sh "{old.as_posix()}/hooks/ro-hook.sh" Stop'}]}]}}
    settings.write_text(json.dumps(stale), encoding="utf-8")
    install("--home", str(home), "--host", "claude-code")
    assert not old.exists()
    backups = home / ".claude/research-orchestrator-backups"
    moved = list(backups.glob(f"{installer.OLD_NAME}-*"))
    assert len(moved) == 1 and (moved[0] / "SKILL.md").read_text(encoding="utf-8") == "old skill\n"
    assert not any(f"{installer.OLD_NAME}/hooks" in command
                   for command in commands(json.loads(settings.read_text(encoding="utf-8"))))
    installed = home / ".claude/skills/research-orchestrator"
    (installed / "local-note.txt").write_text("changed\n", encoding="utf-8")
    install("--home", str(home), "--host", "claude-code")
    assert any((path / "local-note.txt").is_file() for path in backups.glob("research-orchestrator-2*"))
    assert not (installed / "local-note.txt").exists()


def test_dry_run_changes_nothing(home):
    (home / ".claude").mkdir()
    (home / ".claude/settings.json").write_text('{"hooks": {}}', encoding="utf-8")
    before = snapshot(home)
    output = install("--home", str(home), "--dry-run")
    assert snapshot(home) == before
    assert "[dry-run] install skill" in output and "[dry-run] merge" in output


def test_uninstall_removes_only_own_hooks_and_backs_up_the_skill(home):
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    foreign = {"matcher": "Edit", "hooks": [{"type": "command", "command": "formatter"}]}
    settings.write_text(json.dumps({"hooks": {"PostToolUse": [foreign]}}), encoding="utf-8")
    install("--home", str(home))
    install("--home", str(home), "--uninstall")
    assert json.loads(settings.read_text(encoding="utf-8")) == {"hooks": {"PostToolUse": [foreign]}}
    assert json.loads((home / ".codex/hooks.json").read_text(encoding="utf-8")) == {"hooks": {}}
    for root in (".claude", ".codex", ".agents"):
        assert not (home / root / "skills/research-orchestrator").exists()
        assert list((home / root / "research-orchestrator-backups").glob("research-orchestrator-*"))


def test_invalid_settings_json_is_never_overwritten(home):
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="not valid JSON"):
        install("--home", str(home), "--host", "claude-code")
    assert settings.read_text(encoding="utf-8") == "{not json"


def test_multiple_settings_changes_preserve_every_backup(home):
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    original = '{"hooks": {}}'
    settings.write_text(original, encoding="utf-8")
    install("--home", str(home), "--host", "claude-code")
    installed = settings.read_bytes()
    install("--home", str(home), "--host", "claude-code", "--uninstall")
    backups = [path.read_bytes() for path in settings.parent.glob("settings.json.bak-*")]
    assert len(backups) == 2
    assert original.encode() in backups and installed in backups


def test_project_install_is_portable_and_preserves_a_foreign_pre_push_gate(tmp_path, home):
    if not shutil.which("git"):
        pytest.skip("git is unavailable")
    project = tmp_path / "team-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    foreign = project / ".git/hooks/pre-push"
    foreign.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    output = install("--project", str(project), "--home", str(home))
    assert (project / ".claude/skills/research-orchestrator/SKILL.md").is_file()
    assert (project / ".agents/skills/research-orchestrator/SKILL.md").is_file()
    assert (project / ".codex/skills/research-orchestrator/SKILL.md").is_file()
    claude = json.loads((project / ".claude/settings.json").read_text(encoding="utf-8"))
    assert all("${CLAUDE_PROJECT_DIR}/.claude/skills/research-orchestrator/hooks/ro-hook.sh" in command
               for command in commands(claude))
    codex = json.loads((project / ".codex/hooks.json").read_text(encoding="utf-8"))
    assert commands(codex)
    gate = foreign.read_text(encoding="utf-8")
    assert gate == "#!/bin/sh\necho mine\n"
    assert "Existing pre-push hook left intact" in output and "hooks/pre-push.sample" in output
    saved = list((project / ".ro/research-orchestrator-backups").glob("pre-push-*"))
    assert saved == []
    assert not (home / ".claude").exists()
    before = snapshot(project)
    install("--project", str(project), "--home", str(home))
    assert snapshot(project) == before


def test_installed_wrapper_finds_its_runner(tmp_path, home):
    shell = shutil.which("sh")
    if not shell:
        pytest.skip("a POSIX shell is required")
    install("--home", str(home), "--host", "claude-code", "--no-hooks")
    wrapper = home / ".claude/skills/research-orchestrator/hooks/ro-hook.sh"
    workdir = tmp_path / "no-policy"
    workdir.mkdir()
    payload = json.dumps({"cwd": str(workdir), "tool_name": "Bash", "tool_input": {"command": "echo ready"}})
    result = subprocess.run([shell, wrapper.as_posix(), "PreToolUse"], input=payload.encode(), cwd=workdir,
                            capture_output=True, env={**os.environ, "RO_HOOK_PYTHON": ""})
    assert result.returncode == 0 and json.loads(result.stdout) == {}, result.stderr
    assert not (home / ".claude/settings.json").exists()


def test_plugin_no_hooks_route_provides_cli_and_preserves_host_registration(home):
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    contents = '{"enabledPlugins":{"research-orchestrator@example":true},"hooks":{"Stop":[]}}\n'
    settings.write_text(contents, encoding="utf-8", newline="\n")
    install("--home", str(home), "--host", "claude-code", "--no-hooks")
    assert settings.read_text(encoding="utf-8") == contents
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    assert shim.is_file()
    command = ([os.environ["COMSPEC"], "/d", "/c", str(shim), "--help"] if os.name == "nt" else
               [shutil.which("sh"), shim.as_posix(), "--help"])
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "brief" in result.stdout


def test_plugin_shim_only_uses_checkout_without_copying_skill_or_changing_hooks(home):
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    original = b'{"enabledPlugins":{"research-orchestrator@example":true},"hooks":{"Stop":[]}}\r\n'
    settings.write_bytes(original)
    install("--home", str(home), "--shim-only")
    assert settings.read_bytes() == original
    for host in (".claude", ".codex", ".agents"):
        assert not (home / host / "skills").exists()
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    script = shim.read_text(encoding="utf-8")
    runtime = installer.SOURCE / "scripts/ro.py"
    assert str(runtime.resolve()).replace("\\", "/") in script.replace("\\", "/")
    command = ([os.environ["COMSPEC"], "/d", "/c", str(shim), "--help"] if os.name == "nt" else
               [shutil.which("sh"), shim.as_posix(), "--help"])
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and "Research Orchestrator" in result.stdout, result.stderr
    before = snapshot(home)
    install("--home", str(home), "--shim-only")
    assert snapshot(home) == before


@pytest.mark.parametrize("flag", ["--uninstall", "--remove-hooks", "--no-shim"])
def test_shim_only_conflicting_flags_leave_home_unchanged(home, flag):
    before = snapshot(home)
    with pytest.raises(SystemExit) as result:
        install("--home", str(home), "--shim-only", flag)
    assert result.value.code == 2
    assert snapshot(home) == before


def test_foreign_hook_in_shared_entry_survives_install_and_uninstall(home):
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    foreign = {"type": "command", "command": "formatter"}
    own = {"type": "command", "command": 'sh "/old/research-orchestrator/hooks/ro-hook.sh" Stop'}
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [own, foreign]}]}}), encoding="utf-8")
    install("--home", str(home), "--host", "claude-code")
    assert "formatter" in commands(json.loads(settings.read_text(encoding="utf-8")))
    install("--home", str(home), "--host", "claude-code", "--uninstall")
    assert json.loads(settings.read_text(encoding="utf-8")) == {"hooks": {"Stop": [{"hooks": [foreign]}]}}


def test_brief_says_how_to_install_hooks_before_any_self_test(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: "ro")
    target = make_project(tmp_path, "fresh", "--preset", "quick", "--platforms", "Claude Code", "--user", "operator")
    assert ro.main(["--project", str(target), "--session", "s", "brief"]) == 0
    output = capsys.readouterr().out
    assert "hooks never ran: self-test not recorded" in output
    assert "hooks not installed — run install.py (or the Claude Code plugin)" in output
    Project(target, session="s").write_json("hooks-self-test.json", {"status": "active"})
    assert ro.main(["--project", str(target), "--session", "s", "brief"]) == 0
    assert "install.py" not in capsys.readouterr().out


@pytest.mark.parametrize("removed,survivor", [("claude-code", ".codex"), ("codex", ".claude")])
def test_partial_uninstall_repoints_shared_gate_and_surviving_gate_denies_invalid_refs(home, tmp_path, removed, survivor):
    shell = shutil.which("sh")
    assert shell, "Git's POSIX shell is needed to exercise pre-push"
    project = make_project(tmp_path, "gate-project", "--preset", "quick", "--user", "operator")
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    install("--home", str(home), "--project", str(project))
    install("--home", str(home), "--project", str(project), "--host", removed, "--uninstall")
    gate = project / ".git/hooks/pre-push"
    assert gate.is_file()
    registrations = list((gate.parent / "research-orchestrator/registrations").glob("*.json"))
    assert len(registrations) == 1
    assert survivor + "/skills/research-orchestrator/scripts/ro.py" in registrations[0].read_text(encoding="utf-8")
    # A malformed ref is fail-closed: execution proves the surviving runtime is reachable.
    result = subprocess.run([shell, gate.as_posix(), "origin"], input="malformed refs\n", text=True,
                            cwd=project, capture_output=True, timeout=15)
    output = json.loads(result.stdout)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("suffix", ["dollar-$team", "apostrophe-'quoted", "backtick-`quoted", 'double-"quoted'])
def test_hook_template_paths_are_literal_after_json_parsing(home, tmp_path, suffix):
    args = installer.parser().parse_args(["--home", str(home)])
    setup = installer.Installer(args)
    path = tmp_path / suffix / "skills/research-orchestrator"
    expected = path.resolve().as_posix()
    claude = setup.claude_template(expected)
    codex = setup.codex_template(path)
    for template in (claude, codex):
        for command in commands({"hooks": template}):
            assert shlex.split(command)[1] == expected + "/hooks/ro-hook.sh"
        json.loads(json.dumps(template))
    windows = codex["PreToolUse"][0]["hooks"][0]["commandWindows"]
    assert windows == "& " + installer.literal(expected + "/hooks/ro-hook.cmd", "powershell") + " PreToolUse"


def test_special_character_project_gate_and_hooks_execute_without_path_expansion(home, tmp_path):
    shell = shutil.which("sh")
    assert shell
    project = make_project(tmp_path, "literal-$team-'quote-`tick", "--preset", "quick", "--user", "operator")
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    install("--home", str(home), "--project", str(project), "--host", "codex")
    gate = project / ".git/hooks/pre-push"
    # Git invokes the gate from its repository; a relative argv avoids MSYS's
    # native command-line parsing of apostrophes before the shell reads the gate.
    result = subprocess.run([shell, ".git/hooks/pre-push", "origin"], input="bad\n", text=True,
                            cwd=project, capture_output=True, timeout=15)
    assert result.returncode == 1 and json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    template = json.loads((project / ".codex/hooks.json").read_text(encoding="utf-8"))
    command = template["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    payload = json.dumps({"cwd": str(project), "tool_name": "Bash", "tool_input": {"command": "echo ready"}})
    result = subprocess.run([shell, "-c", command], input=payload, text=True, capture_output=True, cwd=project,
                            env={**os.environ, "RO_HOOK_PYTHON": sys.executable}, timeout=15)
    assert result.returncode == 0 and json.loads(result.stdout) == {}, result.stderr


def test_default_cli_shim_runs_and_repoints_after_partial_uninstall(home, tmp_path):
    home = home / "shim-$team-'quote-`tick"
    home.mkdir()
    install("--home", str(home))
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    assert shim.is_file()
    install("--home", str(home), "--host", "claude-code", "--uninstall")
    assert ".codex" in shim.read_text(encoding="utf-8")
    command = ([os.environ["COMSPEC"], "/d", "/c", str(shim), "--help"] if os.name == "nt" else
               [shutil.which("sh"), shim.as_posix(), "--help"])
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and "Research Orchestrator" in result.stdout, result.stderr
    install("--home", str(home), "--host", "codex", "--uninstall")
    assert not shim.exists()


def test_cli_shim_opt_out_and_project_codex_portability_is_explicit(home, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    output = install("--home", str(home), "--project", str(project), "--host", "codex", "--no-shim")
    assert "Only .claude/ is shareable" in output
    assert "after moving or cloning" in output
    assert not (home / ".local/bin/ro").exists()
    assert not (home / "AppData/Local/Programs/ro/ro.cmd").exists()


def test_uninstall_no_hooks_refuses_before_changing_owned_or_foreign_files(home, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    settings = project / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "foreign-formatter"}]}]}}), encoding="utf-8")
    install("--home", str(home), "--project", str(project))
    before = snapshot(project), snapshot(home)
    with pytest.raises(SystemExit) as refusal:
        install("--home", str(home), "--project", str(project), "--uninstall", "--no-hooks")
    assert refusal.value.code == 2
    assert (snapshot(project), snapshot(home)) == before


def test_explicit_shim_flag_retains_compatibility(home):
    install("--home", str(home), "--host", "claude-code", "--shim")
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    assert shim.is_file()


def test_default_shim_uninstall_preserves_another_scope(home, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for project in (first, second):
        install("--home", str(home), "--project", str(project), "--host", "claude-code", "--no-hooks")
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    before = shim.read_bytes()
    install("--home", str(home), "--project", str(first), "--host", "claude-code", "--uninstall")
    assert shim.read_bytes() == before


@pytest.mark.parametrize("project_scope", [False, True])
def test_codex_only_upgrade_repoints_shared_runtime_away_from_older_claude(home, tmp_path, project_scope):
    arguments = ["--home", str(home)]
    base = home
    if project_scope:
        base = tmp_path / "project"
        base.mkdir()
        subprocess.run(["git", "init", "-q", str(base)], check=True, capture_output=True)
        arguments += ["--project", str(base)]
    install(*arguments, "--host", "claude-code")
    older = base / ".claude/skills/research-orchestrator/scripts/ro.py"
    older.write_text("raise SystemExit('older runtime')\n", encoding="utf-8")
    install(*arguments, "--host", "codex")
    assert older.read_text(encoding="utf-8") == "raise SystemExit('older runtime')\n"
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    assert ".codex" in shim.read_text(encoding="utf-8")
    command = ([os.environ["COMSPEC"], "/d", "/c", str(shim), "--help"] if os.name == "nt" else
               [shutil.which("sh"), shim.as_posix(), "--help"])
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and "Research Orchestrator" in result.stdout, result.stderr
    if project_scope:
        registration = next((base / ".git/hooks/research-orchestrator/registrations").glob("*.json"))
        runtime = json.loads(registration.read_text(encoding="utf-8"))["runtime"]
        assert runtime == (base.resolve() / ".codex/skills/research-orchestrator/scripts/ro.py").as_posix()


@pytest.mark.parametrize("legacy_global", [False, True])
def test_project_uninstall_repoints_cli_to_surviving_global_install(home, tmp_path, legacy_global):
    install("--home", str(home), "--host", "claude-code", "--no-hooks")
    registry = home / ".ro/cli-shim-registrations.json"
    if legacy_global:
        registry.unlink()
    project = tmp_path / "project"
    project.mkdir()
    install("--home", str(home), "--project", str(project), "--host", "codex", "--no-hooks")
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    assert ".codex" in shim.read_text(encoding="utf-8")
    install("--home", str(home), "--project", str(project), "--host", "codex", "--uninstall")
    assert shim.is_file()
    script = shim.read_text(encoding="utf-8")
    # Shims and registrations record resolved paths (8.3 short names, /var -> /private/var).
    runtime = home.resolve() / ".claude/skills/research-orchestrator/scripts/ro.py"
    assert str(runtime).replace("\\", "/") in script.replace("\\", "/")
    registrations = json.loads(registry.read_text(encoding="utf-8"))["registrations"]
    assert set(registrations) == {str(home.resolve())}
    command = ([os.environ["COMSPEC"], "/d", "/c", str(shim), "--help"] if os.name == "nt" else
               [shutil.which("sh"), shim.as_posix(), "--help"])
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and "Research Orchestrator" in result.stdout, result.stderr


def test_project_uninstall_repoints_cli_to_another_registered_project(home, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for project in (first, second):
        project.mkdir()
        install("--home", str(home), "--project", str(project), "--host", "claude-code", "--no-hooks")
    install("--home", str(home), "--project", str(second), "--host", "claude-code", "--uninstall")
    shim = home / ("AppData/Local/Programs/ro/ro.cmd" if os.name == "nt" else ".local/bin/ro")
    runtime = first.resolve() / ".claude/skills/research-orchestrator/scripts/ro.py"
    assert str(runtime).replace("\\", "/") in shim.read_text(encoding="utf-8").replace("\\", "/")


@pytest.mark.skipif(os.name != "nt", reason="PowerShell literal evaluation")
def test_powershell_literals_preserve_dollar_quotes_and_backticks(tmp_path):
    shell = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert shell
    value = str(tmp_path / "dollar-$team-apostrophe-'quote-backtick-`tick")
    command = "[Console]::Write(" + installer.literal(value, "powershell") + ")"
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, timeout=15, env={**os.environ, "team": "wrong"})
    assert result.returncode == 0 and result.stdout == value, result.stderr


@pytest.mark.parametrize("layout", ["linked-worktrees", "shared-hooks-path"])
def test_shared_git_gate_owns_each_scope_and_uninstall_preserves_the_other(home, tmp_path, layout):
    from ro_gate import registration
    first = make_project(tmp_path, "scope-one", "--preset", "quick", "--user", "operator")
    subprocess.run(["git", "init", "-q", str(first)], check=True, capture_output=True)
    if layout == "linked-worktrees":
        subprocess.run(["git", "-C", str(first), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(first), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "fixture"], check=True, capture_output=True)
        second = tmp_path / "scope-two"
        subprocess.run(["git", "-C", str(first), "worktree", "add", "-qb", "second", str(second)],
                       check=True, capture_output=True)
        hookdir = first / ".git/hooks"
    else:
        second = make_project(tmp_path, "scope-two", "--preset", "quick", "--user", "operator")
        subprocess.run(["git", "init", "-q", str(second)], check=True, capture_output=True)
        hookdir = tmp_path / "shared-hooks"
        for project in (first, second):
            subprocess.run(["git", "-C", str(project), "config", "core.hooksPath", str(hookdir)],
                           check=True, capture_output=True)
    for project, host in ((first, "claude-code"), (second, "codex")):
        install("--home", str(home), "--project", str(project), "--host", host)
    registrations = hookdir / "research-orchestrator/registrations"
    records = {json.loads(path.read_text(encoding="utf-8"))["scope"]: path.read_bytes()
               for path in registrations.glob("*.json")}
    assert len(records) == 2
    assert registration(first) == (first, True)
    assert registration(second) == (second, True)
    nested = second / "nested"
    nested.mkdir()
    assert registration(nested) == (second, True)

    def check(project, expected):
        result = subprocess.run([shutil.which("sh"), (hookdir / "pre-push").as_posix(), "origin"],
                                cwd=project, input="invalid refs\n", text=True, capture_output=True, timeout=15)
        assert result.returncode == expected, (result.stdout, result.stderr)
        if expected:
            assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"

    check(first, 1)
    check(second, 1)
    install("--home", str(home), "--project", str(first), "--host", "claude-code", "--uninstall")
    remaining = list(registrations.glob("*.json"))
    assert len(remaining) == 1
    assert remaining[0].read_bytes() == records[os.path.normcase(str(second.resolve()))]
    assert registration(first) == (first, False)
    assert registration(second) == (second, True)
    check(first, 0)
    check(second, 1)
    install("--home", str(home), "--project", str(second), "--host", "codex", "--uninstall")
    assert list(registrations.glob("*.json")) == []
    assert registration(first) == (first, False)
    assert registration(second) == (second, False)
    check(first, 0)
    check(second, 0)


def test_legacy_gate_marker_does_not_grant_ownership(home, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    gate = project / ".git/hooks/pre-push"
    original = "#!/bin/sh\n" + installer.PRE_PUSH_MARK + "\n# another installation's runtime\nexit 1\n"
    gate.write_text(original, encoding="utf-8", newline="\n")
    for operation in ([], ["--uninstall"]):
        install("--home", str(home), "--project", str(project), "--host", "claude-code", *operation)
        assert gate.read_text(encoding="utf-8") == original


def test_dispatcher_forwards_exact_git_ref_bytes_and_remote(home, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    runtime = project / ".claude/skills/research-orchestrator/scripts/ro.py"
    runtime.write_text("import json, sys\nprint(json.dumps([sys.argv[1:], sys.stdin.buffer.read().hex()]))\n",
                       encoding="utf-8")
    payload = b"refs/heads/main " + b"a" * 40 + b" refs/heads/main " + b"b" * 40 + b"\r\n"
    result = subprocess.run([shutil.which("sh"), ".git/hooks/pre-push", "destination with space"],
                            cwd=project, input=payload, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["hook", "pre-push", "--remote", "destination with space"], payload.hex()]
    runtime.unlink()
    result = subprocess.run([shutil.which("sh"), ".git/hooks/pre-push", "origin"],
                            cwd=project, input=payload, capture_output=True, timeout=15)
    assert result.returncode != 0


def test_installed_git_gate_recovers_after_registered_python_is_removed(home, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    runtime = project / ".claude/skills/research-orchestrator/scripts/ro.py"
    runtime.write_text("import json, sys\nprint(json.dumps([sys.argv[1:], sys.stdin.buffer.read().hex()]))\n",
                       encoding="utf-8")
    gate = project / ".git/hooks/pre-push"
    text = gate.read_text(encoding="utf-8")
    text = text.replace(Path(sys.executable).resolve().as_posix(), "/missing/registered-python")
    gate.write_text(text, encoding="utf-8", newline="\n")
    registration = next((gate.parent / "research-orchestrator/registrations").glob("*.json"))
    data = json.loads(registration.read_text(encoding="utf-8"))
    data["python"] = "/missing/registered-python"
    registration.write_text(json.dumps(data), encoding="utf-8")
    refs = b"refs/heads/main a refs/heads/main b\r\n"
    result = subprocess.run([shutil.which("sh"), str(gate), "origin", "destination"],
                            cwd=project, input=refs, capture_output=True, timeout=15,
                            env={**os.environ, "RO_HOOK_PYTHON": sys.executable})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["hook", "pre-push", "--remote", "origin"], refs.hex()]


@pytest.mark.parametrize("plugin_active", [False, True])
@pytest.mark.parametrize("policy", ["off", "on", "commented"])
def test_project_read_matcher_is_opt_in_and_independent_of_plugin(home, tmp_path, plugin_active, policy):
    project = tmp_path / "project"
    project.mkdir()
    setting = "- Read bound: on" if policy == "on" else "- Read bound: off"
    if policy == "commented":
        setting = "<!-- - Read bound: on -->"
    (project / "agents.md").write_text("## Project settings\n" + setting + "\n", encoding="utf-8")
    settings = project / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"enabledPlugins": {"research-orchestrator@local": plugin_active}}),
                        encoding="utf-8")
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    hooks = json.loads(settings.read_text(encoding="utf-8"))["hooks"]
    entries = hooks.get("PreToolUse", [])
    read_entries = [entry for entry in entries if entry["matcher"] == "Glob|Grep|Read"]
    assert len(read_entries) == (1 if policy == "on" else 0)
    assert sum("Bash" in entry["matcher"].split("|") for entry in entries) == (0 if plugin_active else 1)
    before = settings.read_bytes()
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    assert settings.read_bytes() == before
    (project / "agents.md").write_text("## Project settings\n- Read bound: off\n", encoding="utf-8")
    install("--home", str(home), "--project", str(project), "--host", "claude-code")
    entries = json.loads(settings.read_text(encoding="utf-8"))["hooks"].get("PreToolUse", [])
    assert not any("Read" in entry["matcher"].split("|") for entry in entries)


@pytest.mark.parametrize("autonomy,brief", [
    ("present", "none"),
    ("away", "none"),
    ("present", "reviewer: Inspect evidence"),
    ("away", "reviewer: Inspect evidence"),
])
def test_project_claude_matchers_survive_governing_policy_changes(home, tmp_path, autonomy, brief):
    project = tmp_path / "project"
    project.mkdir()
    rules = project / "agents.md"
    rules.write_text(f"## Project settings\n- Autonomy: {autonomy}\n- Brief requirements: {brief}\n", encoding="utf-8")
    setup = installer.Installer(installer.parser().parse_args(
        ["--home", str(home), "--project", str(project), "--host", "claude-code"]))
    def tools():
        entries = setup.claude_template("${CLAUDE_PROJECT_DIR}/.claude/skills/research-orchestrator")["PreToolUse"]
        return {tool for entry in entries for tool in entry["matcher"].split("|")}
    assert {"AskUserQuestion", "Agent"} <= tools()
    assert {"Edit", "Write", "NotebookEdit", "Bash", "PowerShell"} <= tools()
    assert "rerun install.py --project" not in " ".join(setup.notes)
    rules.write_text("## Project settings\n- Autonomy: away\n- Brief requirements: reviewer: Inspect evidence\n",
                     encoding="utf-8")
    assert {"AskUserQuestion", "Agent"} <= tools()


@pytest.mark.parametrize("scope", ["home", "missing", "unreadable", "no-section"])
def test_unknown_project_policy_keeps_question_and_agent_claude_matchers(home, tmp_path, scope):
    arguments = ["--home", str(home), "--host", "claude-code"]
    if scope != "home":
        project = tmp_path / "project"
        project.mkdir()
        arguments += ["--project", str(project)]
        if scope == "unreadable":
            (project / "agents.md").write_bytes(b"\xff")
        elif scope == "no-section":
            (project / "agents.md").write_text("# Custom rules\n", encoding="utf-8")
    setup = installer.Installer(installer.parser().parse_args(arguments))
    entries = setup.claude_template("portable-root")["PreToolUse"]
    tools = {tool for entry in entries for tool in entry["matcher"].split("|")}
    assert {"AskUserQuestion", "Agent"} <= tools
    assert {"Edit", "Write", "NotebookEdit", "Bash", "PowerShell"} <= tools
