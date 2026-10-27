# Wisp archive cleanup — Plan

## Agent: A

### H-A-02 — Cover empty input
- Sources: D-A-001
- Goal: empty archives can return success with no output
- Evidence: D-A-001 confirms filenames with spaces survive the refactor; the empty case is still untested
- Improvement: cover a missing boundary case without changing the command interface
- Next test: run the command on an empty fixture; require exit 0 and no files
