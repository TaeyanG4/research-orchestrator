# Archive boundary discoveries

## D-A-001 — Nonempty records preserved
- Source: A
- Host: Shell
- User: operator
- Date: 2026-10-25
- Finding: all six nonempty fixture records matched byte for byte
- Evidence: archive_cases.py compared 6/6 records successfully
  - Spaced labels and trailing delimiters were preserved.
- Implication: keep the parser; verify empty input next

The empty-input case remains unmeasured.
