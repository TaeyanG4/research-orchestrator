"""Objective artifact grading rejects neighboring wrong values without a model judge."""

import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from conftest import SKILL
from scripts.evals import checks


@pytest.mark.parametrize('severity', [None, 'WARN', 'ERROR'])
def test_clean_checker_uses_real_report_counts_and_bulleted_diagnostics(tmp_path, capsys, severity):
    from conftest import NOW, make_project
    from check_project import Checker
    from scripts.evals.deterministic_artifacts import clean_check
    root = make_project(tmp_path, 'report', '--preset', 'quick', '--user', 'operator')
    checker = Checker(root, now=NOW)
    checker.run(quiet=True)
    checker.issues = []
    if severity:
        checker.add(severity, 'fixture.check', 'plan.md', 'diagnostic from actual formatter')
    checker.report(int(severity == 'ERROR'), int(severity == 'WARN'))
    output = capsys.readouterr().out
    ctx = SimpleNamespace(text=lambda name: output)
    assert clean_check(ctx, 'checker.txt') is (severity is None)
    # The summary remains authoritative if individual diagnostics were clipped.
    ctx.text = lambda name: '\n'.join(line for line in output.splitlines() if not line.startswith('- '))
    assert clean_check(ctx, 'checker.txt') is (severity is None)


@pytest.mark.parametrize('text', ['CONSISTENCY: PASS', 'CONSISTENCY: cannot read files',
    'CONSISTENCY: OK (1 plan items)\n- WARN fixture.check: stale',
    'CONSISTENCY: OK (1 plan items)\nERROR fixture.check: broken'])
def test_clean_checker_rejects_unsupported_or_contradictory_summaries(text):
    from scripts.evals.deterministic_artifacts import clean_check
    assert not clean_check(SimpleNamespace(text=lambda name: text), 'checker.txt')


@pytest.mark.parametrize('mutation', ['none', 'wrong-warning', 'missing', 'truthy-string'])
def test_checker_summary_case_routes_require_boolean_outcomes(tmp_path, mutation):
    ctx = context(tmp_path, 'checker-summary-integrity')
    values = {key: {'clean': key in ('clean', 'info')} for key in ctx.data('checker-outputs.json')}
    if mutation == 'wrong-warning':
        values['clipped-warning']['clean'] = True
    elif mutation == 'missing':
        values.pop('unreadable')
    elif mutation == 'truthy-string':
        values['clean']['clean'] = 'true'
    write(ctx, 'verdicts.json', values)
    assert all(checks.SCRIPTED_CHECKS['checker-summary-integrity', path.name](ctx)[0]
               for path in (ctx.case_dir / 'graders').glob('*.md')) is (mutation == 'none')


@pytest.mark.parametrize('nested', [False, True])
@pytest.mark.parametrize('program', ['input-driven', 'sibling-helper', 'empty', 'hardcoded'])
def test_finite_audit_requires_replay_but_allows_nested_bundle_and_metadata(tmp_path, nested, program):
    from scripts.evals.deterministic_artifacts import finite_audit
    ctx = context(tmp_path, 'analytic-complete-coverage')
    bundle = ctx.outputs / ('project/audit' if nested else '.')
    bundle.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ctx.case_dir / 'files/quantities.txt', bundle / 'quantities.txt')
    (bundle / 'result.json').write_text(json.dumps({'count': 3, 'total': 10, 'units': 'items'}))
    code = "from pathlib import Path\nimport json\nv=[int(x) for x in Path('quantities.txt').read_text().splitlines()]\n"
    if program in ('input-driven', 'sibling-helper'):
        code += "Path('result.json').write_text(json.dumps({'count':len(v),'total':sum(v),'units':'items'}))\n"
        if program == 'sibling-helper':
            (bundle / 'helper.py').write_text(code)
            code = 'import helper\n'
    elif program == 'hardcoded':
        code += "Path('result.json').write_text(json.dumps({'count':3,'total':10}))\n"
    else:
        code = ''
    (bundle / 'calculate.py').write_text(code)
    assert finite_audit(ctx) is (program in ('input-driven', 'sibling-helper'))


