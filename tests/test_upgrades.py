"""Historical generated rules upgrade while edits and user regions stay protected."""

from __future__ import annotations

import hashlib
import shutil

import pytest

from conftest import FIXTURES, SKILL, check, copy_fixture, found, init, make_project, rs, run_init, severities

PROJECT_RULES = "## Project rules\n\n- Always review schema changes twice.\n  Keep  this   spacing.\n\n### Notes\n\n- end\n"
PROJECT_FILES = ("plan.md", "discoveries.md", "handoff.md")


@pytest.mark.parametrize("version", rs.FROZEN_TEMPLATES)
def test_every_frozen_template_renders_and_upgrades_without_force(tmp_path, version):
    target = make_project(tmp_path, "upgrade")
    path = target / "agents.md"
    values = check(target).values
    rendered = init.render_agents(values, target.name, version)
    assert "{{" not in rendered
    path.write_text(rendered + "\n" + PROJECT_RULES, encoding="utf-8", newline="\n")
    before = {name: (target / name).read_bytes() for name in PROJECT_FILES}
    initial = check(target)
    assert not found(initial, "ERROR", "settings.missing")
    assert not found(initial, check_id="agents.rules.edited")
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    assert rs.split_agents(path.read_text(encoding="utf-8"))[1] == PROJECT_RULES
    assert before == {name: (target / name).read_bytes() for name in before}
    upgraded = check(target)
    assert not found(upgraded, check_id="agents.rules.edited")
    assert not found(upgraded, check_id="agents.rules.stale")
    assert upgraded.values == initial.values


def test_next_template_version_recognises_frozen_v3_render(tmp_path, monkeypatch):
    old_version = rs.CURRENT_TEMPLATE
    next_version = "v99.0"
    settings = rs.resolve({}, None, {})
    old = init.render_agents(settings, "example")
    templates = tmp_path / "templates"
    frozen = templates / rs.CURRENT_TEMPLATE
    frozen.mkdir(parents=True)
    shutil.copyfile(init.TEMPLATES / "AGENTS.md.template", frozen / "AGENTS.md.template")
    current = (frozen / "AGENTS.md.template").read_text(encoding="utf-8").replace(
        f"ro-template: {old_version}", f"ro-template: {next_version}") + "\nA later generated pointer.\n"
    (templates / "AGENTS.md.template").write_text(current, encoding="utf-8")
    monkeypatch.setattr(init, "TEMPLATES", templates)
    monkeypatch.setattr(rs, "CURRENT_TEMPLATE", next_version)
    monkeypatch.setattr(rs, "TEMPLATE_VERSIONS", (*rs.TEMPLATE_VERSIONS, next_version))
    stored = rs.read_settings(old)
    assert stored.version == old_version
    assert init.render_agents(settings, "example", old_version) == old
    assert init.rules_state(old, stored, settings) == "stale"
    assert init.rules_state(old + "\nA hand edit.\n", stored, settings) == "edited"
    new = init.render_agents(settings, "example")
    assert init.rules_state(new, rs.read_settings(new), settings) == "ok"


@pytest.mark.parametrize("deleted", [("Guard set", "Guard thresholds"), ("Block",),
                                     ("Block", "External actions", "Publish scan", "Brief requirements")])
def test_missing_current_settings_are_structural_errors(tmp_path, deleted):
    target = make_project(tmp_path, "current")
    path = target / "agents.md"
    path.write_text("\n".join(line for line in path.read_text(encoding="utf-8").split("\n")
                              if not any(line.startswith(f"- {field}:") for field in deleted)),
                    encoding="utf-8", newline="\n")
    assert {issue.field for issue in found(check(target), "ERROR", "settings.missing")} == set(deleted)


def test_frozen_v2_fixture_reports_info_only(tmp_path) -> None:
    target = copy_fixture("v2", tmp_path / "v2")
    checker = check(target)
    assert checker.code == 0
    counts = severities(checker)
    assert counts["ERROR"] == 0 and counts["WARN"] == 0, [i.render() for i in checker.issues]
    assert [i.check for i in found(checker, "INFO")] == ["agents.settings.v2"]
    assert checker.values["workflow"] == "classic" and checker.values["verification"] == "cross-host-once"
    assert checker.values["preset"] == "custom"


def test_reconfigure_upgrades_v2_preserving_settings_and_user_region(tmp_path) -> None:
    target = copy_fixture("v2", tmp_path / "v2")
    (target / ".git").mkdir()
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\n" + PROJECT_RULES, encoding="utf-8", newline="\n")
    before = {name: (target / name).read_bytes() for name in PROJECT_FILES}
    original = check(target).values
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    text = agents.read_text(encoding="utf-8")
    assert rs.split_agents(text)[1] == PROJECT_RULES
    assert text.count("\n## Project rules\n") == 1
    assert {name: (target / name).read_bytes() for name in before} == before
    checker = check(target)
    assert checker.code == 0 and not found(checker, "WARN"), [i.render() for i in checker.issues]
    for key in ("preset", "workflow", "platform_mode", "git", "collector", "reviewer", "fallback"):
        assert checker.values[key] == original[key], key
    again = run_init(target, "--reconfigure", "--git", "commit")
    assert again.returncode == 0, again.stderr
    assert rs.split_agents(agents.read_text(encoding="utf-8"))[1] == PROJECT_RULES


