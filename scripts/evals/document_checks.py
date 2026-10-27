"""Saved artifact assertions for compact work records and evidence review."""
from __future__ import annotations

import re
import json

CHECKS = {}


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"{case}/{name}: artifact predicate {passed}"
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return False, f"{case}/{name}: required evidence missing or malformed"
    CHECKS[case, name + '.md'] = check


def dated_records_preserved(ctx):
    found = 0
    for name in ('handoff.md', 'discoveries.md'):
        before = (ctx.case_dir / 'files/project' / name).read_text(encoding='utf-8')
        after = ctx.text('project/' + name)
        for match in re.finditer(r'^#{2,3} (?:D-\S+|\d{4}-\d{2}-\d{2})[^\n]*\n.*?(?=^#{1,3} |\Z)',
                                 before, re.M | re.S):
            found += 1
            if match[0].rstrip() not in after:
                return False
    return found >= 2


def linked_review(ctx):
    handoff = ctx.text('project/handoff.md')
    shared = re.search(r'^## Shared state\s*\n(.*?)(?=^## |\Z)', handoff, re.M | re.S)
    return (shared and 'docs/retrospective.md' in shared[1] and
            bool(ctx.text('project/docs/retrospective.md').strip()) and
            {p.name for p in (ctx.outputs / 'project').glob('*.md')} ==
            {'agents.md', 'plan.md', 'discoveries.md', 'handoff.md'})


register('post-close-review', '01-dated-records', dated_records_preserved)
register('post-close-review', '02-linked-review', linked_review)

LABELS = {'Current best', 'Active compute', 'Plan collection'}


def missing_summaries(ctx, name, severity):
    issues = ctx.data(name)
    if not isinstance(issues, list):
        return False
    rows = [row for row in issues if row.get('check') == 'handoff.shared.missing' and row.get('field') in LABELS]
    return len(rows) == 3 and {row['field'] for row in rows} == LABELS and all(
        row['severity'] == severity for row in rows)


def settings(ctx, name):
    return dict(re.findall(r'^- ([\w ]+):\s*([^\n]+)', ctx.text(name + '/agents.md'), re.M))


register('work-summary-omission', '01-work-compact', lambda c:
         not any(re.search(r'^- ' + re.escape(label) + ':', c.text('work/handoff.md'), re.M) for label in LABELS))
register('work-summary-omission', '02-work-info', lambda c: missing_summaries(c, 'work-check.json', 'INFO'))
register('work-summary-omission', '03-research-control', lambda c: missing_summaries(c, 'research-check.json', 'ERROR'))
register('work-summary-omission', '04-scope', lambda c:
         settings(c, 'work').get('Profile') == 'work' and
         settings(c, 'work').get('Plan collector') == 'off' and
         settings(c, 'research').get('Profile') == 'research' and
         settings(c, 'research').get('Plan collector') == 'Shell/worker')

register('host-runner-diagnostics', '01-runner-decisions', lambda c:
         all(c.data('observations.json')[name]['observed'] == expected for name, expected in
             [('benign', 'no hook decision'), ('read-bound', 'warned'),
              ('unmonitored-stop', 'warned'), ('future-record', 'warned')]))
register('host-runner-diagnostics', '02-missing-stays-unknown', lambda c:
         c.data('observations.json')['missing-diagnostics']['observed'] == 'unknown/inconclusive')
register('host-runner-diagnostics', '03-delivery-separated', lambda c:
         all(c.data('observations.json')[row['name']]['host_output'] == row['host_output']
             for row in json.loads((c.case_dir / 'files/observations-input.json').read_text(encoding='utf-8'))))