def context(tmp_path, case):
    source = SKILL / 'evals' / case
    shutil.copytree(source / 'files', tmp_path / 'outputs')
    return checks.CheckContext(source, tmp_path, SKILL, sys.executable)


def write(ctx, name, value):
    (ctx.outputs / name).parent.mkdir(parents=True, exist_ok=True)
    (ctx.outputs / name).write_text(json.dumps(value), encoding='utf-8')


@pytest.mark.parametrize('mutation', ['none', 'sampled', 'numeric', 'wrong-class', 'wrong-id', 'circular'])
def test_analytic_assertions_reject_neighboring_evidence(tmp_path, mutation):
    ctx = context(tmp_path, 'analytic-complete-coverage')
    handoff = ('## Instruments\n\n### I-A-01 — exhaustive tally\n- Provenance: independent\n'
               '- Coverage: complete\n- Agreement: unmeasured\n- Resolution: unmeasured\n')
    discovery = ('## D-A-001 — use the calculation\n- Decision class: method-change\n- Instrument: I-A-01\n')
    report = 'CONSISTENCY: PASS\n'
    if mutation == 'sampled':
        handoff = handoff.replace('Coverage: complete', 'Coverage: held-out')
    elif mutation == 'numeric':
        handoff = handoff.replace('Agreement: unmeasured', 'Agreement: rank 0.9')
    elif mutation == 'wrong-class':
        discovery = discovery.replace('method-change', 'model-change')
    elif mutation == 'wrong-id':
        discovery = discovery.replace('I-A-01', 'I-A-02')
    elif mutation == 'circular':
        report = 'ERROR guard.instrument.circular: no eligible instrument\nCONSISTENCY: FAIL\n'
    for filename, content in [('project/handoff.md', handoff), ('project/discoveries.md', discovery),
                              ('checker.txt', report)]:
        target = ctx.outputs / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    predicate = checks.SCRIPTED_CHECKS['analytic-complete-coverage', '93-eligible-complete-evidence.md']
    assert predicate(ctx)[0] is (mutation == 'none')


@pytest.mark.parametrize('marker,expected', [('<!-- ro-template: v3.2 -->', True),
    ('<!-- ro-template: v3.2 (workflow=classic) -->', False), ('', False)])
def test_compact_marker_requires_one_version_only_marker(tmp_path, marker, expected):
    ctx = context(tmp_path, 'compact-render-metadata')
    (ctx.outputs / 'agents.md').write_text(marker, encoding='utf-8')
    assert checks.SCRIPTED_CHECKS['compact-render-metadata', '01-version-marker.md'](ctx)[0] is expected


@pytest.mark.parametrize('key,expected', [('workflow=classic pointers=hooks', True),
                                        ('workflow=classic', False), ('pointers=hooks', False)])
def test_sidecar_requires_workflow_and_pointer_conditions(tmp_path, key, expected):
    ctx = context(tmp_path, 'compact-render-metadata')
    write(ctx, '.ro/template-render.json', {'render_key': key})
    assert checks.SCRIPTED_CHECKS['compact-render-metadata', '02-sidecar.md'](ctx)[0] is expected


@pytest.mark.parametrize('settings,expected', [('- Platforms: single — local\n', True),
    ('- Platform mode: single\n- Platforms: local\n', False), ('- Platforms: single — remote\n', False)])
def test_single_host_uses_one_exact_setting(tmp_path, settings, expected):
    ctx = context(tmp_path, 'compact-render-metadata')
    (ctx.outputs / 'agents.md').write_text(settings, encoding='utf-8')
    assert checks.SCRIPTED_CHECKS['compact-render-metadata', '03-single-host.md'](ctx)[0] is expected


