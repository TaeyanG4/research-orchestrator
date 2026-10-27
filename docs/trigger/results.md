# Trigger description evidence

Reviewed 2026-10-26. **Retain the current description.** The retained fresh
`current-2` run scores all 20 queries correctly by majority vote, including all
eight held-out queries. It measures the unchanged description before the package
rename; it does not establish exact-release or cross-host performance.

## Experiment and coverage

The frozen set contains 10 positive queries and 10 near-miss negatives. Seed 42
assigns 6+6 to development and 4+4 to held-out evaluation. Each query requires three
valid repeats; a selection rate of at least 0.5 determines its prediction.
Precision is `TP / (TP + FP)`, recall is `TP / (TP + FN)`, and coverage is scored
queries divided by all queries. Null precision/recall means a zero denominator.

| Evidence | Split | TP | FP | TN | FN | Inconclusive | Precision | Recall | Coverage | Positive coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Historical | Development | 4 | 0 | 6 | 0 | 2 | 100% | 100% | 10/12 | 4/6 |
| Historical | Held-out | 1 | 0 | 4 | 0 | 3 | 100% | 100% | 5/8 | 1/4 |
| Historical | Combined | 5 | 0 | 10 | 0 | 5 | 100% | 100% | 15/20 | 5/10 |
| Earlier app bridge | Held-out | 0 | 0 | 3 | 0 | 5 | null | null | 3/8 | 0/4 |
| Earlier standalone | Held-out | 0 | 0 | 3 | 0 | 5 | null | null | 3/8 | 0/4 |
| Builder repair follow-up | Held-out | 0 | 0 | 3 | 0 | 5 | null | null | 3/8 | 0/4 |
| Builder standard-timeout sweep | Held-out | 0 | 0 | 3 | 0 | 5 | null | null | 3/8 | 0/4 |
| Fresh current-2 | Development | 6 | 0 | 6 | 0 | 0 | 100% | 100% | 12/12 | 6/6 |
| Fresh current-2 | Held-out | 4 | 0 | 4 | 0 | 0 | 100% | 100% | 8/8 | 4/4 |
| Fresh current-2 | Combined | 10 | 0 | 10 | 0 | 0 | 100% | 100% | 20/20 | 10/10 |

## Fresh measurement and limitations

The [current-2 archive](evidence/current-2.zip) retains `results.json` and all 60
sanitised per-attempt records. Native streams, stderr and command inventories are
withheld with source hashes. Its report was created at `2026-10-26T04:49:16.488079+00:00` on
`codex-cli 0.154.0`, requesting `gpt-6.1-sol`. The original invocation recorded that explicit
model override alongside the inherited `gpt-6-astra` configuration. The report
format does not record the configured timeout, worker count or retry limit; these
values are not inferred. Every repeat used one attempt and completed a valid
measurement endpoint. There were no recorded contamination findings or candidate
changes.

The original detector was replayed against every fresh native prefix. All 30
positive attempts selected the skill. One development negative, the isolated
checkpoint-error fix, selected it in one of three repeats; all other negative
attempts were nonselections. Thus **20/20 describes majority-query correctness;
attempt-level correctness is 59/60**. The held-out set has 12/12 positive selections
and 12/12 negative nonselections. This is one repeated run over a small, previously
used query set, rather than a new independent test population or an estimate of
performance across arbitrary prompts.

The fresh and historical reports share the description SHA-256
`0bb5fa4916f5889f6a4db09feddf8069d1e0ad6cc0223f4a7d94d5826d1a86a1` and query-set SHA-256
`718c996bfd29924bb030e87660fc74ef0179d05c4ea7a1ccbf02afb7db036ff0`.
The measured skill snapshot SHA-256 is
`e85eae51cea66b94071530881c0360d61b9c4790249e609065bcb00216c18675`.
Its name and body preceded the release rename. The description is unchanged, but
name-sensitive triggering and later body changes require a new run to establish
results for the exact released package. Exported names are placeholders for that
measured identity; the archive never substitutes the released name as if tested.

