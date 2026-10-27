# Kaggle adapter

Use this only for `Competition: kaggle/<slug>`. Install and authenticate the official Kaggle CLI separately; never print credentials or put them in coordination files. The repository's `docs/host-dry-runs/kaggle-cli-2026-10-27.md` records CLI 2.2.4 help for `competitions submit` and `competitions submissions`: the syntax below is verified for those two commands only, not account execution. Other commands remain unverified; check their help or use the website. Replace placeholders with the actual slug/path; no command here runs as part of the checker or initializer.

## Read before deciding

Only `submissions` syntax is verified here; `list`, `files`, `submission-limits` and `quota` remain unverified.

```bash
kaggle competitions list --search <slug>
kaggle competitions files <slug>
kaggle competitions submission-limits <slug>
kaggle competitions submissions <slug> --format json
kaggle quota
```

Re-read submission limits, pending submissions, and quota immediately before deciding on a submission or accelerator run. For code competitions, record the published runtime limit and the candidate's measured runtime as `Observed at` facts, with source and measurement time, before checking that the candidate fits the limit. Record the observation time. Quota is account-wide; another project can consume it. The rules page, current status, deadline/time zone, and data-access agreement remain authoritative. A configured credential does not mean the account has accepted rules or completed required verification. Use the website when acceptance is required; never bypass it.

For read access from Python, the official API exposes the same submission history:

```python
from kaggle.api.kaggle_api_extended import KaggleApi

api = KaggleApi()
api.authenticate()
history = api.competition_submissions("<slug>")
```

Read response fields by their documented names for the installed version; do not parse human-aligned CLI tables for automation. The CLI's `--format json` is preferable when available. A returned response can still represent a pending or failed score.

## Download and send an authorized candidate

`download` is unverified. For a code competition, the verified submit form is:

```bash
kaggle competitions submit <slug> -f <output-file> -k <owner>/<notebook> -v <version> -m "X-A-001: expected range"
```

```bash
kaggle competitions download <slug> --path <directory>
kaggle competitions submit <slug> -f <file> -m "X-A-001: expected score 0.83-0.85"
kaggle competitions submissions <slug> --format json
```

The submit command changes the account and consumes an attempt; use it only under the user's action authorization. Before it runs, create `X-A-001` with `Kind: submission`, the exact file's hash, destination `kaggle/<slug>`, family, and timestamped Expected. After the platform responds, put its submission reference in the heading, map the file or notebook-version identity into `Candidate`, and map the observed score plus time into `Result`. Keep `Final: pending` until the final score exists. Record a failure as `Status: error`; keep its identity rather than silently sending the same artifact again. A deliberate retry uses `Retry of`.

For a code competition, submit the completed notebook version using the CLI's `-k <owner>/<notebook> -v <version>` options together with the output filename; check `competitions submit --help` for the installed syntax. An accepted upload is not a completed notebook, a valid artifact, or a scored result. Poll status and read errors before planning another attempt.

## Known quirks

- Daily submission allowance and weekly compute allowance are different resources; `kaggle quota` does not report daily attempts. Re-read `submission-limits` instead.
- Authentication errors can be command-specific. Modern token/OAuth support and legacy key support differ; use the official setup instructions for the installed version and never expose token values while debugging.
- CLI status and scores can lag. Keep pending results explicit; do not invent a score from elapsed time or from a success message.
- Simulation ratings have warm-up and refresh dynamics; usually only the latest two candidates remain active. Record the competition's actual behavior in the instrument's `Dynamics`, and verify it before replacing an active candidate.
- Final submission selection is made on the website; there is no general CLI/API command that marks the final picks. Verify the chosen entries there and mirror them in Shared state with a rationale.
- Rules text and live API allowances can disagree. Use current authoritative account status for the available allowance and the rules for what is permitted; resolve uncertainty before consuming an attempt.

This adapter adds no project files. Its ledger is the shared `## External actions` section, and its scoring instrument is in `## Instruments`.
