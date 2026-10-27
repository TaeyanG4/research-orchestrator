# owned job monitor — Plan

## Queue

### H-A-01 — Run the owned batch simulation
- Claimed: none
- Sources: none
- Hypothesis: The batch simulation can complete while ownership and monitoring remain visible.
- Evidence: simulate_job.py performs an eight-second local batch and records ownership samples.
- Improvement: Establish evidence before committing to the next step.
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
- Next test: Claim CPU and launch simulate_job.py through the owned job workflow, then monitor it to completion.
- Stages: s1 inspect inputs | s2 analyze evidence | s3 record decision
