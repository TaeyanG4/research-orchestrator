# Reconstructing the iteration-6 snapshot

The [minimal evidence archive](iteration-6.zip) contains the original and adjudicated grades, benchmark tables, saved regrade procedure, adjudication changes and source hashes. It includes no transcripts or native event streams. Manifest entries link source bytes to exported bytes; omitted entries retain only the digest of withheld material. The original raw material remains in the owner's external archive. The separate [task-output archive](iteration-6-outputs.zip) now includes 4,497 sanitized task files from the adjudicated snapshot, alongside its saved grades and timings. Its [summary and archive digest](iteration-6-outputs.json) and member manifest link source hashes to exported hashes.

Verify the export and reconstruct the headline arithmetic with Python 3.12+:

```text
python scripts/evals/export_evidence.py --output docs/evals/evidence/iteration-6.zip --verify
python scripts/evals/reconstruct_snapshot.py docs/evals/evidence/iteration-6.zip --namespace original
python scripts/evals/reconstruct_snapshot.py docs/evals/evidence/iteration-6.zip --namespace adjudicated
```

These commands read saved verdicts. They do not run scenarios or graders. The adjudicated result has 40 current and 36 baseline included runs, 18 exclusions, and 31 matched cases. Assertion totals are 231/232 and 110/207. Averaging each matched case's pass rate gives 99.71% and 56.31%; do not substitute unmatched means or pooled assertion rates.

The archived `adjudicated/regrade.py` documents the historical procedure: classify recorded infrastructure interruptions, retain unaffected judgments, apply recorded recovered judgments, and replay deterministic artifact checks. It cannot be independently rerun from the minimal archive because raw execution artifacts are withheld. The arithmetic and original-to-adjudicated verdict changes are reconstructible. Produced task files now permit inspection of substantive results, including coordination records, analysis code and result files. Process claims still depend on withheld execution traces; sanitation also removes host bindings, so the export is not a replayable workspace. Excluded attempts and failed assertions retain their saved verdicts. No output file implies a passing run. No new regrade was performed for this repair.

Owner decision (2026-10-26): no further scenario runs or description optimisation for 6.0.0. The owner validates in real use. Behaviour evidence is the adjudicated iteration-6 snapshot, not a measurement of the exact final runtime.

No new paired runs were made for 6.0.0 by owner decision. The additional output export changes inspectability, not the measured runtime or the historical scores.
