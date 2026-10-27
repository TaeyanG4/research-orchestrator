# Session reminder fixture

Initialize a local team-work project. Set both handoff slots to released, Current user none, and leave their pending work intact. Clear RO_SLOT, RO_SESSION and CODEX_THREAD_ID, then give each hook payload cwd and a session_id.

For session-one run SessionStart, SessionStart, Stop, Stop in separate local processes. For session-two run Stop, Stop, SessionStart, SessionStart in separate local processes. Capture responses in order. Each independent session receives one selection reminder, shared across lifecycle events; neither session receives another slot's brief. Preserve handoff.md bytes and record its before/after SHA-256 values.
