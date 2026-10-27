# Setting values

Defaults below preserve missing values in older projects; `research` retains their pre-profile scoring and review policy. New no-preset/`custom` projects start with `Profile: work`, `Verification: self`, `Enforcement: block`, the four default safety checks in `Block`, and the detected host in `Platforms` (or `local`; explicit `multi` retains the built-in pair). See [presets.md](presets.md) for new-project policy.

| Line | Values | Default | When an edit takes effect |
| --- | --- | --- | --- |
| `Preset` | a preset name, `custom`, or `user:<name>` | `custom` | records the preset last applied; the lines below it are authoritative |
| `Profile` | `work` (input alias `normal`), `research`, `competition` | `research` | checker immediately; `--reconfigure` for references |
| `Workflow` | `classic`, `unified` | `classic` | `--reconfigure --migrate` (moves the plan items) |
| `Verification` | `cross-host-once`, `independent-review`, `hybrid`, `self` | `cross-host-once` | `--reconfigure` |
| `Item size` | `short`, `staged` | `short` | `--reconfigure` |
| `Guards` | `off`, `light since YYYY-MM-DD`, `strict since YYYY-MM-DD` | `off` | checker immediately; init/reconfigure dates activation and updates references |
| `Guard set` | `auto`, or comma-separated guard IDs | `auto` | checker immediately; `--reconfigure` for references; explicit list replaces defaults |
| `Guard thresholds` | comma-separated `key=value` pairs | `saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75` | immediately |
| `Language` | BCP-47 shape `[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*`, e.g. `ko`, `zh-CN` | infer from request; initializer `en`; ask only if unclear | immediately; preset precedence applies |
| `Environment` | `windows`, `linux`, `macos` / `bash` (bash-like shells), `powershell` | detected OS/shell; ask only if detection fails or is ambiguous | immediately; preset precedence applies |
| `Enforcement` | `off`, `warn`, `block` | `off` | immediately; blocking also requires the check in Block |
| `Block` | comma-separated check IDs, or `none` | `none` | immediately; presets list the four deterministic safety checks, plus external.gate for competition |
| `Read bound` | `off`, `on`; flag `--read-bound` | `off` | immediately; opt into `jobs.read-bound` advice for running-job paths |
| `External actions` | semicolon-separated command prefixes or `regex:` patterns | `none` (profile adapter defaults for competition) | immediately |
| `Receipt policy` | `independent`, `self`; flag `--receipt-policy` | `self` for competition-solo, otherwise `independent` | immediately; ledger and duplicate checks always apply |
| `Publish scan` | `secrets`; optional `literal:text` / `regex:pattern` entries separated by semicolons | `secrets` | immediately |
| `Brief requirements` | `type: required line` entries separated by semicolons, or `none` | `none` | immediately |
| `Autonomy` | `present`, `away` | `present` | immediately; away questions go to chat while independent work continues; ambiguous slot assignment instead starts a new slot without asking |
| `Stale slot after` | positive duration, e.g. `30m`, `2h`, `1d`; flag `--stale-slot-after` | `2h` | next session assignment; no protected job and an older newest event/claim make a taken slot a stale candidate, not permission to reclaim it |
| `Queue freeze` | `off`, or `until YYYY-MM-DD`; flag `--queue-freeze` | `off`, including older files without this line | immediately; pause new queue items through that date; expiry warns |
| `Phase clock` | `off`, or `start YYYY-MM-DD, deadline YYYY-MM-DD` | `off` | immediately; enables phase milestones when G8 is selected |
| `Competition` | `off`, or `<platform>/<slug>` | `off` | selects competition guidance and its adapter |
| `Platform mode` | `multi`, `single`, `adaptive` | `adaptive` | `--reconfigure` |
| `Platforms` | comma-separated hosts (`single`: exactly one, written `Platforms: single — <host>`; `multi`: two or more) | built-in host pair in `scripts/ro_settings.py` | immediately |
| `Git sync` | `push`, `commit`, `off` | `off` | `--reconfigure` |
| `Plan collector` | `off`, or `on — <platform> / <model>` | `off` | immediately |
| `Plan queue limits` | `stop at <N>, resume at <M>` | `stop at 50, resume at 5` | immediately |
| `Reviewer` | `off`, or `on — <platform> / <model>` | `off` | immediately |
| `Cross-check fallback` | `wait`, `same-host` | `wait` for `multi`, `same-host` otherwise | immediately |


Read [presets.md](presets.md) for choosing, applying and saving settings. The `direction-parts=full` guard threshold opts research into all direction-review sections; `profile` is the default.
