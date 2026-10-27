---
type: llm
focus: trace
weight: 1
---

Executed evidence shows the staged pre-check received the unregistered second checkout, not the policy root, and both the `git -C` and `cd ... &&` pushes kept the advisory, without scanning the hook directory's staged changes, with a warning that defers to the target checkout's pre-push gate.
