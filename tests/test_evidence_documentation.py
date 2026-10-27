"""Installed capability lookup and release notes stay useful without host probes."""

import re

from conftest import ROOT, SKILL


def check_rows(text):
    return {
        columns[0].strip("`"): columns[1:]
        for line in text.splitlines()
        if line.startswith("| `")
        for columns in [[part.strip() for part in line.strip("|").split("|")]]
    }


def test_installed_capability_matrix_contains_the_dated_check_host_evidence():
    installed = (SKILL / "references/hooks-capabilities.md").read_text(encoding="utf-8")
    evidence = (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
    matrix = check_rows(installed)
    assert not check_rows(evidence.split("## Dated host scope and interpretation", 1)[1])
    assert '../../skills/research-orchestrator/references/hooks-capabilities.md' in evidence
    assert set(matrix) == {
        "shell.background", "shell.detach", "shell.heredoc", "shell.cd", "jobs.mutate-bound",
        "jobs.read-bound", "jobs.unmonitored", "records.timestamp", "records.id", "publish.scan",
        "external.gate", "ask.away", "brief.requirements",
    }
    assert matrix["publish.scan"][1:3] == ["Unverified", "Unverified"]
    assert re.search(r"(?:no|unmapped).*(?:agent|tool)", matrix["brief.requirements"][2], re.I)
    assert re.search(r"persisted.{0,30}`/hooks`.{0,40}(?:not|unverified)", installed, re.I)
    assert re.search(r"(?:not|unverified).{0,80}(?:later|subsequent).{0,30}(?:repair|runtime)", installed, re.I)
    assert len(installed.encode("utf-8")) <= 10_000
    daily = (SKILL / "references/hooks.md").read_text(encoding="utf-8")
    assert "[hooks-capabilities.md](hooks-capabilities.md)" in daily
    assert "capability matrix" in daily


def test_all_readmes_link_probe_claims_to_host_records_and_matrix_to_installed_table():
    shapes = []
    for name in ("README.md", "README.ko.md", "README.ja.md", "README.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for host, record in (("Claude Code", "claude-code"), ("Codex", "codex")):
            row = next(line for line in text.splitlines() if line.startswith(f"| {host} |"))
            assert row.endswith("| `ro`, Git pre-push |")
            index = (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
            target = f"../host-dry-runs/{record}-2026-10-27.md"
            assert f"]({target})" in index
            assert (ROOT / "docs/evals" / target).is_file()
        assert text.count("](docs/evals/README.md)") == 1
        assert "](skills/research-orchestrator/references/hooks.md)" not in text
        assert "](skills/research-orchestrator/references/hooks-capabilities.md)" in text
        shapes.append([len(match[1]) for match in re.finditer(r"^(#+) ", text, re.M)])
    assert all(shape == shapes[0] for shape in shapes)


def test_plan_reconciles_contract_generation_and_the_two_folded_guards():
    text = (ROOT / "docs/plans/v3-plan.md").read_text(encoding="utf-8")
    reconciliation = text.split("## Reconciliation after round 10 (2026-10-27)", 1)[1]
    bullets = [line for line in reconciliation.splitlines() if line.startswith("- ")]
    contract = next(line for line in bullets if "brief.requirements" in line)
    assert {"brief.requirements", "ro brief --contract"} <= set(re.findall(r"`([^`]+)`", contract))
    assert re.search(r"(?:not implemented|unimplemented)", contract, re.I)
    for guard in ("G9", "G10"):
        row = next(line for line in bullets if guard in line)
        assert re.search(r"retract", row, re.I)
    assert {"Intake", "Rejected consistent gains", "Decisions"} <= set(re.findall(r"`([^`]+)`", reconciliation))
    assert re.search(r"(?:seven|7) days", reconciliation)
    assert "G3" in reconciliation
    for prefix in ("| G9 ", "| G10 ", "| Review checklists from memory"):
        row = next(line for line in text.splitlines() if line.startswith(prefix))
        assert "#reconciliation-after-round-10-2026-10-27" in row


def test_fixed_and_security_use_six_concise_user_facing_areas_without_provenance():
    # The six-area shape belongs to the 6.0.0 release notes; later patch notes are short.
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("\n## 6.0.0", 1)[1]
    areas = {
        "Jobs and shell", "Installation and hooks", "Records and verification",
        "State and migration", "External actions and publication", "Validation and runtime",
    }
    for section in ("Fixed", "Security"):
        body = text.split(f"### {section}\n", 1)[1].split("\n### ", 1)[0]
        bullets = [line for line in body.splitlines() if line.startswith("- ")]
        assert len(bullets) == 6
        assert {re.match(r"- \*\*([^:]+):\*\*", line)[1] for line in bullets} == areas
        assert all(len(line) <= 280 for line in bullets)
        assert all(not line.strip() or line.startswith("- ") for line in body.splitlines())
        assert not re.search(r"round[- ]\d|iteration-\d|ro-evidence-archive|2026-10-27|re-probed", body, re.I)
    evidence = (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
    provenance = evidence.split("## Release repair provenance", 1)[1].split("\n## ", 1)[0]
    for scope in ("Round-10", "Mocked regressions", "iteration-6", "--skip-tests", "full test gate"):
        assert scope in provenance
