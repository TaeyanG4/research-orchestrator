"""Deterministic installer and host assertions over retained artifacts.

These checks consume saved data only. They never launch a host or execute a
recorded command, and missing provenance is a failure rather than a prose pass.
"""
from __future__ import annotations

import hashlib
import ast
import json
import ntpath
from pathlib import Path
import re
import shlex


CHECKS = {}


def register(case, name, predicate):
    def check(ctx):
        try:
            passed = bool(predicate(ctx))
            return passed, f"{case}/{name}: retained artifact check {'passed' if passed else 'failed'}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            return False, f"{case}/{name}: unavailable or malformed artifact ({type(exc).__name__})"
    CHECKS[case, name + '.md'] = check


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def rows(value):
    return {row['id']: row for row in objects(value) if isinstance(row.get('id'), str)}


def result_code(row):
    return next((row[key] for key in ('exit_code', 'returncode', 'exit_status', 'exit') if key in row), None)


def argv(row):
    value = next((row[key] for key in ('argv', 'command', 'args') if key in row), [])
    return shlex.split(value) if isinstance(value, str) else value


def option(words, name):
    for index, word in enumerate(words):
        if word == name and index + 1 < len(words):
            return words[index + 1]
        if word.startswith(name + '='):
            return word.partition('=')[2]
    return None


def environment(row):
    return row.get('env', row.get('environment', {}))


def payload(row):
    return decoded(row.get('stdin', row.get('payload', row.get('input', '{}'))))


def output(row):
    return decoded(row.get('stdout', row.get('output', '{}')))


def response_text(row):
    return json.dumps(output(row), ensure_ascii=False)


def wrapper_rows(c, filename):
    return [row for row in objects(c.data(filename)) if 'stdout' in row and any(
        str(word).replace('\\', '/').rsplit('/', 1)[-1] in ('ro-hook.sh', 'ro-hook.cmd', 'ro_hook_runner.py')
        for word in argv(row))]


def no_path_python(c, row):
    data = c.data('replay.json')
    if row.get('python_on_path') is False or (isinstance(data, dict) and data.get('python_on_path') is False):
        return True
    for evidence in objects(data):
        if set(evidence) >= {'python', 'python3'} and evidence['python'] is None and evidence['python3'] is None:
            return True
    # A retained empty PATH directory is independently inspectable too.
    value = environment(row).get('PATH')
    if not isinstance(value, str) or not value:
        return value == ''
    delimiter = ';' if ';' in value or ntpath.splitdrive(value)[0] else ':'
    entries = value.split(delimiter)
    mapped = [c.outputs / Path(entry.replace('\\', '/')).name for entry in entries]
    return bool(mapped) and all(path.is_dir() and not any(child.name.lower().startswith(('python', 'py.'))
           for child in path.iterdir()) for path in mapped)


def hook_rows(c, event, session=None, variable=None):
    matches = []
    for row in wrapper_rows(c, 'session-results.json'):
        if event not in argv(row):
            continue
        data = payload(row)
        if not isinstance(data, dict) or 'slot' in data:
            continue
        env = environment(row)
        identity = env.get(variable) if variable else data.get('session_id')
        if session is not None and identity != session:
            continue
        if variable and ('session_id' in data or env.get('RO_SLOT') != 'A'):
            continue
        if result_code(row) == 0 and isinstance(output(row), dict):
            matches.append(row)
    return matches


def job_rows(c):
    found = []
    for path in c.outputs.rglob('jobs.json'):
        if path.parent.name == '.ro':
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, list):
                found.extend(row for row in data if isinstance(row, dict))
    return [row for row in found if row.get('slot') == 'B' and row.get('session') == 'native-second']


def native_startups(c):
    for identity, own, other in [('native-first', 'A', 'B'), ('native-second', 'B', 'A')]:
        found = hook_rows(c, 'SessionStart', identity)
        if not any(f'Slot {own}:' in response_text(row) and re.search(r'Claim H-' + own + r'-\d+:', response_text(row))
                   and not re.search(r'Claim H-' + other + r'-\d+:', response_text(row)) for row in found):
            return False
    return True


