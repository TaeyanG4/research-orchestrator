"""Historical generated rules upgrade while edits and user regions stay protected."""

from __future__ import annotations

import shutil

import pytest

from conftest import check, found, init, make_project, rs, run_init

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


def test_files_from_before_6_0_are_refused_with_the_upgrade_route(tmp_path) -> None:
    """7.0 reads only the v3 layout; a file without a template marker names the 6.0.x upgrade."""
    target = make_project(tmp_path, "old")
    path = target / "agents.md"
    text = path.read_text(encoding="utf-8")
    old = "\n".join(line for line in text.split("\n") if not line.startswith("<!-- ro-template:"))
    path.write_text(old, encoding="utf-8", newline="\n")
    errors = found(check(target), "ERROR", "agents.settings.unsupported")
    assert len(errors) == 1 and "6.0.x" in errors[0].message
    result = run_init(target, "--reconfigure")
    assert result.returncode == 1 and "predates release 6.0" in result.stderr
    assert path.read_text(encoding="utf-8") == old  # nothing is rewritten
