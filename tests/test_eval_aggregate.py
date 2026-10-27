"""Benchmark comparisons exclude judge errors and use matched valid cases."""
from __future__ import annotations

import json

import pytest

from scripts.evals import aggregate_evals as aggregate, run_evals as runner


def save_run(root, case, config, *, rate=.5, seconds=10, tokens=100, error=None,
             contaminated=False):
    run = root / case / config
    run.mkdir(parents=True)
    texts = [f"Useful result {index}" for index in range(4)]
    runner.write_json(run.parent / "eval_metadata.json", {"assertions": texts})
    runner.write_json(run / "run.json", {"returncode": 0, "contaminated": contaminated})
    runner.write_json(run / "timing.json", {"total_duration_seconds": seconds, "total_tokens": tokens})
    runner.write_json(run / "grading.json", {
        "summary": {"passed": int(4 * rate), "failed": int(4 * (1 - rate)), "total": 4, "pass_rate": rate},
        "expectations": [{"text": text, "passed": index < int(4 * rate),
                          "evidence": f"Result row {index}: observed {'present' if index < int(4 * rate) else 'absent'}."}
                         for index, text in enumerate(texts)],
    })
    runner.write_json(run / "grading_status.json", {"error": error})
    return run


@pytest.mark.parametrize("error,rate", [("Codex judge timed out", 0),
                                       ("judge response requires an expectations array", 1)])
