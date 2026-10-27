"""Saved artifact assertions for byte-stream, wrapper, and publication boundaries.

Only retained artifacts are read here; trace and prose assertions use the explicit
judge registry. These predicates never execute a stored command or run a host.
"""
from __future__ import annotations

import math
import re


CHECKS = {}


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"{case}/{name}: saved artifact check {'passed' if passed else 'failed'}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return False, f"{case}/{name}: missing or malformed saved artifact"
    CHECKS[case, name + '.md'] = check


def exact_bools(value, expected):
    return isinstance(value, list) and all(type(item) is bool for item in value) and value == expected


register('unicode-job-errors', '01-bounded-reads', lambda c:
         exact_bools(c.data('scan-results.json')['bounded_reads'], [False, True, False, True, False]))
register('unicode-job-errors', '02-later-write', lambda c:
         exact_bools(c.data('scan-results.json')['later_write'], [False, False, True, False]))


def decision(ctx, name, blocked):
    result = ctx.data('decisions.json')[name]
    if not isinstance(result, dict):
        return False
    output = result.get('hookSpecificOutput', {})
    if not isinstance(output, dict):
        return False
    denied = output.get('permissionDecision') == 'deny' or result.get('decision') == 'block'
    reason = str(output.get('permissionDecisionReason', result.get('reason', '')))
    return denied and 'external.gate' in reason if blocked else not denied


for filename, name in [('01-python-options', 'python-options'), ('02-wrapped-options', 'env-options'),
                       ('03-shim-options', 'shim-options')]:
    register('external-wrapper-options', filename, lambda c, name=name: decision(c, name, False))
register('external-wrapper-options', '04-direct-controls', lambda c:
         all(decision(c, name, True) for name in ('direct', 'lookalike', 'second-statement')))


def scaled_default(ctx):
    report = ctx.data('deadline-report.json')
    count, seconds = report['objects'], report['default_seconds']
    return (type(count) is int and count > 0 and type(seconds) in (int, float)
            and math.isclose(seconds, 60 + .05 * count, rel_tol=0, abs_tol=1e-8))


def actionable_refusal(ctx):
    report = ctx.data('deadline-report.json')
    count, refusal = report['objects'], report['refusal']
    return (report['refused'] is True and type(count) is int and count > 0
            and f'{count} outgoing objects' in refusal
            and re.search(r'\bdeadline=[1-9][0-9]*s\b', refusal))


register('publish-deadline-recovery', '01-scaled-default', scaled_default)
register('publish-deadline-recovery', '02-actionable-refusal', actionable_refusal)
