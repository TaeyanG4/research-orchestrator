"""Delivery probe tests: every Codex subprocess is mocked."""

import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tomllib

import pytest

from scripts.host import codex_hook_delivery_probe as probe


def test_three_configurations_and_report(tmp_path, monkeypatch, capsys):
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    original = ('model = "original"\nmodel_provider = "custom"\n'
                'developer_instructions = "do-not-copy"\n'
                '[model_providers.custom]\nname = "Custom"\nenv_key = "CODEX_PROBE_AUTH"\n'
                'experimental_bearer_token = "do-not-copy"\n[windows]\nsandbox = "elevated"\n')
    (real_home / "config.toml").write_text(original, encoding="utf-8")
    (real_home / "auth.json").write_text("do-not-copy", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(real_home))
    monkeypatch.setenv("CODEX_PROBE_AUTH", "env-secret")
    monkeypatch.setenv("CODEX_THREAD_ID", "do-not-inherit")
    monkeypatch.setattr(probe, "resolve_codex", lambda value: "mock-codex")
    calls = []

    def run(argv, **kwargs):
        project = kwargs["cwd"]
        case = project.name
        assert all((project.parent / item / ".ro" / "sessions").is_dir() for item in ("A", "B", "C"))
        home = Path(kwargs["env"]["CODEX_HOME"])
        calls.append(project)
        assert argv[:2] == ["mock-codex", "exec"]
        assert argv[-1] == probe.PROMPT and "Write-Output probe" in argv[-1]
        assert argv[argv.index("--model") + 1] == "test-model"
        assert "features.hooks=true" in argv and "--dangerously-bypass-hook-trust" in argv
        assert kwargs["stdin"] is subprocess.DEVNULL and kwargs["timeout"] == 120
        assert kwargs.get("shell", False) is False
        assert home.is_relative_to(project) and home != real_home
        assert kwargs["env"]["CODEX_PROBE_AUTH"] == "env-secret"
        assert "CODEX_THREAD_ID" not in kwargs["env"] and not (home / "auth.json").exists()
        config_text = (home / "config.toml").read_text(encoding="utf-8")
        assert "do-not-copy" not in config_text and "env-secret" not in config_text
        config = tomllib.loads(config_text)
        assert config["windows"]["sandbox"] == "elevated"
        assert config["model_providers"]["custom"]["env_key"] == "CODEX_PROBE_AUTH"
        assert argv[argv.index("-s") + 1] == ("workspace-write" if case == "A" else "danger-full-access")
        if case == "A":
            assert f'projects.{json.dumps(str(project))}.trust_level="trusted"' in argv
            assert (project / ".codex" / "config.toml").read_text() == ""
        if case == "C":
            declarations = config["hooks"]
            assert not (home / "hooks.json").exists()
        else:
            location = project / ".codex" if case == "A" else home
            declarations = json.loads((location / "hooks.json").read_text())["hooks"]
        assert set(declarations) == {"SessionStart", "PreToolUse"}
        assert all(entry[0]["matcher"] == "*" for entry in declarations.values())
        assert all(entry[0]["hooks"][0]["commandWindows"].startswith("& '") for entry in declarations.values())
        if case == "A":
            return subprocess.CompletedProcess(argv, 7, "", "error: sandbox setup\n")
        (project / "delivered.log").write_text("SessionStart\t\nPreToolUse\tBash\n", encoding="utf-8")
        if case == "C":
            raise subprocess.TimeoutExpired(argv, 120, output=b"partial", stderr=b"error: timed out")
        return subprocess.CompletedProcess(argv, 0, "mock events", "")

    monkeypatch.setattr(probe.subprocess, "run", run)
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    assert probe.main(["--model", "test-model"]) == 1
    report = next((tmp_path / "docs" / "host-dry-runs").glob("codex-delivery-probe-*.md")).read_text()
    assert "| A: project JSON | failed | 7 | false |" in report
    assert "| B: home JSON | completed | 0 | true |" in report
    assert "| C: home TOML | timeout | n/a | true |" in report
    assert "PreToolUse" in report and "error: timed out" in report
    assert len(set(calls)) == 3 and all(path.is_relative_to(tmp_path / "_hook-probe") for path in calls)
    retained = calls[2].parent.parent / "done" / calls[2].parent.name
    assert (retained / "C" / "stdout.log").read_text() == "partial"
    assert (real_home / "config.toml").read_text() == original
    assert sorted(path.name for path in real_home.iterdir()) == ["auth.json", "config.toml"]
    assert "env-secret" not in report and "| B: home JSON" in capsys.readouterr().out


