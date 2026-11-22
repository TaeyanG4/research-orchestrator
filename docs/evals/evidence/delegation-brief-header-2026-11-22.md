# delegation-brief-header — one paired run (2026-11-22)

One execution of the case added in 8.0.0, outside the builder evidence (`builder-coverage.json` still lists it as unattempted there).

- Command: `python scripts/evals/run_evals.py --iteration 8 --case delegation-brief-header --configs with_skill old_skill --jobs 2`, then `python scripts/evals/grade_evals.py --iteration 8 --case delegation-brief-header --configs with_skill old_skill`.
- Executor and judge: the configured Codex model (codex-cli 0.154.0). `with_skill` is the 8.0.0 working tree; `old_skill` is the runner's pinned release 5.1.0 baseline (its content digest is enforced; 7.0.0 cannot be selected).
- Workspace: a local `iteration-8/delegation-brief-header/` folder with transcripts and grading, not committed.

| Grader | with_skill | old_skill (5.1.0) | What it shows |
|---|---|---|---|
| 01 generated header in brief.md | pass | fail | 8.0.0 brief starts with `ro-delegate: v1` and the generated rules; the 5.1.0 brief is careful prose that asks for seven report sections but has no marker, clock-time rule, no-delete rule or resource limits |
| 02 numbers copied with the set, inferred explanation kept inferred | pass | pass | No difference: both runs kept the session explanation marked unverified |
| 03 stage outcome written with `ro event` | pass | fail | 8.0.0 wrote the event with `ro event H-A-01/s1`; 5.1.0 edited handoff.md directly |
| 04 one run folder, record files off limits | pass | pass | Both briefs name the run folder and protect the records |

Totals: with_skill 4/4, old_skill 2/4.

Reading: one run each, so this is adoption evidence, not an effect size. The two differing graders test commands that only 8.0.0 has; the behavioural grader (02) did not separate the configurations, and no delegated agent ran because the case format allows no Agent tool. Whether the header reduces delegated-agent mistakes still needs runs with a real delegated agent.