def test_hand_edited_v2_rule_requires_force(tmp_path) -> None:
    target = copy_fixture("v2", tmp_path / "v2")
    agents = target / "agents.md"
    edited = agents.read_text(encoding="utf-8").replace("## Read order", "## Read order\n\nAn extra local rule.", 1)
    agents.write_text(edited, encoding="utf-8", newline="\n")
    refused = run_init(target, "--reconfigure")
    assert refused.returncode == 1 and agents.read_text(encoding="utf-8") == edited
    assert [i.check for i in found(check(target), "WARN")] == ["agents.rules.edited"]
    forced = run_init(target, "--reconfigure", "--force")
    assert forced.returncode == 0 and "An extra local rule." not in agents.read_text(encoding="utf-8")


def test_v2_setting_changes_are_stale_and_apply_without_force(tmp_path) -> None:
    target = copy_fixture("v2", tmp_path / "v2")
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace("- Git sync: push", "- Git sync: off"),
                      encoding="utf-8", newline="\n")
    assert [i.check for i in found(check(target), "WARN")] == ["agents.rules.stale"]
    applied = run_init(target, "--reconfigure")
    assert applied.returncode == 0, applied.stderr
    assert severities(check(target))["WARN"] == 0


# SHA-256 of the v2 example committed at cee6852, with LF line endings.
FROZEN_V2 = {
    "agents.md": "8f09f152952545cde76a8dd08ff92f3bc26161cdb1bc2d07edec679f8a7ac9e7",
    "plan.md": "ebe94feca0b27a601d50ceb2f1b5f990791d7cf9c2111b59207c5d2bb9e43ea7",
    "discoveries.md": "82d45767155c4917696a7d083eb896ed5c90460ac65f82396e06dd578ae59bde",
    "handoff.md": "116625cd1ab88e5051150f8924e02c7559b025251dfe2dabaea712dd2a6d6a37",
}


def test_fixture_is_the_frozen_v2_example() -> None:
    folder = FIXTURES / "v2"
    assert sorted(path.name for path in folder.iterdir()) == sorted(FROZEN_V2)
    for name, digest in FROZEN_V2.items():
        data = (folder / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, name


def test_frozen_v2_template_is_the_original_bytes() -> None:
    data = (SKILL / "templates" / "v2" / "AGENTS.md.template").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == "ab21a77bcd43999df96e898775854a714537026b74a1f5ad3d63a21fce357171"


@pytest.mark.parametrize("mode", ["single", "multi"])
def test_original_v2_template_upgrades_without_force(tmp_path, mode) -> None:
    target = copy_fixture("v2", tmp_path / "original")
    agents = target / "agents.md"
    stored = rs.read_settings(agents.read_text(encoding="utf-8"))
    settings = rs.resolve({}, None, stored.values)
    settings.update(platform_mode=mode, git="off")
    if mode == "single":
        settings.update(platforms="Claude Code", reviewer="off", collector="off")
        # The frozen example has two hosts. Build a valid single-host variant
        # before taking the preservation snapshot; do not ask upgrade to hide it.
        for name in ("discoveries.md", "handoff.md"):
            path = target / name
            text = path.read_text(encoding="utf-8").replace("Codex", "Claude Code")
            if name == "discoveries.md":
                text = text.replace(": CLOSED —", ": CLOSED — same host —")
            path.write_text(text, encoding="utf-8", newline="\n")
    rendered = init.render_agents(settings, "Original template project", "v2")
    region = "\n## Project rules\n\n- Retain the original local maintenance rule.\n"
    agents.write_text(rendered + region, encoding="utf-8", newline="\n")
    before = {name: (target / name).read_bytes() for name in PROJECT_FILES}
    initial = check(target)
    assert not found(initial, "ERROR"), [issue.render() for issue in initial.issues]
    assert not found(initial, check_id="agents.rules.edited")
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    upgraded = check(target)
    assert not found(upgraded, "ERROR"), [issue.render() for issue in upgraded.issues]
    assert not found(upgraded, check_id="agents.rules.stale")
    assert agents.read_text(encoding="utf-8").endswith(region)
    assert before == {name: (target / name).read_bytes() for name in before}


def test_changed_v2_executor_example_is_a_prose_edit(tmp_path) -> None:
    target = copy_fixture("v2", tmp_path / "edited")
    path = target / "agents.md"
    text = path.read_text(encoding="utf-8")
    edited = "\n".join("# Example: Other: Remote runner" if line.startswith("# Example: Other:") else line
                       for line in text.split("\n"))
    assert edited != text
    path.write_text(edited, encoding="utf-8", newline="\n")
    assert found(check(target), "WARN", "agents.rules.edited")
    result = run_init(target, "--reconfigure")
    assert result.returncode == 1 and path.read_text(encoding="utf-8") == edited