Protocol `first-selection-v1` stops at the first completed skill read or qualifying
use announcement and audits the entire prefix through that event. Nonselection
requires a clean `turn.completed` and exit 0. The temporary skill contains only
`SKILL.md`; its referenced runtime files are intentionally absent. These results
measure selection, not execution or successful completion of the queried task.
Announcement matching is a heuristic. The native catalog is not fully exposed in
JSONL, so discovery isolation still depends on the host honoring disable settings;
clean traces cannot establish the absence of hidden context. Codex measurements
are a proxy for other hosts. No candidate comparison supports a description change.

## Earlier incomplete measurements

Historical coverage remains 15/20, with only 1/4 held-out positives measurable.
Its six contaminated attempts and one timeout remain excluded, without
retrospective trimming or reclassification. Earlier app-bridge and standalone
sweeps each produced 15 timeouts and nine clean nonselections; all 12 positive
attempts were unmeasured. Their respective hosts were `codex-cli 0.154.0` and
`codex-cli 0.153.4`, with 120-second and 60-second timeouts and a `gpt-6.1-sol`
request. Each used four workers and no retries.

The builder repair follow-up used `codex-cli 0.154.0`, the configured model,
60-second timeout, four workers and no retries: 15 timeouts and nine clean
nonselections. The standard-timeout sweep used the same host, a 180-second timeout,
four workers and no retries: three credited positive selections, nine clean
nonselections and 12 timeouts. No positive query in either sweep completed all
three repeats. Shortened-name announcements in timed-out traces were not credited
by the original exact-name detector. The standard-timeout analysis also records a
collaboration-spawn diagnostic despite a disabled feature, reinforcing the
isolation caveat. These failed measurements and their unavailable metrics remain
separate from the fresh result; the fresh result does not repair their traces or
establish the cause of earlier host execution failures.

## Retained evidence and checks

Owner decision (2026-10-26): no further scenario runs or description optimisation for 6.0.0; the owner validates in real use. Behaviour evidence is the adjudicated iteration-6 snapshot. The trigger measurements below remain historical.

- [Fresh current-2 archive](evidence/current-2.zip): all 60 valid attempts, 61 public artifacts (raw streams withheld).
- [Historical archive](evidence/historical.zip): all 60 original attempts, 61 public artifacts (raw streams withheld).
- [Earlier app-bridge archive](evidence/app-bridge-heldout.zip): 24 attempts, 25 public artifacts (raw streams withheld).
- [Earlier standalone archive](evidence/standalone-heldout.zip): 24 attempts, 25 public artifacts (raw streams withheld).
- [Builder repair archive](evidence/builder-repair-heldout.zip): 24 attempts, 25 public artifacts (raw streams withheld).
- [Builder standard-timeout archive](evidence/builder-full-heldout.zip): 24 attempts plus analysis, 26 public artifacts (raw streams withheld).
- [Coverage records](evidence/coverage.json): recomputable split/class metrics, input metadata and archive digests.

Every manifest links original SHA-256 digests to sanitized export digests.
Absolute host paths become opaque identifiers; credentials, host user, loopback
service URLs, fictional project names and the pre-rename skill identifier become
disclosed placeholders. Original source digests, statuses, exclusions and
unavailable metrics remain authoritative; raw model/isolation inventories are withheld. Sanitized
exports cannot be replayed as commands and do not hash to the original input
identifiers; source digests identify those original bytes.

`tests/test_trigger_evidence.py` checks consistency between retained attempt records,
source-digest entries and exported records. It validates manifest/archive digests,
recomputes split metrics and class coverage, checks measured-prefix boundaries and
rejects exposed host paths. Raw traces and stderr are withheld; their saved digests
identify the omitted bytes but do not independently verify their contents or replay
the skill-selection decisions.
Its negative control shows that perfect measured recall can coexist with missing
positive coverage. The fresh result is covered by the same parameterized checks.

## Skill-creator method

Applied intent/coverage review, Writing Style, Progressive Disclosure and
description-guidance rereads, the Description Optimization stratified held-out
method, and an analyst pass over per-attempt variation, missing coverage and
near-miss controls. Reused the existing objective evidence assertions and replayed
the native detector; no new model run was launched during this release-doc pass.

Skipped candidate drafting/promotion because no comparison supports a rewrite.
No skill behavior changed in this evidence export, so existing case settings and
graders remain unchanged. Paired task-output grading and the output viewer belong
to the separate behavioral evaluation; they do not validate native selection.
Packaging was skipped because this delivery is an uncommitted repository update.
