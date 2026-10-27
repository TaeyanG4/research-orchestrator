---
type: llm
focus: trace
weight: 1
---

verdicts.json passes windows-child with p95_ms 151, baseline_p95_ms 60, overhead_ms 91, overhead_budget_ms 150 and budget_ms and absolute_budget_ms 300, while retaining budget_ms 150 for windows-in-process, linux-supervisor and macos-supervisor and passing only macos-supervisor among those three.
