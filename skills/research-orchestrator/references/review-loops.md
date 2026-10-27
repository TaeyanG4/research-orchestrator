# Review loops

Read this when one deliverable goes through repeated review and fix rounds: a release, a report, a large change, or an important stage. It complements [verification](verification.md), which decides whose review counts for a discovery.

**Why:** a moving target judged by a fresh reviewer each round does not converge. Each new session inspects different corners, so scores drift up and down while real defects slowly shrink. Fixed exit criteria, carried-over findings and early checks make a loop end in a few rounds.

## Before the first round

- Write the exit criterion into the item (in `Goal` or `Next test`): "no BLOCKER or MAJOR finding, and the checklist in `<file>` passes". Do not use a score threshold.
- Write the round cap next to it, for example `Review rounds: at most 3`. When the cap is reached, stop, record every remaining finding as a follow-up item, and ask the owner, or record the owner's earlier decision.
- List what is out of scope and give the list to every reviewer: evidence that cannot exist before release, budgets the owner fixed, work deferred by a recorded decision. A reviewer flags an out-of-scope item only when the documentation overstates or hides it.
- Start the slow, late-appearing checks now: run the checks on every target platform (for example a CI matrix on a clean branch) and the full publication scan over every folder, archive member, encoded text and native identifier.

## Each round

- Use one reviewer per round. Keep the release or publication review for the final round.
- Give the reviewer the previous round's findings. The reviewer first verifies each of them as fixed or not fixed, then reports only new BLOCKER or MAJOR findings; MINOR findings are batched into one list for a later round.
- Fix the findings in one change set, record one event for the round, and keep the findings in the follow-up items or review lines that the item already uses.
- While iterating, run the tests affected by the change. Run the full test suite once, at the final gate, on the exact candidate that will be released.

## Ending the loop

The loop ends when the exit criterion holds, or when the cap is reached and the owner decides. Release or close only the reviewed candidate; any later change starts a new short loop with the same criterion.
