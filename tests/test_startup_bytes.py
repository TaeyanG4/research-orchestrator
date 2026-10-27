"""Keep fixed startup reading small as operational references grow."""

from startup_bytes import measure


def test_every_preset_stays_within_startup_budget():
    for name, row in measure().items():
        assert row["core"] <= 12_000
        assert row["total"] <= 16_000, (name, row)
        assert not row["references"], (name, row["references"])
