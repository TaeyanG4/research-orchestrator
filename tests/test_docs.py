"""Release documentation budgets and reachability apply to all nested references."""

import importlib.util
import re
import shutil

from conftest import ROOT, SKILL, init, rs


SPEC = importlib.util.spec_from_file_location("release_docs", ROOT / "scripts" / "validate_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_every_reference_is_reachable():
    errors = []
    release.check_core_split(errors)
    assert errors == []


def test_stale_v2_assets_removed_and_readme_translations_share_structure():
    readmes = list(ROOT.glob("README*.md"))
    texts = [path.read_text(encoding="utf-8") for path in readmes]
    for name in ("setup.svg", "hero.svg", "take-over.svg", "cross-host-check.svg"):
        assert not (ROOT / "assets" / "readme" / name).exists()
        assert all(f"assets/readme/{name}" not in text for text in texts)
    structures = [[len(match[1]) for match in re.finditer(r"^(#+) ", text, re.M)] for text in texts]
    assert all(structure == structures[0] for structure in structures)


def test_generated_reading_pointers_resolve_for_all_presets():
    for name in (None, *rs.BUILTIN_PRESETS):
        preset = rs.load_preset(name) if name else None
        flags = {"platforms": "host-one"} if preset and preset["platform_mode"] == "single" else {}
        values = rs.resolve(flags, preset, {})
        rendered = init.render_agents(values, "example")
        references = re.findall(r"`(?:<skill-root>/)?(references/[\w./-]+\.md)`", rendered)
        assert bool(references) == (name is not None), name
        assert "core's operation table" in rendered
        for reference in references:
            assert (SKILL / reference).is_file(), (name, reference)


def test_note_identifier_kind_has_a_documented_role():
    text = (SKILL / "references" / "operations-safety.md").read_text(encoding="utf-8")
    assert "`N-<slot>-<number>`" in text and "user-maintained note" in text


def test_release_workflow_runs_all_hosts_with_read_only_permissions():
    text = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read\n" in text
    assert "os: [windows-latest, ubuntu-latest, macos-latest]" in text
    assert "runs-on: ${{ matrix.os }}" in text
    assert "python-version: '3.12'" in text
    assert "run: python scripts/validate_release.py" in text
    assert "run: python -m pip install pytest" in text
    assert "persist-credentials: false" in text
    assert "${{ secrets." not in text
    assert not re.search(r"(?m)^\s*(?:permissions:\s*write-all|[\w-]+:\s*write)\s*$", text)
    fixture = SKILL / "evals" / "release-ci-matrix" / "files" / "validate.yml"
    assert fixture.read_text(encoding="utf-8") == text


def test_reviewer_has_only_read_tools_and_verification_pointer():
    agent = ROOT / "agents" / "ro-reviewer.md"
    text = agent.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    assert "name: ro-reviewer\n" in frontmatter
    assert re.findall(r"^tools: (.+)$", frontmatter, re.M) == ["Read, Grep, Glob"]
    verification = (SKILL / "references" / "verification.md").read_text(encoding="utf-8")
    link = re.search(r"\[reviewer instructions\]\(([^)]+)\)", verification)
    assert link and (SKILL / "references" / link[1]).is_file()
    fixture = SKILL / "evals" / "reviewer-read-only" / "files" / "ro-reviewer.md"
    assert fixture.read_text(encoding="utf-8") == text


def test_direct_skill_install_has_self_contained_review_instructions(tmp_path):
    installed = tmp_path / "project" / ".claude" / "skills" / SKILL.name
    shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("evals", "__pycache__"))
    errors = []
    release.check_core_split(errors, installed)
    assert errors == []
    assert not (tmp_path / "agents" / "ro-reviewer.md").exists()
    verification = (installed / "references" / "verification.md").read_text(encoding="utf-8")
    link = re.search(r"\[reviewer instructions\]\(([^)]+)\)", verification)[1]
    reviewer = installed / "references" / link
    assert reviewer.is_file()
    assert "[verification](verification.md)" in reviewer.read_text(encoding="utf-8")


def test_release_rejects_repository_only_reference_even_when_it_exists(tmp_path, monkeypatch):
    skill = tmp_path / "skill"
    skill.mkdir()
    refs = reference_tree(skill, monkeypatch)
    (tmp_path / "reviewer.md").write_text("Repository-only reviewer\n", encoding="utf-8")
    with (refs / "start.md").open("a", encoding="utf-8") as stream:
        stream.write("[Reviewer](../../reviewer.md)\n")
    errors = []
    release.check_core_split(errors, skill)
    assert errors == ["references/start.md: link leaves installed skill ../../reviewer.md"]


