# Archive migration — Plan

## Agent: A

### H-A-01 — Audit dates in the pilot export
- Sources: D-A-001
- Hypothesis: All pilot dates retain their documented timezone.
- Evidence: D-A-001 established identifier uniqueness; timezone behavior remains untested.
- Improvement: Add the timezone check missing from the identifier-only pilot.
- Impact: 2
- Information: 3
- Confidence: 2
- Unblock: 1
- Diversity: 1
- Cost: 1
- Priority: 16
- Resource: CPU
- Parallel: NO
- Other: NONE
- Next test: Inspect the five pilot date strings and compare them with the archive schema.