register('native-session-slots', '01-distinct-startup', native_startups)
register('native-session-slots', '02-command-job-owner', lambda c: bool(job_rows(c)) and any(
    'launch' in argv(row) and '--slot' not in argv(row) and not any(str(word).startswith('--slot=') for word in argv(row))
    and (option(argv(row), '--session') == 'native-second' or environment(row).get('RO_SESSION') == 'native-second')
    and environment(row).get('RO_SLOT') == 'A' and result_code(row) == 0
    for row in objects(c.data('session-results.json')) if any(key in row for key in ('argv', 'command', 'args'))))
register('native-session-slots', '03-owner-stop-block', lambda c: any(
    output(row).get('decision') == 'block' and 'jobs.unmonitored' in response_text(row)
    and any(job.get('id') in response_text(row) for job in job_rows(c)) and environment(row).get('RO_SLOT') == 'A'
    for row in hook_rows(c, 'Stop', 'native-second')))
register('native-session-slots', '04-other-session-stop', lambda c: any(
    output(row).get('decision') != 'block' and 'jobs.unmonitored' not in response_text(row)
    for row in hook_rows(c, 'Stop', 'native-first')))
register('native-session-slots', '05-monitor-resolves-stop', lambda c: any(
    (job.get('monitor') or {}).get('active') is False and bool((job.get('monitor') or {}).get('reason'))
    and job.get('status') in ('finished', 'killed') for job in job_rows(c)) and any(
    output(row).get('decision') != 'block' and 'jobs.unmonitored' not in response_text(row)
    for row in hook_rows(c, 'Stop', 'native-second')))
register('native-session-slots', '06-unregistered-startup', lambda c: any(
    'slot' in response_text(row).lower() and '--slot' in response_text(row)
    and not re.search(r'Slot [AB]:', response_text(row)) for row in hook_rows(c, 'SessionStart', 'native-third')))


def default_association(c):
    filename = hashlib.sha256(b'native-default').hexdigest() + '.json'
    selections = [json.loads(path.read_text(encoding='utf-8')).get('slot')
                  for path in c.outputs.rglob(filename) if path.parent.name == 'sessions']
    return any(f'Slot {slot}:' in response_text(row) for slot in selections
               for row in hook_rows(c, 'SessionStart', 'native-default'))


register('native-session-slots', '07-default-command-association', default_association)
register('native-session-slots', '08-corrupt-association-recovery', lambda c:
         default_association(c) and any('hooks inactive' in response_text(row) or 'hooks.failure' in response_text(row)
         for row in hook_rows(c, 'SessionStart', 'native-default')))
register('native-session-slots', '09-environment-session', lambda c: all(any(
    'Slot B:' in response_text(row) and 'Slot A:' not in response_text(row)
    for row in hook_rows(c, 'SessionStart', 'native-second', variable)) for variable in ('RO_SESSION', 'CODEX_THREAD_ID')))
register('native-session-slots', '10-legacy-fallback', lambda c: any(
    not payload(row).get('session_id') and not environment(row).get('RO_SESSION') and not environment(row).get('CODEX_THREAD_ID')
    and environment(row).get('RO_SLOT') == 'B' and 'Slot B:' in response_text(row)
    and 'Host session: local:' not in response_text(row) for row in hook_rows(c, 'SessionStart')))


register('hook-interpreter-override', '90-01-selected-interpreter', lambda c: any(
    result_code(row) == 0 and (Path(environment(row).get('RO_HOOK_PYTHON', '')).is_absolute() or
                              ntpath.isabs(environment(row).get('RO_HOOK_PYTHON', '')))
    and output(row).get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
    and 'shell.background' in output(row).get('hookSpecificOutput', {}).get('permissionDecisionReason', '')
    and 'PreToolUse' in argv(row) and isinstance(payload(row), dict)
    and no_path_python(c, row) for row in wrapper_rows(c, 'replay.json')))
