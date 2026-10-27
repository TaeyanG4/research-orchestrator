# Plan collector

Read this when running a collection round with `Plan collector: on — <platform> / <model>`. `Plan queue limits` reads `stop at <N>, resume at <M>`. A sub-agent proposes diverse candidates when useful work is running low.

1. **When** — at session start and after each finished item, count the plan items (`### H-` headings). Start a round when the count is at or below the resume limit and `Plan collection` in `handoff.md` Shared state reads `idle`. While `Queue freeze: until YYYY-MM-DD` is active (through that date), skip collection so new scope does not displace the agreed work.
2. **Who** — only a session on the collector's platform, because it launches a sub-agent with the collector's model (in Claude Code, the Agent tool with the model set). Other sessions skip collection.
3. **Mark** — set `Plan collection: running — <your agent> (since YYYY-MM-DD HH:MM)` before starting, so no second round starts.
4. **Collect** — give the sub-agent the discovery index (headings plus Finding/Status/Cross-check lines), every plan item's heading and `Hypothesis`/`Goal`, the project goal, and any sources the user allows (papers, forums, documentation). It opens matching discoveries before proposing a related item. Accept only candidates meeting the profile's item fields and the duplicate check in [plan-items.md](plan-items.md). Prefer diversity.
5. **Add** — put accepted items under your own IDs where your workflow puts new items (classic: your own section; unified: the queue with `Claimed: none`), until the count reaches the stop limit or no worthwhile candidates remain.
6. **Finish** — set `Plan collection: idle` and log one event with heading `none`: `Action: plan collection round (Claude Code / sonnet): added H-A-12, H-A-13`, those IDs under `New plan items`, and `Discovery updates: none — collection, no experiment`.

Between rounds nothing is collected, so the queue drains to the resume limit before the next round. A `running` marker left by a released slot is stale; clear it and log the cleanup.
