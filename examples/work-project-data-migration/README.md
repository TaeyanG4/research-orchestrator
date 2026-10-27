# Brindle inventory migration

A three-day inventory migration finishes its production cutover and leaves unscored, staged retention cleanup in the unified queue. One event per session lists completed items; discoveries preserve the reusable rehearsal evidence and cutover decision. An independent session verifies the rehearsal. The direction review records Gap and Decisions; the ledger preserves the outcome expected before cutover. Direction cadence resumes if the settled migration scope changes.

All identities, studies, services, numbers and artifact paths are fictional. Artifact paths and hashes are illustrative records, not bundled executable projects. The four coordination files were generated first, then their records were filled and instructional samples removed; generated settings and reference pointers are unchanged.

From the repository root, create the empty directory `examples/work-project-data-migration`, then run this exact initializer command (`python` is Python 3.12):

```sh
python skills/research-orchestrator/scripts/init_research_orchestrator.py examples/work-project-data-migration -n "Brindle inventory migration" --preset work-project --user mira --agents 1 --platforms "Lumen" --environment linux/bash --git off --guards "light since 2026-10-23" --external-actions "brindlectl cutover"
```

Check the filled snapshot:

```sh
python skills/research-orchestrator/scripts/check_project.py examples/work-project-data-migration --strict
```
