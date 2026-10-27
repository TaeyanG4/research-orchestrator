"""Synthetic replay excerpts, counter-replays, and their recording burden.

These retain workflow and synthetic-only boundaries; historical records cover the
derived-instrument, saturation, override, insight, direction and selection failures.
"""

from __future__ import annotations

import pytest

from conftest import check
from guard_helpers import BASE_FIELDS, replay
from test_guards import guard_issues

REPLAYS = {
    "replay-own-lineage-panel": {"guard.instrument.circular", "guard.rejection.evidence", "guard.outcome.missing"},
    "replay-in-sample-validation": {"guard.instrument.insample", "guard.outcome.missing"},
}


def burden(checker) -> tuple[list[int], int]:
    added = [len(set(discovery.fields) - BASE_FIELDS) for discovery in checker.discoveries.values()]
    warnings = sum(issue.severity == "WARN" for issue in guard_issues(checker))
    return added, warnings


@pytest.mark.parametrize("fixture,expected", REPLAYS.items())
def test_anonymised_failure_replays_detect_the_recorded_failure_modes(tmp_path, capsys, fixture, expected) -> None:
    checker = check(replay(tmp_path, fixture))
    warnings = {issue.check for issue in guard_issues(checker) if issue.severity == "WARN"}
    assert warnings == expected, [issue.render() for issue in checker.issues]
    assert not [issue for issue in checker.issues if issue.severity == "ERROR"]
    fields, volume = burden(checker)
    assert volume >= len(expected) and fields
    with capsys.disabled():
        print(f"\nBURDEN {fixture}: added fields per discovery={fields}; guard warning volume={volume}; "
              f"distinct warning checks={len(warnings)}")


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_changed_cohorts_and_justified_same_family_picks_have_zero_guard_warnings(tmp_path, capsys,
                                                                               workflow) -> None:
    checker = check(replay(tmp_path, "replay-changed-cohorts", workflow, "competition"))
    assert not [issue for issue in guard_issues(checker) if issue.severity in {"WARN", "ERROR"}], \
        [issue.render() for issue in checker.issues]
    assert not [issue for issue in checker.issues if issue.severity == "ERROR"]
    assert len(checker.instruments) == 1 and set(checker.external_actions) == {"X-A-001", "X-A-002"}
    fields, volume = burden(checker)
    assert volume == 0
    with capsys.disabled():
        print(f"\nBURDEN replay-changed-cohorts ({workflow}): added fields per discovery={fields}; "
              f"guard warning volume={volume}")


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_procedural_work_can_declare_every_guard_inapplicable_without_a_clock(tmp_path, capsys, workflow) -> None:
    checker = check(replay(tmp_path, "replay-procedural-work", workflow, "work"))
    assert not guard_issues(checker), [issue.render() for issue in checker.issues]
    assert checker.values["phase_clock"] == "off"
    assert not checker.instruments and not checker.external_actions
    fields, volume = burden(checker)
    with capsys.disabled():
        print(f"\nBURDEN replay-procedural-work ({workflow}): added fields per discovery={fields}; "
              f"guard warning volume={volume}")
