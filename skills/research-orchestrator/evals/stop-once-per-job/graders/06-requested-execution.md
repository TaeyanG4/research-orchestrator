---
type: llm
focus: trace
weight: 1
---

The captured completed-command trace and retained harness source establish four actual Stop adapter calls against the evaluated runtime, with adapter recreation and one stable session as requested, whose independently captured raw responses match stop-results.json in order; authored JSON, printed source, replayed responses, or an unrelated command do not establish those calls.
