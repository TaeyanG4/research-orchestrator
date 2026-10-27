# External-action transition matrix

| Project | Initial External actions choice |
| --- | --- |
| inherited | Omit --external-actions when initializing. |
| custom | Explicitly set `release-client publish; delivery-tool send`. |
| opted-out | Explicitly set `none` with --external-actions. |
| legacy | Omit --external-actions, then remove only `external_actions_source=...` from the template marker if present, to model an older file with no provenance. |

Keep Enforcement block during reconfiguration. For hook probes use a configured adapter prefix in inherited, `release-client publish artifact.txt` in custom, and the same harmless command text in opted-out. Probes evaluate only; no publication command may run. Configure a competition identity but no external credentials.
