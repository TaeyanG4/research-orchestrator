"""Synthetic controls for saved-artifact predicates; no host or behaviour run."""

import json
from pathlib import Path

import pytest

from scripts.evals import host_artifacts as checks
from conftest import ROOT, SKILL


class Context:
    def __init__(self, outputs, documents):
        self.outputs = outputs
        self.documents = documents
        self.executions = []

    def data(self, name):
        return self.documents[name]

    def text(self, name):
        return self.documents[name]


def test_host_lifecycle_predicate_rejects_a_false_positive(tmp_path):
    context = Context(tmp_path, {'probe-audit.json': [
        {'id': 'stop-matching', 'observed': 'warned'}, {'id': 'post-matching', 'observed': 'warned'},
        {'id': 'post-wrong-event', 'observed': 'unknown/inconclusive'},
        {'id': 'post-no-mutation', 'observed': 'unknown/inconclusive'},
        {'id': 'stop-no-diagnostic', 'observed': 'unknown/inconclusive'}]})
    predicate = checks.CHECKS['host-lifecycle-probe-evidence', '02-inconclusive-evidence.md']
    assert predicate(context)[0]
    context.documents['probe-audit.json'][-1]['observed'] = 'warned'
    assert not predicate(context)[0]


def test_saved_codex_execution_after_denial_cannot_pass(tmp_path):
    context = Context(tmp_path, {'evidence-review.json': {'results': [
        {'id': 'parser-error-after-denial', 'observed': 'not blocked (shell executed)'},
        {'id': 'deleted-after-denial', 'observed': 'not blocked (file deleted)'}]}})
    predicate = checks.CHECKS['codex-enforcement-evidence', '90-01-rejects-execution-after-denial.md']
    assert predicate(context)[0]
    context.documents['evidence-review.json']['results'][0]['observed'] = 'denied'
    assert not predicate(context)[0]


def test_wrapper_artifact_requires_real_shape_and_expected_response(tmp_path):
    row = {'argv': ['sh', 'installed/hooks/ro-hook.sh', 'PreToolUse'], 'exit_code': 0,
           'stdin': '{}', 'env': {'RO_HOOK_PYTHON': str(tmp_path / 'python'), 'PATH': ''},
           'stdout': json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny',
                                                      'permissionDecisionReason': 'shell.background: refused'}})}
    context = Context(tmp_path, {'replay.json': [row]})
    predicate = checks.CHECKS['hook-interpreter-override', '90-01-selected-interpreter.md']
    assert predicate(context)[0]
    row['argv'][1] = 'replacement.py'
    assert not predicate(context)[0]


def test_native_startup_predicate_rejects_cross_session_claims(tmp_path):
    def row(identity, slot):
        return {'argv': ['python', 'ro_hook_runner.py', 'SessionStart'], 'exit_code': 0,
                'stdin': json.dumps({'cwd': '.', 'session_id': identity}),
                'stdout': json.dumps({'hookSpecificOutput': {'additionalContext': f'Slot {slot}: taken\nClaim H-{slot}-01: time'}})}
    context = Context(tmp_path, {'session-results.json': [row('native-first', 'A'), row('native-second', 'B')]})
    predicate = checks.CHECKS['native-session-slots', '01-distinct-startup.md']
    assert predicate(context)[0]
    context.documents['session-results.json'][1] = row('native-second', 'A')
    assert not predicate(context)[0]


def test_preservation_hashes_require_matching_before_and_after(tmp_path):
    a, b = 'a' * 64, 'b' * 64
    context = Context(tmp_path, {'install-audit.md': f'Skill before: {a}\nSkill after: {a}\n'})
    predicate = checks.CHECKS['installer-plugin-deduplication', '90-02-result.md']
    assert predicate(context)[0]
    context.documents['install-audit.md'] = f'Skill before: {a}\nSkill after: {b}\n'
    assert not predicate(context)[0]


