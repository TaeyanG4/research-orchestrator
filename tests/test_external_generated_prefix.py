"""Generated wrapper commands pass their own gate without exempting later commands."""

import pytest

import ro_checks as checks
import ro_hooks as hooks
from ro_command import command_prefix
from test_ro_hooks import configured, denied, project_at, shell_payload


@pytest.mark.parametrize("dialect,shell", [("bash", "sh"), ("powershell", "powershell")])
def test_generated_external_prefix_passes_public_gate_but_trailing_direct_call_is_denied(tmp_path, dialect, shell):
    project = project_at(tmp_path, selected="external.gate")
    policy = tmp_path / "agents.md"
    policy.write_text(policy.read_text(encoding="utf-8").replace(
        "literal:release-tool publish", "regex:release-tool publish").replace(
        "/bash", "/" + dialect), encoding="utf-8")
    prefix = command_prefix(tmp_path / "runtime with spaces" / "ro.py", shell=shell)
    assert " -E -S " in prefix
    command = (prefix + " --project workspace --slot A --session author external"
               " --artifact artifact.txt --action X-A-001"
               " -- release-tool publish artifact.txt")
    assert hooks.hook(project, "PreToolUse", shell_payload(command, dialect), check="external.gate") == {}
    response = hooks.hook(project, "PreToolUse", shell_payload(
        command + "; release-tool publish artifact.txt", dialect), check="external.gate")
    assert denied(response)
    assert "external.gate" in str(response)


@pytest.mark.parametrize("dialect", ["bash", "powershell"])
@pytest.mark.parametrize("interpreter", [
    "python -E -S", "python3 -I -B -u", "python3.12 -O -s -P", "py -3.12 -E -S",
])
def test_supported_interpreter_flags_preserve_external_wrapper(tmp_path, dialect, interpreter):
    command = interpreter + " tools/ro.py external -- release-tool publish artifact.txt"
    values = {**configured(shell=dialect), "external_actions": "regex:release-tool publish"}
    findings = checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, [], values)
    assert not any(f.check == "external.gate" for f in findings)


@pytest.mark.parametrize("option", ["-c", "-m", "-W", "-X", "--unknown"])
def test_operand_and_unsupported_options_cannot_establish_external_wrapper(tmp_path, option):
    command = "python " + option + " ro.py external -- release-tool publish artifact.txt"
    assert checks.external_direct(checks.tokens(command, "bash").parts,
                                  "regex:release-tool publish", "linux")