register('hook-interpreter-override', '90-02-unavailable-interpreter', lambda c: any(
    result_code(row) == 0 and output(row) == {} and
    'configured Python interpreter unavailable' in row.get('stderr', '')
    for row in wrapper_rows(c, 'replay.json')))
register('hook-interpreter-override', '90-04-exit-status', lambda c: any(
    result_code(row) == 2 and row.get('stdout') == '' and
    not any(event in argv(row) for event in ('PreToolUse', 'PostToolUse', 'Stop', 'SessionStart', 'pre-push'))
    for row in wrapper_rows(c, 'replay.json')))


def cache_snapshots(value, context=''):
    """Read explicit before/after lists; never infer a pass from a prose claim."""
    if not isinstance(value, dict):
        return []
    found = []
    before = value.get('before', value.get('cache_before'))
    after = value.get('after', value.get('cache_after'))
    if isinstance(before, list) and isinstance(after, list):
        found.append((context, before, after))
    if isinstance(before, dict) and isinstance(after, dict):
        found.extend((str(key), before[key], after[key]) for key in before.keys() & after.keys()
                     if isinstance(before[key], list) and isinstance(after[key], list))
    for key, child in value.items():
        found.extend(cache_snapshots(child, context + '/' + key))
    return found


def confined_cache(c):
    data = c.data('replay.json')
    snapshots = cache_snapshots(data)
    named = {name.lower(): (before, after) for name, before, after in snapshots}
    installed = [(before, after) for name, (before, after) in named.items() if 'install' in name or 'script' in name]
    project = [(before, after) for name, (before, after) in named.items() if 'project' in name]
    if not installed or not project or any(set(after) - set(before) for before, after in installed + project):
        return False
    writes = [path for name, before, after in snapshots if 'cache' in name.lower()
              for path in set(after) - set(before)]
    roots = [row[key] for row in objects(data) for key in ('user_cache', 'user_cache_dir', 'pycache_prefix')
             if isinstance(row.get(key), str)]
    disabled = any(row.get('bytecode_disabled') is True for row in objects(data))
    return disabled and not writes or bool(roots) and all(any(
        str(path).replace('\\', '/').startswith(root.replace('\\', '/').rstrip('/') + '/') for root in roots)
        for path in writes)


register('hook-interpreter-override', '90-user-cache', confined_cache)


def no_window_helper(c):
    text = json.dumps(c.data('replay.json'))
    if 'ro_proc.py' not in text or 'CREATE_NO_WINDOW' not in text:
        return False
    source = (c.checker_skill / 'scripts/ro_proc.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'no_window_flags']
    constants = [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'CREATE_NO_WINDOW' for target in node.targets)]
    return (len(functions) == 1 and len(constants) == 1 and isinstance(constants[0].value, ast.Constant)
            and constants[0].value.value == 0x08000000 and any(isinstance(node, ast.Name) and node.id == 'CREATE_NO_WINDOW'
                                                            for node in ast.walk(functions[0])))


register('hook-interpreter-override', '90-windowless-processes', no_window_helper)


def classified(c, identifiers, prefix=None, passed=None):
    actual = rows(c.data('evidence-review.json'))
    return all(identifier in actual and
               (prefix is None or str(actual[identifier].get('observed', actual[identifier].get('result', ''))).startswith(prefix)) and
               (passed is None or actual[identifier].get('passed', actual[identifier].get('pass')) is passed)
               for identifier in identifiers)


register('codex-enforcement-evidence', '90-01-rejects-execution-after-denial', lambda c:
         classified(c, ('parser-error-after-denial', 'deleted-after-denial'), 'not blocked'))
