---
type: llm
focus: trace
weight: 1
---

binding-checks.json records two simultaneously live jobs sharing worker.py and --input inputs.txt with distinct output directories, and an overlapping output launch is refused.
