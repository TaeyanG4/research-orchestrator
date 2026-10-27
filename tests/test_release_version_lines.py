"""The README release lines must name the manifest version."""
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_versions", ROOT / "scripts" / "validate_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
FILES = ["plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json",
         ".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json", *release.READMES]


def copy_tree(target: Path) -> None:
    for name in FILES:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target / name)


def test_current_readmes_match_manifest_version():
    errors = []
    release.check_manifests(errors)
    assert not [error for error in errors if "release line" in error]


def test_stale_readme_release_line_is_reported(tmp_path, monkeypatch):
    copy_tree(tmp_path)
    readme = tmp_path / "README.ko.md"
    version = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
    readme.write_text(readme.read_text(encoding="utf-8").replace(version, "0.0.1", 1), encoding="utf-8")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    errors = []
    release.check_manifests(errors)
    assert any("README.ko.md: release line names 0.0.1" in error for error in errors)