register('codex-enforcement-evidence', '90-02-requires-successful-tool-evidence', lambda c:
         classified(c, ('clean-without-call', 'warned-read-failed'), 'unknown/inconclusive'))
register('codex-enforcement-evidence', '90-03-incomplete-or-retried-probes', lambda c:
         classified(c, ('interrupted-denial', 'retried-denial'), 'unknown/inconclusive'))
register('codex-enforcement-evidence', '90-04-accepts-supported-results', lambda c:
         classified(c, ('protected-delete', 'completed-benign'), passed=True))
register('codex-enforcement-evidence', '90-05-nonzero-inconclusive-gate', lambda c:
         any(type(row.get(key)) is int and row[key] == 1 for row in objects(c.data('evidence-review.json'))
             for key in ('aggregate_exit_status', 'aggregate_exit_code', 'aggregate_exit', 'exit_status', 'exit_code')))
register('codex-enforcement-evidence', '90-08-uncertain-tool-state', lambda c:
         classified(c, ('unconfirmed-tool-end',), 'unknown/inconclusive'))


def fixture_markers(c):
    codex = [path.parent.parent for path in c.outputs.rglob('hooks.json') if path.parent.name == '.codex']
    claude = [path for path in c.outputs.rglob('agents.md') if 'claude' in '/'.join(path.parts).lower()]
    return bool(codex and claude) and all((path / '.ro/hook-diagnostics.on').is_file() for path in codex) and all(
        not (path.parent / '.ro/hook-diagnostics.on').exists() for path in claude)


register('codex-enforcement-evidence', '90-06-project-diagnostics-marker', fixture_markers)
register('host-lifecycle-probe-evidence', '01-target-warnings', lambda c: all(
    rows(c.data('probe-audit.json'))[key].get('observed') == 'warned' for key in ('stop-matching', 'post-matching')))
register('host-lifecycle-probe-evidence', '02-inconclusive-evidence', lambda c: all(
    rows(c.data('probe-audit.json'))[key].get('observed') == 'unknown/inconclusive'
    for key in ('post-wrong-event', 'post-no-mutation', 'stop-no-diagnostic')))


def current_settings(c, host):
    return [json.loads(path.read_text(encoding='utf-8')) for path in c.outputs.rglob('settings.json')
            if path.parent.name == host and 'backups' not in path.as_posix()]


def hook_commands(document):
    return [hook.get('command', '') for entries in document.get('hooks', {}).values() for entry in entries
            for hook in entry.get('hooks', [])]


register('installer-plugin-deduplication', '90-01-result', lambda c: any(
    document.get('enabledPlugins', {}).get('research-orchestrator@research-orchestrator') is True
    and not any('/research-orchestrator/hooks/ro-hook.' in command for command in hook_commands(document))
    for document in current_settings(c, '.claude')))
register('installer-plugin-deduplication', '90-04-result', lambda c: any(
    'unrelated-check' in hook_commands(document) for document in current_settings(c, '.claude')))


def preserved_hash(c, label):
    text = c.text('install-audit.md')
    # Hash tables and labelled before/after sections are both ordinary report
    # formats. An assertion of preservation without two matching hashes fails.
    for block in re.split(r'\n\s*\n|(?m:^#{1,6} )', text):
        if re.search(label, block, re.I):
            hashes = re.findall(r'\b[a-fA-F0-9]{64}\b', block)
            if len(hashes) >= 2 and len({value.lower() for value in hashes}) == 1:
                return True
    return False


register('installer-plugin-deduplication', '90-02-result', lambda c: preserved_hash(c, r'\bskill\b'))
register('installer-plugin-deduplication', '90-03-result', lambda c: preserved_hash(c, r'pre-push|git.gate'))


def codex_install(c):
    settings = [path for path in c.outputs.rglob('hooks.json') if path.parent.name == '.codex']
    return any((path.parent / 'skills/research-orchestrator/SKILL.md').is_file() and
               any('/research-orchestrator/hooks/ro-hook.' in command for command in hook_commands(
                   json.loads(path.read_text(encoding='utf-8')))) for path in settings) and any(
               'install.py' in row.get('command', '') and '--host' in row.get('command', '') and
               'codex' in row.get('command', '') for row in c.executions)


