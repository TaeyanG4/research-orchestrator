Provenance: anonymised from a past project's records

`direction-selection.json` adds the strategy review, direction-debate events, intake rows and final
schedule. It preserves all 55, 72, 17 and 13 source lines respectively, including blank separators,
heading/field/row shapes, field names, date strings, numeric tokens and verdict states in source
order. Neutral summaries replace names and prose; dates and numeric receipts retain incidental
identifier fragments as well as observations. The independent integrity digests pin each stream.
The direction and selection manifests use these excerpts and the existing outward-action ledger.

`records.json` retains all 14 discovery entries and all 134 outward actions in their original order.
Discovery lines retain field order, repeated fields, blank separators, review order, dates and verdict states.
Every original numeric token is retained in its line's `numbers` array, including signs, precision, bounds,
versions and coefficients; heading numbers are separate. Exact timestamp strings are also retained in each
line's `dates` array. Neutral summaries replace the original prose and
names. Field qualifiers retain dates and neutral reviewer numbers while removing names and artifact paths.
Actions retain their six-field order, exact dates, visible score, final score, terminal state and
numeric reference. Their neutral descriptions retain every original numeric token in order after
`numeric receipt:`. An empty description stays empty. Numeric receipts deliberately include incidental
identifier numbers: they are not additional observations. The integrity digests cover the discovery numeric
stream and the action dates, scores, verdict states and references.

The replay manifests select records from this corpus. Runtime snapshots preserve source field order,
repeated updates, blank separators, review order, dates and numeric receipts. They translate review grammar
into valid P1 lifecycle syntax (`CORRECTED` becomes `CLOSED`; a resolution says `after challenge`). The full
original verdict state history remains in the corpus. Guard fields are
explicit additions, measured by the burden tests. Counter-replays add recorded remedial decisions; they do
not claim those decisions happened historically. The saturation snapshot uses only the visible score and
sets every Final field to pending. The later final score column remains in the corpus for integrity checks
and never enters the saturation decision.

The source does not retain a pre-action forecast for each selected action. The snapshot records that absence
with the original action date at the schema's minute precision and disables E1 explicitly. It never invents
an earlier forecast or treats a retrospective expected value as evidence. G1 and G3 remain enabled.
