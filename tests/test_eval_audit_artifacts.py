"""Saved audit predicates have discriminating deterministic negative controls."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.evals import audit_artifacts as audit
from scripts.evals.checks import CheckContext, SCRIPTED_CHECKS


@pytest.mark.parametrize('change', ['none', 'successful', 'unrelated', 'started', 'created', 'missing-exit'])
def test_repair_refusal_through_final_registry(tmp_path, change):
    outputs = tmp_path / 'outputs/trial'
    outputs.mkdir(parents=True)
    row = {'type': 'command_execution', 'command': 'python init_research_orchestrator.py trial --workflow unified',
           'exit_code': 2, 'aggregated_output': 'existing workflow conflicts with requested workflow'}
    if change == 'successful':
        row['exit_code'] = 0
    elif change == 'unrelated':
        row['aggregated_output'] = 'Permission denied'
    elif change == 'missing-exit':
        row.pop('exit_code')
    elif change == 'created':
        (outputs / 'plan.md').write_text('unexpected mutation')
    event = {'type': 'item.started' if change == 'started' else 'item.completed', 'item': row}
    (tmp_path / 'events.jsonl').write_text(json.dumps(event) + '\n', encoding='utf-8')
    ctx = CheckContext(tmp_path, tmp_path, tmp_path, 'python')
    passed, _ = SCRIPTED_CHECKS['repair-snapshot-scope', '90-refusal.md'](ctx)
    assert passed is (change == 'none')
    assert not ctx.executions or change == 'successful'


def test_scripted_registry_has_no_accidental_overrides():
    from scripts.evals import checks
    registries = [checks.ARTIFACT_CHECKS, checks.HOST_ARTIFACT_CHECKS,
                  checks.CHECKER_CASE_CHECKS, checks.AUDIT_ARTIFACT_CHECKS,
                  checks.STARTUP_ARTIFACT_CHECKS, checks.RUNTIME_BOUNDARY_CHECKS,
                  checks.STAGE_BOUNDARY_CHECKS, checks.DOCUMENT_CHECKS]
    seen = set()
    for registry in registries:
        assert not seen.intersection(registry)
        seen.update(registry)


def test_manifest_normalizes_shapes_without_ignoring_duplicates():
    digest = hashlib.sha256(b'kept').hexdigest()
    assert audit.manifest({'files': [{'path': 'trial/a.txt', 'sha256': digest}]}) == {'a.txt': digest}
    with pytest.raises(ValueError):
        audit.manifest([{'path': 'a', 'sha256': digest}, {'path': 'a', 'sha256': digest}])
    with pytest.raises(ValueError):
        audit.manifest({'a': 'looks unchanged'})


@pytest.mark.parametrize('mutation', ['none', 'missing-hidden', 'altered', 'extra'])
def test_snapshot_requires_all_retained_bytes(tmp_path, mutation):
    trial = tmp_path / 'trial'
    paths = ['nested/archive.txt', 'notes.txt', '.ro/local-state.json', 'agents.md', 'discoveries.md', 'handoff.md']
    before = {}
    for name in paths:
        path = trial / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        before[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if mutation == 'missing-hidden':
        before.pop('.ro/local-state.json')
    elif mutation == 'altered':
        (trial / 'notes.txt').write_bytes(b'changed')
    elif mutation == 'extra':
        (trial / 'extra.txt').write_bytes(b'extra')
    ctx = SimpleNamespace(outputs=tmp_path, data=lambda name: before)
    assert audit.complete_snapshot(ctx) is (mutation == 'none')


@pytest.mark.parametrize('hardcoded', [False, True])
def test_numeric_replay_rejects_fixed_answers(monkeypatch, hardcoded):
    base = {'count': 4, 'mean_current_seconds': 12, 'mean_candidate_seconds': 9, 'saved_seconds': 3}
    changed = {'count': 3, 'mean_current_seconds': 100 / 3, 'mean_candidate_seconds': 8, 'saved_seconds': 100 / 3 - 8}
    def fake_run(ctx, inputs, output, overrides=None):
        if overrides:
            assert overrides['timings.csv'].count(b'\n') == 4
        return base if hardcoded or not overrides else changed
    monkeypatch.setattr(audit, 'run_saved', fake_run)
    assert audit.comparison_code(SimpleNamespace(unchanged=lambda name: True)) is not hardcoded


@pytest.mark.parametrize('change', ['none', 'stale-count', 'stale-multiplier', 'wrong-dof'])
def test_replication_controls_check_arithmetic_and_coherence(tmp_path, change):
    import math
    import statistics
    source = tmp_path / 'files'
    source.mkdir()
    (source / 'observations.json').write_text('[2,4,9]')
    (source / 'method.json').write_text('{"degrees_of_freedom":2,"multiplier":1.5}')
    rows = []
    for values, multiplier in [([2, 4, 9], 1.5), ([3, 5, 11, 17], 1.5), ([2, 4, 9], 2.25)]:
        mean, sd = statistics.mean(values), statistics.stdev(values)
        margin = multiplier * sd / math.sqrt(len(values))
        rows.append({'observations': values, 'method': {'degrees_of_freedom': len(values) - 1, 'multiplier': multiplier},
                     'exit_code': 0, 'result': {'n': len(values), 'mean': mean, 'sd': sd, 'interval': [mean - margin, mean + margin]}})
    if change == 'stale-count':
        rows[1]['result']['n'] = 3
    elif change == 'stale-multiplier':
        rows[2]['result']['interval'] = rows[0]['result']['interval']
    elif change == 'wrong-dof':
        rows[1]['method']['degrees_of_freedom'] = 2
    ctx = SimpleNamespace(case_dir=tmp_path, data=lambda name: {'input-driven.py': rows})
    assert audit.valid_program(ctx) is (change == 'none')


def test_replay_renames_list_shaped_inputs_to_detect_answer_keys(tmp_path, monkeypatch):
    source = tmp_path / 'files'
    source.mkdir()
    (source / 'runs.json').write_text('[{"name":"one"},{"name":"two"}]')
    saved = {'included': ['one'], 'excluded': ['two']}
    ctx = SimpleNamespace(case_dir=tmp_path, data=lambda name: saved)
    def replay(ctx, inputs, output, overrides=None):
        if overrides:
            assert overrides['runs.json'] == [{'name': 'case-0'}, {'name': 'case-1'}]
            return {'included': ['case-0'], 'excluded': ['case-1']}
        return saved
    monkeypatch.setattr(audit, 'run_saved', replay)
    assert audit.audit_replays(ctx, ['runs.json'], 'runs')
    monkeypatch.setattr(audit, 'run_saved', lambda *args, **kwargs: saved)
    assert not audit.audit_replays(ctx, ['runs.json'], 'runs')


@pytest.mark.parametrize('link', ['reviewer.md', '../../outside/reviewer.md'])
def test_direct_copy_reviewer_link_must_stay_inside_runtime(tmp_path, link):
    runtime = tmp_path / 'local-skill/references'
    runtime.mkdir(parents=True)
    (runtime / 'verification.md').write_text(f'[Review]({link})')
    (runtime / 'reviewer.md').write_text('Inspect supplied evidence.')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'reviewer.md').write_text('Inspect supplied evidence.')
    source = tmp_path / 'source/references'
    source.mkdir(parents=True)
    (source / 'reviewer.md').write_text('Inspect supplied evidence.')
    context = SimpleNamespace(outputs=tmp_path, checker_skill=source.parent)
    assert audit.bundled_reviewer(context) is (link == 'reviewer.md')


@pytest.mark.parametrize('include_service', [True, False])
def test_retry_plan_uses_terminal_evidence_instead_of_scenario_name(tmp_path, include_service):
    source = tmp_path / 'files'
    source.mkdir()
    (source / 'runs.json').write_text(json.dumps([
        {'name': 'renamed-service', 'events': [{'type': 'turn.failed', 'error': {'message': '503 Service Unavailable'}}]},
        {'name': 'quoted', 'events': [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '503 Service Unavailable'}}]},
    ]))
    rows = {'renamed-service': {'retries': 3, 'fresh_session': True, 'resume': False}} if include_service else {}
    context = SimpleNamespace(case_dir=tmp_path, data=lambda name: rows)
    assert audit.retry_plan(context) is include_service
