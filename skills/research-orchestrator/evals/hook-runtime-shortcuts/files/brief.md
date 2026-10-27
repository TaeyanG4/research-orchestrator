# Fixture brief

Inspect both shipped wrappers and the runner. For Edit and Write, test quiet() with an agents.md declaring Enforcement: block and each registry state: absent, empty list, finished job with no ownership, running job, attention job, malformed JSON, missing jobs.json with a recovery snapshot containing a running job, and a finished job with unverified tree ownership. Retain the input and boolean result for every row. Also test PostToolUse with an empty registry.

Save quiet-results.json as an array with `tool`, `event`, `registry`, `input` and `quiet` (boolean) per row. Use registry labels `absent`, `empty`, `finished`, `running`, `attention`, `malformed`, `recovery`, `unverified-tree` and event labels `PreToolUse`/`PostToolUse`. Include a PostToolUse row for each tool.

Use a deterministic clock substitute to make a valid adapter self-test appear to take one second, and save its result in self-test-results.json. Keep an invalid-adapter control. Explain why correctness status uses the runner deadline and the single release latency budget instead of a separate 50 ms cutoff. Do not actually sleep or invoke a host.
