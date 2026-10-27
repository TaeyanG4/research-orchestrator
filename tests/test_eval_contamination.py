"""Access audits use operation evidence, and contamination cannot earn a score."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.evals import aggregate_evals as aggregate, contamination, grade_evals as grade, run_evals as runner


def layout(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("Source instructions", encoding="utf-8")
    workspace = tmp_path / "workspace"
    run = workspace / "iteration-1" / "example" / "with_skill"
    run.mkdir(parents=True)
    root = workspace / "_runs" / "this-run"
    return run, {"source_repo": source, "workspace": workspace,
                 "project": root / "project", "runtime": root / "skill",
                 "baseline_roots": [tmp_path / "separate-baseline"]}


def command_event(command, **fields):
    return {"type": "item.completed", "item": {"type": "command_execution", "command": command,
                                                "exit_code": 0, **fields}}


def save_events(run, *events):
    (run / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")


def legacy_eval_run(run, policy, *paths):
    """Saved findings from the old whole-path reserved-name check."""
    report = contamination.audit_run(run, **policy)
    report.update(contaminated=True, findings=[{
        "reason": "eval_or_grader_path", "path": str(path),
        "resolved_path": contamination._resolved(str(path), str(policy["project"])),
        "operation": "command_execution", "evidence": f"events.jsonl:{number}",
        "contaminating": True, "outcome": "attempted_access",
    } for number, path in enumerate(paths, 1)])
    return {"returncode": 0, "error": None, "status": "contaminated", "executor_status": "completed",
            "contaminated": True, "contamination": report, "excluded": True,
            "exclusion_reason": contamination.CONTAMINATION_EXCLUSION_REASON}


@pytest.mark.parametrize("ancestor", ["evals", "graders"])
def test_assigned_trees_ignore_reserved_ancestor_names(tmp_path, ancestor):
    nested = tmp_path / ancestor
    nested.mkdir()
    run, policy = layout(nested)
    save_events(run, command_event(f'Get-Content "{policy["runtime"] / "SKILL.md"}"'),
                command_event("Get-Content ./brief.md"),
                command_event(f'Get-ChildItem "{policy["project"].parent}"'),
                command_event(f'Get-Content "{run / "evidence" / "receipt.json"}"'))
    assert not contamination.audit_run(run, **policy)["contaminated"]


@pytest.mark.parametrize("boundary", ["project", "runtime", "evidence"])
@pytest.mark.parametrize("reserved", ["evals", "graders"])
def test_reserved_descendants_stay_forbidden_in_assigned_trees(tmp_path, boundary, reserved):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    root = run / "evidence" if boundary == "evidence" else policy[boundary]
    save_events(run, command_event(f'Get-Content "{root / reserved / "answer.md"}"'))
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert {finding["reason"] for finding in report["findings"]} == {"eval_or_grader_path"}


def test_powershell_array_and_python_raw_paths_are_literal_operands(tmp_path):
    run, policy = layout(tmp_path)
    policy.update(workspace=Path("H:/lab/evals"), project=Path("H:/lab/evals/_runs/one/project"),
                  runtime=Path("H:/lab/evals/_runs/one/skill"))
    first, second = [policy["runtime"] / name for name in ("SKILL.md", "references/session.md")]
    joined = f"{first},{second}"
    raw = "r" + str(first)
    save_events(run, command_event(f"Get-Content '{first}','{second}'"),
                command_event(f"checker = Path(r'{first}')"))
    assert not contamination.audit_run(run, **policy)["contaminated"]
    saved = legacy_eval_run(run, policy, joined, raw)
    report = contamination.audit_saved_run(run, saved)
    assert not report["contaminated"] and report["reclassified_previous_contamination"]
    # Splitting a list must still expose a forbidden operand in that same list.
    save_events(run, command_event(f"Get-Content '{first}','{policy['runtime'] / 'graders/answer.md'}'"))
    assert contamination.audit_saved_run(run, saved)["contaminated"]


def test_reaudit_requires_each_original_operation_to_be_reproduced(tmp_path):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    first, second = policy["runtime"] / "SKILL.md", policy["project"] / "brief.md"
    save_events(run, command_event(f'Get-Content "{first}"'), command_event(f'Get-Content "{second}"'))
    saved = legacy_eval_run(run, policy, first, second)
    report = contamination.audit_saved_run(run, saved)
    assert not report["contaminated"] and len(report["reclassified_findings"]) == 2
    save_events(run, command_event(f'Get-Content "{first}"'))
    assert contamination.audit_saved_run(run, saved)["contaminated"]


def test_reclassification_cannot_erase_a_runtime_integrity_finding(tmp_path):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    target = policy["runtime"] / "SKILL.md"
    save_events(run, command_event(f'Get-Content "{target}"'))
    saved = legacy_eval_run(run, policy, target)
    saved["contamination"]["findings"].append({"reason": "runtime skill modified", "operation": "content_digest"})
    assert contamination.audit_saved_run(run, saved)["contaminated"]


def ancestor_probe(path, *, directory=False):
    assignment = "$rules = Join-Path $candidate 'AGENTS.md'; " if directory else ""
    target = "$rules" if directory else "$candidate"
    return (f"$candidates = @('{path}'); foreach ($candidate in $candidates) {{ {assignment}"
            f"if (Test-Path -LiteralPath {target}) {{ Write-Output {target}; "
            f"Get-Content -LiteralPath {target} -Raw }} }}")


@pytest.mark.parametrize("directory", [False, True])
def test_absent_ancestor_instruction_probe_is_not_other_run_access(tmp_path, directory):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    target = policy["workspace"] if directory else policy["workspace"] / "AGENTS.md"
    command = ancestor_probe(target, directory=directory)
    save_events(run, {"type": "item.started", "item": {"type": "command_execution", "command": command,
                                                     "status": "in_progress", "exit_code": None}},
                command_event(command, aggregated_output=""))
    report = contamination.audit_run(run, **policy)
    assert not report["contaminated"]
    assert any(f["outcome"] == "absent_ancestor_instructions" for f in report["findings"])
    saved = legacy_eval_run(run, policy, target)
    assert contamination.audit_saved_run(run, saved)["reclassified_previous_contamination"]
    # Recovery needs the actual completed probe, not an empty or partial trace.
    save_events(run)
    assert contamination.audit_saved_run(run, saved)["contaminated"]
    save_events(run, {"type": "item.started", "item": {"type": "command_execution", "command": command,
                                                     "status": "in_progress", "exit_code": None}})
    assert contamination.audit_saved_run(run, saved)["contaminated"]


@pytest.mark.parametrize("defect", ["exists", "output", "bare-contents", "missing-output", "error", "failed", "unguarded", "unrelated-loop",
                                    "extra-read", "other-file", "other-run", "directory-listing"])
def test_instruction_probe_exception_cannot_hide_real_or_unconfirmed_access(tmp_path, defect):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    target = policy["workspace"] / "AGENTS.md"
    fields = {"aggregated_output": ""}
    if defect == "exists":
        target.write_text("Private workspace instructions", encoding="utf-8")
    elif defect == "output":
        fields["aggregated_output"] = str(target) + "\nPrivate workspace instructions"
    elif defect == "bare-contents":
        fields["aggregated_output"] = "Private workspace instructions without a filename"
    elif defect == "missing-output":
        fields.pop("aggregated_output")
    elif defect == "error":
        fields["error"] = "Permission denied"
    elif defect == "failed":
        fields["exit_code"] = 1
    elif defect == "other-file":
        target = target.with_name("answers.md")
    elif defect == "other-run":
        target = policy["workspace"] / "_runs" / "other" / "AGENTS.md"
    command = ancestor_probe(target)
    if defect == "unguarded":
        command = f"Get-Content '{target}'"
    elif defect == "unrelated-loop":
        command = command.replace("in $candidates", "in $otherPaths")
    elif defect == "extra-read":
        command += "; Get-Content -LiteralPath $candidate"
    elif defect == "directory-listing":
        command = f"Get-ChildItem '{policy['workspace']}'"
    save_events(run, command_event(command, **fields))
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert not report.get("reclassified_previous_contamination")


def test_ancestor_probe_with_native_help_requires_filename_announcement(tmp_path):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    target = policy["workspace"] / "AGENTS.md"
    command = ancestor_probe(target).replace("Write-Output $candidate",
                                            "Get-Item -LiteralPath $candidate | Select-Object FullName")
    command += f"; python '{policy['runtime'] / 'init.py'}' --help"
    fields = {"aggregated_output": "usage: init.py [-h]\n\noptions:\n  -h, --help show help\n"}
    save_events(run, command_event(command, **fields))
    assert not contamination.audit_run(run, **policy)["contaminated"]
    save_events(run, command_event(command.replace(
        "Get-Item -LiteralPath $candidate | Select-Object FullName; ", ""), **fields))
    assert contamination.audit_run(run, **policy)["contaminated"]


@pytest.mark.parametrize("structured", [False, True])
def test_code_looking_file_names_remain_real_operands(tmp_path, structured):
    run, policy = layout(tmp_path)
    path = "import x/evals/answer.md"
    event = ({"type": "file_read", "path": path, "success": True} if structured
             else command_event(f'Get-Content "{path}"'))
    save_events(run, event)
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert any(f["path"] == path and f["contaminating"] for f in report["findings"])


@pytest.mark.parametrize("form", ["python", "here-string", "here-string-flags", "here-string-implicit-stdin"])
def test_embedded_program_is_not_itself_a_path_but_embedded_operands_are_checked(tmp_path, form):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    target = policy["runtime"] / "SKILL.md"
    code = f"from pathlib import Path; p=Path(r'{target}'); print(p.read_text())"
    stdin_args = {"here-string": "-", "here-string-flags": "-B -u -", "here-string-implicit-stdin": ""}
    command = f'python -c "{code}"' if form == "python" else f"@'\n{code}\n'@ | python {stdin_args[form]}"
    save_events(run, command_event(command))
    report = contamination.audit_run(run, **policy)
    assert not report["contaminated"]
    code_findings = [f for f in report["findings"] if f["outcome"] == "code_not_path"]
    assert code_findings
    saved = legacy_eval_run(run, policy, *[f["path"] for f in code_findings])
    assert contamination.audit_saved_run(run, saved)["reclassified_previous_contamination"]
    save_events(run, command_event(command.replace(str(target), str(policy["runtime"] / "graders" / "answer.md"))))
    assert contamination.audit_saved_run(run, saved)["contaminated"]


@pytest.mark.parametrize("form", ["python", "here-string-flags", "here-string-implicit-stdin"])
def test_program_extraction_keeps_source_other_run_and_installed_negative_controls(tmp_path, host_context, form):
    run, policy = layout(tmp_path)
    targets = [policy["source_repo"] / "README.md", policy["workspace"] / "_runs" / "other" / "answer.md",
               Path(host_context["installed_skill_roots"][0]) / "installed" / "SKILL.md"]
    for target in targets:
        code = f"from pathlib import Path; print(Path(r'{target}').read_text())"
        command = (f'python -c "{code}"' if form == "python" else
                   f"@'\n{code}\n'@ | python " + ("-B -" if form == "here-string-flags" else ""))
        save_events(run, command_event(command))
        assert contamination.audit_run(run, **policy, host_context=host_context)["contaminated"]


def test_failed_shell_parse_does_not_turn_whole_command_into_a_path(tmp_path):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    target = policy["runtime"] / "SKILL.md"
    command = f'''powershell -Command "@'\nfrom pathlib import Path\np=Path(r'{target}')\n'@ | python -B -'''
    save_events(run, command_event(command))
    report = contamination.audit_run(run, **policy)
    assert not report["contaminated"]
    assert any(f["path"] == command and f["outcome"] == "code_not_path" for f in report["findings"])
    saved = legacy_eval_run(run, policy, command)
    assert contamination.audit_saved_run(run, saved)["reclassified_previous_contamination"]
    # Parse failure still exposes literal foreign operands; it is no exemption.
    save_events(run, command_event(command.replace(str(target), str(policy["runtime"] / "graders/answer.md"))))
    assert contamination.audit_saved_run(run, saved)["contaminated"]


def test_comma_delimited_relative_ancestor_probe_is_recoverable(tmp_path):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    command = ancestor_probe("../../..", directory=True).replace("@('../../..')", "@('../../..', '.')")
    save_events(run, command_event(command, aggregated_output=""))
    report = contamination.audit_run(run, **policy)
    assert not report["contaminated"]
    saved = legacy_eval_run(run, policy, "../../..,")
    assert contamination.audit_saved_run(run, saved)["reclassified_previous_contamination"]
    (policy["workspace"] / "AGENTS.md").write_text("Private instructions", encoding="utf-8")
    assert contamination.audit_saved_run(run, saved)["contaminated"]


def test_array_filename_comma_is_not_a_delimiter_or_absent_parent_probe(tmp_path):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    command = ancestor_probe("../../..,", directory=True)
    save_events(run, command_event(command, aggregated_output=""))
    assert contamination.audit_run(run, **policy)["contaminated"]


def test_multiline_filename_is_not_exempted_by_an_unrelated_here_string(tmp_path):
    run, policy = layout(tmp_path)
    filename = "evals/first line\nanswer.md"
    command = f'''Get-Content '{filename}'\n@'\nprint('hello')\n'@ | python -B -'''
    save_events(run, command_event(command))
    report = contamination.audit_run(run, **policy)
    assert any(f["path"] == filename and f["contaminating"] for f in report["findings"])


@pytest.mark.parametrize("code", [
    "assert folder.name != 'evals'",
    "changed = value.replace('workspace/evals', 'recorded/area')",
    "print('No evals copied; inputs preserved.')",
    "print(f'Copied {count} files; no evals directory.')",
    "ignore = shutil.ignore_patterns('evals', '*.pyc')",
    "# The evals word is only data\npass",
])
def test_python_literal_data_is_not_file_access_and_cannot_hide_a_read(tmp_path, code):
    run, policy = layout(tmp_path)
    command = f"@'\n{code}\n'@ | python -B -"
    save_events(run, command_event(command))
    assert not contamination.audit_run(run, **policy)["contaminated"]
    target = "workspace/evals" if "workspace/evals" in code else "evals"
    saved = legacy_eval_run(run, policy, target)
    assert contamination.audit_saved_run(run, saved)["reclassified_previous_contamination"]
    for changed in (command + f"\nGet-Content '{target}'",
                    command.replace("\n'@", f"\nfrom pathlib import Path\nPath('{target}').read_text()\n'@")):
        save_events(run, command_event(changed))
        assert contamination.audit_saved_run(run, saved)["contaminated"]


def test_powershell_name_predicate_does_not_exempt_a_later_read(tmp_path):
    run, policy = layout(tmp_path)
    command = "Get-ChildItem . -Directory | Where-Object { $_.Name -eq 'evals' }"
    save_events(run, command_event(command))
    saved = legacy_eval_run(run, policy, "evals")
    assert contamination.audit_saved_run(run, saved)["reclassified_previous_contamination"]
    save_events(run, command_event(command + "; Get-Content evals"))
    assert contamination.audit_saved_run(run, saved)["contaminated"]


def test_python_stdin_reads_use_preceding_shell_directory_change(tmp_path):
    run, policy = layout(tmp_path)
    program = "@'\nfrom pathlib import Path\nprint(Path('README.md').read_text())\n'@ | python -B -"
    save_events(run, command_event(f"Set-Location '{policy['source_repo']}'\n{program}"))
    report = contamination.audit_run(run, **policy)
    assert any(f["outcome"] == "successful_read" and f["resolved_path"].endswith("source/README.md")
               for f in report["findings"])


@pytest.mark.parametrize("case_name, expected_included, expected_excluded", [
    ("evaluation-trace-audit", {"staged-runtime", "ancestor-probe", "python-program", "prompt-only"},
     {"source-read", "other-run", "hidden-grader", "installed-skill", "ancestor-present",
      "absent-trace", "runtime-modified"}),
    ("evaluation-trace-code-operands",
     {"python-flags", "python-implicit-stdin", "unparsed-command", "ancestor-array",
      "python-data-literals", "powershell-name-filter"},
     {"python-source", "python-installed", "python-other-run", "unparsed-grader", "ancestor-present",
      "ancestor-comma-filename", "missing-trace", "python-data-then-read", "filter-then-read"}),
])
def test_trace_audit_case_discriminates_through_real_auditor(tmp_path, case_name, expected_included, expected_excluded):
    case = runner.load_cases(runner.DEFAULT_SKILL, [case_name])[0]
    data = json.loads((case.path / "files" / "trace-cases.json").read_text(encoding="utf-8"))
    results = {}
    for scenario in data["scenarios"]:
        root = tmp_path / scenario["name"]
        paths = {name: root / relative for name, relative in data["path_variables"].items()}

        def expand(value):
            if isinstance(value, str):
                for name, path in paths.items():
                    value = value.replace("{" + name + "}", path.as_posix())
            elif isinstance(value, list):
                return [expand(item) for item in value]
            elif isinstance(value, dict):
                return {expand(key): expand(item) for key, item in value.items()}
            return value

        for filename, content in expand({**data["existing_files"], **scenario.get("extra_files", {})}).items():
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        run = paths["workspace"] / "iteration-1" / "case" / "with_skill"
        run.mkdir(parents=True)
        save_events(run, *expand(scenario["events"]))
        policy = {"source_repo": paths["source"], "workspace": paths["workspace"],
                  "project": paths["project"], "runtime": paths["runtime"],
                  "host_context": {"installed_skill_roots": [str(paths["installed"].parent)]}}
        report = contamination.audit_run(run, **policy)
        saved = {"contamination": report}
        if scenario.get("previous_findings"):
            findings = expand(scenario["previous_findings"])
            for finding in findings:
                finding["resolved_path"] = contamination._resolved(finding["path"], str(paths["project"]))
            saved = {"status": "contaminated", "contamination": {
                **report, "contaminated": True, "findings": findings}}
        results[scenario["name"]] = contamination.audit_saved_run(run, saved)
        if scenario["name"] == "ancestor-probe":
            # A changed input snapshot turns the positive control negative.
            (paths["workspace"] / "AGENTS.md").write_text("Private instructions", encoding="utf-8")
            assert contamination.audit_saved_run(run, saved)["contaminated"]
    included = {name for name, report in results.items() if not report["contaminated"]}
    assert included == expected_included
    assert {name for name in results if name not in included} == expected_excluded


@pytest.mark.parametrize("independent_exclusion", [None, "manual review required", "transport failure"])
def test_regrade_recovers_proven_false_positive_without_erasing_other_exclusions(tmp_path, monkeypatch,
                                                                              independent_exclusion):
    nested = tmp_path / "evals"
    nested.mkdir()
    run, policy = layout(nested)
    target = policy["runtime"] / "SKILL.md"
    save_events(run, command_event(f'Get-Content "{target}"'))
    saved = legacy_eval_run(run, policy, target)
    if independent_exclusion:
        saved["exclusion_reason"] = independent_exclusion
    (run / "transcript.md").write_text("Saved executor trace", encoding="utf-8")
    runner.write_json(run / "run.json", saved)
    runner.write_json(run / "timing.json", {"total_duration_seconds": 1})
    runner.write_json(run / "grading.json", {"excluded": True, "summary": {"pass_rate": None}})
    runner.write_json(run / "grading_status.json", {"excluded": True, "error": saved["exclusion_reason"]})
    case = runner.Case(tmp_path, "example", "Task", "Result", (runner.Assertion(Path("01-result.md"), "Result"),))
    runner.write_json(run.parent / "eval_metadata.json", {"assertions": [a.text for a in case.assertions]})
    calls = []

    def check(context):
        calls.append(context)
        return True, "Saved result verified"

    monkeypatch.setitem(grade.SCRIPTED_CHECKS, (case.name, "01-result.md"), check)
    # Aggregation cannot turn an old exclusion placeholder into a fresh score.
    assert aggregate.generate_benchmark(run.parent.parent)["runs"] == []
    result = grade.grade_run(case, run)
    if independent_exclusion:
        assert result["excluded"] and result["exclusion_reason"] == independent_exclusion
        assert calls == []
    else:
        assert result["summary"]["pass_rate"] == 1 and len(calls) == 1
        restored = json.loads((run / "run.json").read_text(encoding="utf-8"))
        assert restored["status"] == "completed" and not restored["contaminated"]
        benchmark = aggregate.generate_benchmark(run.parent.parent)
        assert len(benchmark["runs"]) == 1 and benchmark["excluded_runs"] == []


@pytest.fixture
def host_context(tmp_path):
    home = tmp_path / "host home"
    codex_home = tmp_path / "custom codex home"
    return {"user_home": str(home), "codex_home": str(codex_home),
            "home_variables": {"HOME": str(home), "USERPROFILE": str(home)},
            "installed_skill_roots": [str(home / name / "skills") for name in (".codex", ".agents", ".claude")]
                                     + [str(codex_home / "skills")],
            "global_agents": {"path": str(codex_home / "AGENTS.md"), "size_bytes": 12, "empty": False}}


@pytest.mark.parametrize("root", [".codex", ".agents", ".claude"])
@pytest.mark.parametrize("spelling", ["absolute", "relative", "~", "$HOME", "${HOME}",
                                     "$env:USERPROFILE", "${env:USERPROFILE}", "%USERPROFILE%"])
def test_installed_skill_access_resolves_real_home_paths(tmp_path, host_context, root, spelling):
    run, policy = layout(tmp_path)
    target = Path(host_context["user_home"]) / root / "skills" / "installed" / "SKILL.md"
    if spelling == "absolute":
        path = str(target).swapcase().replace("/", "\\") if os.name == "nt" else str(target)
    elif spelling == "relative":
        path = os.path.relpath(target, policy["project"])
    else:
        path = f"{spelling}/{root}/skills/installed/SKILL.md"
    save_events(run, command_event(f'Get-Content "{path}"', exit_code=1))
    report = contamination.audit_run(run, **policy, host_context=host_context)
    assert report["contaminated"]
    assert "installed_skill" in {finding["reason"] for finding in report["findings"]}


@pytest.mark.parametrize("target,reason", [("skills/installed/SKILL.md", "installed_skill"),
                                          ("AGENTS.md", "global_agents")])
def test_custom_codex_home_and_tool_workdir_access(tmp_path, host_context, target, reason):
    run, policy = layout(tmp_path)
    save_events(run, {"type": "tool_use", "name": "Read", "input": {
        "file_path": target, "cwd": "$env:CODEX_HOME"}})
    report = contamination.audit_run(run, **policy, host_context=host_context)
    assert reason in {finding["reason"] for finding in report["findings"]}
    save_events(run, {"type": "file_read", "path": "$env:CODEX_HOME/" + target})
    assert contamination.audit_run(run, **policy, host_context=host_context)["contaminated"]


def test_powershell_automatic_home_without_home_environment(tmp_path, host_context):
    run, policy = layout(tmp_path)
    host_context["home_variables"].pop("HOME")
    save_events(run, command_event(r'Get-Content "$HOME\.agents\skills\installed\SKILL.md"'))
    report = contamination.audit_run(run, **policy, host_context=host_context)
    assert report["contaminated"] and report["findings"][0]["reason"] == "installed_skill"


@pytest.mark.parametrize("size", [None, 0, 12])
def test_global_agents_only_flags_a_nonempty_snapshot(tmp_path, host_context, size):
    run, policy = layout(tmp_path)
    host_context["global_agents"].update(size_bytes=size, empty=size == 0 if size is not None else None)
    save_events(run, {"type": "file_read", "path": host_context["global_agents"]["path"]})
    report = contamination.audit_run(run, **policy, host_context=host_context)
    assert report["contaminated"] == bool(size)
    if size:
        assert report["findings"][0]["reason"] == "global_agents"


def test_host_paths_take_precedence_over_allowed_trees(tmp_path, host_context):
    run, policy = layout(tmp_path)
    policy["project"] = Path(host_context["user_home"]) / "project"
    policy["runtime"] = Path(host_context["codex_home"])
    save_events(run, command_event(f'Get-Content "{host_context["installed_skill_roots"][0]}/SKILL.md"'),
                command_event(f'Get-Content "{host_context["global_agents"]["path"]}"'))
    report = contamination.audit_run(run, **policy, host_context=host_context)
    assert {finding["reason"] for finding in report["findings"]} == {"installed_skill", "global_agents"}


def test_installed_skill_audit_does_not_flag_siblings_project_paths_or_prose(tmp_path, host_context):
    run, policy = layout(tmp_path)
    installed = host_context["installed_skill_roots"][0]
    save_events(run, command_event(f'Get-Content "{installed}-other/SKILL.md"'),
                command_event("Get-Content .codex/skills/local/SKILL.md"),
                {"type": "agent_message", "text": f"Avoid {installed} and {host_context['global_agents']['path']}"},
                {"type": "tool_use", "name": "Write", "input": {
                    "file_path": "notes.md", "content": f"Avoid {installed}"}})
    assert not contamination.audit_run(run, **policy, host_context=host_context)["contaminated"]


@pytest.mark.parametrize("target", ["installed", "global"])
def test_saved_host_audit_uses_original_paths_and_size(tmp_path, host_context, monkeypatch, target):
    run, policy = layout(tmp_path)
    report = contamination.audit_run(run, **policy, host_context=host_context)
    assert not report["contaminated"]
    # Rechecking a saved trace must not substitute the current host or restat AGENTS.md.
    for key in ("CODEX_HOME", "HOME", "USERPROFILE"):
        monkeypatch.setenv(key, str(tmp_path / "different-host"))
    path = "~/.agents/skills/installed/SKILL.md" if target != "global" else host_context["global_agents"]["path"]
    event = command_event(f'Get-Content "{path}"')
    (run / "transcript.md").write_text(runner.render_transcript("Task", [event], "Done"), encoding="utf-8")
    saved = json.loads(json.dumps({"contamination": report}))
    audited = contamination.audit_saved_run(run, saved)
    assert audited["contaminated"]
    assert audited["policy"]["host_context"] == host_context


@pytest.mark.parametrize("target,reason", [
    ("source", "source_repository"), ("source-case", "eval_or_grader_path"),
    ("relative-eval", "eval_or_grader_path"), ("relative-grader", "eval_or_grader_path"),
    ("other-output", "other_workspace_run"), ("other-temp", "other_workspace_run"),
    ("baseline", "baseline_snapshot"), ("custom-baseline", "baseline_snapshot"),
    ("relative-source", "source_repository"), ("windows-spelling", "source_repository"),
])
def test_detects_forbidden_command_paths(tmp_path, target, reason):
    run, policy = layout(tmp_path)
    targets = {"source": policy["source_repo"] / "README.md",
               "source-case": policy["source_repo"] / "evals" / "case" / "case.yaml",
               "relative-eval": "evals/case/case.yaml", "relative-grader": r"..\graders\01-result.md",
               "other-output": run.parent / "old_skill" / "outputs" / "answer.md",
               "other-temp": policy["workspace"] / "_runs" / "another-run" / "project" / "answer.md",
               "baseline": policy["workspace"] / "old-skill-snapshot" / "SKILL.md",
               "custom-baseline": policy["baseline_roots"][0] / "SKILL.md",
               "relative-source": os.path.relpath(policy["source_repo"] / "README.md", policy["project"]),
               "windows-spelling": (str(policy["source_repo"] / "README.md").swapcase() if os.name == "nt"
                                    else str(policy["source_repo"] / "README.md")).replace("\\", "/")}
    save_events(run, command_event(f'Get-Content "{targets[target]}"',
                                   exit_code=0 if reason == "source_repository" else 1))
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert reason in {finding["reason"] for finding in report["findings"]}
    assert all(finding["evidence"].startswith("events.jsonl:") for finding in report["findings"])


@pytest.mark.parametrize("event", [
    {"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": "graders/01.md"}]}},
    {"type": "file_read", "file_path": "evals/case.yaml"},
    {"type": "response_item", "payload": {"type": "function_call", "name": "read_file",
                                           "arguments": '{"path": "evals/case.yaml"}'}},
    {"type": "tool_use", "name": "Read", "input": {"file_path": "graders/01.md"}},
    {"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "exec_command",
                                          "arguments": {"cmd": "cat evals/case.yaml"}}},
])
def test_detects_structured_file_and_tool_access(tmp_path, event):
    run, policy = layout(tmp_path)
    save_events(run, event)
    assert contamination.audit_run(run, **policy)["contaminated"]


def test_operation_workdir_is_resolved_before_relative_access(tmp_path):
    run, policy = layout(tmp_path)
    save_events(run, command_event("cat README.md", cwd=str(policy["source_repo"])))
    assert contamination.audit_run(run, **policy)["contaminated"]


def trace_read(path, *, completed, exit_code=None, output="", item_id="item_12"):
    # current-sol-2/query-01-repeat-1, events 23/26: the model guessed
    # <source>/references/presets.md, then PowerShell reported PathNotFound.
    command = ('"C:\\\\Windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe" '
               f'-Command "Get-Content -LiteralPath \'{path}\'"')
    return {"type": "item.completed" if completed else "item.started", "item": {
        "id": item_id, "type": "command_execution", "command": command,
        "aggregated_output": output, "exit_code": exit_code,
        "status": "completed" if completed and exit_code == 0 else "failed" if completed else "in_progress"}}


def test_trigger_trace_missing_source_guess_is_only_a_finding(tmp_path):
    run, policy = layout(tmp_path)
    guessed = policy["source_repo"] / "references" / "presets.md"
    save_events(run, trace_read(guessed.as_posix(), completed=False),
                trace_read(guessed.as_posix(), completed=True, exit_code=1,
                           output=f"Get-Content : '{guessed}'\nFullyQualifiedErrorId : PathNotFound,"
                                  "Microsoft.PowerShell.Commands.GetContentCommand"))
    report = contamination.audit_run(run, **policy)
    assert not report["contaminated"]
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["reason"] == "source_repository"
    assert finding["outcome"] == "failed" and not finding["contaminating"]
    assert finding["evidence"] == "events.jsonl:2"


def test_trigger_trace_later_real_source_read_stays_contaminated(tmp_path):
    run, policy = layout(tmp_path)
    # In the same trace, events 31/33 read the corrected source location.
    real = policy["source_repo"] / "skills" / "research-orchestrator" / "references" / "presets.md"
    real.parent.mkdir(parents=True)
    real.write_text("# Presets and settings", encoding="utf-8")
    guessed = policy["source_repo"] / "references" / "presets.md"
    save_events(run, trace_read(guessed.as_posix(), completed=True, exit_code=1),
                trace_read(real.as_posix(), completed=False, item_id="item_16"),
                trace_read(real.as_posix(), completed=True, exit_code=0,
                           output="# Presets and settings", item_id="item_16"),
                trace_read(real.as_posix(), completed=True, exit_code=1, item_id="item_30"))
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert len(report["findings"]) == 2
    successful = [finding for finding in report["findings"] if finding["contaminating"]]
    assert len(successful) == 1 and successful[0]["outcome"] == "successful_read"
    assert successful[0]["evidence"] == "events.jsonl:3"


@pytest.mark.parametrize("path,inside", [
    ("H:/lab/tools/research-orchestrator/references/presets.md", True),
    ("H:/lab/tools/research-orchestrator-workspace/_trigger-runs/one/SKILL.md", False),
    ("H:/lab/tools/research-orchestrator-other/README.md", False),
    (r"H:\lab\tools\research-orchestrator\..\research-orchestrator-workspace\one", False),
])
def test_trigger_source_ancestry_compares_components(path, inside):
    source = contamination._normal("H:/lab/tools/research-orchestrator")
    assert contamination._within(contamination._normal(path), source) is inside


@pytest.mark.parametrize("cwd_field", ["cwd", "workdir", "working_directory"])
@pytest.mark.parametrize("outer", [False, True])
def test_relative_source_read_uses_command_cwd_not_project(tmp_path, cwd_field, outer):
    run, policy = layout(tmp_path)
    event = command_event("Get-Content ./README.md")
    (event if outer else event["item"])[cwd_field] = str(policy["source_repo"])
    save_events(run, event)
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert Path(report["findings"][0]["resolved_path"]) == policy["source_repo"] / "README.md"


@pytest.mark.parametrize("change", ["cd", "Set-Location -LiteralPath", "pushd"])
def test_relative_source_read_honors_shell_directory_change(tmp_path, change):
    run, policy = layout(tmp_path)
    save_events(run, command_event(f'{change} "{policy["source_repo"]}"; Get-Content ./README.md'))
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert any(finding["contaminating"] and Path(finding["resolved_path"]) == policy["source_repo"] / "README.md"
               for finding in report["findings"])


@pytest.mark.parametrize("command,exit_code,status,outcome", [
    ("Get-Content README.md", 1, "failed", "failed"),
    ("Get-Content README.md", None, "in_progress", "unconfirmed"),
    ("Get-Content README.md", None, "completed", "unconfirmed"),
    ("Get-Content missing.md", 0, "completed", "not_a_file"),
    ("Get-Content .", 0, "completed", "not_a_file"),
    ("Write-Output README.md", 0, "completed", "not_a_read"),
])
def test_source_access_requires_completed_read_of_real_file(tmp_path, command, exit_code, status, outcome):
    run, policy = layout(tmp_path)
    save_events(run, command_event(command, exit_code=exit_code, status=status,
                                   cwd=str(policy["source_repo"])))
    report = contamination.audit_run(run, **policy)
    assert not report["contaminated"]
    assert report["findings"] and {finding["outcome"] for finding in report["findings"]} == {outcome}


def test_source_path_echo_in_a_different_statement_is_not_a_read(tmp_path):
    run, policy = layout(tmp_path)
    save_events(run, command_event(f'Get-Content ./notes.md; Write-Output "{policy["source_repo"] / "README.md"}"'))
    report = contamination.audit_run(run, **policy)
    assert not report["contaminated"]
    assert report["findings"][0]["outcome"] == "not_a_read"


def test_successful_source_file_read_event(tmp_path):
    run, policy = layout(tmp_path)
    save_events(run, {"type": "file_read", "path": str(policy["source_repo"] / "README.md"), "success": True})
    assert contamination.audit_run(run, **policy)["contaminated"]


@pytest.mark.parametrize("code,reads", [
    ("print('README.md')", False),
    ("print(Path('README.md'))", False),
    ("open('README.md', 'w').write('replacement')", False),
    ("open('README.md').read()", True),
    ("Path('README.md').read_text()", True),
])
def test_python_source_access_requires_literal_read_not_print(tmp_path, code, reads):
    run, policy = layout(tmp_path)
    save_events(run, command_event(f'python -c "{code}"', cwd=str(policy["source_repo"])))
    assert contamination.audit_run(run, **policy)["contaminated"] is reads


def test_python_script_execution_reads_script_but_does_not_infer_argument_reads(tmp_path):
    run, policy = layout(tmp_path)
    script = policy["source_repo"] / "inspect.py"
    script.write_text("print('done')", encoding="utf-8")
    save_events(run, command_event(f'python -B "{script}" "{policy["source_repo"] / "README.md"}"'))
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert [Path(finding["resolved_path"]).name for finding in report["findings"] if finding["contaminating"]] == ["inspect.py"]


def test_runtime_project_and_prose_are_not_access_to_source(tmp_path):
    run, policy = layout(tmp_path)
    # A workspace nested in the source repository still has allowed staged trees.
    policy["source_repo"] = tmp_path
    events = [command_event(f'Get-Content "{policy["runtime"] / "SKILL.md"}"'),
              command_event(f'python "{policy["project"] / "analyze.py"}"'),
              {"type": "item.completed", "item": {"type": "agent_message", "text": "Never read evals/ or graders/"}},
              {"type": "file_change", "changes": [{"path": "notes.md", "content": "Do not read evals/private"}]}]
    save_events(run, *events)
    (run / "transcript.md").write_text(runner.render_transcript("Read evals/ answers", events,
                                                               "I avoided graders/"), encoding="utf-8")
    assert not contamination.audit_run(run, **policy)["contaminated"]


def test_transcript_event_fallback_and_reaudit_cannot_clear_previous_flag(tmp_path):
    run, policy = layout(tmp_path)
    event = command_event("cat graders/01.md")
    (run / "transcript.md").write_text(runner.render_transcript("Task", [event], "Done"), encoding="utf-8")
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"] and report["findings"][0]["evidence"].startswith("transcript.md:")
    (run / "transcript.md").write_text("No events left", encoding="utf-8")
    assert contamination.audit_saved_run(run, {"contamination": report})["contaminated"]


def test_own_evidence_remains_readable_under_source_without_exempting_other_files(tmp_path):
    run, policy = layout(tmp_path)
    policy["source_repo"] = tmp_path
    save_events(run, command_event(f'Get-Content "{run / "evidence" / "request" / "receipt.json"}"'))
    assert not contamination.audit_run(run, **policy)["contaminated"]
    (run / "run.json").write_text("{}", encoding="utf-8")
    receipt = run.parent / "old_skill" / "evidence" / "receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}", encoding="utf-8")
    save_events(run, command_event(f'Get-Content "{run / "run.json"}"'),
                command_event(f'Get-Content "{run.parent / "old_skill" / "evidence" / "receipt.json"}"'))
    report = contamination.audit_run(run, **policy)
    assert report["contaminated"]
    assert len(report["findings"]) == 2


def test_own_temp_root_and_file_tool_contents_are_not_other_run_access(tmp_path):
    run, policy = layout(tmp_path)
    save_events(run, command_event("Get-ChildItem .."),
                command_event(f'Get-ChildItem "{policy["project"].parent}"'),
                {"type": "tool_use", "name": "Write", "input": {
                    "file_path": "notes.md", "content": "Never read evals/case.yaml or graders/01.md"}},
                {"type": "function_call", "name": "functions.edit_file", "arguments": json.dumps({
                    "path": "notes.md", "old_text": "graders/private", "new_text": "evals/private"})})
    assert not contamination.audit_run(run, **policy)["contaminated"]
    save_events(run, command_event("Get-ChildItem ../.."))
    assert contamination.audit_run(run, **policy)["contaminated"]


def test_contaminated_run_is_excluded_before_scripted_or_judge_grading(tmp_path, monkeypatch):
    monkeypatch.setattr(grade, "JUDGED_CHECKS", grade.JUDGED_CHECKS | {("example", "90-quality.md")})
    run, policy = layout(tmp_path)
    (run / "outputs").mkdir()
    (run / "transcript.md").write_text("trace", encoding="utf-8")
    report = contamination.audit_run(run, **policy)
    runner.write_json(run / "run.json", {"returncode": 0, "error": None, "contamination": report})
    runner.write_json(run / "timing.json", {"total_duration_seconds": 2})
    # Re-audit catches accesses added after the original audit, including stale positive grades.
    save_events(run, command_event("cat evals/expected.md"))
    case = runner.Case(tmp_path, "example", "Task", "Result", (
        runner.Assertion(Path("01-result.md"), "Result"), runner.Assertion(Path("90-quality.md"), "Useful")))

    def unexpected(*args, **kwargs):
        pytest.fail("Contaminated evidence must not be scored")

    monkeypatch.setitem(grade.SCRIPTED_CHECKS, (case.name, "01-result.md"), unexpected)
    monkeypatch.setattr(grade, "judge_run", unexpected)
    result = grade.grade_run(case, run)
    assert result["excluded"] and result["summary"]["pass_rate"] is None
    assert result["expectations"] == []
    assert json.loads((run / "run.json").read_text(encoding="utf-8"))["status"] == "contaminated"
    assert json.loads((run / "grading_status.json").read_text(encoding="utf-8"))["excluded"]


def test_aggregate_reports_exclusions_and_ignores_stale_positive_grade(tmp_path, capsys):
    iteration = tmp_path / "iteration-1"
    for case, contaminated, rate in (("clean", False, .25), ("leaked", True, 1)):
        run = iteration / case / "with_skill"
        run.mkdir(parents=True)
        texts = [f"Result {index}" for index in range(4)]
        runner.write_json(run.parent / "eval_metadata.json", {"assertions": texts})
        runner.write_json(run / "run.json", {"returncode": 0, "contaminated": contaminated})
        runner.write_json(run / "timing.json", {"total_duration_seconds": 1, "total_tokens": None})
        runner.write_json(run / "grading.json", {"summary": {"passed": int(4 * rate), "failed": int(4 * (1-rate)),
                                                               "total": 4, "pass_rate": rate},
                          "expectations": [{"text": text, "passed": index < int(4 * rate), "evidence": "Saved trace"}
                                           for index, text in enumerate(texts)]})
    benchmark = aggregate.generate_benchmark(iteration)
    assert benchmark["run_summary"]["with_skill"]["pass_rate"]["mean"] == .25
    assert len(benchmark["runs"]) == 1
    assert benchmark["excluded_runs"][0]["run_dir"] == "leaked/with_skill"
    assert benchmark["excluded_runs"][0]["reason"] == "contaminated"
    assert aggregate.main([str(iteration)]) == 1
    assert "Excluded leaked/with_skill: contaminated" in capsys.readouterr().out
    assert "leaked/with_skill: contaminated" in (iteration / "benchmark.md").read_text(encoding="utf-8")


def test_all_contaminated_runs_produce_no_numeric_comparison(tmp_path):
    run = tmp_path / "case" / "old_skill"
    run.mkdir(parents=True)
    runner.write_json(run / "run.json", {"status": "contaminated"})
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"] == [] and len(benchmark["excluded_runs"]) == 1
    assert benchmark["run_summary"]["delta"]["pass_rate"] is None
