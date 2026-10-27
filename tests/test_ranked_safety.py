"""Regression probes for atomic claims, ancestor renames and shared credential formats."""

import re
import sys

import pytest

from conftest import SCRIPTS, SKILL, concurrent_results, item, set_queue, set_slot, unified_project
from ro_checks import Call, outcome, pre_checks
from ro_evidence import _patterns
from ro_markdown import mask_fences
from ro_state import Project, redact


def test_primary_unified_claim_procedure_uses_locked_cli():
    text = (SKILL / "references" / "workflow-unified.md").read_text(encoding="utf-8")
    first_step = text.split("## Claims\n", 1)[1].split("\n2.", 1)[0]
    assert "`ro --slot <slot> claim <ID>`" in first_step
    assert "lock" in first_step and "competing slots" in first_step


def test_competing_cli_claims_have_one_durable_winner(tmp_path):
    root = unified_project(tmp_path)
    set_slot(root, "A", "Codex")
    set_slot(root, "B", "Claude")
    set_queue(root, item("H-A-01"))
    body = ("import sys;sys.path.insert(0,sys.argv[1]);import ro;"
            "print('ready',flush=True);sys.stdin.readline();"
            "sys.exit(ro.main(['--project',sys.argv[2],'--slot',sys.argv[3],'claim','H-A-01']))")
    results = concurrent_results([[sys.executable, "-c", body, str(SCRIPTS), str(root), slot]
                                  for slot in ("A", "B")])
    winners = [slot for slot, (code, _, _) in zip(("A", "B"), results) if code == 0]
    assert len(winners) == 1, results
    assert sum("taken slot" in error for _, _, error in results) == 1, results
    claims = re.findall(r"^- Claimed: (.+)$", mask_fences((root / "plan.md").read_text(encoding="utf-8")), re.M)
    assert len(claims) == 1 and claims[0].startswith(winners[0] + " since ")


@pytest.mark.parametrize("operand", ["runs", "runs/job-a", "runs/job-a/input.txt"])
@pytest.mark.parametrize("form", ["Rename-Item -LiteralPath {path} -NewName previous",
                                  "Rename-Item -Path {path} -NewName previous",
                                  "Rename-Item {path} previous"])
@pytest.mark.parametrize("absolute", [False, True])
def test_rename_sources_protect_bound_ancestors(operand, form, absolute):
    root = "D:/project"
    jobs = [{"status": "running", "bound": [root + "/runs/job-a/input.txt"]}]
    values = {"environment": "windows/powershell", "enforcement": "block", "block": "jobs.mutate-bound"}
    command = form.format(path=(root + "/" if absolute else "") + operand)
    findings = pre_checks(Call("shell", "powershell", command), root, jobs, values)
    assert any(f.check == "jobs.mutate-bound" and outcome(f, values) == "block" for f in findings)


@pytest.mark.parametrize("command", ["Rename-Item -LiteralPath runs-copy -NewName previous",
                                     "Rename-Item runs/job-b previous",
                                     "Rename-Item -LiteralPath runs -NewName previous -WhatIf"])
def test_unaffected_sibling_and_dry_run_renames_remain_allowed(command):
    root = "D:/project"
    jobs = [{"status": "running", "bound": [root + "/runs/job-a"]}]
    values = {"environment": "windows/powershell", "enforcement": "block", "block": "jobs.mutate-bound"}
    assert pre_checks(Call("shell", "powershell", command), root, jobs, values) == []


@pytest.mark.parametrize("synthetic", ["github_pat_" + "aB9_" * 20, "ASIA" + "A1" * 8,
                                       "AKIA" + "A1" * 8, "ghp_" + "a_B9" * 80,
                                       "sk-proj-" + "a_B9-" * 80, "access_token=" + "A1" * 12])
def test_publication_recognition_and_redaction_share_complete_matches(tmp_path, synthetic):
    patterns = _patterns(Project(tmp_path))
    assert any(pattern.search(synthetic) for pattern in patterns)
    assert redact("before " + synthetic + " after") == "before [REDACTED] after"


def test_noncredential_diagnostic_text_is_preserved():
    text = "remote-id: archive-482; github_pat_short; ASIA-short; job completed"
    assert redact(text) == text
