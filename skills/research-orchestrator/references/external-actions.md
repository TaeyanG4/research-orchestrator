# External actions and receipts

Read this when preparing an outward action or independent receipt, or resolving an E1 finding. [research-guards.md](research-guards.md) defines guard activation, applicability and severity; the record and execution rules live here.

## E1 — External actions

**Why:** an outward action may be costly to reverse; expectations written after seeing its result cannot test the decision, and duplicate actions waste scarce attempts.

- Use one `## External actions` section in `handoff.md`, with IDs `X-<slot>-NNN`.
- Record `Kind`, `Candidate: <name>, hash <artifact hash>`, `Destination`, optional `Family`, and `Expected: <outcome or range> (written YYYY-MM-DD HH:MM)` before acting. Kinds include deploy, release, publish, message and other outward actions.
- Record `Result: <outcome> (observed YYYY-MM-DD HH:MM)` or explicit `pending`, `Final: <outcome>` or `pending`, and `Status: prepared | in-flight | unknown | done | complete | error | withdrawn`. Retain artifact identity and destination while results mature.
- `ext.expected` warns for missing or malformed expectations or ones written at/after the result time. `ext.duplicate` warns for matching hash and destination without a retry reference. Both become ERROR in strict mode.
- Other missing or invalid fields use `external.field.missing` or `external.field.invalid`, WARN in light mode and ERROR in strict mode. Field order stays WARN; unknown fields stay INFO.
- Declare E1 inapplicable when no hard-to-reverse outward action occurs. These evidence checks do not themselves authorize an action or enforce a host hook.

Unambiguous action history prevents an old prepared record from repeating an action that already happened.

- A deliberate retry names `Retry of: X-A-001`, citing an earlier action with the same hash and destination. Chains use observed time, or written time while pending, independently of file order.
- The checker and wrapper reject forward, self, dangling, mismatched and cyclic links, including invalid ancestry inherited through a chain.
- Reconcile later or undated matching attempts before execution. Only never-attempted preparations can be withdrawn without retry reconciliation; withdrawing an attempted action does not erase its history.
- Each field appears once; use either `Scope` or `Contract`. The wrapper checks cardinality across the ledger. A malformed ledger leaves both command and ledger untouched; reconcile ambiguity from evidence before retrying.

- **Work:** before a production deploy, expect error rate below 0.5 percent, then record the observed rate against the artifact hash.
- **Research:** before posting a report, record an expected effect within the stated interval and later record the observed replication outcome.
- **Competition:** before sending an external candidate, record the expected score range, then its observed and final outcomes under the same X-id.

## Review and execution

Self review lowers coordination cost by giving up an independent check, while receipts still bind the decision to particular artifacts.

- `Receipt policy: independent | self` controls who signs. `competition-solo` defaults to `self`; `competition-team` and other presets use `independent`, requiring another reviewer session. Choose explicitly when that trade-off matters.
- Both policies retain the ledger, prior expectation, artifact identity, duplicate checks and durable attempt journal.
- `ro --session author-session receipt add artifact.txt --reviewer reviewer-session --verdict PASS --scope release-contract --dest endpoint` binds a verdict to its SHA256. Under `self`, reviewer and author may match.
- Supply a stable author through `--session`, `RO_SESSION` or `CODEX_THREAD_ID`; a fresh CLI process identity does not count. Identities are caller assertions stored with provenance, not authenticated identities.
- A later FAIL invalidates an earlier PASS for the same artifact and scope; changed bytes need another review. `ro receipt check artifact.txt --scope release-contract --dest endpoint` checks current bytes, scope, destination and policy.

A complete, stable hash identifies the approved bytes across checkouts and later execution.

- UTF-8 text-file receipts normalise CRLF to LF; binary files retain raw bytes.
- Directory receipts sort POSIX relative paths and hash each file's raw bytes, excluding `.git`, `__pycache__` and `.ro`; their SHA256 covers the canonical JSON manifest. Links and junctions are refused because mutable targets defeat a stable tree identity.
- Hashing streams in bounded chunks, with a 10,000-file manifest cap. Unreadable or disappearing directories abort receipt creation, validation and dependent execution; incomplete hashes cannot authorize execution.
- Resolve read failures before retrying. Failed validation leaves receipts and the prepared ledger unchanged.
- Use immutable artifact copies to avoid mutation between validation and the child's read.

Validation and a durable attempt journal prevent duplicate execution even when the visible ledger is later edited.

- Prepare the E1 record with the artifact path as candidate and `Status: prepared`. Optional `Scope` (or `Contract`) equals the receipt scope; otherwise the X ID is the scope.
- Run `ro external --artifact artifact.txt --action X-A-001 -- <command>`; omitting the artifact infers it from Candidate. Fresh explicit arguments execute, never commands from the ledger.
- Validation recomputes the hash and requires the latest policy-eligible PASS, matching destination, contract and prior expectation. Failed or unavailable validation refuses execution. Per-action locks prevent duplicates without delaying unrelated actions.
- Before spawning, the wrapper journals the attempt and marks `in-flight`. Success becomes `done`, failure `error`, and interruption or `--deadline` expiry `unknown` (default 300 seconds). Results can remain pending until observed; editing back to `prepared` cannot bypass the journal.
- Under the external lock, the wrapper checks journal identities by hash and destination across all action IDs. Restore omitted predecessors and retain every matching attempt in the reconciled retry chain; a withdrawn entry or a new ID cannot conceal a prior attempt. A live predecessor still blocks execution.
- The direct-call hook recognises configured `External actions` patterns and project wrappers. Competition defaults select an adapter from `Competition: <platform>/...`; an unsupported platform has no default patterns. Configure its actual outward command prefixes with `--external-actions` before relying on the gate.

Stopping local processes cannot prove whether a remote service accepted the action.

- Timeout and interruption terminate the owned Windows job object or POSIX process group, including descendants whose launcher exited, then verify that the tree is empty.
- Unverified termination keeps `unknown`. Verified local cleanup also leaves a timed-out remote action `unknown` until service evidence resolves it.
- Read `.ro/external-results/<X-id>.json` before updating `Result` or retrying; success and failure messages point there. It retains action ID, exit code, stdout, stderr and start diagnostics.

Bounded, redacted diagnostics preserve useful reconciliation evidence without retaining credential fragments.

- Each stream is redacted before retaining at most 16,384 characters from its beginning and end, with a truncation marker and omitted-character count. Recognition spans chunks and multiline private keys.
- Diagnostic lines over 4,096 characters are withheld and counted as omitted; a late delimiter could otherwise expose a credential fragment. Arrange a separate command-owned log when the complete response matters.

An uncertain remote outcome can already represent success, so retrying without reconciliation can execute the action twice.

- Before retrying, record `Reconciled: not-accepted (observed YYYY-MM-DD HH:MM); <service evidence>` on the predecessor after its expectation/result; seconds are accepted for rapid retries.
- Create a new X-id with `Retry of` and a later expectation. Confirmed acceptance means observe the existing action instead of retrying it.
- Forward the chain's stable `RO_IDEMPOTENCY_KEY` when the service supports idempotency.
- Reconcile crashes after possible acceptance, timeouts and failed responses before retrying; local failure alone does not establish non-acceptance.