def test_openai_interface_covers_v3_scope_and_resume():
    text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
    for field in ("short_description", "default_prompt"):
        value = re.search(rf"^  {field}: (.+)$", text, re.M)[1].lower()
        assert all(word in value for word in ("work project", "research", "competition"))
    assert "Resume existing state" in text


def test_release_accepts_compact_goal_shapes_but_requires_evidence():
    for prefix in ([], ["Claimed"]):
        for goal in ("Goal", "Hypothesis"):
            fields = [*prefix, goal, "Evidence", "Next test"]
            assert fields in release.WORK_PLAN_SHAPES
            assert [field for field in fields if field != "Evidence"] not in release.WORK_PLAN_SHAPES


def reference_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "REFERENCE_FILES", ("start.md",))
    references = tmp_path / "references"
    (references / "nested").mkdir(parents=True)
    (tmp_path / "SKILL.md").write_text("[Read](references/start.md)\n", encoding="utf-8")
    (references / "start.md").write_text("[Details](nested/details.md#details)\n", encoding="utf-8")
    (references / "nested" / "details.md").write_text("# Details\n", encoding="utf-8")
    return references


def test_release_follows_links_and_rejects_orphans_even_when_named_in_template(tmp_path, monkeypatch):
    references = reference_tree(tmp_path, monkeypatch)
    errors = []
    release.check_core_split(errors, tmp_path)
    assert errors == []
    (references / "nested" / "orphan.md").write_text("No route here\n", encoding="utf-8")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "AGENTS.md.template").write_text("references/nested/orphan.md\n", encoding="utf-8")
    release.check_core_split(errors, tmp_path)
    assert errors == ["references/nested/orphan.md is not reachable from SKILL.md"]


def test_release_budgets_count_utf8_bytes_at_the_boundary(tmp_path, monkeypatch):
    references = reference_tree(tmp_path, monkeypatch)
    core = tmp_path / "SKILL.md"
    link = core.read_text(encoding="utf-8")
    core.write_text(link + "x" * (release.SKILL_MAX_BYTES - len(link.encode("utf-8"))), encoding="utf-8", newline="\n")
    detail = references / "nested" / "details.md"
    detail.write_text("é" * (release.REFERENCE_MAX_BYTES // 2), encoding="utf-8")
    errors = []
    release.check_core_split(errors, tmp_path)
    assert errors == []
    core.write_text(core.read_text(encoding="utf-8") + "x", encoding="utf-8", newline="\n")
    detail.write_text(detail.read_text(encoding="utf-8") + "x", encoding="utf-8")
    release.check_core_split(errors, tmp_path)
    assert len(errors) == 2
    assert "SKILL.md is 12001 bytes" in errors[0]
    assert "references/nested/details.md is 10001 bytes" in errors[1]


def test_release_budgets_ignore_checkout_line_endings(tmp_path, monkeypatch):
    references = reference_tree(tmp_path, monkeypatch)
    core = tmp_path / "SKILL.md"
    link = core.read_bytes().replace(b"\r\n", b"\n")
    core.write_bytes(link + b"\n" * (release.SKILL_MAX_BYTES - len(link)))
    detail = references / "nested" / "details.md"
    detail.write_bytes(b"\n" * release.REFERENCE_MAX_BYTES)
    for path in (core, detail):
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    errors = []
    release.check_core_split(errors, tmp_path)
    assert errors == []
    detail.write_bytes(detail.read_bytes() + b"x")
    release.check_core_split(errors, tmp_path)
    assert errors == ["references/nested/details.md is 10001 bytes; the budget is 10000"]


def test_release_checks_nested_data_references_and_broken_links(tmp_path, monkeypatch):
    references = reference_tree(tmp_path, monkeypatch)
    (references / "start.md").write_text("[Data](nested/data.json) [Missing](lost.md)\n", encoding="utf-8")
    (references / "nested" / "data.json").write_text("{}\n", encoding="utf-8")
    errors = []
    release.check_core_split(errors, tmp_path)
    assert "references/start.md: broken link lost.md" in errors
    assert "references/nested/details.md is not reachable from SKILL.md" in errors
    assert not any("data.json" in error for error in errors)