def test_judge_errors_are_reported_and_excluded_until_regraded(tmp_path, capsys, error, rate):
    run = save_run(tmp_path, "case", "with_skill", rate=rate, error=error)
    save_run(tmp_path, "case", "old_skill", rate=.25)
    assert aggregate.main([str(tmp_path)]) == 1
    benchmark = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert [row["configuration"] for row in benchmark["runs"]] == ["old_skill"]
    assert benchmark["metadata"]["excluded_runs"] == 1
    excluded, = benchmark["excluded_runs"]
    assert excluded["run_dir"] == "case/with_skill" and error in excluded["reason"]
    assert error in capsys.readouterr().out
    assert error in (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    assert benchmark["run_summary"]["delta"]["pass_rate"] is None

    runner.write_json(run / "grading_status.json", {"error": None})
    assert aggregate.main([str(tmp_path)]) == 0
    benchmark = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert benchmark["excluded_runs"] == []
    assert benchmark["run_summary"]["with_skill"]["pass_rate"]["mean"] == rate
    assert benchmark["run_summary"]["delta"]["pass_rate"] == rate - .25


@pytest.mark.parametrize("status", [None, {"error": None, "cleanup_errors": ["cleanup failed"]}])
def test_ordinary_failures_and_legacy_grades_remain_valid(tmp_path, status):
    run = save_run(tmp_path, "case", "with_skill", rate=0)
    if status is None:
        (run / "grading_status.json").unlink()
    else:
        runner.write_json(run / "grading_status.json", status)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["excluded_runs"] == []
    assert benchmark["run_summary"]["with_skill"]["pass_rate"]["mean"] == 0


@pytest.mark.parametrize("exclusion", [{"excluded": True, "exclusion_reason": "transport failure"},
                                       {"failure_category": "transport"}, {"failure_category": "rate_limit"}])
@pytest.mark.parametrize("rate", [0, 1])
def test_transport_failure_excludes_stale_numeric_grades(tmp_path, exclusion, rate):
    run = save_run(tmp_path, "case", "with_skill", rate=rate)
    runner.write_json(run / "run.json", {"returncode": 1, **exclusion})
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"] == []
    assert [row["reason"] for row in benchmark["excluded_runs"]] == ["transport failure"]
    assert benchmark["run_summary"]["delta"]["pass_rate"] is None


@pytest.mark.parametrize("message", [
    "Selected model is at capacity. Please try a different model.",
    "unexpected status 503 Service Unavailable: upstream timeouts; retry shortly.",
])
@pytest.mark.parametrize("category", [None, "executor"])
@pytest.mark.parametrize("rate", [0, 1])
def test_saved_host_failure_replaces_stale_executor_classification(tmp_path, message, category, rate):
    run = save_run(tmp_path, "case", "with_skill", rate=rate)
    status = {"returncode": 1, "status": "failed"}
    if category:
        status["failure_category"] = category
    runner.write_json(run / "run.json", status)
    (run / "events.jsonl").write_text(json.dumps({"type": "turn.failed", "error": {"message": message}}),
                                      encoding="utf-8")
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"] == []
    assert [row["reason"] for row in benchmark["excluded_runs"]] == ["transport failure"]
    assert json.loads((run / "run.json").read_text(encoding="utf-8")) == status


@pytest.mark.parametrize("ending", [
    {"type": "turn.completed"},
    {"type": "turn.failed", "error": {"message": "Permission denied"}},
])
def test_saved_recovered_host_failure_does_not_remove_valid_scores(tmp_path, ending):
    run = save_run(tmp_path, "case", "with_skill", rate=0)
    runner.write_json(run / "run.json", {"returncode": 1, "status": "failed", "failure_category": "executor"})
    (run / "events.jsonl").write_text("\n".join(map(json.dumps, [
        {"type": "error", "message": "Selected model is at capacity. Please try a different model."}, ending,
    ])), encoding="utf-8")
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert len(benchmark["runs"]) == 1 and not benchmark["excluded_runs"]


@pytest.mark.parametrize("category", ["setup/copy", "launch"])
@pytest.mark.parametrize("rate", [0, 1])
def test_infrastructure_failure_excludes_stale_numeric_grades(tmp_path, category, rate):
    run = save_run(tmp_path, "case", "with_skill", rate=rate)
    runner.write_json(run / "run.json", {"returncode": 0, "failure_category": category,
                                        "error": "Harness could not preserve the project"})
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"] == []
    assert [row["reason"] for row in benchmark["excluded_runs"]] == [f"infrastructure failure: {category}"]


@pytest.mark.parametrize("status", ['{"error":', '[]', '{"excluded": true}'])
def test_invalid_or_excluded_grading_status_cannot_earn_a_score(tmp_path, status):
    run = save_run(tmp_path, "case", "with_skill", rate=1)
    (run / "grading_status.json").write_text(status, encoding="utf-8")
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"] == []
    assert len(benchmark["excluded_runs"]) == 1
    assert benchmark["excluded_runs"][0]["reason"]


def test_asymmetric_exclusions_do_not_create_delta_and_report_coverage(tmp_path, capsys):
    for config in ("with_skill", "old_skill"):
        save_run(tmp_path, "matched", config, rate=.5, seconds=10, tokens=100)
        save_run(tmp_path, "excluded", config, contaminated=True)
    save_run(tmp_path, "asymmetric", "with_skill", rate=1, seconds=20, tokens=200)
    save_run(tmp_path, "asymmetric", "old_skill", rate=1, error="judge timeout")
    save_run(tmp_path, "missing", "with_skill", rate=1, seconds=30, tokens=300)

    assert aggregate.main([str(tmp_path)]) == 1
    benchmark = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    summary = benchmark["run_summary"]
    assert summary["with_skill"]["pass_rate"]["mean"] == .8333
    assert summary["old_skill"]["pass_rate"]["mean"] == .5
    assert summary["delta"] == {"pass_rate": 0, "time_seconds": 0, "tokens": 0}
    assert benchmark["metadata"]["comparison"] == {"matched_cases": 1, "total_cases": 4}
    assert "1 / 4 cases matched" in capsys.readouterr().out
    assert "1 / 4 cases matched" in aggregate.generate_markdown(benchmark)
    assert any("1 / 4 cases matched" in note for note in benchmark["notes"])
    # The viewer treats every run_summary key except delta as a configuration.
    assert set(summary) == {"with_skill", "old_skill", "delta"}
    assert "expectations" in benchmark["runs"][0] and "result" in benchmark["runs"][0]


@pytest.mark.parametrize("layout", ["disjoint", "empty", "unrelated_config"])
def test_no_matched_cases_suppresses_every_delta(tmp_path, layout):
    if layout != "empty":
        save_run(tmp_path, "new", "with_skill", rate=1)
        save_run(tmp_path, "old" if layout == "disjoint" else "new",
                 "old_skill" if layout == "disjoint" else "another_config", rate=0)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["metadata"]["comparison"]["matched_cases"] == 0
    assert benchmark["run_summary"]["delta"] == {"pass_rate": None, "time_seconds": None, "tokens": None}
    assert "Delta unavailable" in aggregate.generate_markdown(benchmark)


def test_delta_uses_with_minus_old_and_only_paired_numeric_metrics(tmp_path):
    save_run(tmp_path, "first", "with_skill", rate=1, seconds=20, tokens=200)
    save_run(tmp_path, "first", "old_skill", rate=.5, seconds=10, tokens=100)
    save_run(tmp_path, "second", "with_skill", rate=.25, seconds=5, tokens=1000)
    save_run(tmp_path, "second", "old_skill", rate=.5, seconds=15, tokens=None)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["metadata"]["comparison"] == {"matched_cases": 2, "total_cases": 2}
    assert benchmark["run_summary"]["delta"] == {"pass_rate": .125, "time_seconds": 0, "tokens": 100}


def test_no_paired_token_measurements_suppresses_token_delta(tmp_path):
    save_run(tmp_path, "first", "with_skill", tokens=100)
    save_run(tmp_path, "first", "old_skill", tokens=None)
    save_run(tmp_path, "second", "with_skill", tokens=None)
    save_run(tmp_path, "second", "old_skill", tokens=200)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["run_summary"]["delta"]["tokens"] is None


@pytest.mark.parametrize("timing", [None, {}, {"total_duration_seconds": None, "total_tokens": None}])
@pytest.mark.parametrize("grade_timing", [None, {}, {"total_duration_seconds": None}])
def test_unavailable_metrics_remain_null_without_excluding_valid_scores(tmp_path, timing, grade_timing):
    run = save_run(tmp_path, "case", "with_skill")
    save_run(tmp_path, "case", "old_skill", seconds=9, tokens=90)
    if timing is None:
        (run / "timing.json").unlink()
    else:
        runner.write_json(run / "timing.json", timing)
    grading = json.loads((run / "grading.json").read_text(encoding="utf-8"))
    grading["timing"] = grade_timing
    runner.write_json(run / "grading.json", grading)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["excluded_runs"] == []
    current = next(row for row in benchmark["runs"] if row["configuration"] == "with_skill")
    assert current["result"]["time_seconds"] is None
    assert current["result"]["tokens"] is None
    for metric in ("time_seconds", "tokens"):
        assert benchmark["run_summary"]["with_skill"][metric]["mean"] is None
        assert benchmark["run_summary"]["delta"][metric] is None


@pytest.mark.parametrize("grade_timing,expected", [({}, 12), (None, 12),
                                                  ({"total_duration_seconds": None}, 12),
                                                  ({"total_duration_seconds": 0}, 0),
                                                  ({"total_duration_seconds": 15}, 15)])
def test_recorded_duration_fallback_keeps_real_zero_and_aggregate_duration(tmp_path, grade_timing, expected):
    run = save_run(tmp_path, "case", "with_skill", seconds=12)
    grading = json.loads((run / "grading.json").read_text(encoding="utf-8"))
    grading["timing"] = grade_timing
    runner.write_json(run / "grading.json", grading)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"][0]["result"]["time_seconds"] == expected


@pytest.mark.parametrize("timing", [True, "unknown", [12]])
def test_malformed_grading_timing_is_excluded_instead_of_crashing(tmp_path, timing):
    run = save_run(tmp_path, "case", "with_skill")
    grading = json.loads((run / "grading.json").read_text(encoding="utf-8"))
    grading["timing"] = timing
    runner.write_json(run / "grading.json", grading)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"] == []
    assert "timing must be an object or null" in benchmark["excluded_runs"][0]["reason"]


@pytest.mark.parametrize("defect", ["empty", "missing", "duplicate", "invented", "string-bool", "integer-bool",
                                    "empty-evidence", "nonstring-evidence", "nondict-verdict", "no-verdicts",
                                    "forged-count", "forged-rate", "boolean-count", "boolean-rate", "nan-rate",
                                    "infinite-rate", "oversized-rate", "negative-rate", "no-summary"])
def test_unsupported_grades_are_excluded_instead_of_earning_perfect_scores(tmp_path, defect):
    run = save_run(tmp_path, "case", "with_skill", rate=1)
    grading = json.loads((run / "grading.json").read_text(encoding="utf-8"))
    verdicts = grading["expectations"]
    if defect == "empty":
        grading["expectations"] = []
        grading["summary"].update(passed=99, failed=0, total=99, pass_rate=1)
    elif defect == "missing":
        verdicts.pop()
    elif defect == "duplicate":
        verdicts[-1] = verdicts[0]
    elif defect == "invented":
        verdicts[0]["text"] = "A different assertion"
    elif defect.endswith("-bool"):
        verdicts[0]["passed"] = "true" if defect == "string-bool" else 1
    elif defect.endswith("-evidence"):
        verdicts[0]["evidence"] = " \n " if defect == "empty-evidence" else ["Evidence"]
    elif defect == "nondict-verdict":
        verdicts[0] = True
    elif defect == "no-verdicts":
        grading.pop("expectations")
    elif defect == "forged-count":
        grading["summary"]["passed"] = 99
    elif defect == "forged-rate":
        grading["summary"]["pass_rate"] = .5
    elif defect == "boolean-count":
        grading["summary"]["failed"] = False
    elif defect == "no-summary":
        grading.pop("summary")
    else:
        grading["summary"]["pass_rate"] = {"boolean-rate": True, "nan-rate": float("nan"),
                                              "infinite-rate": float("inf"), "oversized-rate": 10**1000,
                                              "negative-rate": -1}[defect]
    runner.write_json(run / "grading.json", grading)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert benchmark["runs"] == []
    assert len(benchmark["excluded_runs"]) == 1
    assert "invalid run artifacts" in benchmark["excluded_runs"][0]["reason"]
    assert benchmark["run_summary"]["delta"]["pass_rate"] is None


@pytest.mark.parametrize("assertions", [None, [], ["Useful result 0"] * 4, [True], [""]])
def test_aggregation_requires_valid_case_assertions(tmp_path, assertions):
    run = save_run(tmp_path, "case", "with_skill")
    runner.write_json(run.parent / "eval_metadata.json", {"assertions": assertions})
    assert aggregate.generate_benchmark(tmp_path)["runs"] == []


def test_grades_are_checked_against_source_case_not_only_saved_metadata(tmp_path):
    case = runner.load_cases(runner.DEFAULT_SKILL, ["non-ml-replication"])[0]
    run = save_run(tmp_path, case.name, "with_skill", rate=1)
    benchmark = aggregate.generate_benchmark(tmp_path, skill_path=str(runner.DEFAULT_SKILL))
    assert benchmark["runs"] == []
    assert "differ from the source case" in benchmark["excluded_runs"][0]["reason"]
    # The default source skill performs the same cross-check.
    assert aggregate.generate_benchmark(tmp_path)["runs"] == []


def test_valid_verdicts_are_ordered_and_scores_derived_without_summary_extras(tmp_path):
    run = save_run(tmp_path, "case", "with_skill", rate=.25)
    grading = json.loads((run / "grading.json").read_text(encoding="utf-8"))
    grading["expectations"].reverse()
    grading["summary"]["unsupported_score"] = 100
    runner.write_json(run / "grading.json", grading)
    benchmark = aggregate.generate_benchmark(tmp_path)
    saved, = benchmark["runs"]
    assert [item["text"] for item in saved["expectations"]] == [f"Useful result {index}" for index in range(4)]
    assert {key: saved["result"][key] for key in ("passed", "failed", "total", "pass_rate")} == {
        "passed": 1, "failed": 3, "total": 4, "pass_rate": .25}
    assert "unsupported_score" not in saved["result"]


def test_grade_integrity_case_discriminates_through_the_real_aggregator(tmp_path):
    case = runner.load_cases(runner.DEFAULT_SKILL, ["evaluation-grade-integrity"])[0]
    inputs = case.path / "files"
    assertions = json.loads((inputs / "assertions.json").read_text(encoding="utf-8"))["assertions"]
    candidates = json.loads((inputs / "grades.json").read_text(encoding="utf-8"))["candidates"]
    skill = tmp_path / "skill"
    benchmark_root = tmp_path / "benchmark"
    for candidate in candidates:
        # Independent source definitions prevent substituted saved metadata
        # from silently redefining what a candidate was supposed to achieve.
        source = skill / "evals" / candidate["name"]
        graders = source / "graders"
        graders.mkdir(parents=True)
        (source / "prompt.md").write_text(runner.PROMPT_HEADER + "Audit the saved results.\n", encoding="utf-8")
        (source / "case.yaml").write_text(
            f'schema_version: "1.1"\nname: {candidate["name"]}\nexpected_outcome: |\n  Evidence-backed results.\n',
            encoding="utf-8")
        for index, assertion in enumerate(assertions, 1):
            (graders / f"{index:02}-assertion.md").write_text(runner.GRADER_HEADER + assertion + "\n",
                                                           encoding="utf-8")
        run = save_run(benchmark_root, candidate["name"], "with_skill")
        runner.write_json(run.parent / "eval_metadata.json", candidate["metadata"])
        runner.write_json(run / "grading.json", candidate["grading"])
        runner.write_json(run / "timing.json", candidate.get("timing", {}))
    benchmark = aggregate.generate_benchmark(benchmark_root, skill_path=str(skill))
    included = {run["eval_name"]: run["result"] for run in benchmark["runs"]}
    assert set(included) == {"valid-partial", "valid-perfect"}
    assert {name: result["pass_rate"] for name, result in included.items()} == {
        "valid-partial": .5, "valid-perfect": 1}
    assert benchmark["run_summary"]["with_skill"]["pass_rate"]["mean"] == .75
    assert included["valid-partial"]["time_seconds"] is None
    assert included["valid-partial"]["tokens"] is None
    assert benchmark["run_summary"]["with_skill"]["time_seconds"]["mean"] == 12
    assert benchmark["run_summary"]["with_skill"]["tokens"]["mean"] == 120
    assert {row["eval_name"] for row in benchmark["excluded_runs"]} == {
        candidate["name"] for candidate in candidates} - set(included)
    assert all(row["reason"] for row in benchmark["excluded_runs"])


@pytest.mark.parametrize("key", ["execution_metrics", "user_notes_summary"])
@pytest.mark.parametrize("value", [None, {}, "unknown", [], True])
def test_optional_grade_metadata_cannot_crash_a_benchmark(tmp_path, key, value):
    run = save_run(tmp_path, "case", "with_skill", rate=.5)
    grading = json.loads((run / "grading.json").read_text(encoding="utf-8"))
    grading[key] = value
    runner.write_json(run / "grading.json", grading)
    benchmark = aggregate.generate_benchmark(tmp_path)
    if value is None or isinstance(value, dict):
        result, = benchmark["runs"]
        assert result["result"]["pass_rate"] == .5
        assert result["result"]["errors"] is None
        assert result["notes"] == []
        assert benchmark["excluded_runs"] == []
    else:
        assert benchmark["runs"] == []
        assert key in benchmark["excluded_runs"][0]["reason"]


@pytest.mark.parametrize("field", ["duration", "graded-duration", "tokens", "errors"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 10**1000, True, "12"])
def test_invalid_measurements_exclude_only_the_affected_run(tmp_path, field, value):
    run = save_run(tmp_path, "corrupt", "with_skill", rate=1)
    save_run(tmp_path, "valid", "with_skill", rate=.5, seconds=12, tokens=120)
    if field in {"duration", "tokens"}:
        path = run / "timing.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["total_duration_seconds" if field == "duration" else "total_tokens"] = value
    else:
        path = run / "grading.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["timing" if field == "graded-duration" else "execution_metrics"] = {
            "total_duration_seconds" if field == "graded-duration" else "errors_encountered": value}
    runner.write_json(path, data)
    benchmark = aggregate.generate_benchmark(tmp_path)
    assert [row["eval_name"] for row in benchmark["runs"]] == ["valid"]
    assert [row["eval_name"] for row in benchmark["excluded_runs"]] == ["corrupt"]
    assert "finite nonnegative number or null" in benchmark["excluded_runs"][0]["reason"]
    summary = benchmark["run_summary"]["with_skill"]
    assert summary["pass_rate"]["mean"] == .5
    assert summary["time_seconds"]["mean"] == 12
    assert summary["tokens"]["mean"] == 120
    json.dumps(benchmark, allow_nan=False)
