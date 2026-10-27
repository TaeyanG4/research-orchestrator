# Local hook runtime cost, 2026-10-27

The current fast-path release budget is **p95 < 150 ms**; see the [current measurements and gate](hook-latency-gatefix.md). The historical batches below used a 225 ms policy. Each local measurement warms twice, collects three batches of 20 calls, takes the nearest-rank p95 in each batch and reports their median. These timings invoked no host application and establish no Linux/macOS performance.

The separate no-project Windows measurement on 2026-10-27 used 30 calls per wrapper, including shell startup and `{}` output, and never reached the interpreter sentinel. Median/p95: cmd.exe **29.87/32.08 ms**; POSIX sh on Windows **29.60/30.96 ms**. These per-call adapter costs establish no host/workflow comparison; Linux/macOS remain pending. This historical batch uses its stated 30-call method, not the warmed three-batch method above.

| Local layer / measurement | Batch p95s (ms) | Median p95 (ms) | Samples |
|---|---|---:|---|
| Earlier Windows wrapper, benign shell | 93.7 / 93.3 / 93.6 | 93.6 | [Earlier JSON](evidence/hook-latency-2026-10-27.json) |
| Earlier Git Bash wrapper, benign shell | 119.6 / 122.6 / 122.8 | 122.6 | Earlier JSON |
| Earlier Windows wrapper, unbound Edit | 57.0 / 59.1 / 58.6 | 58.6 | Earlier JSON |
| Earlier supervised-child fallback, benign shell | 131.7 / 131.2 / 128.6 | 131.2 | Earlier JSON |
| Round 7 Windows wrapper, unchanged PostToolUse | 58.35 / 57.77 / 60.99 | 58.35 | [Round 7 JSON](evidence/hook-latency-r7-2026-10-27.json) |
| Round 7 Windows wrapper, unbound Edit | 62.59 / 60.76 / 59.57 | 60.76 | Round 7 JSON |
| Round 7 warm in-process PostToolUse quiet check | 0.242 / 0.233 / 0.241 | 0.241 | Round 7 JSON |

Earlier measurements used Windows Python 3.12.6 with 1.4 MB discovery and 0.5 MB handoff text. The interpreter was on an isolated PATH; `RO_HOOK_PYTHON` was unset and wrappers resolved it themselves. Calls returned empty JSON with exit zero; the unbound Edit fixture had no jobs registry. All measured layers met the common budget.

Round 7 measurements used Windows Python 3.12.6 with 1,654,551 discovery bytes, 562,511 handoff bytes, a current record snapshot, no jobs registry and no queued warnings. A pytest run was active concurrently; values are load-affected observations, not a controlled before/after speedup. The unchanged PostToolUse path avoids body reads and child dispatch, but the installed wrapper still starts Python; the 0.241 ms figure measures only the warm in-process predicate. In that candidate, project-scoped Claude question/delegation matchers omitted inactive tools; generic plugin matchers and Edit/Write still incurred wrapper startup. Later matcher repairs were not remeasured. No host delivery or persisted-trust result is inferred from timing.
