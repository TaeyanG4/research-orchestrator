"""Stop leaves stdin untouched and starts no interpreter without either job registry."""

import json
from pathlib import Path

import pytest

from test_hook_root_termination import invoke, wrapper_command, wrapper_environment


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("registry", [None, ".ro/jobs.json", ".ro/recovery/jobs.json"])
def test_stop_checks_primary_and_recovery_registries_before_starting_python(tmp_path, wrapper, registry):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    project = tmp_path / "project"
    nested = project / "nested"
    nested.mkdir(parents=True)
    (project / "agents.md").write_text("# Rules\n", encoding="utf-8")
    if registry:
        path = project / registry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
    result = invoke([*command, "Stop", "--general"], nested, env)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    sentinel = Path(env["RO_TEST_SENTINEL"])
    if registry is None:
        assert json.loads(result.stdout) == {}
        assert not sentinel.exists()
    else:
        assert sentinel.read_text().splitlines() == ["started"]
        assert result.stdout.decode().splitlines()[-1] == '{"payload":"unchanged"}'
