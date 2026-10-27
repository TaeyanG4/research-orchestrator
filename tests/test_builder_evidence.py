"""Native execution failures remain auditable and cannot inflate behavioral coverage."""
import hashlib
from contextlib import ExitStack
import json
from pathlib import Path
import re
import zipfile

from scripts.evals.baseline import BASELINE_DIGEST, BASELINE_REVISION
from scripts.evals.export_evidence import verify_evidence
from scripts.evals.run_evals import DEFAULT_SKILL, load_cases


EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "evals" / "evidence"


def test_native_builder_attempts_retain_trace_pin_and_unavailable_grades():
    coverage = json.loads((EVIDENCE / "builder-coverage.json").read_text(encoding="utf-8"))
    raw_hashes = []
    with ExitStack() as stack:
        archives = {}
        for source in [coverage, *coverage.get("additional_archives", [])]:
            archive_path = EVIDENCE / source["archive"]
            assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == source["archive_sha256"]
            assert verify_evidence(archive_path) > 0
            archive = stack.enter_context(zipfile.ZipFile(archive_path))
            archives[source["archive"]] = archive
            for member in archive.namelist():
                assert not member.endswith(("events.jsonl", "transcript.md"))
        for attempt in coverage["attempts"]:
            archive = archives[attempt.get("archive", coverage["archive"])]
            run = json.loads(archive.read(attempt["archive_run"]))
            manifest = json.loads(archive.read("manifest.json"))
            withheld = next(row for row in manifest["omitted"] if row["path"] == attempt["archive_events"])
            raw_hashes.append(withheld["source_sha256"])
            grade = json.loads(archive.read(attempt["archive_grade"]))
            assert run["status"] == attempt["status"] == "timeout"
            assert run["failure_category"] == "timeout"
            assert grade["excluded"] and grade["summary"]["pass_rate"] is None
            assert grade["expectations"] == []
            timing_path = attempt["archive_run"].rsplit("/", 1)[0] + "/timing.json"
            assert attempt["total_tokens"] == json.loads(archive.read(timing_path))["total_tokens"]
            if run["config"] == "old_skill":
                assert run["baseline_revision"] == BASELINE_REVISION
                assert run["baseline_content_sha256"] == BASELINE_DIGEST
    assert len(raw_hashes) == len(set(raw_hashes)) == coverage["summary"]["attempted_runs"]


def test_followup_exclusions_preserve_unmeasured_results_and_unchanged_inputs():
    coverage = json.loads((EVIDENCE / "builder-coverage.json").read_text(encoding="utf-8"))
    benchmark = coverage["followup_aggregate"]
    assert benchmark["runs"] == [] and len(benchmark["excluded_runs"]) == 2
    assert all(value is None for value in benchmark["run_summary"]["delta"].values())
    for row in coverage["followup_analysis"]["runs"]:
        assert row["original_run_fields_preserved"]
        assert row["recorded_tool_executions"] == row["final_response_bytes"] == 0
        assert row["changed_inputs"] == row["new_task_artifacts"] == []
        assert row["assertion_pass_rate"] is None and row["timing"]["total_tokens"] is None
        for name, digest in row["input_sha256"].items():
            assert digest == row["output_files_sha256"][name]
        assert row["reported_runtime_integrity"]["unchanged"]


def test_builder_coverage_includes_unattempted_cases_without_pass_credit():
    coverage = json.loads((EVIDENCE / "builder-coverage.json").read_text(encoding="utf-8"))
    cases = coverage["cases"]
    assert {case["name"] for case in cases} == {case.name for case in load_cases(DEFAULT_SKILL)}
    assert coverage["summary"]["available_cases"] == len(cases)
    assert coverage["summary"]["valid_paired_cases"] == sum(case["valid_pair"] for case in cases)
    assert coverage["summary"]["pass_rate"] is None
    assert coverage["paired_aggregate"]["runs"] == []
    assert coverage["paired_aggregate"]["excluded_runs"]
    for case in cases:
        assert case["completed_configurations"] == []
        assert case["valid_pair"] is False and case["pass_rate"] is None


def test_recheck_preserves_original_evidence_and_discloses_runtime_mismatch():
    coverage = json.loads((EVIDENCE / "builder-coverage.json").read_text(encoding="utf-8"))
    benchmark = coverage["recheck_aggregate"]
    assert benchmark["runs"] == [] and len(benchmark["excluded_runs"]) == 2
    assert all(value is None for value in benchmark["run_summary"]["delta"].values())
    with zipfile.ZipFile(EVIDENCE / "builder-recheck-preflight.zip") as archive:
        analysis = json.loads(archive.read(coverage["recheck_analysis"]["archive_member"]))
        manifest = json.loads(archive.read("manifest.json"))
        source_hashes = {row["path"]: row["source_sha256"] for row in [*manifest["files"], *manifest["omitted"]]}
        assert analysis["original_retained_files_unchanged"]
        for name, original in analysis["original_retained_file_hashes"].items():
            assert source_hashes["recheck/" + name] == original["sha256"]
        for run in analysis["runs"]:
            assert run["task_tool_operations_observed"] == run["task_final_message_bytes"] == 0
            assert run["input_unchanged_byte_for_byte"]
            assert run["runtime_before_sha256"] == run["runtime_after_sha256"]
            matches = run["independently_recomputed_source_runtime_sha256"] == run["runtime_before_sha256"]
            assert run["source_runtime_matches_recorded_runtime"] is matches
            if run["configuration"] == "with_skill":
                assert not matches
