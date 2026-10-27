# History-archive scenario

Initialize a fresh project in `project/` with preset `solo-research`, platform `Claude Code`, user `operator` and slot A, then run `python make_history.py project`. The script appends 331 discoveries (300 VERIFIED, 20 PENDING, 10 HOLD and VERIFIED `D-A-331`, which live item `H-A-01` cites in `Sources`) and 700 completed-log events from slots A and B, including the stage event `H-A-01/s1` of that live item. Use explicit session `history-session` for `ro` commands. The fixture is synthetic: its numbers and reviews exist only to exercise archiving.