@pytest.mark.parametrize('preset,user,expected', [('quick', 'operator', True), ('solo-research', 'operator', False),
                                               ('quick', 'none', False)])
def test_quick_setup_checks_preset_and_user(tmp_path, preset, user, expected):
    ctx = context(tmp_path, 'quick-detected-setup')
    (ctx.outputs / 'agents.md').write_text(f'- Preset: {preset}\n', encoding='utf-8')
    (ctx.outputs / 'handoff.md').write_text(f'- Current user: {user}\n', encoding='utf-8')
    assert checks.SCRIPTED_CHECKS['quick-detected-setup', '01-initialized-quick.md'](ctx)[0] is expected


@pytest.mark.parametrize('redacted', [True, False])
def test_publication_redaction_checks_diagnostics_not_just_the_report(tmp_path, redacted):
    ctx = context(tmp_path, 'publication-destination-history')
    (ctx.outputs / 'audit.md').write_text('Publication denied; content redacted.', encoding='utf-8')
    output = 'publish.scan: content redacted' if redacted else 'publish.scan: ' + 'sk-' + 'a1B2' * 7
    record = {'type': 'item.completed', 'item': {'type': 'command_execution', 'exit_code': 1,
              'command': 'git push origin main', 'aggregated_output': output}}
    (ctx.run_dir / 'events.jsonl').write_text(json.dumps(record) + '\n', encoding='utf-8')
    assert checks.SCRIPTED_CHECKS['publication-destination-history', '03-credential-redacted.md'](ctx)[0] is redacted


@pytest.mark.parametrize('change', ['none', 'wrong-tail', 'wrong-boundary', 'wrong-correctness', 'missing'])
def test_scripted_latency_recomputes_all_samples_and_enforces_strict_boundary(tmp_path, change):
    ctx = context(tmp_path, 'hook-latency-budget')
    values = [183, 225, 151, 150, 151, 149, 99]
    source = ctx.data('measurements.json')['runs']
    rows = [{'id': row['id'], 'p95_ms': value, 'budget_ms': 150,
             'pass': value < 150 and row['hook_output_correct']} for row, value in zip(source, values)]
    if change == 'wrong-tail':
        rows[0]['p95_ms'] = 310
    elif change == 'wrong-boundary':
        rows[3]['pass'] = True
    elif change == 'wrong-correctness':
        rows[-1]['pass'] = True
    elif change == 'missing':
        rows.pop()
    write(ctx, 'verdicts.json', rows)
    names = ['90-01-windows-margin.md', '90-02-exact-boundary.md', '90-03-tighter-paths.md',
             '90-04-all-percentiles.md', '90-05-correctness-required.md']
    assert all(checks.SCRIPTED_CHECKS['hook-latency-budget', name](ctx)[0] for name in names) is (change == 'none')


@pytest.mark.parametrize('exit_code,output,expected', [(1, 'block jobs.mutate-bound: overlap', True),
    (0, 'warn jobs.mutate-bound: uncertain', False), (1, 'block shell.cd: cwd', False),
    (True, 'block jobs.mutate-bound: overlap', False)])
def test_scripted_failed_runner_check_requires_actual_block_result(tmp_path, exit_code, output, expected):
    ctx = context(tmp_path, 'failed-runner-protection')
    write(ctx, 'failed-protection.json', {'exit_code': exit_code, 'stdout': output, 'stderr': ''})
    assert checks.SCRIPTED_CHECKS['failed-runner-protection', '01-failed-binding-blocked.md'](ctx)[0] is expected


@pytest.mark.parametrize('count,parallel,expected', [(1, False, True), (2, False, False), (1, True, False), (0, False, False)])
def test_scripted_reservation_requires_one_exclusive_winner(tmp_path, count, parallel, expected):
    ctx = context(tmp_path, 'atomic-compute-reservation')
    write(ctx, 'reservation-snapshot.json', [{'confirmed': True, 'compute': {'resource': 'CPU', 'parallel': parallel}}] * count)
    assert checks.SCRIPTED_CHECKS['atomic-compute-reservation', '01-one-reservation.md'](ctx)[0] is expected


