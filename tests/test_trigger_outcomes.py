"""Missing trigger evidence remains unknown, with a reproducible reason."""
import json
import subprocess

import pytest

from scripts.trigger import explain_results, run_trigger_eval as trigger
from scripts.trigger.outcomes import inconclusive_reason
from test_trigger_eval import run_mock, successful, raw
from scripts.evals.run_evals import DEFAULT_SKILL, load_case


@pytest.mark.parametrize("attempt,code", [
    ({"status": "timeout", "failure_category": "timeout", "detection": {"triggered": True}}, "timeout"),
    ({"status": "error", "failure_category": "rate_limit"}, "rate_limit"),
    ({"status": "error", "failure_category": "transport"}, "transport"),
    ({"status": "error", "error": "Cannot inventory installed skills"}, "setup_error"),
    ({"status": "error", "returncode": 1, "error": "executor failed"}, "executor_error"),
    ({"status": "error", "returncode": 0}, "incomplete_execution"),
    ({"status": "ok"}, "missing_measurement"),
    ({"status": "contaminated", "failure_category": "timeout"}, "contamination"),
    ({"status": "ok", "candidate_changed": True, "triggered": True}, "contamination"),
    ({"status": "ok", "triggered": True, "detection": {"other_skill_paths": [{"path": "outside/SKILL.md"}]}},
     "contamination"),
])
def test_inconclusive_classification_keeps_cause_and_no_prediction(attempt, code):
    run = {"triggered": attempt.get("triggered"), "attempts": [attempt]}
    result = trigger.summarize([{"should_trigger": True, "runs": [run]}], .5)
    row = result["results"][0]
    assert result["counts"]["inconclusive"] == 1
    assert row["predicted"] is row["pass"] is row["trigger_rate"] is None
    assert row["inconclusive_reasons"][0]["code"] == code
    assert row["inconclusive_reasons"][0]["detail"]
    assert row["inconclusive_reasons"][0]["repeat"] == 1


def test_failed_source_guess_is_not_reclassified_as_contamination():
    attempt = {"status": "ok", "triggered": True, "contamination": {
        "contaminated": False, "findings": [{"reason": "source_repository", "contaminating": False}]}}
    assert inconclusive_reason(attempt) is None


@pytest.mark.parametrize("run,code", [
    ({"status": "timeout"}, "timeout"),
    ({"attempts": [None]}, "invalid_record"),
    ({"contamination": True}, "invalid_record"),
    ({"contamination": {"findings": [None]}}, "invalid_record"),
    ({"status": []}, "invalid_record"),
    ({"failure_category": []}, "invalid_record"),
    ({"returncode": {}}, "invalid_record"),
    ({"triggered": True, "attempts": [{"status": "ok", "triggered": False}]}, "inconsistent_measurement"),
    ({"status": "ok", "triggered": True, "detection": {"triggered": False}}, "inconsistent_measurement"),
    ({"status": "ok", "triggered": True, "returncode": 1}, "incomplete_execution"),
    ({"status": "ok", "triggered": True, "returncode": 0, "failure_category": "executor"}, "incomplete_execution"),
])
def test_contradictory_or_malformed_records_never_earn_scores(run, code):
    row = trigger.summarize([{"should_trigger": True, "runs": [run]}], .5)["results"][0]
    assert row["predicted"] is None
    assert row["inconclusive_reasons"][0]["code"] == code


def test_explicit_selection_endpoint_allows_owned_process_termination():
    record = {"status": "ok", "triggered": True, "returncode": -9,
              "measurement_protocol": "first-selection-v1", "selection_boundary": {"event": 6}}
    assert inconclusive_reason(record) is None
    record["triggered"] = False
    assert inconclusive_reason(record)["code"] == "incomplete_execution"


def test_declared_repeat_shortfall_is_unknown():
    rows = [{"should_trigger": True, "runs": [{"status": "ok", "triggered": True}]}]
    result = explain_results.explain({"threshold": .5, "repeats": 3, "metrics": {"all": {"results": rows}}})
    row = result["metrics"]["all"]["results"][0]
    assert row["predicted"] is None
    assert row["inconclusive_reasons"][0]["code"] == "repeat_count_mismatch"


def test_saved_timeout_selection_never_becomes_a_retrospective_success():
    attempt = {"status": "timeout", "triggered": None, "detection": {"triggered": True}}
    reason = inconclusive_reason(attempt)
    assert reason["code"] == "timeout" and "Selection was observed" in reason["detail"]


