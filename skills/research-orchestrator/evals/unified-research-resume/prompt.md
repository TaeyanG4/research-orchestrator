---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Resume this research project as operator on local, using slot A. The saved settings are correct. Complete only H-A-01: run the supplied analyze.py against observations.csv and decide whether the pooled elapsed-time estimate conceals a source difference. The script writes the summary and records the queue as it stood at analysis time; leave the script and input data unchanged.

Record the result as a discovery with reproducible evidence. Write its Finding field as a single JSON object with the n, overall_mean, and source_means values from the computed summary; put your interpretation in a separate field. Queue H-A-02 to check the source imbalance on new balanced observations, and leave that follow-up unstarted for the next session. Finish the normal item lifecycle, check the files, and close the session.

Input files: agents.md, analyze.py, discoveries.md, handoff.md, observations.csv, plan.md