def test_new_scripted_routes_exist_and_missing_artifacts_fail_closed(tmp_path):
    case = 'explicit-multislot-selection'
    ctx = context(tmp_path, case)
    for grader in (ctx.case_dir / 'graders').glob('*.md'):
        assert (case, grader.name) in checks.SCRIPTED_CHECKS
        assert checks.SCRIPTED_CHECKS[case, grader.name](ctx)[0] is False


def test_judged_fence_assertions_route_to_structural_checks():
    case = 'fenced-record-examples'
    assert all((case, grader.name) in checks.SCRIPTED_CHECKS for grader in (SKILL / 'evals' / case / 'graders').glob('*.md'))


@pytest.mark.parametrize('flags', ['-E -S', '-B -X pycache_prefix=cache', '-Xpycache_prefix=cache -E -S'])
def test_resolved_command_prefix_flags_preserve_execution_evidence(tmp_path, flags):
    from scripts.evals.command_trace import ro_commands
    from scripts.evals.deterministic_artifacts import invocations
    from types import SimpleNamespace

    execution = {'command': f'python {flags} ro.py --project workspace --slot A monitor J-A-0001',
                 'aggregated_output': '- Job: J-A-0001; item H-A-01; outcome: process exited with code 0'}
    commands = ro_commands([execution])
    assert [(command.subcommand, command.job) for command in commands] == [('monitor', 'J-A-0001')]
    assert invocations(SimpleNamespace(executions=[execution]), 'monitor') == [
        (['J-A-0001'], execution['aggregated_output'])]


@pytest.mark.parametrize('mutation', ['none', 'earlier-release', 'only-one-ready'])
def test_claim_barrier_evidence_rejects_sequential_attempts(tmp_path, mutation):
    ctx = context(tmp_path, 'claim-contention')
    records = [{'ready_at': 10.0}, {'ready_at': 11.0}, {'released_at': 12.0}]
    if mutation == 'earlier-release':
        records[-1]['released_at'] = 10.5
    elif mutation == 'only-one-ready':
        records.pop(0)
    write(ctx, 'contention.json', {'events': records})
    assert checks.SCRIPTED_CHECKS['claim-contention', '02-concurrent-attempts.md'](ctx)[0] is (mutation == 'none')


@pytest.mark.parametrize('after', [{'plan.md': 'a' * 64}, {'plan.md': 'b' * 64}, {}])
def test_saved_policy_hashes_require_complete_before_after_match(tmp_path, after):
    ctx = context(tmp_path, 'saved-policy-roundtrip')
    before = {'plan.md': 'a' * 64}
    write(ctx, 'source-hashes.json', {'before': before, 'after': after})
    assert checks.SCRIPTED_CHECKS['saved-policy-roundtrip', '07-source-unchanged.md'](ctx)[0] is (after == before)


@pytest.mark.parametrize('multiple_selected,single_selected,expected', [(True, False, True), (False, False, False), (True, True, False)])
def test_hook_owner_boundary_check_discriminates_implicit_slot_routing(tmp_path, multiple_selected, single_selected, expected):
    ctx = context(tmp_path, 'explicit-multislot-selection')
    def response(selected):
        return {'message': 'Select a slot with --slot' if selected else 'Slot A: ready'}
    write(ctx, 'slot-results.json', {
        'identity_free_hooks': {event: response(multiple_selected) for event in ('SessionStart', 'Stop')},
        'single_slot_hooks': {event: response(single_selected) for event in ('SessionStart', 'Stop')},
    })
    assert checks.SCRIPTED_CHECKS['explicit-multislot-selection', '04-owner-event-boundary.md'](ctx)[0] is expected