register('installer-plugin-deduplication', '90-05-result', codex_install)


def minimum_python(c):
    if re.search(r'Python\s+3\.12\+', c.text('install-audit.md'), re.I) is None:
        return False
    # The rejection must occur in retained execution output, not merely in a
    # copied source snippet. The fixture's simulated-version call is inspectable.
    return any(('require_python' in row.get('command', '') or 'version_info' in row.get('command', ''))
               and re.search(r'3\s*[,\.]\s*11', row.get('command', ''))
               and 'Python 3.12+ is required' in row.get('aggregated_output', '')
               for row in c.executions)


register('installer-plugin-deduplication', '90-06-result', minimum_python)


def report(c):
    # final.md is written by the executor, unlike a transcript which also
    # contains the question and copied source file with all the expected facts.
    return c.text('final.md').replace('`', '').replace('**', '').replace('__', '')


def workflow(c):
    return (c.case_dir / 'files/validate.yml').read_text(encoding='utf-8')


register('release-ci-matrix', '01-platforms', lambda c:
         set(re.findall(r'\b(?:windows|ubuntu|macos)-[\w.-]+\b', report(c))) ==
         set(re.findall(r'\b(?:windows|ubuntu|macos)-[\w.-]+\b', workflow(c))) ==
         {'windows-latest', 'ubuntu-latest', 'macos-latest'})
register('release-ci-matrix', '02-python', lambda c:
         re.search(r'(?i)(?:python(?:-version)?\s*[:=]?\s*)3\.12\b', report(c)) is not None and
         re.search(r"python-version:\s*['\"]3\.12['\"]", workflow(c)) is not None and
         not re.search(r'(?i)python(?:-version)?\s*[:=]?\s*3\.(?!12\b)\d+', report(c)))
register('release-ci-matrix', '03-gate', lambda c:
         'python scripts/validate_release.py' in report(c) and 'pytest' in report(c) and
         workflow(c).find('python -m pip install pytest') < workflow(c).find('python scripts/validate_release.py') and
         'python -m pip install pytest' in workflow(c))
register('release-ci-matrix', '04-permissions', lambda c:
         re.search(r'contents\s*:\s*read\b', report(c), re.I) is not None and
         re.search(r'no\s+(?:\w+\s+){0,3}write|read[- ]only|does not grant[^.\n]*write', report(c), re.I) is not None and
         not re.search(r'contents\s*:\s*write\b', report(c), re.I) and
         not re.search(r'(?m)^\s*(?:permissions:\s*write-all|[\w-]+:\s*write)\s*$', workflow(c)))
register('release-ci-matrix', '05-no-credentials', lambda c:
         re.search(r'(?:no|without|does not (?:use|reference))\s+(?:\w+\s+){0,3}secrets', report(c), re.I) is not None and
         (re.search(r'persist-credentials\s*:\s*false', report(c), re.I) is not None or
          re.search(r'(?:disabl\w*[^.\n]*credential[^.\n]*persist|credential[^.\n]*persist[^.\n]*disabl)', report(c), re.I) is not None) and
         'persist-credentials: false' in workflow(c) and '${{ secrets.' not in workflow(c))


def hook_setup(c):
    return c.text('hook-setup.md').replace('`', '')


register('hook-portability', '90-portable-entry-points', lambda c:
         all(value in hook_setup(c) for value in ('hooks/ro-hook.sh', 'hooks/ro-hook.cmd', 'python3', 'py -3')) and
         all(value in hook_setup(c).lower() for value in ('linux', 'windows')))
