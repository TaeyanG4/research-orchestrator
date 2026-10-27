"""Synthetic artifact controls; these do not execute behavior cases or a judge."""
import json
import shutil

import pytest

from conftest import SKILL
from scripts.evals.checks import CheckContext, SCRIPTED_CHECKS


def context(tmp_path, case):
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    return CheckContext(SKILL / 'evals' / case, tmp_path, SKILL, 'python')


def test_post_close_preservation_and_link_checks_reject_rewritten_history(tmp_path):
    ctx = context(tmp_path, 'post-close-review')
    shutil.copytree(ctx.case_dir / 'files/project', ctx.outputs / 'project')
    check = SCRIPTED_CHECKS['post-close-review', '01-dated-records.md']
    assert check(ctx)[0]
    handoff = ctx.outputs / 'project/handoff.md'
    original = handoff.read_text(encoding='utf-8')
    handoff.write_text(original.replace('output preserved', 'output changed'), encoding='utf-8')
    assert not check(ctx)[0]
    handoff.write_text(original.replace('## Shared state', '## Shared state\n- Review: [Review](docs/retrospective.md)'), encoding='utf-8')
    review = ctx.outputs / 'project/docs/retrospective.md'
    review.parent.mkdir()
    review.write_text('Cited review', encoding='utf-8')
    link = SCRIPTED_CHECKS['post-close-review', '02-linked-review.md']
    assert link(ctx)[0]
    (ctx.outputs / 'project/continuity.md').write_text('competing state', encoding='utf-8')
    assert not link(ctx)[0]


@pytest.mark.parametrize('name,severity,grader', [('work-check.json', 'INFO', '02-work-info.md'),
                                                 ('research-check.json', 'ERROR', '03-research-control.md')])
def test_work_summary_artifact_checks_need_each_real_severity(tmp_path, name, severity, grader):
    ctx = context(tmp_path, 'work-summary-omission')
    rows = [{'severity': severity, 'check': 'handoff.shared.missing', 'field': field}
            for field in ('Current best', 'Active compute', 'Plan collection')]
    p = ctx.outputs / name
    p.write_text(json.dumps(rows), encoding='utf-8')
    check = SCRIPTED_CHECKS['work-summary-omission', grader]
    assert check(ctx)[0]
    rows[0]['severity'] = 'WARN'
    p.write_text(json.dumps(rows), encoding='utf-8')
    assert not check(ctx)[0]
    p.write_text('[]', encoding='utf-8')
    assert not check(ctx)[0]


def test_work_summary_control_requires_an_enabled_collector(tmp_path):
    ctx = context(tmp_path, 'work-summary-omission')
    for name, profile in [('work', 'work'), ('research', 'research')]:
        root = ctx.outputs / name
        root.mkdir()
        (root / 'agents.md').write_text(f'- Profile: {profile}\n- Plan collector: off\n', encoding='utf-8')
    check = SCRIPTED_CHECKS['work-summary-omission', '04-scope.md']
    assert not check(ctx)[0]
    (ctx.outputs / 'research/agents.md').write_text(
        '- Profile: research\n- Plan collector: Shell/worker\n', encoding='utf-8')
    assert check(ctx)[0]


def test_host_audit_keeps_runner_decision_and_delivery_distinct(tmp_path):
    ctx = context(tmp_path, 'host-runner-diagnostics')
    inputs = json.loads((ctx.case_dir / 'files/observations-input.json').read_text(encoding='utf-8'))
    values = {row['name']: {'observed': row['expected'], 'host_output': row['host_output']} for row in inputs}
    p = ctx.outputs / 'observations.json'
    keys = ['01-runner-decisions.md', '02-missing-stays-unknown.md', '03-delivery-separated.md']
    p.write_text(json.dumps(values), encoding='utf-8')
    assert all(SCRIPTED_CHECKS['host-runner-diagnostics', key](ctx)[0] for key in keys)
    values['benign']['observed'] = 'warned'
    values['missing-diagnostics']['observed'] = 'warned'
    values['read-bound']['host_output'] = 'warned'
    p.write_text(json.dumps(values), encoding='utf-8')
    assert not any(SCRIPTED_CHECKS['host-runner-diagnostics', key](ctx)[0] for key in keys)
