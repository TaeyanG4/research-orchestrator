---
type: llm
focus: trace
weight: 1
---

codex-setup.md scopes verified Codex exec enforcement to the six probes recorded on 2026-10-27 with codex-cli 0.154.0, gpt-6.1-sol and declared windows/powershell. All six used --dangerously-bypass-hook-trust, granting trust for that invocation; the persisted /hooks route itself was not exercised, and ro commands and Git pre-push remain the relied-on gates.
