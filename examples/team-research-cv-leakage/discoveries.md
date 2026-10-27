# Aster customer overlap study — Discoveries

## D-B-001 — Random folds leak customer groups
- Source: B
- Host: Prism
- User: tavi
- Date: 2026-10-24
- Cross-check: VERIFIED
- Finding: rows from the same customer_id land in both training and held-out folds under random cross-validation
- Evidence: random cross-validation accuracy 0.9162 vs grouped cross-validation accuracy 0.9027; reproduce with experiments/e001_group_check.py
- Implication: random cross-validation is optimistic by about 0.013; use grouped folds for model selection
- Reviews:
  - Lumen (A): CLOSED — reproduced with fold seed 7; gap 0.0131
- Decision class: data-change
- Instrument: I-B-01
- Outcome: supported
- Control: not applicable — direct comparison of two predefined partition rules, without candidate search; alternative: fresh fold seed reproduces the gap

## D-A-001 — Exact duplicates explain most of the gap
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-24
- Cross-check: PENDING
- Finding: removing exact duplicate rows shrinks the random/grouped cross-validation accuracy gap from 0.0135 to 0.0041
- Evidence: random/grouped accuracy 0.9071 / 0.9030 after deduplication; reproduce with experiments/e002_dedup.py
- Implication: new current best: baseline model at grouped cross-validation accuracy 0.9030 on deduplicated data; deduplicate before building folds
- Reviews:
- Consistency: not applicable — one fixed customer archive
- Decision class: data-change
- Instrument: I-B-01
- Outcome: supported
- Control: not applicable — deterministic removal of exact duplicates, without parameter selection; alternative: rerun on a fresh fold seed before accepting the pending finding

## D-C-001 — Encoders are fit before the fold split
- Source: C
- Host: Lumen
- User: mira
- Date: 2026-10-24
- Cross-check: PENDING
- Finding: converters/encode.py fits target encoders using labels from the full training set before splitting grouped folds
- Evidence: code audit of converters/encode.py; notes/conversion_audit.md
- Implication: target encoding leaks labels across folds; fit encoders using each fold's training partition
- Reviews:
- Kind: insight
- Status: planned H-A-04

## D-A-002 — Global target encoding does not hold under grouped cross-validation
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-24
- Cross-check: PENDING
- Finding: global target encoding does not hold under grouped cross-validation on deduplicated data (accuracy 0.9027 → 0.8991)
- Evidence: seed 13 grouped cross-validation accuracy 0.8991 vs 0.9027 without conversion; reproduce with experiments/e003_target_conversion.py
- Implication: do not retry global target encoding; only fold-aware conversion (H-A-04, taken over from H-C-02) is worth testing
- Reviews:
- Decision class: data-change
- Instrument: I-B-01
- Outcome: rejected
- Rejected on: I-B-01; fired: outputs/e003.csv records all converted fields
- Control: not applicable — single prespecified encoding intervention, without selecting a winning variant; alternative: held-out comparison on the same deduplicated partition
