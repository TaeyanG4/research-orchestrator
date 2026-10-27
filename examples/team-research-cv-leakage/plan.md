# Aster customer overlap study — Plan

## Agent: A

### H-A-04 — Fold-aware target encoding (from H-C-02)
- Sources: D-C-001, D-A-002, D-A-001
- Hypothesis: target encoding fit inside each grouped cross-validation training fold improves accuracy without leakage
- Evidence: D-C-001 (PENDING) finds every converter is fit before the fold split; D-A-002 (PENDING) shows global target encoding drops grouped cross-validation accuracy from 0.9027 to 0.8991; D-A-001 (PENDING) sets the deduplicated baseline at 0.9030
- Improvement: conversion is fit only on training folds of deduplicated data, unlike the global conversion tested in H-A-03
- Impact: 3
- Information: 2
- Confidence: 2
- Unblock: 1
- Diversity: 2
- Cost: 1
- Priority: 17
- Resource: CPU
- Parallel: YES
- Other: NONE
- Next test: grouped cross-validation(5) accuracy with fold-aware conversion against the 0.9030 baseline

## Agent: B

### H-B-03 — Cross-check D-A-001
- Sources: D-A-001
- Hypothesis: exact duplicate rows explain most of the random/group accuracy gap
- Evidence: D-A-001 (Lumen) reports the gap shrinking from 0.0135 to 0.0041 after deduplication; not yet verified
- Improvement: independent rerun by a different host on a fresh fold seed
- Impact: 2
- Information: 3
- Confidence: 2
- Unblock: 3
- Diversity: 1
- Cost: 0
- Priority: 19
- Resource: CPU
- Parallel: YES
- Other: NONE
- Next test: rerun experiments/e002_dedup.py with fold seed 11 and compare the gap

### H-B-02 — GPU comparison under grouped cross-validation
- Sources: D-B-001
- Hypothesis: the GPU ensemble keeps its lead over the baseline under grouped cross-validation
- Evidence: D-B-001 (VERIFIED) shows random accuracy overstated every earlier model comparison by about 0.013
- Improvement: re-evaluates on deduplicated grouped cross-validation folds instead of random cross-validation
- Impact: 3
- Information: 3
- Confidence: 1
- Unblock: 1
- Diversity: 2
- Cost: 2
- Priority: 17
- Resource: GPU
- Parallel: YES
- Other: Comet runner
- Next test: 5-fold grouped cross-validation run; overflow to Comet runner if the local GPU is busy

## Agent: C

_No active items. Slot released; the next new session may take it._
