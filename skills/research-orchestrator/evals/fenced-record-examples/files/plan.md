# guard — Plan

Active unfinished plan items only. Read `<skill-root>/references/plan-items.md` for item format, duplicate checks and priority; `<skill-root>/SKILL.md` for the item lifecycle; and `<skill-root>/references/workflow-classic.md` for ownership.


Each slot keeps its items in its own `## Agent: <name>` section. Item format:

```markdown
### H-A-01 — Short title
- Sources: D-B-001, D-A-004 / none
- Hypothesis: ...
- Evidence: ...
- Improvement: ...
- Impact: 0-3
- Information: 0-3
- Confidence: 0-3
- Unblock: 0-3
- Diversity: 0-3
- Cost: 0-3
- Priority: ...
- Resource: CPU | GPU | EITHER
- Parallel: YES | NO
- Other: NONE | <external executor>
- Next test: ...
```

## Agent: A

### H-A-01 — test item
- Sources: none
- Hypothesis: a claim
- Evidence: a reason
- Improvement: none
- Impact: 1
- Information: 1
- Confidence: 1
- Unblock: 1
- Diversity: 1
- Cost: 1
- Priority: 9
- Resource: CPU
- Parallel: YES
- Other: NONE
- Next test: a test

~~~~markdown
### H-A-998 ? example only
- Claimed: sample
~~~~

````markdown
### H-A-999 ? example only
```
- Claimed: another sample
### H-A-999 ? still an example
````
