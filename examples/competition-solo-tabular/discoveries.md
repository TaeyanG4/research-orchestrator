# Mallow tabular challenge — Discoveries

## D-A-001 — Held-out and public instruments differ
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-25
- Session: lumen:A@2026-10-25T08:00
- Cross-check: VERIFIED
- Finding: five archived candidates have held-out versus settled final rank agreement 0.80; current public scores cannot establish final-cohort quality
- Evidence: outputs/calibration.csv: prior-season calibration, disjoint store groups; bootstrap public spread 0.002; labels constructed from next-month orders only
- Implication: use held-out evidence for model changes; treat public feedback as noisy evidence
- Reviews:
  - Lumen (A): CLOSED — reviewer subagent:opal@2026-10-25T08:50 — recomputed ranks and checked store-group separation
- Decision class: other
- Instrument: I-A-01, I-A-02

## D-A-002 — Freeze two standalone families
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-25
- Session: lumen:A@2026-10-25T08:00
- Cross-check: VERIFIED
- Finding: boosting gains on dense stores; the linear model remains stronger on sparse stores
- Evidence: outputs/families.csv: held-out AUC 0.842 versus 0.837; sparse-store AUC 0.790 versus 0.804; X-A-001 and X-A-002
- Implication: freeze both candidates and audit the private result after close
- Reviews:
  - Lumen (A): CLOSED — reviewer subagent:opal@2026-10-25T11:50 — recomputed regional losses and checked the two final choices against the frozen files
- Decision class: method-change
- Outcome: supported
- Instrument: I-A-01
- Family: boosting
- Result: auc=0.842 on I-A-01 cohort store-heldout
- Kind: direction-review
- Gap: public AUC 0.841 versus target 0.850 on I-A-02, 2026-10-25
- Decomposition: dense stores improve; sparse stores lose 0.014 AUC (outputs/families.csv)
- Core families: boosting and regularized linear built standalone; D-A-002
- Data audit: customer groups disjoint; label dates follow the feature cutoff; source/store effects checked (D-A-001)
- Intake: fictional arena method note reports linear AUC 0.838; replicated family before considering ensembles
- Rejected consistent gains: none
- Decisions: H-A-03 created; freeze the two existing submissions
- Control: not applicable — two prespecified standalone families, without variant selection; alternative: compare dense and sparse store cohorts separately
