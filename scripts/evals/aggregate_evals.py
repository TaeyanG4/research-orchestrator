#!/usr/bin/env python3
"""Aggregate valid saved evaluations and compare matched with_skill/old_skill cases."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics

if __package__:
    from .contamination import audit_saved_run
    from .run_evals import DEFAULT_SKILL, load_case, saved_transport_category, write_json
else:
    from contamination import audit_saved_run
    from run_evals import DEFAULT_SKILL, load_case, saved_transport_category, write_json


def _read(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return data


def _stats(values: list) -> dict:
    known = [value for value in values if type(value) in {int, float}]
    if not known:
        return {"mean": None, "stddev": None, "min": None, "max": None}
    return {"mean": round(statistics.mean(known), 4),
            "stddev": round(statistics.stdev(known), 4) if len(known) > 1 else 0,
            "min": min(known), "max": max(known)}


def _case_assertions(run_dir: Path, skill_path: str) -> list[str]:
    """Check saved assertions against available source cases, including old runs."""
    metadata_path = run_dir.parent / "eval_metadata.json"
    texts = _read(metadata_path).get("assertions") if metadata_path.exists() else None
    case_path = (Path(skill_path) if skill_path else DEFAULT_SKILL) / "evals" / run_dir.parent.name
    if case_path.is_dir():
        current = [assertion.text for assertion in load_case(case_path).assertions]
        if texts is not None and texts != current:
            raise ValueError("Saved case assertions differ from the source case; regrade in a new iteration")
        texts = current
    elif skill_path:
        raise ValueError("The supplied skill has no matching source case")
    if (not isinstance(texts, list) or not texts
            or any(not isinstance(text, str) or not text.strip() for text in texts)
            or len(set(texts)) != len(texts)):
        raise ValueError("Missing, empty, or duplicate case assertions")
    return texts


def _validated_grading(grading: dict, texts: list[str]) -> tuple[dict, list[dict]]:
    """A summary is only a cross-check; derive every score from complete verdicts."""
    verdicts = grading.get("expectations")
    if not isinstance(verdicts, list) or not verdicts:
        raise ValueError("Missing or empty assertion verdicts")
    seen = {}
    for verdict in verdicts:
        if (not isinstance(verdict, dict) or set(verdict) != {"text", "passed", "evidence"}
                or not isinstance(verdict["text"], str) or type(verdict["passed"]) is not bool
                or not isinstance(verdict["evidence"], str) or not verdict["evidence"].strip()):
            raise ValueError("Each verdict needs text, boolean passed, and nonempty evidence")
        if verdict["text"] not in texts or verdict["text"] in seen:
            raise ValueError("Unexpected or duplicate assertion verdict")
        seen[verdict["text"]] = verdict
    if set(seen) != set(texts):
        raise ValueError("Grade omitted a case assertion")
    ordered = [seen[text] for text in texts]
    passed = sum(verdict["passed"] for verdict in ordered)
    derived = {"passed": passed, "failed": len(ordered) - passed, "total": len(ordered),
               "pass_rate": passed / len(ordered)}
    summary = grading.get("summary")
    if (not isinstance(summary, dict)
            or any(type(summary.get(key)) is not int or summary[key] != derived[key]
                   for key in ("passed", "failed", "total"))
            or type(summary.get("pass_rate")) not in {int, float}
            or not 0 <= summary["pass_rate"] <= 1
            or not math.isclose(summary["pass_rate"], derived["pass_rate"], rel_tol=0, abs_tol=1e-12)):
        raise ValueError("Summary is missing, invalid, or inconsistent with assertion verdicts")
    return derived, ordered


def _measurement(value: object, name: str) -> int | float | None:
    """Keep absent measurements null, but exclude corrupt numeric evidence."""
    if value is None:
        return None
    try:
        valid = type(value) in {int, float} and value >= 0 and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite nonnegative number or null")
    return value


def generate_benchmark(benchmark_dir: Path, skill_name: str = "", skill_path: str = "") -> dict:
    runs, excluded = [], []
    models = set()
    # Only harness run directories count. Never discover executor-created JSON
    # files under outputs/ as if they were independently graded runs.
    directories = sorted({path.parent for pattern in ("*/*/run.json", "*/*/grading.json")
                          for path in benchmark_dir.glob(pattern)})
    for run_dir in directories:
        identity = {"eval_id": run_dir.parent.name, "eval_name": run_dir.parent.name,
                    "configuration": run_dir.name, "run_number": 1,
                    "run_dir": run_dir.relative_to(benchmark_dir).as_posix()}
        try:
            run = _read(run_dir / "run.json")
            transport = saved_transport_category(run_dir, run)
            if transport or run.get("excluded"):
                reason = ("transport failure" if transport else
                          run.get("exclusion_reason", "run excluded"))
                excluded.append({**identity, "reason": reason})
                continue
            if run.get("failure_category") in {"launch", "setup/copy"}:
                excluded.append({**identity, "reason": f"infrastructure failure: {run['failure_category']}"})
                continue
            report = audit_saved_run(run_dir, run)
            if report["contaminated"]:
                excluded.append({**identity, "reason": "contaminated", "contamination": report})
                if run.get("status") != "contaminated":
                    run.update(status="contaminated", contaminated=True, contamination=report)
                    write_json(run_dir / "run.json", run)
                continue
            # Legacy grades may lack status, but a recorded judge error must
            # never turn a placeholder numeric grade into an assertion failure.
            status_path = run_dir / "grading_status.json"
            if status_path.exists():
                status = _read(status_path)
                if status.get("error") or status.get("excluded"):
                    reason = f"Grading error: {status['error']}" if status.get("error") else "grading excluded"
                    excluded.append({**identity, "reason": reason})
                    continue
            grading = _read(run_dir / "grading.json")
            if grading.get("excluded"):
                excluded.append({**identity, "reason": grading.get("exclusion_reason", "grading excluded")})
                continue
            summary, expectations = _validated_grading(grading, _case_assertions(run_dir, skill_path))
            timing_path = run_dir / "timing.json"
            timing = _read(timing_path) if timing_path.exists() else {}
            # Unmeasured duration is not a zero-second run. A null aggregate
            # duration can still fall back to a recorded executor duration.
            graded_timing = grading.get("timing")
            if graded_timing is not None and not isinstance(graded_timing, dict):
                raise ValueError("Grading timing must be an object or null")
            seconds = (graded_timing or {}).get("total_duration_seconds")
            if seconds is None:
                seconds = timing.get("total_duration_seconds")
            optional = {}
            for key in ("execution_metrics", "user_notes_summary"):
                value = grading.get(key)
                if value is not None and not isinstance(value, dict):
                    raise ValueError(f"Grading {key} must be an object or null")
                optional[key] = value or {}
            result = {**summary, "time_seconds": _measurement(seconds, "duration"),
                "tokens": _measurement(timing.get("total_tokens"), "tokens"),
                "errors": _measurement(optional["execution_metrics"].get("errors_encountered"), "errors")}
            runs.append({**identity, "result": result, "expectations": expectations,
                         "notes": optional["user_notes_summary"].get("needs_review", [])})
            if run.get("model"):
                models.add(run["model"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            excluded.append({**identity, "reason": f"Unavailable/invalid run artifacts: {exc}"})
    configs = sorted({run["configuration"] for run in runs}, key=lambda name: (name != "with_skill", name))
    run_summary = {}
    for config in configs:
        selected = [run["result"] for run in runs if run["configuration"] == config]
        run_summary[config] = {metric: _stats([result[metric] for result in selected])
                               for metric in ("pass_rate", "time_seconds", "tokens")}
        run_summary[config]["included_runs"] = len(selected)
    comparison_configs = ("with_skill", "old_skill")
    cases = {path.parent.name for path in directories if path.name in comparison_configs}
    by_config = {config: {run["eval_id"]: run["result"] for run in runs if run["configuration"] == config}
                 for config in comparison_configs}
    matched = sorted(by_config["with_skill"].keys() & by_config["old_skill"].keys())
    comparison = {"matched_cases": len(matched), "total_cases": len(cases)}
    delta = {}
    for metric in ("pass_rate", "time_seconds", "tokens"):
        pairs = [(by_config["with_skill"][case][metric], by_config["old_skill"][case][metric])
                 for case in matched]
        # Unknown measurements must not leave the two sides using different cases.
        delta[metric] = _stats([current - old for current, old in pairs
                                if type(current) in {int, float} and type(old) in {int, float}])["mean"]
    run_summary["delta"] = delta
    notes = [f"with_skill - old_skill comparison: {len(matched)} / {len(cases)} cases matched."
             + ("" if matched else " Delta unavailable (no matched cases).")]
    if excluded:
        notes.append(f"Excluded {len(excluded)} runs; see excluded_runs for reasons.")
    counts = Counter((run["eval_id"], run["configuration"]) for run in runs)
    return {"metadata": {"skill_name": skill_name, "skill_path": skill_path,
                         "executor_model": ", ".join(sorted(models)) or None,
                         "timestamp": datetime.now(timezone.utc).isoformat(),
                         "evals_run": sorted({run["eval_id"] for run in runs}),
                         "runs_per_configuration": max(counts.values(), default=0),
                         "included_runs": len(runs), "excluded_runs": len(excluded),
                         "comparison": comparison},
            "runs": runs, "excluded_runs": excluded, "run_summary": run_summary,
            "notes": notes}


def generate_markdown(benchmark: dict) -> str:
    metadata = benchmark["metadata"]
    lines = [f"# Skill benchmark: {metadata['skill_name']}", "",
             f"Included runs: {metadata['included_runs']}; excluded runs: {metadata['excluded_runs']}.", "",
             *benchmark["notes"], "",
             "| Configuration | Included | Mean pass rate | Mean seconds |",
             "| --- | ---: | ---: | ---: |"]
    for config, summary in benchmark["run_summary"].items():
        if config != "delta":
            lines.append(f"| {config} | {summary['included_runs']} | {summary['pass_rate']['mean']:.2%} | "
                         f"{summary['time_seconds']['mean']} |")
    if benchmark["excluded_runs"]:
        lines.extend(["", "## Excluded runs", ""])
        lines.extend(f"- {run['run_dir']}: {run['reason']}" for run in benchmark["excluded_runs"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark_dir", type=Path)
    parser.add_argument("--skill-name", default="research-orchestrator")
    parser.add_argument("--skill-path", default="")
    parser.add_argument("--output", "-o", type=Path)
    args = parser.parse_args(argv)
    benchmark = generate_benchmark(args.benchmark_dir, args.skill_name, args.skill_path)
    output = args.output or args.benchmark_dir / "benchmark.json"
    write_json(output, benchmark)
    output.with_suffix(".md").write_text(generate_markdown(benchmark), encoding="utf-8")
    print(f"Included {len(benchmark['runs'])} runs; excluded {len(benchmark['excluded_runs'])} runs")
    for note in benchmark["notes"]:
        print(note)
    for run in benchmark["excluded_runs"]:
        print(f"Excluded {run['run_dir']}: {run['reason']}")
    return int(bool(benchmark["excluded_runs"]) or not benchmark["runs"])


if __name__ == "__main__":
    raise SystemExit(main())
