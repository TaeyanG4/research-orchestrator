# Velin rest interval study — Discoveries

## D-A-001 — Printed interval is reproducible
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-25
- Session: lumen:A@2026-10-25T08:00
- Cross-check: VERIFIED
- Finding: the fictional Velin study reports a difference of 2.0 minutes; the pooled two-sample calculation gives a 95% interval [0.294, 3.706]
- Evidence: Table 2: n=25 per group, means 12.0 and 10.0, standard deviations 3.0 each; SE=sqrt(18/25)=0.848528, df=48, critical t=2.010635
- Implication: the printed arithmetic agrees; this does not establish the original sampling assumptions
- Reviews:
  - Lumen (A): CLOSED — reviewer subagent:opal@2026-10-25T09:10 — independently recomputed the standard error, critical value and interval from Table 2
- Decision class: other
