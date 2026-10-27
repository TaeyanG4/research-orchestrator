---
type: llm
focus: trace
weight: 1
---

audit.json includes python-data-literals and powershell-name-filter while excluding python-data-then-read and filter-then-read, so comparisons, comments, ignore patterns, string replacements, and printed text are not mistaken for access and do not exempt actual protected operands.
