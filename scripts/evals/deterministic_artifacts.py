"""Artifact assertions with explicit fields and negative controls, never an LLM fallback."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile


CHECKS = {}


def register(case, name, predicate):
    def check(ctx):
        try:
            result = bool(predicate(ctx))
            return result, f"{case}/{name}: artifact predicate {'passed' if result else 'failed'}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, AssertionError, subprocess.SubprocessError) as exc:
            return False, f"{case}/{name}: unavailable or malformed artifact ({type(exc).__name__})"
    CHECKS[case, name + ".md"] = check


def helper():
    if __package__:
        from . import checks
    else:
        import checks
    return checks


def all_executions(c):
    rows = []
    for line in (c.run_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        row = event.get('item', {})
        if event.get('type') == 'item.completed' and row.get('type') == 'command_execution':
            rows.append(row)
    return rows


def invocations(c, command, *, include_failed=False):
    """Use token boundaries and real successful tool output, not quoted report prose."""
    if __package__:
        from .command_trace import _source, _statements
    else:
        from command_trace import _source, _statements
    found = []
    for execution in all_executions(c) if include_failed else c.executions:
        for words in _statements(_source(execution.get('command', ''))):
            if words and words[0] == '&':
                words = words[1:]
            if words and re.fullmatch(r'(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?', Path(words[0]).name):
                words = words[1:]
                while words:
                    if words[0].startswith('-X') and words[0] != '-X':
                        words = words[3:] if len(words) > 2 and words[1] == '=' else words[1:]
                    elif re.fullmatch(r'-B|-u|-E|-S|-3(?:\.\d+)?', words[0]):
                        words = words[1:]
                    elif words[0] == '-X' and len(words) > 1:
                        words = words[4:] if len(words) > 3 and words[2] == '=' else words[2:]
                    else:
                        break
            if not words or words[0].replace('\\', '/').rsplit('/', 1)[-1] not in ('ro', 'ro.py'):
                continue
            words = words[1:]
            while words and words[0] in ('--project', '--session', '--slot'):
                words = words[2:]
            if words and words[0] == command:
                found.append((words[1:], execution.get('aggregated_output', '')))
    return found


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def records(value):
    """Accept list or ID-keyed JSON formats without guessing truth from prose."""
    if isinstance(value, list):
        return {entry['id']: entry for entry in value if isinstance(entry, dict) and 'id' in entry}
    if isinstance(value, dict):
        for name in ('runs', 'results', 'verdicts', 'observations'):
            if name in value and isinstance(value[name], (list, dict)):
                return records(value[name])
        return {key: entry for key, entry in value.items() if isinstance(entry, dict)}
    return {}


def original(ctx, name):
    return (ctx.case_dir / 'files' / name).read_bytes() == (ctx.outputs / name).read_bytes()


def jobs(ctx, name='.ro/jobs.json'):
    data = ctx.data(name)
    assert isinstance(data, list)
    return data


def stopped(ctx, name='.ro/jobs.json'):
    entries = jobs(ctx, name)
    return bool(entries) and all(entry.get('tree_empty') is True and
        entry.get('status') in ('killed', 'finished') and
        (entry.get('monitor') or {}).get('active') is False and
        bool((entry.get('monitor') or {}).get('reason')) for entry in entries)


def checked_output(ctx, filename, field=None, *, blocked=True, phrase='jobs.mutate-bound'):
    value = ctx.data(filename)
    if field:
        value = value[field]
    return (type(value.get('exit_code')) is int and value['exit_code'] == int(blocked)
            and ('block ' if blocked else 'warn ') + phrase in value.get('stdout', ''))


register('failed-runner-protection', '01-failed-binding-blocked', lambda c: checked_output(c, 'failed-protection.json'))
register('failed-runner-protection', '02-ownership-preserved', lambda c: jobs(c) == json.loads((c.case_dir / 'files/registry.json').read_text(encoding='utf-8')))
register('failed-runner-protection', '03-input-preserved', lambda c: original(c, 'bound/input.txt'))
register('atomic-compute-reservation', '01-one-reservation', lambda c: len(jobs(c, 'reservation-snapshot.json')) == 1 and
         jobs(c, 'reservation-snapshot.json')[0].get('confirmed') is True and
         jobs(c, 'reservation-snapshot.json')[0].get('compute', {}).get('resource') == 'CPU' and
         jobs(c, 'reservation-snapshot.json')[0].get('compute', {}).get('parallel') is False)
register('atomic-compute-reservation', '02-contender-refused', lambda c:
         len(c.data('launch-results.json')['results']) == 2 and
         sum(r.get('exit_code') == 0 for r in c.data('launch-results.json')['results']) == 1 and
         sum(type(r.get('exit_code')) is int and r['exit_code'] != 0 and 'compute reservation conflicts' in r.get('stderr', '')
             for r in c.data('launch-results.json')['results']) == 1)
register('atomic-compute-reservation', '03-workers-stopped', stopped)
for name, field, blocked in [('01-absolute-after-blocked', 'absolute_after', True),
                              ('02-relative-before-blocked', 'relative_before', True),
                              ('03-relative-after-uncertain', 'relative_after', False)]:
    register('directory-change-binding-certainty', name, lambda c, f=field, b=blocked:
             checked_output(c, 'cd-results.json', f, blocked=b) and
             (b or 'Working directory is uncertain' in c.data('cd-results.json')[f]['stdout']))
register('directory-change-binding-certainty', '04-input-preserved', lambda c: original(c, 'bound/input.txt'))
register('explicit-multislot-selection', '01-implicit-refused', lambda c:
         type(c.data('slot-results.json')['implicit'].get('exit_code')) is int and
         c.data('slot-results.json')['implicit']['exit_code'] != 0 and
         'select a slot' in c.data('slot-results.json')['implicit'].get('stderr', ''))
register('explicit-multislot-selection', '02-no-default-allocation', lambda c: c.data('slot-results.json')['implicit_ids'] == {})
register('explicit-multislot-selection', '03-registered-b-allocation', lambda c:
         re.fullmatch(r'H-B-\d+', c.data('slot-results.json')['registered_id']) is not None)
register('explicit-multislot-selection', '04-owner-event-boundary', lambda c:
         set(c.data('slot-results.json')['identity_free_hooks']) == {'SessionStart', 'Stop'} and
         set(c.data('slot-results.json')['single_slot_hooks']) == {'SessionStart', 'Stop'} and
         all('select' in json.dumps(row).lower() and '--slot' in json.dumps(row)
             for row in c.data('slot-results.json')['identity_free_hooks'].values()) and
         all('select' not in json.dumps(row).lower() for row in c.data('slot-results.json')['single_slot_hooks'].values()))


def latency(c, selected=None, percentiles_only=False):
    inputs = json.loads((c.case_dir / 'files/measurements.json').read_text(encoding='utf-8'))['runs']
    outputs = records(c.data('verdicts.json'))
    if set(outputs) != {r['id'] for r in inputs}:
        return False
    for row in inputs:
        if selected and row['id'] not in selected:
            continue
        samples = sorted(row['samples_ms'])
        expected = samples[math.ceil(.95 * len(samples)) - 1]
        out = outputs[row['id']]
        if type(out.get('p95_ms')) not in (int, float) or out['p95_ms'] != expected:
            return False
        if not percentiles_only and (out.get('budget_ms') != 150 or
                out.get('pass') is not (expected < 150 and row['hook_output_correct'] is True)):
            return False
    return True


for name, selected in [('90-01-windows-margin', {'windows-supervisor'}),
                       ('90-02-exact-boundary', {'windows-supervisor-boundary', 'windows-in-process'}),
                       ('90-03-tighter-paths', {'windows-child', 'windows-in-process', 'linux-supervisor', 'macos-supervisor'}),
                       ('90-05-correctness-required', {'incorrect-output'})]:
    register('hook-latency-budget', name, lambda c, ids=selected: latency(c, ids))
register('hook-latency-budget', '90-04-all-percentiles', lambda c: latency(c, percentiles_only=True))
register('hook-latency-budget', '90-07-preserved-measurements', lambda c: original(c, 'measurements.json'))
register('hook-runtime-deadline', '01-deadline-paths', lambda c:
         all(records(c.data('verdicts.json'))[key].get('accepted') is value for key, value in
             {'configured-watchdog': True, 'fallback-child': True, 'unbounded-inline': False}.items()))
register('hook-runtime-deadline', '02-timeout-outcomes', lambda c:
         records(c.data('verdicts.json'))['ordinary-timeout'].get('accepted') is True and
         records(c.data('verdicts.json'))['publication-timeout'].get('accepted') is False)
register('hook-runtime-deadline', '03-budget-and-unknown', lambda c:
         len(records(c.data('verdicts.json'))) == 6 and
         all(row.get('budget_ms') == 150 for row in records(c.data('verdicts.json')).values()) and
         records(c.data('verdicts.json'))['linux-unmeasured'].get('accepted', 'missing') is None)


def fence_records(c, test):
    data = c.data('hook-records.json')
    return original(c, 'record_probe.py') and set(data) == {'tilde', 'long-backtick', 'long-tilde'} and all(test(row) for row in data.values())


register('fenced-record-examples', '90-runtime-policy', lambda c: original(c, 'policy_probe.py') and
         c.data('policy.json') == {variant: {parser: {'enforcement': 'block', 'block': 'external.gate'}
          for parser in ('shared', 'checker', 'runtime')} for variant in ('tilde', 'long-backtick', 'long-tilde')})
register('fenced-record-examples', '90-one-live-item', lambda c: set(helper().blocks(c.text('plan.md'), 'H')) == {'H-A-01'})
register('fenced-record-examples', '90-hook-reservation', lambda c:
         fence_records(c, lambda row: row['example_reservations'] == ['D-A-001'] and row['allocated']['stdout'].strip() == 'D-A-001'))
register('fenced-record-examples', '90-hook-cache', lambda c:
         fence_records(c, lambda row: all(row['example_snapshot'][key] == [] for key in ('ids', 'future', 'duplicate'))))
register('fenced-record-examples', '90-hook-examples', lambda c: fence_records(c, lambda row:
         row['example']['exit_code'] == 0 and isinstance(json.loads(row['example']['stdout']), dict) and
         not re.search(r'records\.(?:id|timestamp)', row['example']['stdout'])))
register('fenced-record-examples', '90-hook-live-records', lambda c: fence_records(c, lambda row:
         row['live']['exit_code'] == 0 and isinstance(json.loads(row['live']['stdout']), dict) and
         all(check in row['live']['stdout'] for check in ('records.id', 'records.timestamp'))))


def fenced_text(text):
    masked = helper().unfenced(text)
    return ''.join(line for line, visible in zip(text.splitlines(keepends=True), masked.splitlines(keepends=True))
                   if not visible.strip() and line.strip())


register('fenced-record-examples', '90-fenced-preserved', lambda c:
         bool(fenced_text((c.case_dir / 'files/plan.md').read_text(encoding='utf-8'))) and
         fenced_text(c.text('plan.md')) == fenced_text((c.case_dir / 'files/plan.md').read_text(encoding='utf-8')))
register('fenced-record-examples', '90-allocation', lambda c:
         all(any(args == [kind] and re.search(r'(?m)^' + identifier + r'\s*$', output)
                 for args, output in invocations(c, 'next-id')) for kind, identifier in [('H', 'H-A-02'), ('D', 'D-A-002'), ('I', 'I-A-01')]))
register('fenced-record-examples', '90-live-index', lambda c:
         any('D-A-001' in output and not re.search(r'D-A-99[89]', output) for _, output in invocations(c, 'index')))


def clean_check(c, filename=None):
    text = c.text(filename) if filename else '\n'.join(str(item.get('aggregated_output', '')) for item in c.executions
            if 'check_project.py' in item.get('command', ''))
    text = '\n'.join(text.splitlines())
    summaries = re.findall(r'^CONSISTENCY:\s*(.*)$', text, re.M)
    if not summaries or re.search(r'(?m)^\s*(?:-\s*)?(?:ERROR|WARN)\b', text):
        return False
    for summary in summaries:
        if re.fullmatch(r'OK \([^\n]+\)', summary):
            continue
        counts = re.fullmatch(r'(\d+) error\(s\), (\d+) warning\(s\), \d+ info \([^\n]+\)', summary)
        if not counts or any(int(count) for count in counts.groups()):
            return False
    return True


register('fenced-record-examples', '90-checker-clean', clean_check)
for name, expected in [('01-warning', {'warning': False, 'clipped-warning': False}),
                       ('02-error', {'error': False, 'contradictory': False}),
                       ('03-clean', {'clean': True, 'info': True}),
                       ('04-unknown', {'unreadable': False, 'invented-pass': False})]:
    register('checker-summary-integrity', name, lambda c, values=expected: all(
        isinstance(c.data('verdicts.json').get(key), dict) and
        c.data('verdicts.json')[key].get('clean') is clean for key, clean in values.items()))
register('identifier-rollover', '90-checker-accepts', clean_check)
register('identifier-rollover', '90-widened-identifiers', lambda c:
         'H-A-100' in helper().blocks(c.text('plan.md'), 'H') and
         'D-A-1000' in helper().blocks(c.text('discoveries.md'), 'D') and
         'I-A-100' in helper().blocks(c.text('handoff.md'), 'I') and
         'X-A-1000' in helper().blocks(c.text('handoff.md'), 'X') and original(c, 'docs/historical-ids.md'))
register('identifier-rollover', '90-prepared-only', lambda c:
         helper().fields(helper().blocks(c.text('handoff.md'), 'X')['X-A-1000']).get('Status') == 'prepared' and
         hashlib.sha256((c.outputs / 'candidate.txt').read_bytes()).hexdigest() in
         helper().fields(helper().blocks(c.text('handoff.md'), 'X')['X-A-1000']).get('Candidate', '') and
         not invocations(c, 'external'))
register('identifier-rollover', '90-evidence-links', lambda c:
         'I-A-100' in helper().fields(helper().blocks(c.text('discoveries.md'), 'D')['D-A-1000']).get('Instrument', '') and
         re.search(r'quality\s*=\s*0\.85\b.*I-A-100.*stable', helper().blocks(c.text('discoveries.md'), 'D')['D-A-1000'], re.S) is not None and
         re.search(r'Status:\s*planned\s+H-A-100\b', c.text('discoveries.md')) is not None and
         'H-A-100' in helper().blocks(c.text('plan.md'), 'H'))


for name, key in [('90-creation-refused', 'add'), ('90-validation-refused', 'check'), ('90-execution-refused', 'external')]:
    register('unreadable-subdirectory', name, lambda c, k=key: original(c, 'receipt_probe.py') and
             c.data('receipt-probe.json')[k] == {'refused': True, 'error_type': 'PermissionError'})
register('unreadable-subdirectory', '95-large-readable-artifact', lambda c:
         c.data('receipt-probe.json').get('large_artifact_hashed') is True and c.data('receipt-probe.json').get('large_artifact_bytes') == 68157440)
register('unreadable-subdirectory', '90-no-execution', lambda c:
         c.data('receipt-probe.json').get('executed') is False and not (c.outputs / 'executed.txt').exists())
for name, key, path in [('90-receipt-preserved', 'receipts', '.ro/receipts.json'), ('90-ledger-preserved', 'ledger', 'handoff.md')]:
    register('unreadable-subdirectory', name, lambda c, k=key, p=path:
             c.data('receipt-probe.json')['before_sha256'][k] == c.data('receipt-probe.json')['after_sha256'][k] ==
             hashlib.sha256((c.outputs / p).read_bytes()).hexdigest())


def snapshot_job(c, name, predicate):
    entries = jobs(c, name)
    return bool(entries) and all(predicate(row) for row in entries)


register('owned-job-supervisor-crash', '90-01-orphan-protected', lambda c:
         snapshot_job(c, 'orphan-observation.json', lambda j: j.get('status') == 'attention' and not j.get('ended') and j.get('orphaned') is True))
register('owned-job-supervisor-crash', '90-07-terminal-outcome', lambda c: stopped(c, 'final-jobs.json'))
register('owned-job-parent-exit', '01-no-premature-completion', lambda c:
         snapshot_job(c, 'parent-exit-observation.json', lambda j: bool(j.get('pid') and j.get('start')) and
                      j.get('status') in ('running', 'attention') and not j.get('ended')))
register('owned-job-parent-exit', '05-terminal-monitor-outcome', lambda c:
         stopped(c) and all('tree killed' in j['monitor']['reason'] for j in jobs(c)))
register('job-monitor-recovery', '01-stall-observed', lambda c: snapshot_job(c, 'stalled-observation.json',
         lambda j: not j.get('ended') and (j.get('monitor') or {}).get('reason') == 'heartbeat silence'))
register('job-monitor-recovery', '02-restarted-monitor-active', lambda c: snapshot_job(c, 'recovered-observation.json',
         lambda j: not j.get('ended') and (j.get('monitor') or {}).get('active') is True and
         bool(j['monitor'].get('pid') and j['monitor'].get('start'))))
register('job-monitor-recovery', '03-incident-retained', lambda c: bool(jobs(c)) and all(any(
         i.get('reason') == 'heartbeat silence' and type(i.get('observed')) in (int, float) and
         type(i.get('resolved')) in (int, float) and i['resolved'] >= i['observed'] for i in j.get('incidents', [])) for j in jobs(c)))
register('job-monitor-recovery', '04-completion-recorded', lambda c: stopped(c) and all(
         j['monitor']['reason'] == 'process exited with code 0' for j in jobs(c)) and
         any(json.loads(path.read_text(encoding='utf-8')).get('completed') is True for path in c.outputs.rglob('result.json')))
register('launch-root-binding', '90-job-cleanup', stopped)
register('hook-effective-working-directory', '07-worker-cleanup', stopped)
register('ancestor-rename-protection', '05-worker-stopped', stopped)
register('credential-storage-redaction', '07-worker-stopped', stopped)
register('hook-effective-working-directory', '06-preserved-inputs', lambda c:
         original(c, 'bound/input.txt') and original(c, 'scratch/input.txt'))
register('ancestor-rename-protection', '04-inputs-preserved', lambda c:
         original(c, 'runs/job-a/input.txt') and original(c, 'runs/job-b/input.txt'))


def settings(c, name='agents.md'):
    return helper().fields(c.text(name))


def saved_preferences(c, keys):
    source = c.data('source-settings.json')
    actual = settings(c, 'target/agents.md')
    source = {key.lower().replace(' ', '_').replace('-', '_'): value for key, value in source.items()}
    return all(actual.get(key) == source[key.lower().replace(' ', '_')] for key in keys)


register('saved-policy-roundtrip', '01-preferences-retained', lambda c: saved_preferences(c, ('Autonomy', 'Language', 'Environment')))
register('saved-policy-roundtrip', '02-custom-guards-retained', lambda c: saved_preferences(c, ('Guard set', 'Guard thresholds')))
register('saved-policy-roundtrip', '03-safety-policy-retained', lambda c:
         saved_preferences(c, ('Enforcement', 'Block', 'Read bound', 'External actions', 'Publish scan', 'Brief requirements')))
register('saved-policy-roundtrip', '04-bindings-excluded', lambda c:
         not {'preset', 'competition', 'phase_clock', 'queue_freeze'} & c.data('saved-policy.json').keys() and
         c.data('saved-policy.json').get('guards') == 'strict' and
         not any(token in c.text('saved-policy.json') for token in ('cedar-origin', '2001-01-01', '2099-12-31', '2099-01-01')))
register('saved-policy-roundtrip', '08-flag-precedence', lambda c:
         settings(c, 'override-target/agents.md').get('Language') == 'ja' and
         settings(c, 'override-target/agents.md').get('Autonomy') == 'away' and
         settings(c, 'override-target/agents.md').get('External actions') == settings(c, 'target/agents.md').get('External actions'))
register('compact-preset-settings', '90-04-result', lambda c: 'Keep the compatibility flag until the next release.' in
         c.text('agents.md').split('## Project rules', 1)[1])
register('compact-preset-settings', '90-02-result', lambda c: '- Git sync: commit' in re.sub(r'<details>.*?</details>', '', c.text('agents.md'), flags=re.S))
register('compact-preset-settings', '90-01-result', lambda c: any(all('- ' + key + ':' in group for key in
         ('Guard thresholds', 'Phase clock', 'Competition', 'Read bound', 'Brief requirements')) for group in re.findall(r'<details>.*?</details>', c.text('agents.md'), re.S)))
register('compact-preset-settings', '90-05-result', clean_check)
register('active-setting-pointers', '90-05-result', clean_check)


def installer_trials(c):
    actual = c.data('audit.json')['trials']
    inputs = json.loads((c.case_dir / 'files/scenarios.json').read_text(encoding='utf-8'))['trials']
    return len(actual) == len(inputs) and all(any(row.get('removed') == trial['remove'] and
        row.get('survivor') == trial['survivor'] and row.get('gate_exists') is True and
        row.get('gate_exit') == 1 and row.get('gate_decision') == 'deny' for row in actual) for trial in inputs)


register('installer-host-survival', '01-surviving-gates', installer_trials)
register('installer-host-survival', '02-literal-paths', lambda c: c.data('audit.json').get('literal_path_roundtrip') is True)
register('installer-host-survival', '03-executable-prefixes', lambda c:
         c.data('audit.json').get('shim_help_exit') == 0 and c.data('audit.json').get('prefix_help_exit') == 0 and
         all('Research Orchestrator' in c.text(name) and 'launch' in c.text(name) for name in ('shim-help.txt', 'prefix-help.txt')))
register('installer-host-survival', '04-portable-host', lambda c:
         c.data('audit.json').get('portable_host') == 'claude-code' and c.data('audit.json').get('codex_reinstall_after_move') is True)
register('direct-install-reviewer', '90-preserved-evidence', lambda c: original(c, 'review-request.md'))
register('work-brief-references', '90-compact-queue', lambda c: bool(helper().blocks(c.text('plan.md'), 'H')) and all(
         len(helper().fields(row)) <= 5 and {'Claimed', 'Evidence', 'Stages'} <= helper().fields(row).keys() and
         bool({'Goal', 'Hypothesis'} & helper().fields(row).keys()) and bool({'Next step', 'Next test'} & helper().fields(row).keys())
         for row in helper().blocks(c.text('plan.md'), 'H').values()))
register('work-brief-references', '90-brief-reference', lambda c: bool(helper().blocks(c.text('plan.md'), 'H')) and all(
         'brief.md' in ' '.join(helper().fields(row).get(key, '') for key in ('Evidence', 'Next test', 'Next step'))
         for row in helper().blocks(c.text('plan.md'), 'H').values()))


register('receipt-policy-boundaries', '01-defaults', lambda c: c.data('checks.json')['defaults'] == {'solo': 'self', 'team': 'independent'})
register('receipt-policy-boundaries', '02-single-action', lambda c:
         sum(row.get('name') == 'self-once' and row.get('exit_code') == 0 and row.get('spawned') is True
             for row in c.data('checks.json')['trials']) == 1 and
         c.data('solo/.ro/external-attempts/X-A-001.json').get('status') == 'done')
register('receipt-policy-boundaries', '03-gates', lambda c:
         all(sum(row.get('name') == name and type(row.get('exit_code')) is int and row['exit_code'] != 0 and
                 row.get('spawned') is False for row in c.data('checks.json')['trials']) == 1 for name in
             ('replay', 'independent-self', 'future-expectation', 'duplicate', 'malformed-ledger', 'journal')))
register('receipt-policy-boundaries', '04-input', lambda c: original(c, 'candidate.txt'))


def export_members(c):
    with zipfile.ZipFile(c.outputs / 'evidence.zip') as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def export_named(c, suffix):
    matches = [raw for name, raw in export_members(c).items() if name.endswith('/' + suffix)]
    if len(matches) != 1:
        raise ValueError('expected one artifact')
    return matches[0]


register('retained-output-export', '01-task-files', lambda c:
         json.loads(export_named(c, 'outputs/result.json')) == {'mean': 2.5, 'count': 4} and
         export_named(c, 'outputs/analyze.py') == (c.case_dir / 'files/saved/case-a/with_skill/outputs/analyze.py').read_bytes())
register('retained-output-export', '02-verdict-timing', lambda c:
         json.loads(export_named(c, 'grading.json'))['expectations'] == [
             {'text': 'The mean equals 3', 'passed': False, 'evidence': 'result.json gives 2.5'}] and
         json.loads(export_named(c, 'timing.json')).get('total_tokens') == 123 and
         json.loads(export_named(c, 'timing.json')).get('duration_ms') == 456)


def export_hashes(c):
    members = export_members(c)
    manifest = json.loads(members['manifest.json'])
    entries = manifest['files']
    if set(members) != {'manifest.json'} | {entry['path'] for entry in entries}:
        return False
    sources = {path.relative_to(c.case_dir / 'files/saved').as_posix(): path.read_bytes()
               for path in (c.case_dir / 'files/saved').rglob('*') if path.is_file()}
    for entry in entries:
        candidates = [value for name, value in sources.items() if entry['path'].endswith('/' + name)]
        if len(candidates) != 1 or hashlib.sha256(candidates[0]).hexdigest() != entry['source_sha256']:
            return False
        if hashlib.sha256(members[entry['path']]).hexdigest() != entry['export_sha256']:
            return False
    return len(entries) == len(sources)


register('retained-output-export', '03-hashes', export_hashes)


def response_pairs(c, filename):
    pairs = []
    for row in objects(c.data(filename)):
        payload = row.get('payload', row.get('request', row.get('stdin')))
        response = row.get('response', row.get('output', row.get('stdout')))
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                continue
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except ValueError:
                continue
        if isinstance(payload, dict) and isinstance(response, dict) and isinstance(payload.get('tool_input'), dict):
            pairs.append((payload, response))
    return pairs


def denied(response):
    return response.get('decision') == 'block' or response.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'


def directory_probe(c, variant):
    matches = []
    for payload, response in response_pairs(c, 'probe-results.json'):
        tool = payload['tool_input']
        cmd = tool.get('command', '')
        cwd = str(payload.get('cwd', '')).replace('\\', '/').rstrip('/')
        workdir = str(tool.get('workdir', tool.get('cwd', ''))).replace('\\', '/').rstrip('/')
        if '../bound/input.txt' in cmd:
            actual = 'parent'
        elif not cwd and not workdir:
            actual = 'unknown'
        elif workdir.endswith('/bound'):
            actual = 'tool'
        elif cwd.endswith('/bound'):
            actual = 'envelope'
        elif cwd.endswith('/scratch'):
            actual = 'sibling'
        else:
            continue
        if actual == variant and 'input.txt' in cmd:
            if variant == 'unknown':
                matches.append(not denied(response) and 'working directory is uncertain' in json.dumps(response).lower())
            else:
                matches.append(denied(response) is (variant != 'sibling'))
    return bool(matches) and all(matches)


for name, kind in [('01-envelope-cwd', 'envelope'), ('02-tool-workdir', 'tool'), ('03-unrelated-sibling', 'sibling'),
                   ('04-parent-relative-target', 'parent'), ('05-unknown-directory', 'unknown')]:
    register('hook-effective-working-directory', name, lambda c, k=kind: directory_probe(c, k))


def rename_probe(c, variant):
    matches = []
    for payload, response in response_pairs(c, 'rename-probes.json'):
        command = payload['tool_input'].get('command', '')
        source = re.search(r'-LiteralPath\s+(?:"([^"]+)"|\x27([^\x27]+)\x27|(\S+))', command, re.I)
        if not source:
            continue
        source = next(value for value in source.groups() if value is not None).replace('\\', '/')
        kind = 'sibling' if source.rstrip('/').endswith('runs/job-b') else 'relative' if source == 'runs' else 'absolute'
        if kind == variant:
            matches.append(denied(response) is (variant != 'sibling'))
    return bool(matches) and all(matches)


for name, kind in [('01-relative-ancestor-denied', 'relative'), ('02-absolute-ancestor-denied', 'absolute'), ('03-sibling-allowed', 'sibling')]:
    register('ancestor-rename-protection', name, lambda c, k=kind: rename_probe(c, k))


def binding_targets(c):
    data = c.data('binding-checks.json')
    selected = {}
    wanted = {'plan.md', 'handoff.md', 'discoveries.md', 'worker.py', 'inputs.txt'}
    for row in objects(data):
        for name, value in row.items():
            if name in wanted:
                selected[name] = value
        target = row.get('target', row.get('path', row.get('file')))
        if target in wanted:
            selected[target] = row.get('checks', row.get('findings', row.get('check_ids')))
    return selected


register('launch-root-binding', '90-inputs-protected', lambda c: all(
         'jobs.mutate-bound' in json.dumps(binding_targets(c)[name]) for name in ('worker.py', 'inputs.txt')))
register('launch-root-binding', '90-coordination-writable', lambda c: all(
         'jobs.mutate-bound' not in json.dumps(binding_targets(c)[name]) for name in ('plan.md', 'handoff.md', 'discoveries.md')))
register('launch-root-binding', '90-binding-notice', lambda c: any(
         'project root is not bound' in output and 'script paths and explicit --bind' in output for _, output in invocations(c, 'launch')))


def credential_results(c):
    rows = []
    for path in (c.outputs / '.ro').rglob('*.json'):
        if path.name == 'jobs.json':
            continue
        try:
            values = json.loads(path.read_text(encoding='utf-8'))
        except ValueError:
            continue
        rows.extend(row for row in objects(values) if 'stdout' in row and 'stderr' in row and 'exit_code' in row)
    return rows


def no_secret(text):
    secrets = ['github_pat_' + 'aB9_' * 20, 'ASIA' + 'A1' * 8, 'PrivateBody6543210', 'SplitToken9753']
    return not any(value in text for value in secrets)


register('credential-storage-redaction', '01-job-command-redacted', lambda c:
         bool(jobs(c)) and no_secret(c.text('.ro/jobs.json')) and all('[REDACTED' in j.get('command', '') for j in jobs(c)))
for name, stream in [('02-external-stdout-redacted', 'stdout'), ('03-external-stderr-redacted', 'stderr')]:
    register('credential-storage-redaction', name, lambda c, k=stream:
             len(credential_results(c)) >= 2 and all(no_secret(row[k]) for row in credential_results(c)))
register('credential-storage-redaction', '04-redaction-markers', lambda c:
         len(credential_results(c)) >= 2 and all('[REDACTED' in row[key] for row in credential_results(c) for key in ('stdout', 'stderr')))
register('credential-storage-redaction', '05-response-evidence-preserved', lambda c:
         any(row['exit_code'] == 0 and 'archive-accepted-482' in row['stdout'] for row in credential_results(c)) and
         any(row['exit_code'] == 7 and 'archive-uncertain-731' in row['stdout'] for row in credential_results(c)))
register('credential-storage-redaction', '06-one-execution-per-action', lambda c:
         c.text('executions.log').splitlines().count('success') == 1 and
         c.text('executions.log').splitlines().count('failure') == 1 and len(c.text('executions.log').splitlines()) == 2)


def contention(c):
    return [row for row in objects(c.data('contention.json')) if type(row.get('exit_code')) is int and
            'stdout' in row and 'stderr' in row]


register('claim-contention', '03-one-winner', lambda c: len(contention(c)) == 2 and
         sum(row['exit_code'] == 0 for row in contention(c)) == 1)
register('claim-contention', '04-rejected-rival', lambda c: len(contention(c)) == 2 and
         sum(row['exit_code'] != 0 and re.search(r'(already|claimed|owned|belongs)', row['stderr'], re.I) is not None and
             'H-A-01' in row['stderr'] for row in contention(c)) == 1)


def winning_claim(c):
    winning = [row for row in contention(c) if row['exit_code'] == 0]
    if len(winning) != 1:
        return False
    command = winning[0].get('args', winning[0].get('argv', winning[0].get('arguments', [])))
    command = ' '.join(command) if isinstance(command, list) else str(command)
    match = re.search(r'--slot[ =]+([AB])\b', command)
    block = helper().blocks(c.text('plan.md'), 'H').get('H-A-01', '')
    claims = re.findall(r'^- Claimed:\s*(.+)$', helper().unfenced(block), re.M)
    return bool(match and len(claims) == 1 and re.match(re.escape(match[1]) + r' since ', claims[0]))


register('claim-contention', '05-durable-owner', winning_claim)
def finite_audit(c):
    """A colocated input/program/result bundle must replay on fresh inputs."""
    from_module = __package__ + '.proc' if __package__ else 'proc'
    from importlib import import_module
    flags = import_module(from_module).no_window_flags
    source = (c.case_dir / 'files/quantities.txt').read_bytes()
    def matches(value, count, total):
        return isinstance(value, dict) and all(type(value.get(key)) in (int, float) and value[key] == expected
            for key, expected in [('count', count), ('total', total)])
    for program in c.outputs.rglob('calculate.py'):
        folder = program.parent
        if not (folder / 'quantities.txt').is_file() or (folder / 'quantities.txt').read_bytes() != source:
            continue
        values = [int(line) for line in source.decode().splitlines() if line.strip()]
        try:
            saved = json.loads((folder / 'result.json').read_text())
        except (OSError, ValueError):
            continue
        if not matches(saved, len(values), sum(values)):
            continue
        for raw, count, total in [(source, len(values), sum(values)), (b'7\n-2\n13\n4\n', 4, 22)]:
            with tempfile.TemporaryDirectory(prefix='ro-finite-check-') as directory:
                root = Path(directory)
                for dependency in folder.glob('*.py'):
                    shutil.copyfile(dependency, root / dependency.name)
                (root / 'quantities.txt').write_bytes(raw)
                result = subprocess.run([c.python, '-E', '-s', '-S', str(root / program.name)], cwd=root,
                    capture_output=True, timeout=10, creationflags=flags())
                output = root / 'result.json'
                if result.returncode or not output.is_file() or output.stat().st_size > 2_000_000 or not matches(
                        json.loads(output.read_text()), count, total):
                    break
        else:
            return True
    return False


register('analytic-complete-coverage', '90-exact-result', finite_audit)
register('analytic-complete-coverage', '90-complete-coverage', lambda c:
         any(helper().fields(block).get('Coverage') == 'complete' for block in helper().blocks(c.text('project/handoff.md'), 'I').values()))
register('analytic-complete-coverage', '90-checker-clean', lambda c: clean_check(c, 'checker.txt'))
register('analytic-complete-coverage', '90-note-kind', lambda c: bool(re.search(r'^#{1,3}\s+N-[A-Z]+-\d+\b', c.text('project/docs/scope-note.md'), re.M)) and
         'docs/scope-note.md' in c.text('project/handoff.md') and
         not re.search(r'^#{1,3}\s+[DH]-[A-Z]+-\d+\b', c.text('project/docs/scope-note.md'), re.M))


def complete_instruments(c):
    return {key: helper().fields(block) for key, block in helper().blocks(c.text('project/handoff.md'), 'I').items()
            if helper().fields(block).get('Coverage') == 'complete'}


def complete_method_decision(c, agreement=None):
    instruments = {key: row for key, row in complete_instruments(c).items()
                   if agreement is None or row.get('Agreement') == agreement}
    return any(helper().fields(block).get('Decision class') == 'method-change' and
               any(key in re.findall(r'\bI-[A-Z]+-\d+\b', helper().fields(block).get('Instrument', ''))
                   for key in instruments)
               for block in helper().blocks(c.text('project/discoveries.md'), 'D').values())


register('analytic-complete-coverage', '91-unmeasured-estimates', lambda c:
         any(row.get('Agreement') == row.get('Resolution') == 'unmeasured' for row in complete_instruments(c).values()))
register('analytic-complete-coverage', '92-neutral-method-decision', complete_method_decision)
register('analytic-complete-coverage', '93-eligible-complete-evidence', lambda c:
         complete_method_decision(c, agreement='unmeasured') and 'CONSISTENCY:' in c.text('checker.txt') and
         not re.search(r'^(?:- )?(?:ERROR|WARN|INFO) guard\.instrument\.circular\b', c.text('checker.txt'), re.M))
register('compact-render-metadata', '01-version-marker', lambda c:
         re.findall(r'<!-- ro-template: .*? -->', c.text('agents.md')) ==
         re.findall(r'<!-- ro-template: v\d+(?:\.\d+)* -->', c.text('agents.md')) and
         len(re.findall(r'<!-- ro-template:', c.text('agents.md'))) == 1)
register('compact-render-metadata', '02-sidecar', lambda c:
         re.search(r'\bworkflow=(?:classic|unified)\b', c.data('.ro/template-render.json')['render_key']) is not None and
         re.search(r'\bpointers=\S+', c.data('.ro/template-render.json')['render_key']) is not None)
register('compact-render-metadata', '03-single-host', lambda c:
         helper().fields(c.text('agents.md')).get('Platforms') == 'single — local' and
         'Platform mode' not in helper().fields(c.text('agents.md')))
register('quick-detected-setup', '01-initialized-quick', lambda c:
         helper().fields(c.text('agents.md')).get('Preset') == 'quick' and
         helper().fields(c.text('handoff.md')).get('Current user') == 'operator')


def publication_diagnostics_redacted(c):
    diagnostics = '\n'.join(str(row.get('aggregated_output', '')) for row in all_executions(c))
    return 'publish.scan' in diagnostics and 'sk-' + 'a1B2' * 7 not in c.text('audit.md') + diagnostics


register('publication-destination-history', '03-credential-redacted', publication_diagnostics_redacted)
register('cli-hook-literal', '90-03-child-literal', lambda c: c.text('argument.txt') == 'hook\n')
register('cli-hook-literal', '90-02-observation-literal', lambda c:
         re.search(r'^- Adapter observation:.*\bhook\b', c.text('handoff.md'), re.M) is not None)
register('cli-hook-literal', '90-01-search-literal', lambda c: any(args == ['hook'] and 'H-A-01' in output for args, output in invocations(c, 'dupcheck')))


def named_rows(value):
    result = {}
    for row in objects(value):
        name = row.get('id', row.get('name', row.get('query')))
        if isinstance(name, str):
            result[name] = row
        for key, child in row.items():
            if isinstance(child, dict):
                result.setdefault(key, child)
    return result


def audit_names(c, section):
    value = c.data('audit.json')[section]
    if isinstance(value, dict):
        return set(value)
    if isinstance(value, list):
        return {row if isinstance(row, str) else row.get('name', row.get('id')) for row in value}
    raise ValueError('audit membership must be a list or mapping')


def audit_reason(c, name):
    data = c.data('audit.json')
    row = named_rows(data).get(name, {})
    text = row.get('reason', row.get('evidence', row.get('reasons', '')))
    for key in ('reasons', 'evidence', 'exclusion_reasons'):
        if isinstance(data.get(key), dict) and name in data[key]:
            text = data[key][name]
    if isinstance(data.get('excluded'), dict) and isinstance(data['excluded'].get(name), str):
        text = data['excluded'][name]
    return json.dumps(text, ensure_ascii=False).lower()


def excluded(c, reasons):
    return all(name in audit_names(c, 'excluded') and re.search(pattern, audit_reason(c, name), re.I)
               for name, pattern in reasons.items())


register('evaluation-grade-integrity', '90-01-unsupported-summary', lambda c: excluded(c,
         {'empty-perfect': r'(empty|no|missing|absent).*(verdict|expectation|evidence)', 'inconsistent-summary': r'(summary|count).*(disagree|inconsisten|mismatch|unsupported)'}))
register('evaluation-grade-integrity', '90-02-complete-unique-typed', lambda c: excluded(c,
         {'missing': r'(missing|incomplete)', 'duplicate': r'duplicate', 'nonboolean': r'bool', 'no-evidence': r'evidence'}))
register('evaluation-grade-integrity', '90-03-source-assertions', lambda c: excluded(c,
         {'substituted-assertion': r'(source|authoritative|substitut|assertion.*mismatch)'}))
register('evaluation-grade-integrity', '90-nonfinite-measurement', lambda c: excluded(c,
         {'nonfinite-duration': r'(finite|overflow|represent|duration)'}))
register('evaluation-grade-integrity', '90-numeric-range', lambda c: excluded(c,
         {'oversized-rate': r'(range|rate|finite)'}))


def grade_summaries(c):
    data = c.data('audit.json')
    if audit_names(c, 'included') != {'valid-partial', 'valid-perfect'}:
        return False
    rows = named_rows(data)
    for name, expected in [('valid-partial', {'passed': 1, 'failed': 1, 'total': 2, 'pass_rate': .5}),
                           ('valid-perfect', {'passed': 2, 'failed': 0, 'total': 2, 'pass_rate': 1.0})]:
        row = rows.get(name, {})
        row = row.get('summary', row)
        if not all(type(row.get(key)) in (int, float) and row[key] == value for key, value in expected.items()):
            return False
    return any(row.get('mean_pass_rate') == .75 for row in objects(data))


register('evaluation-grade-integrity', '90-04-derived-score', grade_summaries)
register('evaluation-trace-audit', '90-01-genuine-runs', lambda c:
         audit_names(c, 'included') == {'staged-runtime', 'ancestor-probe', 'python-program', 'prompt-only'})
register('evaluation-trace-audit', '90-02-protected-access', lambda c: excluded(c, {
         'source-read': r'(source|repository)', 'other-run': r'(other|run)', 'hidden-grader': r'grader',
         'installed-skill': r'installed', 'ancestor-present': r'(ancestor|agents)'}))
register('evaluation-trace-audit', '90-03-unresolved-history', lambda c: excluded(c,
         {'absent-trace': r'(trace|evidence)', 'runtime-modified': r'(modif|runtime)'}))
register('evaluation-trace-code-operands', '90-01-python-stdin', lambda c:
         {'python-flags', 'python-implicit-stdin'} <= audit_names(c, 'included') and
         all(re.search(r'(stdin|program|runtime|operand)', audit_reason(c, name)) for name in ('python-flags', 'python-implicit-stdin')))
register('evaluation-trace-code-operands', '90-02-unparsed-command', lambda c:
         'unparsed-command' in audit_names(c, 'included') and excluded(c, {'unparsed-grader': r'grader'}))
register('evaluation-trace-code-operands', '90-03-array-delimiter', lambda c:
         'ancestor-array' in audit_names(c, 'included') and excluded(c, {'ancestor-comma-filename': r'(comma|ancestor|filename)'}))
register('evaluation-trace-code-operands', '90-04-protected-operands', lambda c: excluded(c,
         {'python-source': r'source', 'python-installed': r'installed', 'python-other-run': r'(other|run)'}))
register('evaluation-trace-code-operands', '90-05-uncleared-findings', lambda c: excluded(c,
         {'ancestor-present': r'(ancestor|agents)', 'missing-trace': r'(trace|evidence)'}))
register('evaluation-trace-code-operands', '90-08-data-literals', lambda c:
         {'python-data-literals', 'powershell-name-filter'} <= audit_names(c, 'included') and
         {'python-data-then-read', 'filter-then-read'} <= audit_names(c, 'excluded'))
register('evaluation-transport-evidence', '90-terminal-services', lambda c: excluded(c,
         {'capacity': r'(host|turn.failed|capacity)', 'bridge': r'(host|turn.failed|bridge)'}))
register('evaluation-transport-evidence', '90-evidence-channel', lambda c:
         {'quoted-capacity', 'tool-capacity'} <= audit_names(c, 'included'))
register('evaluation-transport-evidence', '90-copy-failure', lambda c: excluded(c, {'setup-copy': r'(copy|capture|output)'}))
register('evaluation-transport-evidence', '90-recovery', lambda c:
         {'recovered', 'later-permission-error'} <= audit_names(c, 'included'))


def prediction(c, name, expected, reason=None):
    row = named_rows(c.data('classifications.json'))[name]
    if row.get('prediction', 'missing') is not expected:
        return False
    return reason is None or re.search(reason, json.dumps(row, ensure_ascii=False), re.I) is not None


register('trigger-measurement-reasons', '90-clean-endpoints', lambda c:
         all(prediction(c, name, value) for name, value in {'clean-positive': True, 'recovered-retry': True, 'clean-negative': False}.items()))
register('trigger-measurement-reasons', '90-distinct-failures', lambda c:
         all(prediction(c, name, None, reason) for name, reason in {'throttled': r'(rate.limit|429)', 'unavailable': r'setup', 'empty-query': r'missing.*repeat'}.items()))
register('trigger-measurement-reasons', '90-contamination-priority', lambda c:
         prediction(c, 'exposed-context', None, r'source_repository') and
         re.search(r'(repeat[^\d]*2|"repeat"\s*:\s*2)', json.dumps(named_rows(c.data('classifications.json'))['exposed-context'])) is not None)
register('trigger-measurement-reasons', '90-timeout-unknown', lambda c: prediction(c, 'selected-timeout', None, r'timeout') and
         re.search(r'(repeat[^\d]*1|"repeat"\s*:\s*1)', json.dumps(named_rows(c.data('classifications.json'))['selected-timeout'])) is not None)
register('trigger-measurement-reasons', '90-required-repeats', lambda c: prediction(c, 'short-repeat', None, r'(repeat|missing)'))
register('trigger-measurement-reasons', '90-invalid-records', lambda c: all(prediction(c, name, None, reason) for name, reason in
         {'contradictory-summary': r'(contradict|summary|mismatch)', 'malformed-attempt': r'(malformed|attempt|metadata)',
          'missing-measurement': r'(missing|measurement)'}.items()))
register('trigger-measurement-reasons', '90-preserved-input', lambda c: original(c, 'measurements.json'))


def confusion(c):
    data = c.data('classifications.json')
    names = {'true_positives': 2, 'true_negatives': 1, 'false_positives': 0, 'false_negatives': 0, 'inconclusive': 9, 'coverage': .25}
    aliases = {'true_positives': 'tp', 'true_negatives': 'tn', 'false_positives': 'fp', 'false_negatives': 'fn'}
    values = {}
    for row in objects(data):
        for key in names:
            if key in row:
                values[key] = row[key]
            elif aliases.get(key) in row:
                values[key] = row[aliases[key]]
    return all(type(values.get(key)) in (int, float) and values[key] == value for key, value in names.items())


register('trigger-measurement-reasons', '90-aggregate-coverage', confusion)


def publication_archives(c):
    candidates = list(c.outputs.rglob('*.zip'))
    # The task may retain its deliberate contaminated negative control separately.
    published = [path for path in candidates if not re.search(r'(contaminat|unsafe|negative|before)', path.name, re.I)]
    contents = []
    for path in published:
        with zipfile.ZipFile(path) as archive:
            contents.extend((name, archive.read(name)) for name in archive.namelist() if not name.endswith('/'))
    return contents


register('publication-archive-boundary', '90-01-result', lambda c: any(
         isinstance(json.loads(raw), dict) and json.loads(raw).get('passed') is False
         for name, raw in publication_archives(c) if name.endswith('.json') and not name.endswith('manifest.json')))
register('publication-archive-boundary', '90-02-result', lambda c: bool(publication_archives(c)) and all(
         not re.search(r'[A-Za-z]:[/\\]|/(?:home|Users)/', raw.decode('utf-8')) for _, raw in publication_archives(c)))
register('publication-archive-boundary', '90-03-result', lambda c: bool(publication_archives(c)) and all(
         not re.search(r'(?:transcript|events\.jsonl|inventory)', name, re.I) and
         not re.search(r'"(?:available_skills|thread_id|session_id)"', raw.decode('utf-8'))
         for name, raw in publication_archives(c)))
register('close-recorded-scope', '90-followup', lambda c:
         'Discoveries without follow-ups: none' in c.text('close.txt') and
         any('Discoveries without follow-ups: none' in output for _, output in invocations(c, 'close')))
register('note-id-kind', '90-ids', lambda c: len({identifier for args, output in invocations(c, 'next-id') if args == ['N']
         for identifier in re.findall(r'(?m)^N-A-\d+\s*$', output) if identifier.strip() in c.text('notes.md')}) >= 2)
register('launch-free-slot', '90-04-real-identity', lambda c:
         any('launched job' in event for event in helper().events(c.text('handoff.md'))) and
         all(helper().fields(event).get('Host', '').lower() not in ('ro', '', 'none') and
         helper().fields(event).get('User', '').lower() not in ('', 'none') for event in helper().events(c.text('handoff.md'))
         if 'launched job' in event))
register('project-language', '09-self-verification-fields', lambda c:
         bool(helper().blocks(c.text('discoveries.md'), 'D')) and all(not {'Cross-check', 'Reviews'} & helper().fields(row).keys()
         for row in helper().blocks(c.text('discoveries.md'), 'D').values()) and clean_check(c))
register('project-language', '10-next-step', lambda c: bool(helper().blocks(c.text('plan.md'), 'H')) and all(
         re.search(r'[가-힣]', helper().fields(row).get('Next step', '')) is not None for row in helper().blocks(c.text('plan.md'), 'H').values()) and clean_check(c))
register('saved-policy-roundtrip', '06-effective-gating', lambda c:
         any('deploytool publish artifact.txt' in payload['tool_input'].get('command', '') and denied(response) and 'external.gate' in json.dumps(response)
             for payload, response in response_pairs(c, 'hook-results.json')) and
         any('deploytool inspect artifact.txt' in payload['tool_input'].get('command', '') and not denied(response)
             for payload, response in response_pairs(c, 'hook-results.json')))


def numeric_metrics(c):
    data = c.data('audit.json')
    rows = named_rows(data)
    for name, duration, tokens in [('valid-partial', None, None), ('valid-perfect', 12, 120)]:
        row = rows.get(name, {})
        candidates = [value for value in objects(row) if any(key in value for key in ('total_duration_seconds', 'duration', 'duration_seconds'))]
        if not candidates:
            return False
        row = candidates[0]
        if row.get('total_duration_seconds', row.get('duration_seconds', row.get('duration'))) != duration:
            return False
        if row.get('total_tokens', row.get('tokens', 'missing')) != tokens:
            return False
    flat = {key: value for row in objects(data) for key, value in row.items() if not isinstance(value, (dict, list))}
    return flat.get('mean_duration_seconds', flat.get('mean_duration')) == 12 and flat.get('mean_total_tokens', flat.get('mean_tokens')) == 120


register('evaluation-grade-integrity', '90-06-unavailable-metrics', numeric_metrics)
register('evaluation-grade-integrity', '90-07-optional-records', lambda c: 'valid-partial' in audit_names(c, 'included') and
         any(key in ('execution_errors', 'executor_errors', 'execution_error_count') and value is None
             for row in objects(named_rows(c.data('audit.json'))['valid-partial']) for key, value in row.items()))


def no_recorded_execution(c):
    if not original(c, 'trace-cases.json'):
        return False
    source = c.data('trace-cases.json')
    commands = {row['command'].strip() for row in objects(source) if isinstance(row.get('command'), str)}
    from_module = __package__ + '.command_trace' if __package__ else 'command_trace'
    from importlib import import_module
    extract = import_module(from_module)._source
    return all(extract(row.get('command', '')).strip() not in commands for row in c.executions)


register('evaluation-trace-audit', '90-06-no-trace-execution', no_recorded_execution)
register('evaluation-trace-code-operands', '90-07-data-only-traces', no_recorded_execution)


def bound_only(c):
    data = c.data('binding-checks.json')
    lists = [value for row in objects(data) for key, value in row.items()
             if key in ('bound', 'bound_paths', 'bindings') and isinstance(value, list)]
    for paths in lists:
        names = {str(path).replace('\\', '/').rsplit('/', 1)[-1] for path in paths}
        if names == {'worker.py', 'inputs.txt'}:
            return True
    return False


register('launch-root-binding', '90-no-root-binding', bound_only)


def examples(c):
    return set(re.findall(r'\b(?:quick|work-project|solo-research|team-research|competition-solo|competition-team)-[a-z-]+\b',
                         (c.case_dir / 'files/brief.md').read_text(encoding='utf-8')))




def monitor_before_close(c):
    if not stopped(c):
        return False
    identifiers = {job['id'] for job in jobs(c)}
    monitors = [command.position for command in c.ro_commands if command.subcommand == 'monitor' and command.job in identifiers]
    closes = [command.position for command in c.ro_commands if command.subcommand == 'close']
    return bool(monitors and closes and min(closes) > max(monitors)) and helper().slot(c.text('handoff.md')).get('Current host') == 'released'


register('job-monitor-recovery', '05-close-after-monitor', monitor_before_close)
register('job-monitor-recovery', '06-unrepaired-stall-reported', lambda c:
         sum('heartbeat silence' in output for _, output in invocations(c, 'monitor')) >= 2)
register('non-ml-replication', '06-session-closed', lambda c:
         helper().slot(c.text('handoff.md')).get('Current host') == 'released' and
         helper().slot(c.text('handoff.md')).get('Current user') == 'none' and
         helper().review_pending(c)[0] and bool(helper().events(c.text('handoff.md'))))


def transcript_file(c):
    return (c.run_dir / 'transcript.md').read_text(encoding='utf-8')


def interface_value(c, field):
    text = (c.checker_skill / 'agents/openai.yaml').read_text(encoding='utf-8')
    match = re.search(r'^\s*' + re.escape(field) + r':\s*[\x27\"]?(.+?)[\x27\"]?\s*$', text, re.M)
    return bool(match and match[1] in transcript_file(c))


register('v3-interface-scope', '01-short-scope', lambda c: interface_value(c, 'short_description'))
register('v3-interface-scope', '02-prompt-scope', lambda c: interface_value(c, 'default_prompt'))


def snapshot_alive(c, filename):
    return snapshot_job(c, filename, lambda row: not row.get('ended') and
                        row.get('status') in ('running', 'attention') and bool(row.get('pid') and row.get('start')))


def recorded_block(c, report):
    if 'jobs.mutate-bound' not in c.text(report):
        return False
    for execution in all_executions(c):
        command, output = execution.get('command', ''), execution.get('aggregated_output', '')
        if not re.search(r'(ro(?:\.py)?\b.*\bhook\b|ro_hook_runner\.py|\bpre_checks\(|\bhook\()', command):
            continue
        if 'jobs.mutate-bound' in output and re.search(r'"(?:permissionDecision|decision)"\s*:\s*"(?:deny|block)"|\bblock jobs\.mutate-bound', output):
            return True
    return False


register('owned-job-parent-exit', '02-binding-protection', lambda c:
         snapshot_alive(c, 'parent-exit-observation.json') and recorded_block(c, 'report.md'))
register('owned-job-supervisor-crash', '90-02-binding-protected', lambda c:
         snapshot_alive(c, 'orphan-observation.json') and recorded_block(c, 'report.md'))
register('owned-job-supervisor-crash', '90-03-launch-conflict', lambda c:
         snapshot_alive(c, 'orphan-observation.json') and 'bound path conflicts' in c.text('report.md') and
         any('bound path conflicts' in output for _, output in invocations(c, 'launch', include_failed=True)))
register('owned-job-supervisor-crash', '90-04-release-barrier', lambda c:
         snapshot_alive(c, 'orphan-observation.json') and 'still has a running job' in c.text('report.md') and
         any('still has a running job' in output for _, output in invocations(c, 'release', include_failed=True)))
register('owned-job-supervisor-crash', '90-05-close-barrier', lambda c:
         snapshot_alive(c, 'orphan-observation.json') and 'Slot A: taken; running jobs' in c.text('report.md') and
         any('Slot A: taken; running jobs' in output for _, output in invocations(c, 'close')))
register('owned-job-parent-exit', '03-close-preserves-ownership', lambda c:
         snapshot_alive(c, 'parent-exit-observation.json') and 'Slot A: taken; running jobs' in c.text('report.md') and
         any('Slot A: taken; running jobs' in output for _, output in invocations(c, 'close')))


def observed_worker_stopped(c, registry='.ro/jobs.json', bounded=False):
    if not stopped(c, registry):
        return False
    entries = jobs(c, registry)
    if bounded and not all(type(row.get('ended')) in (int, float) and type(row.get('started')) in (int, float)
                           and 0 <= row['ended'] - row['started'] < 60 for row in entries):
        return False
    # The saved liveness command must report a negative result; termination status
    # alone is insufficient evidence for the independently observed-worker assertion.
    return any(re.search(r'(same_process|process_start|Get-Process|kill\s+-0|os\.kill)', row.get('command', ''), re.I) and
               re.search(r'(?m)^\s*(?:False|false|None|not alive|stopped|"alive"\s*:\s*false)[,\s}]*$',
                         row.get('aggregated_output', '')) for row in all_executions(c))


register('owned-job-parent-exit', '04-tree-termination', lambda c: observed_worker_stopped(c, bounded=True))
register('owned-job-supervisor-crash', '90-06-safe-cleanup', lambda c: observed_worker_stopped(c, 'final-jobs.json'))


def common_read_bindings(c):
    data = c.data('binding-checks.json')
    entries = [row for row in objects(data) if row.get('id') and row.get('bound') and row.get('inputs')
               and row.get('status') in ('running', 'attention') and not row.get('ended')]
    for index, first in enumerate(entries):
        for second in entries[index + 1:]:
            if first['id'] == second['id'] or first.get('run_dir') == second.get('run_dir'):
                continue
            normalize = lambda paths: {str(path).replace('\\', '/').rsplit('/', 1)[-1] for path in paths}
            if {'worker.py', 'inputs.txt'} <= normalize(first['inputs']) & normalize(second['inputs']):
                return any('bound path conflicts' in output for _, output in invocations(c, 'launch', include_failed=True))
    return False


register('launch-root-binding', '08-shared-input-exclusive-output', common_read_bindings)


def attempts_with_slots(c):
    rows = contention(c)
    result = {}
    for row in rows:
        words = row.get('argv', row.get('args', row.get('arguments', row.get('command', []))))
        text = ' '.join(words) if isinstance(words, list) else str(words)
        match = re.search(r'--slot[ =]+([AB])\b', text)
        if match and re.search(r'\bclaim\s+H-A-01\b', text) and re.search(r'\bro(?:\.py)?\b', text):
            result[match[1]] = row
    return result


register('claim-contention', '01-locked-procedure', lambda c: set(attempts_with_slots(c)) == {'A', 'B'})


def readiness_barrier(c):
    data = c.data('contention.json')
    ready, released = [], []
    for row in objects(data):
        for key, value in row.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if re.search(r'ready_(?:at|time)|(?:at|time)_ready', key):
                    ready.append(value)
                if re.search(r'releas(?:e|ed)_(?:at|time)|(?:at|time)_releas', key):
                    released.append(value)
    return len(ready) >= 2 and bool(released) and max(ready) <= min(released)


register('claim-contention', '02-concurrent-attempts', readiness_barrier)


def recovery_rows(c):
    return list(objects(c.data('contention.json')))


def same_hash_pair(row, stem):
    pairs = [(row.get(stem + '_before'), row.get(stem + '_after')),
             (row.get('before_' + stem), row.get('after_' + stem))]
    return any(isinstance(before, (str, int)) and not isinstance(before, bool) and before == after for before, after in pairs)


register('claim-contention', '06-lock-recovery', lambda c:
         any(same_hash_pair(row, 'inode') and (row.get('corrupt_preserved') is True or row.get('damaged_bytes_retained') is True)
             for row in recovery_rows(c)) and any(row.get('lock_held') is True and
             type(row.get('exit_code')) is int and row['exit_code'] != 0 for row in recovery_rows(c)) and
         any(row.get('lock_held') is False and (row.get('recovered') is True or row.get('exit_code') == 0) for row in recovery_rows(c)))


def increasing_identifiers(c):
    sequences = []
    for row in recovery_rows(c):
        for key, value in row.items():
            if re.search(r'(allocat|issued|identifiers)', key) and isinstance(value, list):
                ids = [item if isinstance(item, str) else item.get('id', item.get('identifier', '')) for item in value]
                if len(ids) >= 4 and all(re.fullmatch(r'[DHIXN]-[A-Z]+-\d+', item) for item in ids):
                    sequences.append(ids)
    return any(len({value.rsplit('-', 1)[0] for value in seq}) == 1 and all(int(a.rsplit('-', 1)[1]) < int(b.rsplit('-', 1)[1])
               for a, b in zip(seq, seq[1:])) for seq in sequences)


register('claim-contention', '07-id-high-water', increasing_identifiers)
register('claim-contention', '08-unrecoverable-counter', lambda c: any(
         (row.get('both_unreadable') is True or row.get('primary_unreadable') is True and row.get('snapshot_unreadable') is True) and
         type(row.get('exit_code')) is int and row['exit_code'] != 0 and
         not re.search(r'\b[DHIXN]-[A-Z]+-\d+\b', row.get('stdout', '')) and
         same_hash_pair(row, 'reservations_sha256') for row in recovery_rows(c)))


def source_preserved(c):
    data = c.data('source-hashes.json')
    if isinstance(data.get('before'), dict) and isinstance(data.get('after'), dict):
        return bool(data['before']) and data['before'] == data['after']
    pairs = [row for row in objects(data) if 'before' in row and 'after' in row]
    return bool(pairs) and all(isinstance(row['before'], str) and re.fullmatch(r'[0-9a-f]{64}', row['before']) and
                               row['before'] == row['after'] for row in pairs)


register('saved-policy-roundtrip', '07-source-unchanged', source_preserved)


def fresh_settings(c):
    values = settings(c, 'target/agents.md')
    stamp = re.fullmatch(r'strict since (\d{4}-\d{2}-\d{2})', values.get('Guards', ''))
    if not stamp or stamp[1] == '2001-01-01' or not all(values.get(key) == 'off' for key in ('Competition', 'Phase clock', 'Queue freeze')):
        return False
    return 'maple-target' in c.text('target/agents.md').splitlines()[0] and any(
        stamp[1] in text for text in (c.text('setup-output.txt'), c.text('target/handoff.md')))


register('saved-policy-roundtrip', '05-new-project-state', fresh_settings)


def no_policy_edits(c):
    initialized = saved = False
    for row in all_executions(c):
        source = row.get('command', '')
        if 'init_research_orchestrator.py' in source and row.get('exit_code') == 0:
            initialized = True
            saved |= '--save-preset' in source or '--save-user-preset' in source
            continue
        if re.search(r'(saved-policy\.json|target[/\\]agents\.md|override-target[/\\]agents\.md)', source) and re.search(
                r'(write_text|write_bytes|Set-Content|Add-Content|Out-File|\bsed\b|\btee\b|>>?|apply_patch)', source):
            # A byte-preserving copy is allowed; rebuilding policy content is not.
            return False
    return initialized and saved and original(c, 'source-settings.json')


register('saved-policy-roundtrip', '09-no-compensating-edits', no_policy_edits)




def json_hook_output(c):
    for args, output in invocations(c, 'hook'):
        if args[:1] != ['PreToolUse']:
            continue
        for line in output.splitlines():
            try:
                if isinstance(json.loads(line), dict):
                    return True
            except ValueError:
                continue
    return False
