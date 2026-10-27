---
type: llm
focus: trace
weight: 1
---

audit.json excludes python-source, python-installed, and python-other-run with reasons citing their embedded protected file accesses rather than treating stdin program text as an exemption.