def test_ci_matrix_checks_final_answer_not_source_or_prompt(tmp_path):
    context = Context(tmp_path, {'final.md': 'Matrix: windows-latest, ubuntu-latest, macos-latest.\n'
        'Python **3.12** for every job. Install pytest before python scripts/validate_release.py.\n'
        'Permissions are contents: read with no write permissions. No secrets; persist-credentials: false.'})
    context.case_dir = tmp_path
    (tmp_path / 'files').mkdir()
    (tmp_path / 'files/validate.yml').write_bytes((ROOT / '.github/workflows/validate.yml').read_bytes())
    predicates = [checks.CHECKS['release-ci-matrix', name + '.md'] for name in (
        '01-platforms', '02-python', '03-gate', '04-permissions', '05-no-credentials')]
    assert all(predicate(context)[0] for predicate in predicates)
    context.documents['final.md'] = 'I reviewed the workflow.'
    assert not any(predicate(context)[0] for predicate in predicates)


def test_ci_permission_check_rejects_a_write_grant(tmp_path):
    context = Context(tmp_path, {'final.md': 'contents: read; no write permissions'})
    context.case_dir = tmp_path
    (tmp_path / 'files').mkdir()
    path = tmp_path / 'files/validate.yml'
    path.write_text('permissions:\n  contents: read\n  issues: write\n', encoding='utf-8')
    assert not checks.CHECKS['release-ci-matrix', '04-permissions.md'](context)[0]


def test_annotated_tag_check_requires_control_location_and_no_matched_bytes(tmp_path):
    data = {'nested_annotation': {'exit_code': 1, 'findings': ['tag outer object annotation:3: credential']},
            'clean_annotation': {'exit_code': 0, 'findings': []}}
    context = Context(tmp_path, {'redaction-report.json': data})
    predicate = checks.CHECKS['credential-storage-redaction', '08-annotated-tag-scan.md']
    assert predicate(context)[0]
    data['clean_annotation']['exit_code'] = 1
    assert not predicate(context)[0]
    data['clean_annotation']['exit_code'] = 0
    data['nested_annotation']['findings'].append('github_pat_' + 'aB9_' * 20)
    assert not predicate(context)[0]


def test_wrapper_integrity_distinguishes_replay_from_payload_execution(tmp_path):
    row = {'argv': ['sh', '/installed/hooks/ro-hook.sh', 'PreToolUse'], 'exit_code': 0,
           'stdin': json.dumps({'tool_input': {'command': "printf 'payload ran'"}}), 'stdout': '{}'}
    context = Context(tmp_path, {'replay.json': [row]})
    context.run_dir = tmp_path
    (tmp_path / 'events.jsonl').write_text('{}\n', encoding='utf-8')
    context.executions = [{'command': "sh '/installed/hooks/ro-hook.sh' PreToolUse", 'aggregated_output': '{}'}]
    predicate = checks.CHECKS['hook-interpreter-override', '90-03-real-wrapper.md']
    assert predicate(context)[0]
    context.executions.append({'command': "printf 'payload ran'", 'aggregated_output': 'payload ran'})
    assert not predicate(context)[0]


def test_history_read_guard_requires_specific_independent_test_citation(tmp_path):
    context = Context(tmp_path, {'review.md': 'test_pretool_does_not_open_history_files rejects reads of '
                               'discoveries.md and handoff.md during PreToolUse.'})
    context.checker_skill = SKILL
    predicate = checks.CHECKS['hook-latency-budget', '90-06-history-guard.md']
    assert predicate(context)[0]
    context.documents['review.md'] = 'Fast latency proves that no history was read.'
    assert not predicate(context)[0]


def test_cli_data_hook_and_actual_subcommand_are_distinct(tmp_path):
    context = Context(tmp_path, {'command-results.json': [
        {'argv': ['python', '-E', '-S', 'ro.py', '--session', 'hook', 'dupcheck', 'hook'],
         'exit_code': 0, 'stdout': 'H-A-01'},
        {'argv': ['python', 'ro.py', '--session=hook', 'hook', 'PreToolUse'], 'exit_code': 0, 'stdout': '{}'}]})
    literal = checks.CHECKS['cli-hook-literal', '90-04-global-literal.md']
    actual = checks.CHECKS['cli-hook-literal', '90-05-actual-hook.md']
    assert literal(context)[0] and actual(context)[0]
    context.documents['command-results.json'].pop(0)
    assert not literal(context)[0] and actual(context)[0]
    context.documents['command-results.json'][0]['stdout'] = '[]'
    assert not actual(context)[0]