register('hook-portability', '90-antigravity-command-only', lambda c: any(
         'antigravity' in block.lower() and re.search(r'command[- ]only', block, re.I) is not None
         and re.search(r'check_project\.py|\bchecker\b|\bro\s+\w+', block, re.I) is not None
         and re.search(r'\bnot\s+command[- ]only|supports\s+hooks', block, re.I) is None
         for block in re.split(r'\n\s*\n', hook_setup(c))))


def installer_options(c):
    text = hook_setup(c)
    return (all(value in text for value in ('install.py', '--host', '--project', '--dry-run', '--uninstall')) and
            re.search(r'(?:old[- ]name|previous[- ]name|research-orchestrator-skill)', text, re.I) is not None and
            re.search(r'timestamp\w*[^.\n]*backup|backup[^.\n]*timestamp', text, re.I) is not None and
            re.search(r'unrelated\s+hooks[^.\n]*(?:retain|preserv|kept|keep)|(?:retain|preserv|keep)\w*[^.\n]*unrelated\s+hooks',
                      text, re.I) is not None)


register('hook-portability', '06-installer-backups', installer_options)


def missing_hook_record(c):
    text = hook_setup(c)
    if 'hooks not installed' not in text or 'install.py' not in text:
        return False
    # Inspect the actual brief output, not the question or prose repeating it.
    for row in c.executions:
        source = row.get('command', '')
        if ('brief' in source and re.search(r'\bro(?:\.py)?\b', source) and
                'hooks not installed' in row.get('aggregated_output', '') and
                'self-test not recorded' in row.get('aggregated_output', '')):
            return True
        if re.search(r'ro[_-]hook(?:_runner\.py|\.(?:sh|cmd))', source):
            return False  # A hook ran before the claimed initial brief.
    return False


register('hook-portability', '90-missing-hook-record', missing_hook_record)


def no_history_guard(c):
    text = c.text('review.md')
    test_name = 'test_pretool_does_not_open_history_files'
    source = c.checker_skill.parents[1] / 'tests/test_ro_hooks.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == test_name]
    if len(functions) != 1:
        return False
    code = ast.get_source_segment(source.read_text(encoding='utf-8'), functions[0])
    citation = test_name in text or ('tests/test_ro_hooks.py' in text and re.search(
        r'guard_open|monkeypatch|patched|reject|forbid|raise', text, re.I) is not None)
    return (citation and all(name in text for name in ('discoveries.md', 'handoff.md', 'PreToolUse')) and
            all(value in code for value in ('discoveries.md', 'handoff.md', 'guard_open', 'assert attempted == []')))


register('hook-latency-budget', '90-06-history-guard', no_history_guard)


def statement_words(source):
    if __package__:
        from .command_trace import _source, _statements
    else:
        from command_trace import _source, _statements
    return list(_statements(_source(source)))


def wrapper_integrity(c):
    retained = wrapper_rows(c, 'replay.json')
    wrappers = {str(word).replace('\\', '/') for row in retained for word in argv(row)
                if str(word).endswith(('/ro-hook.sh', '/ro-hook.cmd', '\\ro-hook.sh', '\\ro-hook.cmd'))}
    if not wrappers:
        return False
    # Payload commands stay data: an exact standalone shell statement would be
    # execution, while JSON passed on stdin remains one quoted argument.
    commands = {payload(row).get('tool_input', {}).get('command') for row in retained
                if isinstance(payload(row), dict) and isinstance(payload(row).get('tool_input', {}), dict)} - {None}
    attempted = False
    for execution in c.executions:
        source = execution.get('command', '')
        statements = statement_words(source)
        for words in statements:
            normalized = [word.replace('\\', '/') for word in words]
            if wrappers & set(normalized):
                attempted = True
            if any(statement_words(command) == [words] for command in commands):
                return False
        if any(wrapper in source.replace('\\', '/') for wrapper in wrappers) and re.search(
                r'\b(?:write_text|write_bytes|Set-Content|Add-Content|apply_patch|Remove-Item|Copy-Item|rm|mv|cp|sed)\b', source, re.I):
            return False
    events = (c.run_dir / 'events.jsonl').read_text(encoding='utf-8')
    for line in events.splitlines():
        record = json.loads(line)
        for entry in objects(record):
            if entry.get('name', entry.get('tool_name')) in ('Write', 'Edit', 'apply_patch'):
                body = json.dumps(entry)
                if 'ro-hook.sh' in body or 'ro-hook.cmd' in body or 'ro_hook_runner.py' in body:
                    return False
    return attempted


