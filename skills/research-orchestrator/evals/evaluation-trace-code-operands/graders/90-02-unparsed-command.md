---
type: llm
focus: trace
weight: 1
---

audit.json includes unparsed-command and excludes unparsed-grader because a serialization parse failure does not make the entire command a path or suppress the embedded hidden-grader operand.
