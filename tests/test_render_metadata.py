"""Rendering metadata stays off the reading path without losing edit detection."""

import json

from conftest import check, found, init, make_project, rs, run_init


def test_single_host_marker_sidecar_and_repeat_reconfigure(tmp_path):
    target = make_project(tmp_path, "compact", "--preset", "quick", "--platforms", "local")
    agents = target / "agents.md"
    sidecar = target / ".ro" / "template-render.json"
    before = agents.read_bytes(), sidecar.read_bytes()
    text = before[0].decode()
    assert f"<!-- ro-template: {rs.CURRENT_TEMPLATE} -->" in text
    assert "pointers=" not in text and "external_actions_source=" not in text
    assert "- Platforms: single — local" in text and "- Platform mode:" not in text
    assert "workflow=classic" in json.loads(before[1])["render_key"]
    for _ in range(2):
        result = run_init(target, "--reconfigure")
        assert result.returncode == 0, result.stderr
        assert (agents.read_bytes(), sidecar.read_bytes()) == before


def test_sidecar_detects_unmigrated_workflow_and_preserves_user_region(tmp_path):
    target = make_project(tmp_path, "pending", "--preset", "quick", "--platforms", "local")
    path = target / "agents.md"
    text = path.read_text(encoding="utf-8").replace("- Workflow: classic", "- Workflow: unified")
    text += "\nKeep this user-owned rule.\n"
    path.write_text(text, encoding="utf-8")
    assert found(check(target), check_id="settings.workflow.unmigrated")
    refused = run_init(target, "--reconfigure")
    assert refused.returncode == 1 and "--migrate" in refused.stderr
    assert path.read_text(encoding="utf-8") == text
    migrated = run_init(target, "--reconfigure", "--migrate", "--user", "operator")
    assert migrated.returncode == 0, migrated.stderr
    assert path.read_text(encoding="utf-8").endswith("Keep this user-owned rule.\n")
    stored = rs.read_settings(path.read_text(encoding="utf-8"), target)
    assert stored.rendered["workflow"] == "unified"
    assert not found(check(target), check_id="settings.workflow.unmigrated")


def test_portable_files_without_sidecar_keep_effective_settings(tmp_path):
    target = make_project(tmp_path, "portable", "--preset", "quick", "--platforms", "local")
    sidecar = target / ".ro" / "template-render.json"
    before = check(target).values
    sidecar.unlink()
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    assert check(target).values == before
    assert sidecar.is_file()
