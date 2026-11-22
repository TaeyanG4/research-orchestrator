# Post-close review

Read this after a fixed-window project closes or when the user asks for a retrospective. Preserve the four coordination files; put long source summaries and the final review under the project's `docs/` with links from Shared state. Never rewrite the contemporaneous expectation, decision, or result to fit what became known later.

1. **Collect strong public accounts.** Gather the top write-ups or comparable accounts of effective work, plus the rules, outcome table, and our final artifact identities. Record sources, dates, and access limits. If the window has not fully settled, distinguish provisional from final outcomes.
2. **Summarize with one fixed template.** For each source record: target and final result; evaluation instrument and coverage; data/target construction; core families built standalone; decisive changes and their measured effects; compute and time; external-feedback dynamics; rejected approaches; uncertainties and source citations. Use `not reported` instead of guessing.
3. **Compare independently with our records.** Assign independent investigators bounded questions, such as which core family we omitted, which decision used circular evidence, or whether a known diagnosis became an action. Supply source records and the fixed template, not a desired verdict. Where independent investigators are unavailable, preserve that limitation and request review through the configured verification workflow.
4. **Fact-check independently.** A different reviewer checks every material claim against the cited write-up and our dated discovery/event/action records. Separate an absent record from proof that work did not happen. Resolve conflicting claims before turning them into a conclusion.
5. **Write the post-mortem.** State the observed outcome, decisive failure modes, and the earliest dated point where each feasible alternative was available. For each counterfactual, give prerequisites, cost, available time, evidence, expected metric range, and counterfactual rank or standing using the final outcome table. Distinguish an observed effect from an estimate and uncertainty; do not claim that hindsight made an alternative certain.
6. **Turn lessons into a small enforceable change.** Name the rule or check that would have caught each mistake, the rule it replaces if any, and its recording burden. Record an insight or plan item when work remains; otherwise explain why no action follows. Keep undeclared overrides as a known detection limit.

## Skill retrospective

When the project kept a mistake log ([project-rules.md](project-rules.md#mistake-log)), improve the skill from it after the close:

1. Classify every entry by root cause, not symptom, with two independent readers; reconcile their counts and spot-check the code behind each claim.
2. Separate skill defects and preventable agent errors from project, experiment and host issues.
3. For each recurring cause, name the command, check or default that would have stopped it. Drop proposals that only add prose, and proposals backed by a single incident unless the harm was serious.
4. Turn each accepted incident into a regression fixture before changing code, and replay the project's records with the new checker: valid old records must gain no ERROR.
5. Measure the next project from its tool state (launch failures, refused external actions, records written by commands, hook findings by check) rather than from the log, whose standard changes.

For everyday work, compare completed migrations or service changes and their measured reliability; counterfactual standing may be `not applicable — no ranked outcome`. For research, compare published methods and audit the evidence for the claimed effect. For competitions, compare final standings and methods with the choices in the external-actions ledger. The same fact-checking standard applies to all three.
