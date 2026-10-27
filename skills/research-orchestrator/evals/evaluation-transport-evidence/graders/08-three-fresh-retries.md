---
type: llm
focus: trace
weight: 1
---

retry-plan.json schedules at most three immediate fresh-session retries for terminal usage-limit, 429, capacity and 503 diagnostics, then waits for the stated reset without resuming a broken session or treating quoted diagnostics as retry triggers.
