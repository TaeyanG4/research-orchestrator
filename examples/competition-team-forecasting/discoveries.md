# Tern demand challenge — Discoveries

## D-A-001 — Seasonal baseline withstands a fresh cutoff
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-25
- Session: lumen:A@2026-10-25T08:00
- Cross-check: VERIFIED
- Finding: seasonal median reduces MAE from 12.4 to 10.8 on held-out weeks
- Evidence: outputs/horizons.csv: stores disjoint from fitting; as-of joins exclude future stock updates; fresh cutoff MAE 10.9; three archived seasons give held-out versus final-week rank agreement 0.83; five resampled periods bound MAE spread at 0.2; arena rules report public precision 0.2
- Implication: freeze the seasonal candidate; inspect final-period transfer later
- Reviews:
  - Prism (B): CLOSED — rebuilt as-of joins and reran a fresh cutoff; late-horizon gains persisted
- Decision class: method-change
- Outcome: supported
- Instrument: I-A-01
- Family: seasonal
- Result: mae=10.8 on I-A-01 cohort heldout-weeks
- Control: not applicable — prespecified seasonal baseline, without selecting a tuned variant; alternative: fresh cutoff and five resampled periods bound the uncertainty
