# Cadence audit

Use user operator and the single host Local, Git sync off, work-project preset, and Guard thresholds direction-review=2d.

- fresh/: initialize today with no reviews or work records.
- paused/: copy the fresh project, set Guards to light since 2020-01-01 and Shared state Paused to 2020-01-03; it is an archived project.
- resumed/: copy paused/ and remove its Paused line, leaving its activation date and lack of reviews unchanged.

Run the installed project checker on all three. Preserve every project variant and the full outputs. No review is required for the audit itself.
