"""Exercise the shipped wrappers, including Git shells with drive-letter PWD."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from conftest import ROOT


TIMEOUT = 3
HINTS = ("CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR")


def wrapper_command(wrapper):
    path = ROOT / "hooks" / wrapper
    if wrapper.endswith(".cmd"):
        if os.name != "nt":
            pytest.skip("cmd.exe requires Windows")
        return [os.environ["COMSPEC"], "/d", "/c", str(path)]
    shell = shutil.which("sh")
    assert shell, "A POSIX shell is required for the hook wrapper"
    return [shell, path.as_posix()]


def wrapper_environment(tmp_path, wrapper):
    # Do not let host hints, PWD or an installed interpreter select a real project.
    env = {key: value for key, value in os.environ.items()
           if key not in (*HINTS, "RO_HOOK_PYTHON", "PWD", "CDPATH", "ENV", "BASH_ENV", "PS4")}
    sentinel = tmp_path / ("sentinel.cmd" if wrapper.endswith(".cmd") else "sentinel")
    if wrapper.endswith(".cmd"):
        script = ('@echo off\necho started>>"%RO_TEST_SENTINEL%"\necho %CD%\n'
                  'set /p payload=\necho %payload%\nexit /b 0\n')
    else:
        script = ('#!/bin/sh\nprintf "started\\n" >> "$RO_TEST_SENTINEL"\n'
                  'printf "%s\\n" "$PWD"\nIFS= read -r payload; printf "%s\\n" "$payload"\n')
    sentinel.write_text(script, encoding="utf-8", newline="\n")
    sentinel.chmod(0o755)
    env.update(RO_HOOK_PYTHON=str(sentinel), RO_TEST_SENTINEL=str(tmp_path / "invocations"),
               PATH=str(tmp_path / "empty-path"))
    return env


def invoke(command, cwd, env):
    return subprocess.run(command, cwd=cwd, env=env, input=b'{"payload":"unchanged"}\n',
                          capture_output=True, timeout=TIMEOUT)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows drive/UNC path spellings")
@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("source", HINTS)
@pytest.mark.parametrize("spelling", ["directory-slash", "directory-backslash", "drive",
                                     "drive-root-slash", "drive-root-backslash", "posix-root",
                                     "unc-root-slash", "unc-root-backslash",
                                     "unc-child-slash", "unc-child-backslash"])
def test_native_windows_roots_return_without_interpreter(tmp_path, wrapper, source, spelling):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    directory = tmp_path / "unrelated with spaces" / "nested"
    directory.mkdir(parents=True)
    drive = directory.drive
    # A unique nonexistent loopback share avoids depending on a network server/share.
    unc = f"//127.0.0.1/{tmp_path.name}"
    hints = {"directory-slash": directory.as_posix(), "directory-backslash": str(directory),
             "drive": drive, "drive-root-slash": drive + "/", "drive-root-backslash": drive + "\\",
             "posix-root": "/", "unc-root-slash": unc, "unc-root-backslash": unc.replace("/", "\\"),
             "unc-child-slash": unc + "/nested", "unc-child-backslash": (unc + "/nested").replace("/", "\\")}
    env[source] = hints[spelling]
    result = invoke([*command, "PreToolUse"], tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert json.loads(result.stdout) == {}
    assert not Path(env["RO_TEST_SENTINEL"]).exists()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows drive path spellings")
@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("source", HINTS)
@pytest.mark.parametrize("backslashes", [False, True])
def test_windows_hint_discovers_ancestor_and_preserves_dispatch(tmp_path, wrapper, source, backslashes):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    project = tmp_path / "project with spaces"
    nested = project / "one" / "two"
    nested.mkdir(parents=True)
    (project / "agents.md").write_text("# Rules\n", encoding="utf-8")
    env[source] = str(nested) if backslashes else nested.as_posix()
    result = invoke([*command, "PreToolUse"], tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    cwd, payload = result.stdout.decode().splitlines()
    assert cwd.replace("\\", "/").endswith("/" + tmp_path.name)
    assert payload == '{"payload":"unchanged"}'
    assert Path(env["RO_TEST_SENTINEL"]).read_text().splitlines() == ["started"]


@pytest.mark.skipif(os.name != "nt", reason="Git for Windows drive-letter physical PWD")
@pytest.mark.parametrize("source", HINTS)
@pytest.mark.parametrize("backslashes", [False, True])
@pytest.mark.parametrize("has_project", [False, True])
def test_real_shell_drive_pwd_terminates_and_still_finds_hints(tmp_path, source, backslashes, has_project):
    shell, wrapper = wrapper_command("ro-hook.sh")
    candidates = [Path(shell).with_name("cygpath.exe"),
                  Path(shell).parent.parent / "usr" / "bin" / "cygpath.exe"]
    if found := shutil.which("cygpath"):
        candidates.append(Path(found))
    cygpath = next((path for path in candidates if path.is_file()), None)
    assert cygpath, "Git for Windows supplies cygpath in usr/bin"
    env = wrapper_environment(tmp_path, "ro-hook.sh")
    nested = tmp_path / "project with spaces" / "nested"
    nested.mkdir(parents=True)
    if has_project:
        (nested.parent / "agents.md").write_text("# Rules\n", encoding="utf-8")
    env.update(RO_TEST_CYGPATH=str(cygpath))
    env[source] = str(nested) if backslashes else nested.as_posix()
    # Keep cd and the filesystem real. Only select the equivalent Win32 spelling
    # of physical PWD, so this catches the defect on Git versions using /c/... too.
    driver = ('cd() { command cd "$@" || return; PWD=$("$RO_TEST_CYGPATH" -m "$PWD"); }; '
              'ro_test_wrapper=$1; set -- PreToolUse; . "$ro_test_wrapper"')
    result = invoke([shell, "-c", driver, wrapper, wrapper], tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    if has_project:
        cwd, payload = result.stdout.decode().splitlines()
        assert cwd.replace("\\", "/").endswith("/" + tmp_path.name)
        assert payload == '{"payload":"unchanged"}'
        assert Path(env["RO_TEST_SENTINEL"]).read_text().splitlines() == ["started"]
    else:
        assert json.loads(result.stdout) == {}
        assert not Path(env["RO_TEST_SENTINEL"]).exists()


@pytest.mark.parametrize("source", HINTS)
@pytest.mark.parametrize("physical", ["/", "X:", "X:/", "separator-free",
                                      "//127.0.0.1/{share}", "//127.0.0.1/{share}/nested"])
def test_posix_walk_stops_at_physical_roots(tmp_path, source, physical):
    shell, wrapper = wrapper_command("ro-hook.sh")
    env = wrapper_environment(tmp_path, "ro-hook.sh")
    physical = physical.format(share=tmp_path.name)
    env.update(RO_TEST_PHYSICAL=physical, RO_TEST_HINT="ro-test-physical-root")
    env[source] = env["RO_TEST_HINT"]
    # Reach uncommon canonical roots without mounting drives or creating shares.
    # Source the unchanged wrapper; only cd's physical-path result is injected.
    driver = ('cd() { if [ "$2" = "$RO_TEST_HINT" ]; then PWD=$RO_TEST_PHYSICAL; '
              'else command cd "$@"; fi; }; ro_test_wrapper=$1; set -- PreToolUse; . "$ro_test_wrapper"')
    result = invoke([shell, "-x", "-c", driver, wrapper, wrapper], tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {}
    assert not Path(env["RO_TEST_SENTINEL"]).exists()
    # Trace assertions ensure UNC traversal stops at the share, not at a server
    # or an unrelated local root, and separator-free paths are not rechecked.
    checks = []
    for line in result.stderr.decode().splitlines():
        words = shlex.split(line)
        if words and not words[0].strip("+") and words[1:3] == ["[", "-f"]:
            checks.append(words[3])
    marker = physical.rstrip("/") + "/agents.md"
    matches = [index for index, path in enumerate(checks) if path == marker]
    # The cwd search may already have reached / before the explicit / hint.
    if physical != "/":
        assert len(matches) == 1, checks
    first = matches[-1]
    expected = [marker]
    if physical.endswith("/nested"):
        expected.append(physical.rsplit("/", 1)[0] + "/agents.md")
    assert checks[first:] == expected
