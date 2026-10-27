"""Synthetic artifact controls; no behavior cases, judge, or host is executed."""
import json

import pytest

from conftest import SKILL
from scripts.evals.checks import CheckContext
from scripts.evals.checks import SCRIPTED_CHECKS as CHECKS


def context(tmp_path, case):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    return CheckContext(SKILL / "evals" / case, tmp_path, SKILL, "python")


def save(ctx, name, value):
    path = ctx.outputs / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


def test_optional_research_control_distinguishes_enabled_collector(tmp_path):
    ctx = context(tmp_path, "research-queue-optional-summaries")
    rows = [{"check": "handoff.shared.missing", "field": name, "severity": "INFO"}
            for name in ("Current best", "Active compute", "Plan collection")]
    for name in ("solo", "team"):
        save(ctx, name + "/agents.md", "- Plan collector: off\n")
        save(ctx, name + "-check.json", rows)
    check = CHECKS[ctx.case_dir.name, "02-optional-severity.md"]
    assert check(ctx)[0]
    save(ctx, "team/agents.md", "- Plan collector: Shell/worker\n")
    assert not check(ctx)[0]
    save(ctx, "collector/agents.md", "- Plan collector: Shell/worker\n")
    save(ctx, "collector-check.json", rows)
    control = CHECKS[ctx.case_dir.name, "07-collector-control.md"]
    assert not control(ctx)[0]
    save(ctx, "collector-check.json", [{**row, "severity": "ERROR"} for row in rows])
    assert control(ctx)[0]


@pytest.mark.parametrize("heading", ["##", "###"])
def test_neutral_record_check_rejects_legacy_class_in_new_record(tmp_path, heading):
    ctx = context(tmp_path, "neutral-new-decision-records")
    check = CHECKS[ctx.case_dir.name, "01-research-method.md"]
    save(ctx, "research-discoveries.md", f"{heading} D-A-001 — Procedure\n- Decision class: method-change\n")
    assert check(ctx)[0]
    save(ctx, "research-discoveries.md", f"{heading} D-A-001 — Procedure\n- Decision class: model-change\n")
    assert not check(ctx)[0]


def test_minimal_setup_requires_inferred_flags_and_policy_specific_pointers(tmp_path):
    ctx = context(tmp_path, "minimal-quick-self-guidance")
    arguments = ["quick", "--preset", "quick", "--user", "operator"]
    save(ctx, "setup-results.json", {"quick_arguments": arguments})
    check = CHECKS[ctx.case_dir.name, "01-minimal-command.md"]
    assert check(ctx)[0]
    save(ctx, "setup-results.json", {"quick_arguments": arguments + ["--language=en"]})
    assert not check(ctx)[0]
    save(ctx, "quick/agents.md", "- Verification: self\n")
    save(ctx, "quick/discoveries.md", "# Findings\n")
    check = CHECKS[ctx.case_dir.name, "04-self-guidance.md"]
    assert check(ctx)[0]
    save(ctx, "quick/discoveries.md", "Read references/verification.md.\n")
    assert not check(ctx)[0]


def test_installer_runtime_check_ignores_paths_only_in_shim_comments(tmp_path):
    ctx = context(tmp_path, "installer-runtime-selection")
    runtime = "sandbox/.codex/skills/research-orchestrator/scripts/ro.py"
    data = {"upgrade": {"surviving_runtime": runtime, "shim_text": f"# {runtime}\nexit 0\n"}}
    save(ctx, "runtime-results.json", data)
    check = CHECKS[ctx.case_dir.name, "01-updated-cli.md"]
    assert not check(ctx)[0]
    data["upgrade"]["shim_text"] = f'exec python "{runtime}" "$@"\n'
    save(ctx, "runtime-results.json", data)
    assert check(ctx)[0]
