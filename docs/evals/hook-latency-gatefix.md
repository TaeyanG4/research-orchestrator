# Hook latency release gate

The release budget is **p95 < 150 ms for every host and hook layer** on the documented fast paths: ordinary PreToolUse, unrelated projects, Stop and edit without jobs, unchanged PostToolUse, and cached checker summaries at compact. Equality fails. Correct hook output is required regardless of timing. When `RO_HOOK_PYTHON` resolves to the interpreter already running the installed wrapper, the runner executes the hook in that process. A watchdog thread enforces the nine-second deadline with `os._exit`, so stalled Python work cannot keep the hook alive. Other interpreter selections and library calls retain the supervised child.

## Evidence and measurement

The [current local measurements](evidence/hook-fast-paths.json) restore the 150 ms budget. On Windows Python 3.12, POSIX sh p95 costs were 28.664 ms for unrelated projects, 28.825 ms for Stop without jobs, 27.889 ms for edits without jobs, 125.261 ms for unchanged PostToolUse, and 104.888 ms for ordinary shell checks. Native cmd costs were 36.312, 22.977, 22.801, 48.395 and 105.495 ms respectively. The compact checker summary lookup alone measured 1.872 ms in process; that figure excludes the rest of SessionStart. These synthetic calls invoked no agent host and establish no Linux/macOS performance or host-delivery result.

Reproduce the local measurements with `python scripts/measure_hook_fast_paths.py --output <measurement.json>`. Each wrapper batch includes shell startup and JSON output. Stop and edit shortcuts require both the primary and recovery job registries to be absent. Compact reuses the checker summary only when dependency stamps and the calendar day match; live jobs and observation freshness are still checked. The retained [historical table](evidence/hook-latency-gatefix.json) records older supervisor batches at 183.4, 178.3 and 202.1 ms; they exceed the restored target and are not current measurements.

The subprocess gates warm caches twice, take 20 samples per batch, compute nearest-rank p95 from all samples, and compare the median of three batch p95s with the common budget. The in-process check takes 100 samples and uses nearest-rank p95. Ordinary PreToolUse runs against large synthetic discovery and handoff histories. Separate deterministic tests reject any attempted history reads through pathlib, `io.open`, or builtin `open`; passing a timing gate alone does not prove histories were skipped.

Timing tests carry `@pytest.mark.latency`; the default release validator excludes them. A separate CI step runs the marked installed-runner and direct/in-process checks on Windows, Linux and macOS. With `RO_LATENCY_REPORT`, the installed-runner test writes batch p95 values, the aggregate p95, output correctness and the common budget to `hook-latency.json`; CI retains one artifact per OS and prints its measured value in the job summary. Linux and macOS values remain pending CI evidence.

## Saved-case scope

The `hook-latency-budget` case audits supplied measurements without rerunning them. Its assertions distinguish passing samples, equality at the budget, incorrect output, percentile calculation, unchanged inputs, and the independent no-history-read guard. The current case applies one common budget; historical grades describe the policy they evaluated and are not evidence of a fresh run of this revision.

The updated cases have not been executed. Behaviour evidence remains the adjudicated iteration-6 snapshot; runtime microbenchmarks do not establish model behaviour.

Raw historical notes and measurements are withheld outside the public tree. The measurement table records their SHA-256 hashes; sanitized grades and benchmark summaries remain in [the minimal archive](evidence/hook-latency-eval.zip).
