"""Guidance stays concise, aligned, and backed by concrete cases."""
import re

from conftest import ROOT, SKILL
from ro_time import FUTURE_TOLERANCE


def test_readme_why_paragraphs_have_same_order_and_shape():
    shapes = []
    for name in ('README.md', 'README.ko.md', 'README.ja.md', 'README.zh-CN.md'):
        text = (ROOT / name).read_text(encoding='utf-8')
        why = re.split(r'^## .+$', text, flags=re.M)[1]
        paragraphs = [p for p in why.split('\n\n') if p.strip()]
        assert len(paragraphs) == 1
        assert paragraphs[0].index('28') < len(paragraphs[0]) - 60
        shapes.append([len(re.findall(r'\n\n', section.strip())) for section in
                       re.split(r'^## .+$', text, flags=re.M)])
    assert shapes.count(shapes[0]) == 4


def test_session_examples_and_resource_guidance():
    core = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
    for command in ('brief', 'close'):
        assert f'ro --session <host-session> --slot A {command}' in core
    for path in ('references/plan-items.md', 'templates/HANDOFF.md.template'):
        text = (SKILL / path).read_text(encoding='utf-8')
        assert 'exclusive' in text and '`Other`' in text
        assert re.search(r'(?:database|licen[cs]e|resource)', text, re.I)
    safety = (SKILL / 'references/operations-safety.md').read_text(encoding='utf-8')
    assert re.search(r'(?:five|5) minutes', safety)
    assert FUTURE_TOLERANCE.total_seconds() == 300


def test_runtime_observations_and_reconciled_plan_scope():
    adapter = (SKILL / 'references/adapters/kaggle.md').read_text(encoding='utf-8')
    opening = adapter.split('## Read before deciding', 1)[1].split('\n## ', 1)[0]
    for phrase in ('runtime limit', 'measured runtime', '`Observed at`', 'measurement time'):
        assert phrase in opening
    plan = (ROOT / 'docs/plans/v3-plan.md').read_text(encoding='utf-8').split('## Reconciliation after round 11', 1)[1]
    for phrase in ('rules.standing.replaces', 'rules.lesson.format', 'Per-column probes:', 'not a validated setting'):
        assert phrase in plan


def test_changelog_qualifies_ordering_and_review_migration():
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    direction = next(line for line in changelog.splitlines() if 'floor' in line and 'ordering' in line)
    assert {'priority', 'queue'} <= set(re.findall(r'\w+', direction.lower()))
    for section in ('Changed', 'Migration'):
        text = changelog.split('### ' + section, 1)[1].split('\n### ', 1)[0]
        for phrase in ('multi mode', 'same-host', '5.1.0', 'adaptive mode'):
            assert phrase in text.lower()
