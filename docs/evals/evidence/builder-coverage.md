# Builder behavioral evidence audit

The historical inventory had 47 cases: twelve native attempts touched two cases, with **0/47 valid paired coverage**. Current unexecuted cases are listed in [coverage JSON](builder-coverage.json). Infrastructure exclusions receive no assertion scores, performance delta or winner; original timing, errors and available token usage remain intact.

| Measurement | Observed outcome | Retained evidence |
|---|---|---|
| Initial native attempts | No completed task operation | [43 artifacts](builder-native-attempts.zip), [preservation view](builder-review.html) |
| Repair preflight, 90 seconds per run | Both timed out; unchanged input and empty final messages | [22 artifacts](builder-repair-attempts.zip), [view](builder-repair-review.html) |
| Final preflight, 90 seconds per run | Both timed out before a tool result | [Archive](builder-final-preflight.zip), [view](builder-final-review.html) |
| Recheck preflight, 60 seconds per run | Both timed out; runtime predates later hook fix | [22 artifacts](builder-recheck-preflight.zip), [view](builder-recheck-review.html) |
| Full-duration pair, unchanged 600-second setting | Native turns returned blocked setup; enclosing runs timed out | [22 artifacts](builder-full-duration.zip), [view](builder-full-review.html) |
| Historical seven-case benchmark | 7/37 cases at measurement date | [Benchmark](final-benchmark.md) |

Initial attempts retained no completed task tool operation. Independent review followed skill-creator's grader and benchmark analyzer guidance; reported stalled reads do not establish a cause. All seven baseline attempts pin release 5.1.0 revision `713088d79745589b053ae02996670dc7147a8ee1`, digest `b2c01f24428b04d8a31225e0f7a3aaed0cc819b52715292c165a264a943588c4`. Fresh sessions shared host homes, so they do not establish full isolation.

The repair preflight used `work-project-start` in two fresh sessions. Original errors, timings and source/export hashes are preserved. The staged runtime predates subsequent repairs; unchanged `brief.md` and empty `final.md` do not demonstrate task completion. The associated [trigger repair](../../trigger/results.md) completed none of four positives across three repeats each.

The final preflight recorded current-runtime digest `731856ea58881a221ed50e5dd303cb72bcee7276973e8179207c5f975b0a57fb`. Matching before/after digests establish runtime integrity, not completed behavior. Both runs are excluded, leaving comparison metrics null.

The recheck preserved all 15 original artifact hashes and unchanged inputs. Its source differs from the later record-parser repair, as the independent audit records. Both runs remain excluded without pass credit.

The full-duration pair used current digest `03e48eb0110b5feccdb13ad699ecd9610dd4eb1c115dc67914d085c39a9b4d85`. Saved final messages match native blocked responses; no setup files, task tool items or checker output were produced. Known token usage (265,639 current; 341,244 baseline) is retained without a behavioral comparison.

The seven-case benchmark used one shared executor per configuration and summarized transcripts. Its historical score remains unchanged. [Iteration-6 task exports](iteration-6-outputs.zip), [export scope and hashes](iteration-6-outputs.json) and [withheld-material inventory](withheld-material.json) preserve a separate set of outputs; raw traces and historical viewer content remain outside the release.

Owner decision (2026-10-26): no fresh paired runs or description optimization for 6.0.0; the owner validates in real use. The adjudicated iteration-6 snapshot remains historical evidence. No behavior run, grader or viewer was executed for the current repairs.
