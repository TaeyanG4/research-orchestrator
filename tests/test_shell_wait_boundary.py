"""A foreground wait joins all jobs without hiding detached or partial waits."""

import pytest

import ro_checks as checks


def findings(tmp_path, command, dialect):
    values = {"environment": f"linux/{dialect}", "enforcement": "block",
              "block": "shell.background,shell.detach"}
    return checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, [], values)


@pytest.mark.parametrize("command", [
    "a & b & wait",
    "prepare; first --mode quick & second --mode full & wait;",
    "first &\nsecond &\nwait\n# all workers joined\n",
    "first & second & # launch both\nwait",
    "first & echo 'wait' & wait",
])
def test_final_bash_wait_keeps_the_call_foreground(tmp_path, command):
    assert not findings(tmp_path, command, "bash")


@pytest.mark.parametrize("command", [
    "a &; b &; Get-Job | Wait-Job",
    "first &\nsecond &\nGet-Job | Wait-Job\n# all jobs joined\n",
    "first &; GET-JOB | WAIT-JOB;",
])
def test_final_powershell_wait_for_all_jobs_keeps_the_call_foreground(tmp_path, command):
    assert not findings(tmp_path, command, "powershell")


@pytest.mark.parametrize("command", [
    "a & b &",
    "a & wait &",
    "a & wait; b &",
    "a & wait -n",
    "a & wait 123",
    "a & b && wait",
    "a & b &&\nwait",
    "a & b || wait",
    "a & b | wait",
    "a & (wait)",
    "a & { wait; }",
    "a & echo wait",
    "a & echo $(wait)",
    "a & sh -c 'wait'",
    "a & # wait",
])
def test_partial_conditional_nested_or_trailing_bash_wait_does_not_hide_background(tmp_path, command):
    assert any(f.check == "shell.background" for f in findings(tmp_path, command, "bash"))


@pytest.mark.parametrize("command", [
    "first &; Get-Job | Wait-Job -Any",
    "first &; Get-Job | Wait-Job -Timeout 1",
    "first &; Get-Job -Name selected | Wait-Job",
    "first &; Wait-Job -Id 1",
    "first &; Get-Job | Wait-Job; second &",
    "first &; Get-Job | Wait-Job &",
    "first &; ready && Get-Job | Wait-Job",
    "first &; ready &&\nGet-Job | Wait-Job",
    "first &; (Get-Job | Wait-Job)",
    "first &; Write-Output 'Get-Job | Wait-Job'",
])
def test_partial_conditional_nested_or_trailing_powershell_wait_does_not_hide_background(tmp_path, command):
    assert any(f.check == "shell.background" for f in findings(tmp_path, command, "powershell"))


@pytest.mark.parametrize("dialect,command,expected", [
    ("bash", "a & disown; wait", "shell.background"),
    ("bash", "nohup a & wait", "shell.detach"),
    ("bash", "setsid a & wait", "shell.detach"),
    ("powershell", "Start-Process worker; Get-Job | Wait-Job", "shell.detach"),
    ("powershell", "Start-Job { worker }; Get-Job | Wait-Job", "shell.detach"),
])
def test_final_wait_does_not_exempt_explicit_detach_commands(tmp_path, dialect, command, expected):
    assert any(f.check == expected for f in findings(tmp_path, command, dialect))
