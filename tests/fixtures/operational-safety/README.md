# Operational safety corpus provenance

`mistake-patterns.json` is anonymised from a past project's mistake log. Its 28 numbered entries map one-to-one to
`source_entry` 1–28. Later unnumbered repetitions provide context, not extra entries. Descriptions are paraphrased,
identities are omitted, and examples use neutral paths such as `runs/job-a/` and `scripts/worker-a.sh`.

Under specification §11, 16 entries have deterministic aspects within scope, 10 require judgement, and two are wholly
outside scope. The 16 deterministic entries contain 23 concrete subcases, exercised through actual hook responses
or operational commands in `tests/test_operational_safety.py`. Required recall is **23/23 deterministic subcases
(100%)**, covering **17/16 deterministic source entries (100%)**. Pytest reports measured recall even with `-q`;
a failed or missing subcase reduces the reported coverage.

Three formerly tested subcases are explicitly excluded from this denominator and replayed to require no block:

- Entry 4: writing a `.ps1` file through an unquoted heredoc without backticks. The filename extension no longer
  triggers `shell.heredoc`; only backticks in an unquoted Bash heredoc body do.
- Entry 6, broad process-name kill: `jobs.kill-broad` was removed. The unchanged owned-process identity check remains
  an in-scope deterministic subcase of entry 6.

- Entry 26: `cd scratch/job-a/; worker-a` no longer receives `shell.cd`; only a bare trailing `cd` does. The original command is retained as a no-block control.

The 10 judgement entries remain explicitly excluded: 5, 9, 10, 12, 13, 17, 18, 23, 27, 28. Compound entries retain
`judgement_aspects` beside tested `deterministic_aspects`. This does not claim complete automatic prevention of all
28 historical mistakes. Entry 15 tests explicit `disown`, not arbitrary child cleanup; entry 20 tests stale-observation
reporting, not every later planning decision. Entry 21 preserves the original false-positive qualification and tests
configurable outgoing-history scanning, not a claim that a real credential was leaked. Entry 26 is excluded from deterministic recall; real-output replay and reviewed retry policy still require judgement. Receipt and process-identity
subcases exercise supported commands; raw bypasses are not counted as enforceable.

`benign-bash.json` contains 320 concrete command cases and `benign-powershell.json` contains 325. The original
20 command shapes each use 16 arguments; added PowerShell cases cover here-string data, opaque script blocks and
`Remove-Item -WhatIf`. Bash shapes include quotes, comments, escapes, logical operators, descriptor redirects, subshell
commands, quoted and date-expanding heredocs, ordinary literal file operations and opaque interpreter
calls. PowerShell shapes include call operators in each benign position, a waited `Start-Process`, quotes, comments,
escapes, ordinary literal file operations and opaque interpreter calls. They are grammar examples, never executed.
Each corpus runs with no live jobs, a live bound run directory, and a live bound input file: 960 Bash and
975 PowerShell evaluations. Measured results are **zero blocks and zero warnings for each shell family**; required limits are
zero blocks and at most 2% warnings. `worker & wait` is deliberately absent
from the benign corpus: §11 treats its statement-level ampersand as a background finding without wait tracking.

`out-of-scope-commands.json` tests nested `bash -c`, `powershell -c`, `python -c` and `cmd /c`, cross-shell calls,
script blocks, here-string bodies, aliases/functions, dynamic variables and globs, undeclared shell families, and
uncertain relative mutations after dynamic or multiple directory changes, including literal wrapper directory options.
Separate cases cover MSYS/UNC translation. All require no block; dynamic paths
and uncertain relative targets may warn. A single literal `cd <directory> && command` is resolved; dynamic or multiple changes remain uncertain.

The supported command wrappers and authoritative Git pre-push scanner remain necessary. Hooks prevent accidents;
they are not a security boundary.