def test_dry_print_does_not_launch_read_host_config_or_write(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry-print must not execute or read host settings")

    monkeypatch.setattr(probe.subprocess, "run", forbidden)
    monkeypatch.setattr(probe, "configured_model_settings", forbidden)
    monkeypatch.setattr(probe, "resolve_codex", forbidden)
    root = tmp_path / "absent"
    assert probe.main(["--dry-print", "--root", str(root)]) == 0
    plans = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [plan["case"] for plan in plans] == ["A", "B", "C"]
    assert all("gpt-6.1-sol" in plan["argv"] for plan in plans)
    assert not root.exists()


def test_hook_appends_without_importing_project_code(tmp_path, monkeypatch):
    log = tmp_path / "delivered.log"
    for event, payload in [("SessionStart", {}), ("PreToolUse", {"tool_name": "Bash"})]:
        monkeypatch.setattr(sys, "argv", ["-c", str(log), event])
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        exec(probe.HOOK_CODE, {})
    assert log.read_text().splitlines() == ["SessionStart\t", "PreToolUse\tBash"]


def test_payload_hook_preserves_complete_input_and_repeated_calls_without_env_values(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "SECRET_HOME_VALUE")
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "SECRET_DIAGNOSTICS_VALUE")
    monkeypatch.setenv("CODEX_API_KEY", "SECRET_API_VALUE")
    raw_inputs = [
        '{\r\n  "tool_name": "Bash", "unknown": {"nested": "한글"}, "long": "' + "x" * 100000 + '"\r\n}',
        '  {"tool_name": "Bash", "tool_input": {"command": ["sh", "-c", "echo again"]}}\n',
    ]
    for raw in raw_inputs:
        monkeypatch.setattr(sys, "argv", ["-c", str(tmp_path), "PreToolUse"])
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw.encode("utf-8")), encoding="utf-8"))
        exec(probe.PAYLOAD_HOOK_CODE, {})
    records = [json.loads(path.read_text(encoding="utf-8"))
               for path in tmp_path.glob("payloads/*/payload-PreToolUse.json")]
    assert len(records) == 2
    assert sorted(record["raw_stdin"] for record in records) == sorted(raw_inputs)
    for record in records:
        assert record["payload"] == json.loads(record["raw_stdin"])
        assert {"CODEX_HOME", "RO_HOOK_DIAGNOSTICS"} <= set(record["environment_names"])
        assert "CODEX_API_KEY" not in record["environment_names"]
        assert len(record["environment_names"]) <= 15
        assert "SECRET_" not in json.dumps(record)
    latest = json.loads((tmp_path / "payload-PreToolUse.json").read_text(encoding="utf-8"))
    assert latest["raw_stdin"] == raw_inputs[-1]
    assert (tmp_path / "delivered.log").read_text().splitlines() == ["PreToolUse\tBash"] * 2


def test_cases_d_e_use_project_json_real_sample_and_marker(tmp_path):
    for case in ("D", "E"):
        project = tmp_path / case
        files = probe.hook_files(case, project, {})
        config = json.loads(files[project / ".codex" / "hooks.json"])["hooks"]
        assert files[project / ".codex" / "config.toml"] == ""
        assert project / "codex-home" / "hooks.json" not in files
        argv = probe.command(case, project, "mock-codex", "test-model")
        assert argv[argv.index("-s") + 1] == "workspace-write"
        assert f'projects.{json.dumps(str(project))}.trust_level="trusted"' in argv
        if case == "D":
            assert set(config) == {"SessionStart", "PreToolUse"}
            assert "raw_stdin" in config["PreToolUse"][0]["hooks"][0]["command"]
        else:
            assert files[project / ".ro" / "hook-diagnostics.on"] == ""
            sample = json.loads(probe.SAMPLE.read_text(encoding="utf-8"))["hooks"]
            assert set(config) == set(sample)
            for event, entries in sample.items():
                assert config[event][0]["matcher"] == entries[0]["matcher"]
                wrapped = config[event][0]["hooks"][0]
                assert wrapped["timeout"] == 10
                for field in ("command", "commandWindows"):
                    original = entries[0]["hooks"][0][field].replace("/absolute/path/to/plugin", probe.ROOT.as_posix())
                    assert original in wrapped[field]
                    assert f"event={event}" in wrapped[field] and "exit_code=" in wrapped[field]
                    assert "chain.log" in wrapped[field]