def test_publication_inventory_checks_preserved_bytes_against_input(tmp_path):
    context = Context(tmp_path / 'outputs', {})
    context.case_dir = tmp_path / 'case'
    (context.case_dir / 'files').mkdir(parents=True)
    (context.case_dir / 'files/fixture.json').write_bytes(b'{"passed":false}\n')
    preserved = context.outputs / 'private'
    preserved.mkdir(parents=True)
    source = (context.case_dir / 'files/fixture.json').read_bytes()
    (preserved / 'fixture.json').write_bytes(source)
    digest = checks.hashlib.sha256(source).hexdigest()
    (preserved / 'inventory.json').write_text(json.dumps({'fixture.json': {'sha256': digest}}), encoding='utf-8')
    predicate = checks.CHECKS['publication-archive-boundary', '90-04-result.md']
    assert predicate(context)[0]
    (preserved / 'fixture.json').write_bytes(b'changed')
    assert not predicate(context)[0]


def test_publication_gate_requires_both_observed_controls(tmp_path):
    context = Context(tmp_path, {})
    context.executions = [{'command': 'python -c "from scripts.validate_release import check_publication"',
        'aggregated_output': json.dumps({'contaminated': {'errors': ['publication: unsafe archive']},
                                        'sanitized': {'errors': []}})}]
    predicate = checks.CHECKS['publication-archive-boundary', '90-05-result.md']
    assert predicate(context)[0]
    context.executions[0]['aggregated_output'] = json.dumps({'sanitized': {'errors': []}})
    assert not predicate(context)[0]


def test_codex_dated_report_rejects_the_wrong_runtime_version(tmp_path):
    context = Context(tmp_path, {'codex-setup.md': 'Six probes on 2026-10-27 with codex-cli 0.154.0, '
        'gpt-6.1-sol and windows/powershell: shell.background, jobs.mutate-bound, jobs.read-bound, jobs.unmonitored, records.timestamp and benign. '
        + CODEX_TRUST_BOUNDARY})
    predicate = checks.CHECKS['codex-host-capabilities', '90-01-dated-enforcement-status.md']
    assert predicate(context)[0]
    context.documents['codex-setup.md'] = context.documents['codex-setup.md'].replace('0.154.0', '0.153.0')
    assert not predicate(context)[0]


CODEX_TRUST_BOUNDARY = (
    'All six used --dangerously-bypass-hook-trust, granting trust for that invocation '
    '(the state /hooks trust produces). The persisted /hooks route itself was not exercised. '
    'ro commands and Git pre-push remain the relied-on gates.')


@pytest.mark.parametrize('omitted', [
    '--dangerously-bypass-hook-trust', 'for that invocation',
    'jobs.unmonitored', 'records.timestamp',
    'The persisted /hooks route itself was not exercised.',
    'ro commands and Git pre-push remain the relied-on gates.',
])
def test_codex_dated_report_requires_each_trust_boundary_fact(tmp_path, omitted):
    report = ('Six probes on 2026-10-27 with codex-cli 0.154.0, gpt-6.1-sol and windows/powershell: '
              'shell.background, jobs.mutate-bound, jobs.read-bound, jobs.unmonitored, records.timestamp and benign. ' + CODEX_TRUST_BOUNDARY)
    context = Context(tmp_path, {'codex-setup.md': report.replace(omitted, '')})
    predicate = checks.CHECKS['codex-host-capabilities', '90-01-dated-enforcement-status.md']
    assert not predicate(context)[0]


def test_codex_dated_report_rejects_claimed_persisted_route_verification(tmp_path):
    report = ('Six probes on 2026-10-27 with codex-cli 0.154.0, gpt-6.1-sol and windows/powershell: '
              'shell.background, jobs.mutate-bound, jobs.read-bound, jobs.unmonitored, records.timestamp and benign. ' + CODEX_TRUST_BOUNDARY)
    context = Context(tmp_path, {'codex-setup.md': report.replace('was not exercised', 'was verified')})
    predicate = checks.CHECKS['codex-host-capabilities', '90-01-dated-enforcement-status.md']
    assert not predicate(context)[0]
