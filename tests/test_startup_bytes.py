"""Keep fixed startup reading small as operational references grow."""

from startup_bytes import measure


def test_every_preset_stays_within_startup_budget():
    for name, row in measure().items():
        assert row["core"] <= 12_000
        # 7.0.0: agents.md carries explained working rules for sessions that never load the skill.
        assert row["total"] <= 17_500, (name, row)
        assert not row["references"], (name, row["references"])
