# Wisp archive cleanup

A short software chore: simplify archive paths while preserving output. The unscored follow-up, one reusable finding and one session event demonstrate the quick lifecycle; duplicate checks and self verification remain.

All identities, studies, services, numbers and artifact paths are fictional. Artifact paths and hashes are illustrative records, not bundled executable projects. The four coordination files were generated first, then their records were filled and instructional samples removed; generated settings and reference pointers are unchanged.

From the repository root, create the empty directory `examples/quick-script-cleanup`, then run this exact initializer command (`python` is Python 3.12):

```sh
python skills/research-orchestrator/scripts/init_research_orchestrator.py examples/quick-script-cleanup -n "Wisp archive cleanup" --preset quick --user mira --agents 1 --platforms "Lumen" --environment linux/bash --git off
```

Check the filled snapshot:

```sh
python skills/research-orchestrator/scripts/check_project.py examples/quick-script-cleanup --strict
```