def test_repeat_numbers_and_empty_repeat_classification():
    result = trigger.summarize([
        {"should_trigger": True, "runs": [{"triggered": True}, {"status": "timeout", "triggered": None}]},
        {"should_trigger": False, "runs": []},
    ], .5)
    first, second = result["results"]
    assert first["inconclusive_reasons"][0]["repeat"] == 2
    assert second["inconclusive_reasons"][0]["code"] == "missing_repeats"
    assert result["coverage"] == 0 and result["accuracy"] is None


def test_retry_recovery_scores_only_final_attempt(tmp_path, monkeypatch):
    result, _ = run_mock(tmp_path, monkeypatch, [
        (1, raw({"type": "error", "message": "stream disconnected before completion"}), ""), successful])
    assert result["inconclusive_reason"] is None
    assert result["attempts"][0]["inconclusive_reason"]["code"] == "transport"
    assert inconclusive_reason(result) is None
    assert trigger.summarize([{"should_trigger": True, "runs": [result]}], .5)["counts"]["tp"] == 1


def test_setup_exception_is_saved_with_reason(tmp_path, monkeypatch):
    result, _ = run_mock(tmp_path, monkeypatch, [subprocess.SubprocessError("launch unavailable")])
    assert result["inconclusive_reason"]["code"] == "setup_error"
    saved = json.loads((tmp_path / "result/attempt-1/run.json").read_text())
    assert saved["inconclusive_reason"] == result["inconclusive_reason"]


def test_explain_saved_results_preserves_original_attempts_and_file(tmp_path):
    rows = [{"should_trigger": True, "runs": [{"status": "contaminated", "triggered": None, "attempts": [{
        "status": "contaminated", "triggered": None, "detection": {"triggered": True},
        "contamination": {"contaminated": True, "findings": [{"reason": "source_repository"}]},
        "failure_category": "timeout"}]}]}]
    original = {"threshold": .5, "metrics": {"all": {"results": rows}}, "skill_sha256": "original"}
    source, output = tmp_path / "original.json", tmp_path / "explained.json"
    source.write_text(json.dumps(original))
    before = source.read_bytes()
    assert explain_results.main([str(source), "--output", str(output)]) == 0
    assert source.read_bytes() == before
    result = json.loads(output.read_text())
    row = result["metrics"]["all"]["results"][0]
    assert row["runs"] == rows[0]["runs"] and result["skill_sha256"] == "original"
    assert row["predicted"] is None
    assert row["inconclusive_reasons"] == [{"repeat": 1, "code": "contamination",
                                            "detail": "Excluded context: source_repository"}]
    assert explain_results.main([str(source), "--output", str(output)]) == 2
    assert explain_results.main([str(source), "--output", str(source)]) == 2
    assert source.read_bytes() == before


def test_strict_case_fixture_discriminates_unknown_from_false_and_recovers_retries():
    case = load_case(DEFAULT_SKILL / "evals/trigger-measurement-reasons")
    data = json.loads((case.path / "files/measurements.json").read_text())
    result = trigger.summarize(data["queries"], data["threshold"], data["repeats"])
    assert result["counts"] == {"tp": 2, "tn": 1, "fp": 0, "fn": 0, "inconclusive": 9}
    assert result["coverage"] == .25 and result["accuracy"] == 1
    classified = {row["query"]: row for row in result["results"]}
    assert classified["exposed-context"]["inconclusive_reasons"][0] == {
        "repeat": 2, "code": "contamination", "detail": "Excluded context: source_repository"}
    assert classified["selected-timeout"]["inconclusive_reasons"][0]["code"] == "timeout"
    assert classified["throttled"]["inconclusive_reasons"][0]["code"] == "rate_limit"
    assert classified["unavailable"]["inconclusive_reasons"][0]["code"] == "setup_error"
    assert classified["empty-query"]["inconclusive_reasons"][0]["code"] == "missing_repeats"
    for query, code in (("contradictory-summary", "inconsistent_measurement"),
                        ("malformed-attempt", "invalid_record"), ("missing-measurement", "missing_measurement"),
                        ("short-repeat", "repeat_count_mismatch")):
        assert classified[query]["inconclusive_reasons"][0]["code"] == code
    assert classified["contradictory-summary"]["inconclusive_reasons"][1]["code"] == "inconsistent_measurement"
    # Changing an actual valid measurement changes the oracle's prediction.
    changed = data["queries"][0]
    for run in changed["runs"]:
        run["triggered"] = run["attempts"][-1]["triggered"] = False
    assert trigger.summarize(data["queries"], .5, data["repeats"])["counts"]["fn"] == 1
