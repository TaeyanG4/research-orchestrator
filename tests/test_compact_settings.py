"""Collapsing defaults preserves policy and keeps generated pointers selective."""

import pytest

from conftest import check, found, init, make_project, rs, run_init
from test_presets import answers


@pytest.mark.parametrize("preset", rs.BUILTIN_PRESETS)
def test_collapsed_defaults_round_trip_all_presets(tmp_path, preset):
    target = make_project(tmp_path, preset, "--preset", preset, *answers(preset))
    path = target / "agents.md"
    before = path.read_text(encoding="utf-8")
    stored = rs.read_settings(before)
    assert set(rs.SETTING) <= set(stored.values)
    assert "<details>" in before
    assert init.rules_state(before, stored, rs.resolve({}, None, stored.values)) == "ok"
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    assert path.read_text(encoding="utf-8") == before
    assert not [i for i in check(target).issues if i.severity in {"ERROR", "WARN"}]


def test_quick_hides_default_noise_and_keeps_active_choices_visible(tmp_path):
    target = make_project(tmp_path, "quick", "--preset", "quick", "--platforms", "local")
    text = (target / "agents.md").read_text(encoding="utf-8")
    visible, collapsed = text.split("<details>", 1)
    assert len([line for line in visible.splitlines() if line.startswith("- ")]) <= 14
    for label in ("Guard thresholds", "Phase clock", "Competition", "Read bound", "Brief requirements"):
        assert f"- {label}:" not in visible and f"- {label}:" in collapsed
    assert "- Enforcement: block" in visible and "- Block: shell.background" in visible
    assert "references/sessions.md" not in text and "references/presets.md" not in text
    assert "core's operation table" in text


@pytest.mark.parametrize("label,value,pointer", [("Git sync", "commit", "git-sync"),
    ("Plan collector", "on — local / model", "plan-collector"), ("Language", "ko", "records"),
    ("External actions", "ship release", "external-actions")])
def test_edited_default_is_stale_not_tampered_and_reconfigures(tmp_path, label, value, pointer):
    target = make_project(tmp_path, "edit", "--preset", "quick", "--platforms", "local")
    (target / ".git").mkdir()
    path = target / "agents.md"
    text = path.read_text(encoding="utf-8")
    import re
    text = re.sub(rf"(?m)^- {label}: .*$", f"- {label}: {value}", text)
    path.write_text(text, encoding="utf-8", newline="\n")
    checker = check(target)
    assert found(checker, "WARN", "agents.rules.stale")
    assert not found(checker, check_id="agents.rules.edited")
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    after = path.read_text(encoding="utf-8")
    assert f"references/{pointer}.md" in after
    assert f"- {label}: {value}" in after.split("<details>", 1)[0]
    assert not found(check(target), check_id="agents.rules.stale")


def test_default_custom_project_has_no_generated_operation_list():
    values = rs.resolve({}, None, {})
    generated = init.compose_agents(values, "custom")
    assert "- `references/" not in generated
    assert "No additional references are active." in generated
    assert "\n\n\n" not in generated
