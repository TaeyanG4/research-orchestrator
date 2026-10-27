"""Record path operands before filesystem access can hide a cold UNC lookup."""

import json
import os
from pathlib import Path
import re
import subprocess
import time

import pytest

from conftest import ROOT
from test_hook_root_termination import HINTS, invoke, wrapper_command, wrapper_environment


@pytest.mark.parametrize("physical,expected", [
    ("/", ["/agents.md"]),
    ("/var/local with spaces", ["/var/local with spaces/agents.md", "/var/agents.md", "/agents.md"]),
    ("X:", ["X:/agents.md"]),
    ("X:/", ["X:/agents.md"]),
    ("X:/local with spaces/nested", ["X:/local with spaces/nested/agents.md",
                                    "X:/local with spaces/agents.md", "X:/agents.md"]),
    ("//server/share", ["//server/share/agents.md"]),
    ("//server/share/nested", ["//server/share/nested/agents.md", "//server/share/agents.md"]),
])
@pytest.mark.parametrize("source", HINTS)
def test_shell_records_every_marker_probe_without_inventing_unc(tmp_path, physical, expected, source):
    shell, wrapper = wrapper_command("ro-hook.sh")
    env = wrapper_environment(tmp_path, "ro-hook.sh")
    probes = tmp_path / "probes.txt"
    env.update(RO_TEST_PHYSICAL=physical, RO_TEST_PROBES=str(probes))
    env[source] = "injected-physical-path"
    # No fake filesystem or network request: only cd's resulting PWD and marker
    # existence are substituted. All joins and traversal run in the real wrapper.
    driver = r'''
        ro_test_check() {
            if command [ "$1" = -f ]; then
                printf '%s\n' "$2" >> "$RO_TEST_PROBES"
                return 1
            fi
            command [ "$@"
        }
        alias [=ro_test_check
        cd() { PWD=$RO_TEST_PHYSICAL; }
        PWD=$RO_TEST_PHYSICAL
        . "$1" PreToolUse
    '''
    result = invoke([shell, "-c", driver, wrapper, wrapper], tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert json.loads(result.stdout) == {}
    assert not Path(env["RO_TEST_SENTINEL"]).exists()
    observed = probes.read_text().splitlines()
    assert observed == expected * 2  # cwd, then the selected host hint
    if not physical.startswith("//"):
        assert all(not path.startswith("//") for path in observed), observed


@pytest.mark.skipif(os.name != "nt", reason="cmd.exe requires Windows")
@pytest.mark.parametrize("spelling", ["directory", "drive", "drive-root", "root", "posix",
                                     "extended-drive"])
def test_cmd_records_marker_probes_with_one_join_separator(tmp_path, spelling):
    env = wrapper_environment(tmp_path, "ro-hook.cmd")
    nested = tmp_path / "unrelated with spaces" / "nested"
    nested.mkdir(parents=True)
    env["CLAUDE_PROJECT_DIR"] = {
        "directory": str(nested), "drive": nested.drive,
        "drive-root": nested.anchor, "root": "\\", "posix": "/",
        "extended-drive": "\\\\?\\" + str(nested),
    }[spelling]
    # cmd has no test-function override. Enable command echo in a disposable
    # byte-for-byte wrapper copy except for this one tracing switch.
    traced = tmp_path / "traced.cmd"
    body = (ROOT / "hooks/ro-hook.cmd").read_text()
    assert body.startswith("@echo off\n")
    traced.write_text(body.replace("@echo off\n", "@echo on\n", 1))
    result = invoke([os.environ["COMSPEC"], "/d", "/c", str(traced), "PreToolUse"], tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert not Path(env["RO_TEST_SENTINEL"]).exists()
    probes = re.findall(r'if (?:not )?exist "([^"]+)"', result.stdout.decode(), flags=re.I)
    assert probes, result.stdout
    assert any(path == nested.drive + "\\agents.md" for path in probes), probes
    for probe in probes:
        normalized = probe.replace("\\", "/")
        if normalized.startswith("//?/"):
            assert spelling == "extended-drive"
            normalized = normalized[4:]
        assert not normalized.startswith("//"), probes
        assert "//" not in normalized, probes


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
def test_nonproject_wrapper_finishes_in_under_one_second(tmp_path, wrapper):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    directory = tmp_path / "unrelated with spaces" / "nested"
    directory.mkdir(parents=True)
    # Include a native Windows hint and / so Git for Windows reaches its POSIX
    # root even when its physical cwd retains a drive-letter spelling.
    env.update(CLAUDECODE="1", CLAUDE_PROJECT_DIR=str(directory), CODEX_PROJECT_DIR="/")
    started = time.perf_counter()
    result = subprocess.run([*command, "PreToolUse"], cwd=directory, env=env,
                            input=b'{"payload":"unchanged"}\n', capture_output=True, timeout=1)
    elapsed = time.perf_counter() - started
    assert elapsed < 1, elapsed
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert json.loads(result.stdout) == {}
    assert not Path(env["RO_TEST_SENTINEL"]).exists()
