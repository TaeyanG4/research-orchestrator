# Competition profile

Read this when preparing competition evidence or choosing a candidate. The common record contract is [research-guards.md](research-guards.md); platform commands belong in [adapters/kaggle.md](adapters/kaggle.md). Use `Competition: <platform>/<slug>` and an explicit phase clock for a fixed-window event. The profile enables every guard except G12, which remains opt-in. The same discovery and external-action formats serve both workflows.

## External feedback is an instrument

A leaderboard is an `external-feedback` instrument, not unquestioned ground truth. Register its metric and cohort, measured agreement with the final target, numeric resolution, and `Dynamics` (warm-up, refresh, drift). Distinguish a public score from the hidden final score. Live ratings can take time to settle; scores from different populations are not a single saturation series. An independent validation instrument needs held-out coverage and measured agreement. Training labels, own-model panels, and in-sample folds do not become independent merely because several agree.

For example, an external instrument with resolution `±0.002` cannot reliably order five variants spanning `0.001`. Give those variants the same family and comparable cohort key. If a queued same-family item remains, name a new instrument or a reviewed structural exit. Record the real measurement key on `Result`, such as `score=0.842 on I-A-01 cohort public-current`; do not combine changed cohorts to claim saturation.

## Use the external-actions ledger for submissions

Every submission lives under `handoff.md` `## External actions`, never in a fifth coordination file:

```text
### X-A-001 — external reference 123456
- Kind: submission
- Candidate: candidate-a, hash <sha256 of the exact file>
- Destination: platform/event-a
- Family: family-a
- Expected: score 0.83–0.85 (written 2026-10-25 10:00)
- Result: score=0.842 on I-A-01 cohort public-current (observed 2026-10-25 10:10)
- Final: pending
- Status: complete
```

Register the expectation and hash before sending. Preserve the platform submission reference in the heading, map its file/version identity into `Candidate`, and its scored outcome and observation time into `Result`. The eventual private score goes in `Final`. A deliberate retry names `Retry of`; renaming a byte-identical file is still a duplicate at the same destination. A pending score stays pending rather than being invented from a local estimate.

Read the current submission allowance, pending results, account compute quota, and competition rules before each decision that consumes them. Record when they were observed; remembered numbers are not a current quota. Account-wide quota is shared with other projects. Failed or pending submissions can have platform-specific quota effects; re-read the authoritative status instead of inferring what remains.

## Probe policy and final choices

Per-column probes are an explicit project setting, for example `Per-column probes: off` or `Per-column probes: on — rules allow aggregate diagnostic probes; budget two attempts`. Put project-specific settings under `## Project rules`; this is guidance, not an additional checker setting. Do not infer permission from a public score or a technically accepted file. Confirm rules, purpose, expected information, and budget before enabling probes. Treat every probe as a ledger action with its own expected outcome.

Use direction reviews for the target gap, loss decomposition, standalone core families, data-generation audit, method intake, and consistently beneficial changes that were rejected. Read discussions and top write-ups for methods and score levels, not only for reusable assets. Include source/site/annotator effects, leakage paths, train/evaluation definition differences, and label construction in the first audit where they apply.

Before the deadline, record `Family` on each selected action and set `Final picks: X-A-001, X-A-009 (rationale: complementary measured errors)`. Action-level families drive selection checks; two same-family submissions are acceptable with an explicit rationale. Check that the platform actually marks the intended final choices; a ledger entry alone cannot change a website selection. After close, follow [postmortem.md](postmortem.md).

## Local compute routing

Read with [compute.md](compute.md) for ownership, named resource locks and host-limit retries.

1. If GPU has headroom, run the highest-priority compatible `GPU` or `EITHER` item.
2. If CPU has headroom, run the highest-priority compatible `CPU` or `EITHER` item.
3. If one local resource is busy and the other is idle, fill the idle one with the best compatible independent item.
4. If local CPU and GPU are saturated, an item with an available `Other` executor (a cloud batch service, or a platform that evaluates a deliverable as external feedback) may overflow remotely when the workflow, credentials, quotas, and user authorization permit it.
5. Keep blocked, non-parallel-safe, secret-dependent, or local-artifact-dependent work queued locally.

Check device capacity (for example `nvidia-smi`) before claiming it; a free device is not a reservation.
