# Fixture brief

Create independent two-slot projects for these conditions: (1) A is taken by operator and B is released, payload supplies only a native session ID; (2) A is taken by operator and B by collaborator, payload supplies user=collaborator; (3) both slots are released; (4) both slots are taken by other people with no matching user; (5) the first condition without a native ID. Also repeat condition 2 with RO_USER instead of payload user. Use synthetic session tokens and preserve the startup responses and handoff hashes.

Use startup-results.json keys `unique_free`, `payload_user`, `ambiguous`, `other_users`, `no_identity`, `environment_user`. Every row includes `payload`, `response`, `mapping` (saved JSON or null when absent), `handoff_before` and `handoff_after` SHA256 values. The unique_free row also includes `next_id` from the later command using only that session ID.
