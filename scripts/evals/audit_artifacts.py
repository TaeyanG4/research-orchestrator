"""Deterministic checks for saved evidence audits and reproducible calculations."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from .deterministic_artifacts import helper, objects, named_rows
    from .proc import no_window_flags
else:
    from deterministic_artifacts import helper, objects, named_rows
    from proc import no_window_flags

CHECKS = {}


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"Saved audit check {case}/{name}: {passed}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
            return False, f"Saved audit evidence unavailable: {type(exc).__name__}"
    CHECKS[case, name + '.md'] = check


def manifest(value):
    """Normalize path/hash inventories; reject duplicate or non-SHA256 entries."""
    if isinstance(value, dict) and 'files' in value:
        value = value['files']
    pairs = value.items() if isinstance(value, dict) else ((v['path'], v) for v in value)
    result = {}
    for path, digest in pairs:
        if isinstance(digest, dict):
            digest = digest.get('sha256', digest.get('hash'))
        path = path.replace('\\', '/')
        if path.startswith('trial/'):
            path = path[6:]
        if path in result or not re.fullmatch(r'[a-f0-9]{64}', digest or ''):
            raise ValueError('invalid inventory')
        result[path] = digest
    return result


def complete_snapshot(c):
    actual = {p.relative_to(c.outputs / 'trial').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (c.outputs / 'trial').rglob('*') if p.is_file()}
    required = {'nested/archive.txt', 'notes.txt', '.ro/local-state.json', 'agents.md', 'discoveries.md', 'handoff.md'}
    return required <= actual.keys() and manifest(c.data('before.json')) == manifest(c.data('after.json')) == actual


def refused_repair(c):
    return not (c.outputs / 'trial/plan.md').exists() and any(
        'init_research_orchestrator.py' in row.get('command', '') and
        re.search(r'--workflow[ =]+[\'"]?unified\b', row.get('command', '')) and
        'trial' in row.get('command', '') and type(row.get('exit_code')) is int and row['exit_code'] != 0 and
        re.search(r'(conflict|stored|existing).*workflow|workflow.*(conflict|stored|existing)',
                  row.get('aggregated_output', ''), re.I | re.S)
        for row in c.completed_commands)


register('repair-snapshot-scope', '90-complete-snapshots', complete_snapshot)
register('repair-snapshot-scope', '90-preservation', lambda c:
         bool(manifest(c.data('before.json'))) and manifest(c.data('before.json')) == manifest(c.data('after.json')))
register('repair-snapshot-scope', '90-refusal', refused_repair)


def comparison_controls(c):
    before = c.data('before.json')
    normalized = manifest(before)
    if not normalized:
        return False
    # Compare canonical path/hash objects. These are the public comparison
    # inputs; copying the whole project would conceal a program that ignores them.
    variants = [dict(normalized), dict(normalized), {**normalized, 'extra-file.txt': '1' * 64}]
    first = next(iter(normalized))
    variants[1][first] = ('0' if normalized[first][0] != '0' else '1') + normalized[first][1:]
    candidates = [path for path in c.outputs.glob('*.py') if not (c.case_dir / 'files' / path.name).exists()]
    for candidate in candidates:
        verdicts = []
        for after in variants:
            with tempfile.TemporaryDirectory(prefix='ro-manifest-check-') as directory:
                root = Path(directory)
                (root / 'before.json').write_text(json.dumps(normalized), encoding='utf-8')
                (root / 'after.json').write_text(json.dumps(after), encoding='utf-8')
                shutil.copyfile(candidate, root / candidate.name)
                result = subprocess.run([c.python, '-I', '-S', str(root / candidate.name)], cwd=root,
                                        text=True, encoding='utf-8', capture_output=True, timeout=10,
                                        creationflags=no_window_flags())
                text = result.stdout.lower()
                mismatch = bool(re.search(r'\b(mismatch|different|differs|false|changed)\b|not (?:equal|identical)', text))
                equal = result.returncode == 0 and not mismatch and bool(re.search(r'\b(equal|identical|match|unchanged|true)\b', text))
                verdicts.append(equal if after == normalized else mismatch)
        if all(verdicts):
            return True
    return False


register('repair-snapshot-scope', '90-comparison-controls', comparison_controls)


def run_saved(c, inputs, output, overrides=None):
    """Future grader execution only: rerun a saved program with fresh result state.

    Only programs newly supplied by the executor are candidates. Each receives
    a fresh directory, unchanged fixture dependencies and explicit input files;
    prior results cannot make a no-op program pass. This follows the existing
    replication grader's bounded subprocess contract.
    """
    fixture = c.case_dir / 'files'
    candidates = [p for p in c.outputs.glob('*.py') if not (fixture / p.name).exists()]
    if not candidates:
        raise ValueError('missing saved audit program')
    for candidate in sorted(candidates):
        with tempfile.TemporaryDirectory(prefix='ro-audit-check-') as directory:
            root = Path(directory)
            for source in fixture.iterdir():
                destination = root / source.name
                if source.is_dir():
                    shutil.copytree(source, destination)
                else:
                    shutil.copyfile(source, destination)
            for path in candidates:
                shutil.copyfile(path, root / path.name)
            for name in inputs:
                value = (overrides or {}).get(name)
                raw = (value if isinstance(value, bytes) else json.dumps(value).encode('utf-8')) if value is not None else (fixture / name).read_bytes()
                (root / name).write_bytes(raw)
            result_file = root / output
            result_file.unlink(missing_ok=True)
            result = subprocess.run([c.python, '-I', '-S', str(root / candidate.name)], cwd=root,
                                    capture_output=True, timeout=10, creationflags=no_window_flags())
            if result.returncode == 0 and result_file.is_file() and result_file.stat().st_size < 2_000_000:
                return json.loads(result_file.read_text(encoding='utf-8'))
    raise ValueError('saved programs did not recreate result')


def names(value, key):
    rows = value[key]
    if isinstance(rows, dict):
        return set(rows)
    return {v if isinstance(v, str) else v.get('name', v.get('id')) for v in rows}


def audit_replays(c, inputs, collection):
    baseline = run_saved(c, inputs, 'audit.json')
    saved = c.data('audit.json')
    if any(names(baseline, key) != names(saved, key) for key in ('included', 'excluded')):
        return False
    values = json.loads((c.case_dir / 'files' / inputs[-1]).read_text(encoding='utf-8'))
    renamed = copy.deepcopy(values)
    input_rows = values if isinstance(values, list) else values[collection]
    renamed_rows = renamed if isinstance(renamed, list) else renamed[collection]
    mapping = {row['name']: f'case-{index}' for index, row in enumerate(input_rows)}
    for row in renamed_rows:
        row['name'] = mapping[row['name']]
    changed = run_saved(c, inputs, 'audit.json', {inputs[-1]: renamed})
    return all(names(changed, key) == {mapping[name] for name in names(baseline, key)} for key in ('included', 'excluded'))


def trace_replays(c):
    if not audit_replays(c, ['trace-cases.json'], 'scenarios'):
        return False
    values = json.loads((c.case_dir / 'files/trace-cases.json').read_text(encoding='utf-8'))
    probe = next(row for row in values['scenarios'] if row['name'] == 'ancestor-probe')
    values['existing_files']['{workspace}/AGENTS.md'] = 'Ancestor instructions'
    for event in probe['events']:
        if event.get('type') == 'item.completed':
            event['item']['aggregated_output'] = 'Ancestor instructions'
    changed = run_saved(c, ['trace-cases.json'], 'audit.json', {'trace-cases.json': values})
    return 'ancestor-probe' in names(changed, 'excluded') and 'ancestor-probe' not in names(changed, 'included')


register('evaluation-trace-audit', '90-05-replayable-audit', trace_replays)
register('evaluation-trace-code-operands', '90-06-replayable-audit', lambda c:
         audit_replays(c, ['trace-cases.json'], 'scenarios'))
def grade_replays(c):
    if not audit_replays(c, ['assertions.json', 'grades.json'], 'candidates'):
        return False
    values = json.loads((c.case_dir / 'files/grades.json').read_text(encoding='utf-8'))
    row = next(row for row in values['candidates'] if row['name'] == 'valid-partial')
    row['grading']['expectations'][0]['passed'] = 'true'
    changed = run_saved(c, ['assertions.json', 'grades.json'], 'audit.json', {'grades.json': values})
    return 'valid-partial' in names(changed, 'excluded') and 'valid-partial' not in names(changed, 'included')


register('evaluation-grade-integrity', '90-05-reproducible-audit', grade_replays)


def comparison_code(c):
    inputs = ['timings.csv']
    first = run_saved(c, inputs, 'comparison.json')
    expected = {'count': 4, 'mean_current_seconds': 12, 'mean_candidate_seconds': 9, 'saved_seconds': 3}
    if not all(first.get(key) == value for key, value in expected.items()):
        return False
    changed = run_saved(c, inputs, 'comparison.json', {'timings.csv':
        b'document,current_seconds,candidate_seconds\na,20,6\nb,30,8\nc,50,10\n'})
    expected = {'count': 3, 'mean_current_seconds': 100 / 3, 'mean_candidate_seconds': 8, 'saved_seconds': 100 / 3 - 8}
    return c.unchanged('timings.csv') and all(type(changed.get(key)) in (int, float) and
        math.isclose(changed[key], value, abs_tol=1e-6) for key, value in expected.items())


register('project-language', '08-reproducible-code', comparison_code)
register('project-language', '04-english-structure', lambda c:
         all(helper().blocks(c.text(name), prefix) for name, prefix in [('plan.md', 'H'), ('discoveries.md', 'D')]) and
         helper().fields(c.text('agents.md')).get('Language') == 'ko' and helper().checker_clean(c)[0])
def language_closed(c):
    h = helper()
    items = h.blocks(c.text('plan.md'), 'H')
    completion = [h.fields(event) for event in h.events(c.text('handoff.md'), 'H-A-01')]
    return h.closed_consistently(c)[0] and 'H-A-01' not in items and len(items) == 1 and any(
        set(items) <= set(re.findall(r'H-[A-Z]+-\d+', event.get('New plan items', ''))) for event in completion)


register('project-language', '07-follow-up-and-close', language_closed)


def snapshot_report(c, patterns):
    text = c.text('snapshot-review.md')
    return all(re.search(pattern, text, re.I | re.S) for pattern in patterns)


register('public-snapshot-reconstruction', '90-01-result', lambda c: snapshot_report(c, [r'31\s+(?:matched|paired|cases)', r'18\s+excluded']))
register('public-snapshot-reconstruction', '90-02-result', lambda c: snapshot_report(c, [r'99\.71\s*%', r'56\.31\s*%']))
register('public-snapshot-reconstruction', '90-04-result', lambda c: snapshot_report(c, [r'source.{0,60}(?:hash|sha)', r'export.{0,60}(?:hash|sha)']) and
         not any(p.name in ('transcript.md', 'events.jsonl') for p in c.outputs.rglob('*')))


def trigger_replay(c):
    saved = named_rows(c.data('classifications.json'))
    first = named_rows(run_saved(c, ['measurements.json'], 'classifications.json'))
    values = json.loads((c.case_dir / 'files/measurements.json').read_text(encoding='utf-8'))
    keys = [row['query'] for row in values['queries']]
    if not all(name in saved and name in first and first[name].get('prediction') is saved[name].get('prediction') for name in keys):
        return False
    mapping = {name: f'query-{i}' for i, name in enumerate(keys)}
    for row in values['queries']:
        old_name = row['query']
        row['query'] = mapping[old_name]
        if old_name == 'clean-positive':
            for record in objects(row):
                if 'triggered' in record:
                    record['triggered'] = False
    changed = named_rows(run_saved(c, ['measurements.json'], 'classifications.json', {'measurements.json': values}))
    return all(mapping[name] in changed and changed[mapping[name]].get('prediction') is
               (False if name == 'clean-positive' else first[name].get('prediction')) for name in keys)


register('trigger-measurement-reasons', '90-reproducible-calculation', trigger_replay)
register('evaluation-transport-evidence', '90-reproducible-audit', lambda c:
         audit_replays(c, ['runs.json'], 'runs') and any(
             row.get(key) == 0 for row in objects(c.data('audit.json')) for key in ('mean_pass_rate', 'mean', 'pass_rate_mean')))


def retry_plan(c):
    if __package__:
        from .run_evals import terminal_transport_category
    else:
        from run_evals import terminal_transport_category
    rows = named_rows(c.data('retry-plan.json'))
    values = json.loads((c.case_dir / 'files/runs.json').read_text(encoding='utf-8'))
    values = values.get('runs', values) if isinstance(values, dict) else values
    required = {row['name'] for row in values if terminal_transport_category(
        '\n'.join(json.dumps(event) for event in row.get('events', [])), row.get('stderr', '')) and
        re.search(r'capacity|503|429|usage.limit|rate.limit', json.dumps(row.get('events', [])) + row.get('stderr', ''), re.I)}
    if not required or not required <= rows.keys():
        return False
    for name in required:
        row = rows[name]
        attempts = row.get('retries', row.get('attempts', row.get('max_retries', row.get('immediate_retries'))))
        count = len(attempts) if isinstance(attempts, list) else attempts
        if type(count) is not int or not 1 <= count <= 3:
            return False
        if row.get('fresh_session', row.get('fresh_sessions')) is not True or row.get('resume', False) is not False:
            return False
    return not ({row['name'] for row in values} - required) & rows.keys()


register('evaluation-transport-evidence', '08-three-fresh-retries', retry_plan)


PROGRAMS = ('input-driven.py', 'fixed-count.py', 'fixed-method.py')


def program_controls(c):
    """Read required per-control evidence while accepting ordinary JSON grouping."""
    rows = {name: [] for name in PROGRAMS}
    def visit(value, program=None):
        if isinstance(value, dict):
            program = next((value[key] for key in ('program', 'candidate', 'name')
                            if value.get(key) in PROGRAMS), program)
            inputs = value.get('inputs', value)
            observations = inputs.get('observations', inputs.get('values')) if isinstance(inputs, dict) else None
            method = inputs.get('method') if isinstance(inputs, dict) else None
            result = value.get('result', value.get('actual', value.get('output')))
            exit_code = value.get('exit_code', value.get('returncode', value.get('exit_status')))
            if program and isinstance(observations, list) and isinstance(method, dict) and isinstance(result, dict):
                rows[program].append((observations, method, result, exit_code))
            for key, child in value.items():
                visit(child, key if key in PROGRAMS else program)
        elif isinstance(value, list):
            for child in value:
                visit(child, program)
    visit(c.data('audit.json'))
    return rows


def numeric_control(row):
    values, method, result, code = row
    if type(code) is not int or code != 0 or len(values) < 2:
        return False
    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    margin = method['multiplier'] * sd / math.sqrt(len(values))
    expected = {'n': len(values), 'mean': mean, 'sd': sd}
    interval = result.get('interval', result.get('ci'))
    return all(type(result.get(key)) in (int, float) and math.isclose(result[key], target, abs_tol=1e-6)
               for key, target in expected.items()) and isinstance(interval, list) and len(interval) == 2 and all(
                   type(actual) in (int, float) and math.isclose(actual, target, abs_tol=1e-6)
                   for actual, target in zip(interval, [mean - margin, mean + margin]))


def original_inputs(c):
    root = c.case_dir / 'files'
    return json.loads((root / 'observations.json').read_text()), json.loads((root / 'method.json').read_text())


def valid_program(c):
    values, method = original_inputs(c)
    rows = program_controls(c)['input-driven.py']
    kinds = set()
    for row in rows:
        obs, current, _, _ = row
        if not numeric_control(row) or current.get('degrees_of_freedom') != len(obs) - 1:
            return False
        if obs == values and current == method:
            kinds.add('canonical')
        elif len(obs) != len(values) and current['multiplier'] == method['multiplier']:
            kinds.add('count')
        elif obs == values and current['multiplier'] != method['multiplier']:
            kinds.add('method')
    return kinds == {'canonical', 'count', 'method'}


def negative_programs(c):
    values, method = original_inputs(c)
    rows = program_controls(c)
    return any(len(row[0]) != len(values) and row[1].get('degrees_of_freedom') == len(row[0]) - 1 and
               row[3] == 0 and not numeric_control(row) for row in rows['fixed-count.py']) and any(
                   row[0] == values and row[1].get('multiplier') != method['multiplier'] and row[3] == 0 and
                   not numeric_control(row) for row in rows['fixed-method.py'])


def coherent_fixtures(c):
    values, method = original_inputs(c)
    rows = [row for controls in program_controls(c).values() for row in controls]
    return bool(rows) and all(row[1].get('degrees_of_freedom') == len(row[0]) - 1 and
                             (row[1].get('multiplier') == method['multiplier'] or row[0] == values) for row in rows)


def fresh_replication(c):
    fixtures = ['observations.json', 'method.json', *PROGRAMS]
    if not all((c.case_dir / 'files' / name).read_bytes() == (c.outputs / name).read_bytes() for name in fixtures):
        return False
    guard = b"from pathlib import Path\nassert not Path('result.json').exists(), 'stale result reused'\n"
    changes = {name: guard + (c.case_dir / 'files' / name).read_bytes() for name in PROGRAMS}
    recreated = run_saved(c, fixtures, 'audit.json', changes)
    proxy = type('AuditContext', (), {'case_dir': c.case_dir, 'data': lambda self, name: recreated})()
    return valid_program(proxy) and negative_programs(proxy)


register('replication-coherent-controls', '90-valid-program', valid_program)
register('replication-coherent-controls', '90-negative-controls', negative_programs)
register('replication-coherent-controls', '90-valid-fixtures', coherent_fixtures)
register('replication-coherent-controls', '90-fresh-evidence', fresh_replication)


def bundled_reviewer(c):
    root = (c.outputs / 'local-skill').resolve()
    reference = root / 'references/verification.md'
    links = re.findall(r'\[[^\]]*\]\(([^)]+)\)', reference.read_text(encoding='utf-8'))
    for link in links:
        target = (reference.parent / link.split('#', 1)[0]).resolve()
        if target.name != 'reviewer.md' or not target.is_relative_to(root) or not target.is_file():
            continue
        expected = c.checker_skill / target.relative_to(root)
        if expected.is_file() and target.read_text(encoding='utf-8') == expected.read_text(encoding='utf-8'):
            return True
    return False


register('direct-install-reviewer', '90-bundled-reference', bundled_reviewer)
