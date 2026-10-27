"""Portable review contracts and versioned project policy stay inspectable."""

from __future__ import annotations

import hashlib
import re

from conftest import ROOT, SKILL, check, found, init, make_project, rs, run_init


def test_new_project_scaffolds_rule_replacements_without_new_checker_fields(tmp_path):
    target = make_project(tmp_path, "policy", "--preset", "quick", "--platforms", "local", "--git", "off")
    text = (target / "agents.md").read_text(encoding="utf-8")
    region = rs.split_agents(text)[1]
    assert "Replaces: <rule or none>" in region.split("### Active overrides", 1)[0]
    assert check(target).issues == []
    guidance = (SKILL / "references/project-rules.md").read_text(encoding="utf-8")
    assert "Replaces: <rule or none>" in guidance
    assert re.search(r"(?:remove|replace).{0,40}(?:obsolete|instruction)", guidance, re.I)
    assert re.search(r"not.{0,20}checker field", guidance, re.I)


def test_v34_upgrade_preserves_old_and_new_user_policy_verbatim(tmp_path):
    target = make_project(tmp_path, "policy-upgrade", "--preset", "quick", "--platforms", "local", "--git", "off")
    settings = check(target).values
    old_region = init.render(SKILL / "templates/v3.4/PROJECT_RULES.md.template",
                             {"{{STANDING_RULES_BUDGET}}": str(rs.STANDING_RULES_BUDGET)}, {})
    old_region += "\n- Before each schema change, save a snapshot. | Replaces: nightly snapshot\n"
    agents = target / "agents.md"
    agents.write_text(init.render_agents(settings, target.name, "v3.4") + "\n" + old_region,
                      encoding="utf-8", newline="\n")
    assert not found(check(target), check_id="agents.rules.edited")
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    assert rs.split_agents(agents.read_text(encoding="utf-8"))[1] == old_region
    assert not found(check(target), check_id="agents.rules.stale")


def test_v34_templates_are_frozen_with_their_released_bytes():
    assert rs.CURRENT_TEMPLATE == "v3.5"
    digests = {
        "AGENTS.md.template": "b9fa844d65a0601c686bca948e74cd862e3e945cb87c242dd5b40e8b087fa5ba",
        "PROJECT_RULES.md.template": "fbad56e0a33a2da8787733a92708c2aa45d8f7db6552e595216e06f3bc0efcc8",
    }
    for name, digest in digests.items():
        data = (SKILL / "templates/v3.4" / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest


def test_reviewer_contract_resolves_installed_policy_without_repository_cwd(tmp_path):
    # A plugin can be outside the caller's project and its ordinary Glob root.
    project = tmp_path / "project"
    installed = tmp_path / "plugin-cache" / "skills" / "research-orchestrator" / "references"
    project.mkdir()
    installed.mkdir(parents=True)
    policy = installed / "verification.md"
    policy.write_bytes((SKILL / "references/verification.md").read_bytes())
    assert not list(project.glob("**/research-orchestrator/references/verification.md"))
    assert list(tmp_path.glob("**/research-orchestrator/references/verification.md")) == [policy]
    assert policy.resolve().is_absolute()
    agent = (ROOT / "agents/ro-reviewer.md").read_text(encoding="utf-8")
    contract = (SKILL / "references/verification.md").read_text(encoding="utf-8")
    for text in (agent, contract):
        assert "absolute path" in text
        assert "Glob `**/research-orchestrator/references/verification.md`" in text
        assert "missing or ambiguous" in text
    assert "relative to this plugin's root" not in agent
    assert "tools: Read, Grep, Glob" in agent
    assert re.search(r"(?:missing|ambiguous).{0,100}(?:report|block|stop)", agent, re.I | re.S)


def test_safety_references_keep_constraint_groups_readable_and_bounded():
    for name in ("operations-safety.md", "external-actions.md"):
        text = (SKILL / "references" / name).read_text(encoding="utf-8")
        assert len(text.encode("utf-8")) <= 10_000
        prose = [paragraph for paragraph in re.split(r"\n\s*\n", text)
                 if not re.match(r"(?:#|- |\d+\.)", paragraph)]
        assert all(len(paragraph) <= 500 for paragraph in prose)
        assert re.search(r"\n[^\n]+\.\n\n- ", text)
    release = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("\n## 6.0.0", 1)[1]
    fixed = release.split("### Fixed\n", 1)[1].split("\n### ", 1)[0]
    assert len(re.findall(r"^- \*\*[^\n]+:\*\*", fixed, re.M)) == 6
    assert len(re.findall(r"^- ", fixed, re.M)) == 6