register('hook-interpreter-override', '90-03-real-wrapper', wrapper_integrity)


def named_objects(value, context=''):
    if isinstance(value, dict):
        yield context + '/' + str(value.get('id', value.get('name', ''))), value
        for key, child in value.items():
            yield from named_objects(child, context + '/' + str(key))
    elif isinstance(value, list):
        for child in value:
            yield from named_objects(child, context)


def annotation_scan(c):
    data = c.data('redaction-report.json')
    encoded = json.dumps(data)
    secrets = ['github_pat_' + 'aB9_' * 20, 'ASIA' + 'A1' * 8, 'PrivateBody6543210', 'SplitToken9753']
    if any(secret in encoded for secret in secrets):
        return False
    nested, clean = False, False
    for name, row in named_objects(data):
        label = name.lower()
        findings = row.get('findings', row.get('issues', row.get('locations', row.get('matches'))))
        details = json.dumps(findings) if findings is not None else str(row.get('stdout', row.get('diagnostic', '')))
        if 'nested' in label and (row.get('blocked') is True or row.get('rejected') is True or
                                 type(result_code(row)) is int and result_code(row) != 0):
            nested |= bool(re.search(r'tag|annotation', details, re.I) and re.search(r':\d+|line|object', details, re.I))
        if 'clean' in label:
            clean |= (row.get('accepted') is True or type(result_code(row)) is int and result_code(row) == 0) and findings in (None, [])
    return nested and clean


register('credential-storage-redaction', '08-annotated-tag-scan', annotation_scan)


def ro_arguments(row):
    words = list(argv(row))
    if words[:1] == ['&']:
        words.pop(0)
    if words and re.fullmatch(r'(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?',
                              str(words[0]).replace('\\', '/').rsplit('/', 1)[-1], re.I):
        words.pop(0)
        while words and re.fullmatch(r'-[uBES]|-3(?:\.\d+)?', words[0]):
            words.pop(0)
    if not words or str(words.pop(0)).replace('\\', '/').rsplit('/', 1)[-1] not in ('ro', 'ro.py'):
        return {}, []
    options = {}
    while words and words[0].split('=', 1)[0] in ('--session', '--slot', '--project'):
        key = words.pop(0)
        if '=' in key:
            key, value = key.split('=', 1)
        elif words:
            value = words.pop(0)
        else:
            return {}, []
        options[key] = value
    return options, words


register('cli-hook-literal', '90-04-global-literal', lambda c: any(
         type(result_code(row)) is int and result_code(row) == 0 and
         ro_arguments(row)[0].get('--session') == 'hook' and ro_arguments(row)[1]
         and ro_arguments(row)[1][0] != 'hook' for row in objects(c.data('command-results.json'))))
register('cli-hook-literal', '90-05-actual-hook', lambda c: any(
         type(result_code(row)) is int and result_code(row) == 0 and
         ro_arguments(row)[1][:2] == ['hook', 'PreToolUse'] and isinstance(output(row), dict)
         for row in objects(c.data('command-results.json'))))


