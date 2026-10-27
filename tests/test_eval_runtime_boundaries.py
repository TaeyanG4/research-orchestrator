"""Synthetic retained outputs exercise registry routing without running evals."""
from types import SimpleNamespace

import pytest

from scripts.evals.checks import SCRIPTED_CHECKS


@pytest.mark.parametrize('case,name,payload,expected', [
    ('unicode-job-errors', '01-bounded-reads', {'bounded_reads': [False, True, False, True, False]}, True),
    ('unicode-job-errors', '01-bounded-reads', {'bounded_reads': [False, False, False, True, False]}, False),
    ('unicode-job-errors', '02-later-write', {'later_write': [False, False, True, False]}, True),
    ('unicode-job-errors', '02-later-write', {'later_write': [0, 0, 1, 0]}, False),
    ('external-wrapper-options', '01-python-options', {'python-options': {}}, True),
    ('external-wrapper-options', '01-python-options', {}, False),
    ('external-wrapper-options', '02-wrapped-options', {'env-options': {'decision': 'block'}}, False),
    ('publish-deadline-recovery', '01-scaled-default', {'objects': 20, 'default_seconds': 61}, True),
    ('publish-deadline-recovery', '01-scaled-default', {'objects': 20, 'default_seconds': 60}, False),
    ('publish-deadline-recovery', '02-actionable-refusal',
     {'objects': 20, 'refused': True, 'refusal': '20 outgoing objects; set deadline=122s in Publish scan'}, True),
    ('publish-deadline-recovery', '02-actionable-refusal',
     {'objects': 20, 'refused': True, 'refusal': 'deadline exceeded'}, False),
])
def test_saved_boundary_assertions_use_final_registry(case, name, payload, expected):
    ctx = SimpleNamespace(data=lambda _: payload)
    assert SCRIPTED_CHECKS[case, name + '.md'](ctx)[0] is expected


@pytest.mark.parametrize('mutated', [False, True])
def test_wrapper_direct_controls_require_all_denials(mutated):
    values = {name: {'hookSpecificOutput': {'permissionDecision': 'deny',
                                          'permissionDecisionReason': 'external.gate: use ro external'}}
              for name in ('direct', 'lookalike', 'second-statement')}
    if mutated:
        values['lookalike'] = {}
    ctx = SimpleNamespace(data=lambda _: values)
    assert SCRIPTED_CHECKS['external-wrapper-options', '04-direct-controls.md'](ctx)[0] is (not mutated)