def test_case_selection_and_artifact_reporting(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe, "configured_model_settings", lambda: {})
    monkeypatch.setattr(probe, "resolve_codex", lambda value: "mock-codex")
    calls = []

    def run(argv, **kwargs):
        assert argv[:2] == ["mock-codex", "exec"]
        project = kwargs["cwd"]
        calls.append(project.name)
        if project.name == "D":
            archive = project / "payloads" / "test-call"
            archive.mkdir(parents=True)
            for folder in (project, archive):
                (folder / "payload-PreToolUse.json").write_text('{"raw_stdin":"PRIVATE_PAYLOAD"}', encoding="utf-8")
        else:
            assert (project / ".ro" / "hook-diagnostics.on").is_file()
            (project / "chain.log").write_text("event=PreToolUse\nexit_code=0\n", encoding="utf-8")
            (project / ".ro" / "hook-diagnostics.jsonl").write_text("{}\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(probe.subprocess, "run", run)
    report = tmp_path / "report.md"
    assert probe.main(["--cases", "D", "E", "--root", str(tmp_path / "runs"), "--output", str(report)]) == 0
    assert calls == ["D", "E"]
    text = report.read_text(encoding="utf-8")
    assert "payload calls=1" in text and "chain.log=True; diagnostics=True" in text
    assert "payload-PreToolUse.json" in text and "hook-diagnostics.jsonl" in text
    assert "PRIVATE_PAYLOAD" not in text  # Payloads remain in their explicit artifacts.
    capsys.readouterr()

    def forbidden(*args, **kwargs):
        raise AssertionError("dry-print must not launch or read host settings")

    monkeypatch.setattr(probe.subprocess, "run", forbidden)
    monkeypatch.setattr(probe, "configured_model_settings", forbidden)
    monkeypatch.setattr(probe, "resolve_codex", forbidden)
    absent = tmp_path / "dry-only"
    assert probe.main(["--cases", "D", "E", "--dry-print", "--root", str(absent)]) == 0
    plans = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [plan["case"] for plan in plans] == ["D", "E"]
    assert not absent.exists()


def local_shell(windows):
    if windows:
        if os.name != "nt":
            pytest.skip("Windows batch launcher requires Windows")
        shell = shutil.which("powershell") or shutil.which("pwsh")
    else:
        shell = shutil.which("sh")
        if not shell:
            git = shutil.which("git")
            candidate = Path(git).parent.parent / "bin" / "sh.exe" if git else None
            if candidate and candidate.is_file():
                shell = str(candidate)
    if not shell:
        pytest.skip("shell unavailable")
    return shell


@pytest.mark.parametrize("windows", [False, True])
def test_payload_capture_command_keeps_raw_piped_bytes(tmp_path, windows):
    shell = local_shell(windows)
    field = "commandWindows" if windows else "command"
    command = probe.hooks(tmp_path, capture_payload=True)["PreToolUse"][0]["hooks"][0][field]
    argv = [shell, "-NoProfile", "-Command", command] if windows else [shell, "-c", command]
    raw = ' {"tool_name":"Bash", "unknown":"한글 ☃"}\r\n'.encode("utf-8")
    result = subprocess.run(argv, input=raw, capture_output=True, timeout=15)
    assert result.returncode == 0, (result.stdout, result.stderr)
    record = json.loads((tmp_path / "payload-PreToolUse.json").read_text(encoding="utf-8"))
    assert record["raw_stdin"].encode("utf-8") == raw


@pytest.mark.parametrize("windows", [False, True])
def test_chain_wrapper_forwards_stdin_logs_both_streams_and_preserves_exit(tmp_path, windows):
    shell = local_shell(windows)
    # These are local launcher stubs only: no Codex process is ever invoked.
    project = tmp_path / "project with spaces"
    project.mkdir()
    capture = project / "stdin.json"
    helper = project / "capture.py"
    helper.write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n"
        "print('stdout-sentinel')\n"
        "print('stderr-sentinel', file=sys.stderr)\n"
        "raise SystemExit(7)\n", encoding="utf-8")
    if windows:
        launcher = project / "ro-hook.cmd"
        launcher.write_text(f'@echo off\n"{sys.executable}" -I -S "{helper}" "{capture}"\nexit /b %errorlevel%\n', encoding="utf-8")
        sample_command = f'& "{launcher}" PreToolUse'
    else:
        launcher = project / "ro-hook.sh"
        launcher.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, "-I", "-S", str(helper), str(capture)]) + "\n", encoding="utf-8")
        sample_command = "sh " + shlex.quote(str(launcher)) + " PreToolUse"
    wrapped = probe.wrap_chain(sample_command, project, "PreToolUse", windows=windows)
    argv = [shell, "-NoProfile", "-Command", wrapped] if windows else [shell, "-c", wrapped]
    payload = {"tool_name": "Bash", "tool_input": {"command": ["echo", "한글 ☃"]}, "cwd": str(project)}
    for _ in range(2):
        result = subprocess.run(argv, input=json.dumps(payload, ensure_ascii=False), encoding="utf-8",
                                capture_output=True, timeout=15)
        assert result.returncode == 7, (result.stdout, result.stderr)
        assert json.loads(capture.read_text(encoding="utf-8")) == payload
    log = (project / "chain.log").read_text(encoding="utf-8-sig")
    assert log.count("event=PreToolUse") == 2
    assert log.count("stdout-sentinel") == 2
    # Windows PowerShell also includes stderr text in its native-error metadata.
    assert log.count("stderr-sentinel") >= 2
    assert log.count("exit_code=7") == 2