def preserved_inventory(c):
    originals = {path.name: path.read_bytes() for path in (c.case_dir / 'files').iterdir() if path.is_file()}
    records = []
    for path in c.outputs.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in ('.json', '.md', '.txt'):
            continue
        if not re.search(r'inventory|preserv|audit', path.name, re.I):
            continue
        content = path.read_text(encoding='utf-8')
        records.extend(content.splitlines())
        if path.suffix.lower() == '.json':
            for label, row in named_objects(json.loads(content)):
                records.append(label + ' ' + json.dumps(row))
    if not originals or not records:
        return False
    for name, original in originals.items():
        expected = hashlib.sha256(original).hexdigest()
        if not any(name in record and expected in record for record in records):
            return False
        copies = [path for path in c.outputs.rglob(name) if path.is_file() and
                  not {'public', 'published', 'evidence'}.intersection(part.lower() for part in path.relative_to(c.outputs).parts[:-1])]
        if not any(path.read_bytes() == original for path in copies):
            return False
    return True


register('publication-archive-boundary', '90-04-result', preserved_inventory)


def publication_check_results(c):
    """Read actual validator stdout; report prose alone cannot establish execution."""
    negative = positive = False
    for execution in c.executions:
        command = execution.get('command', '')
        if 'check_publication' not in command and 'validate_release.py' not in command:
            continue
        text = execution.get('aggregated_output', '')
        values = []
        for candidate in (text, *text.splitlines()):
            try:
                values.append(json.loads(candidate))
            except ValueError:
                try:
                    values.append(ast.literal_eval(candidate))
                except (ValueError, SyntaxError):
                    pass
        for value in values:
            for label, row in named_objects(value):
                errors = row.get('errors', row.get('issues', row.get('findings')))
                status = str(row.get('status', row.get('result', ''))).lower()
                bad = row.get('rejected') is True or row.get('passed') is False or status in ('fail', 'rejected') or bool(errors)
                good = row.get('passed') is True or status in ('pass', 'accepted') or errors == []
                negative |= bool(re.search(r'contaminat|unsafe|negative', label, re.I) and bad and
                                 (errors is None or 'publication' in json.dumps(errors).lower()))
                positive |= bool(re.search(r'saniti[sz]|clean|public|export', label, re.I) and good and not errors)
        # Some simple local harnesses print labelled verdict lines instead of JSON.
        negative |= re.search(r'(?im)^.*(?:contaminated|unsafe|negative)[^\n]*(?:\bFAIL\b|\brejected\b)', text) is not None
        positive |= re.search(r'(?im)^.*(?:saniti[sz]ed|clean|export)[^\n]*(?:\bPASS\b|\baccepted\b)', text) is not None
    return negative and positive


register('publication-archive-boundary', '90-05-result', publication_check_results)


def codex_dated_enforcement(c):
    text = c.text('codex-setup.md').replace('`', '').replace('**', '')
    lower = text.lower()
    required = ('2026-10-27', '0.154.0', 'gpt-6.1-sol', 'windows/powershell',
                'shell.background', 'jobs.mutate-bound', 'jobs.read-bound',
                'jobs.unmonitored', 'records.timestamp',
                '--dangerously-bypass-hook-trust')
    # Runtime identity alone does not establish the documented setup route. The
    # trust boundary and relied-on gates are part of this assertion's evidence.
    invocation = re.search(r'per[- ]invocation|for (?:that|the|each|this|a) invocation', lower)
    persisted = any('/hooks' in line and re.search(r'persist(?:ed|ent)|saved', line) and
                    re.search(r'\b(?:not|never)\s+(?:been\s+)?(?:exercised|tested|verified)|'
                              r'\bun(?:exercised|tested|verified)\b', line)
                    for line in re.split(r'[.\n]', lower))
    gates = any(re.search(r'\bro\s+(?:commands|cli|gates)\b', line) and 'git pre-push' in line and
                re.search(r'relied[- ]on|rely on|authoritative|primary', line)
                for line in re.split(r'[.\n]', lower))
    return (all(value in text for value in required) and invocation and persisted and gates and
            re.search(r'\b(?:six|6)\s+(?:recorded\s+)?probes\b', lower) is not None)


register('codex-host-capabilities', '90-01-dated-enforcement-status', codex_dated_enforcement)
