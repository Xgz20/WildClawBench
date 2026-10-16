"""Audited configuration probes; evaluated clients only, never Codex."""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
import tomllib
from pathlib import Path

from . import HARNESS_PORTS
from .io import publish, read_json, require, sha, timestamp

ASTUDIO_MEMORY_FIELDS = {
    'features': {'memories': True},
    'memories': {'generate_memories': True, 'use_memories': True, 'dedicated_tools': True,
                 'extract_model': 'spark-x2.5', 'consolidation_model': 'spark-x2.5'},
}


def set_toml_fields(text, table, fields):
    """Edit reviewed scalar keys while retaining unrelated TOML and comments."""
    require(table in ASTUDIO_MEMORY_FIELDS and set(fields) <= set(ASTUDIO_MEMORY_FIELDS[table]),
            'ASTUDIO_CONFIG_SCOPE', 'Only reviewed AStudio memory fields may be edited')
    parsed = tomllib.loads(text)
    headers = list(re.finditer(r'(?m)^\[' + re.escape(table) + r'\][ \t]*(?:#.*)?$', text))
    if not headers:
        require(table not in parsed, 'ASTUDIO_TOML_LAYOUT', 'Dotted or inline tables require a reviewed editor')
        additions = {key: value for key, value in fields.items() if value is not None}
        if not additions:
            return text
        text += ('\n' if text and not text.endswith('\n') else '') + '\n[' + table + ']\n'
        return set_toml_fields(text, table, additions)
    require(len(headers) == 1, 'ASTUDIO_TOML_LAYOUT', 'Ambiguous configuration table')
    start = headers[0].end()
    next_header = re.search(r'(?m)^\[', text[start:])
    end = start + next_header.start() if next_header else len(text)
    body = text[start:end]
    for key, value in fields.items():
        require(value is None or type(value) in {bool, str}, 'ASTUDIO_CONFIG_VALUE', key)
        pattern = r'(?m)^([ \t]*' + re.escape(key) + r'[ \t]*=[ \t]*)(true|false|"(?:\\.|[^"\\])*")([ \t]*(?:#.*)?)$'
        matches = list(re.finditer(pattern, body))
        require(len(matches) <= 1, 'ASTUDIO_TOML_LAYOUT', key)
        if matches:
            if value is None:
                body = re.sub(pattern + r'\n?', '', body)
            else:
                body = re.sub(pattern, lambda m: m[1] + json.dumps(value, ensure_ascii=False) + m[3], body)
        else:
            require(key not in parsed.get(table, {}), 'ASTUDIO_TOML_LAYOUT', 'Unsupported key spelling: ' + key)
            if value is not None:
                body += ('\n' if body and not body.endswith('\n') else '') + key + ' = ' + json.dumps(value, ensure_ascii=False) + '\n'
    result = text[:start] + body + text[end:]
    expected = tomllib.loads(result).get(table, {})
    require(all((key not in expected if value is None else expected.get(key) == value) for key, value in fields.items()),
            'ASTUDIO_TOML_VERIFY', table)
    return result


def set_memory_feature(text, enabled):
    """Change one TOML boolean, preserving all unrelated text and comments."""
    value = 'true' if enabled else 'false'
    config = tomllib.loads(text)
    headers = list(re.finditer(r'(?m)^\[features\][ \t]*(?:#.*)?$', text))
    if not headers:
        require('features' not in config, 'ASTUDIO_TOML_LAYOUT', 'Dotted/inline feature tables need a reviewed editor')
        return text + ('\n' if text and not text.endswith('\n') else '') + '\n[features]\nmemories = ' + value + '\n'
    require(len(headers) == 1, 'ASTUDIO_TOML_LAYOUT', 'Ambiguous feature table')
    start = headers[0].end()
    next_header = re.search(r'(?m)^\[', text[start:])
    end = start + next_header.start() if next_header else len(text)
    body = text[start:end]
    pattern = r'(?m)^([ \t]*memories[ \t]*=[ \t]*)(true|false)([ \t]*(?:#.*)?)$'
    matches = list(re.finditer(pattern, body))
    if matches:
        require(len(matches) == 1, 'ASTUDIO_TOML_LAYOUT', 'Ambiguous memory setting')
        body = re.sub(pattern, lambda m: m[1] + value + m[3], body)
    else:
        require('memories' not in config.get('features', {}), 'ASTUDIO_TOML_LAYOUT', 'Unsupported key spelling')
        body += ('\n' if body and not body.endswith('\n') else '') + 'memories = ' + value + '\n'
    result = text[:start] + body + text[end:]
    require(tomllib.loads(result)['features']['memories'] is enabled, 'ASTUDIO_TOML_VERIFY', 'Result does not select intended value')
    return result


def _replace_owned(path, expected, desired, mode):
    require(path.read_bytes() == expected, 'CONFIG_CONCURRENT_EDIT', str(path))
    fd, name = tempfile.mkstemp(prefix='.memory-e2e-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(mode))
            stream.write(desired)
            stream.flush()
            os.fsync(stream.fileno())
        require(path.read_bytes() == expected, 'CONFIG_CONCURRENT_EDIT', str(path))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def astudio_configuration_probe(folder, roundtrip=False):
    folder.mkdir()
    guard_script = Path(__file__).parent / 'native/astronstudio-config.mjs'
    guard = subprocess.run(['node', str(guard_script)], capture_output=True, timeout=60, check=False)
    publish(folder / 'guard.stdout.log', guard.stdout)
    publish(folder / 'guard.stderr.log', guard.stderr)
    if guard.returncode:
        result = {'harness': 'AstronStudio', 'status': 'NEEDS_ATTENTION', 'mutated': False,
                  'reason': 'ASTUDIO_IDLE_OR_DESKTOP_IDENTITY_UNVERIFIED', 'restored': True}
        publish(folder / 'receipt.json', result)
        return result
    identity = json.loads(guard.stdout)
    roots = [Path('/Users/gzx/.acode'), Path('/Users/gzx/.acode/acode/acode-home-overlay')]
    records = []
    for i, home in enumerate(roots):
        path = home / 'config.toml'
        require(path.resolve() == path and path.is_file(), 'ASTUDIO_HOME_PATH', str(path))
        original = path.read_bytes()
        require(len(original) < 1048576, 'ASTUDIO_CONFIG_SIZE', str(path))
        parsed = tomllib.loads(original.decode())
        record = {'path': str(path), 'home': str(home), 'before': parsed.get('features', {}).get('memories', False),
                  'before_sha256': sha(original), 'original': original, 'owned': original, 'mode': path.stat().st_mode}
        records.append(record)
        backup = folder / f'config-{i}.original.private'
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
    journal = folder / 'events.jsonl'
    def log(value):
        with journal.open('a') as stream:
            stream.write(json.dumps({'at': timestamp(), **value}, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    error = None
    try:
        for record in records:
            path = Path(record['path'])
            log({'kind': 'BASELINE', 'path': str(path), 'memory_enabled': record['before'], 'sha256': record['before_sha256']})
            if roundtrip:
                data = set_memory_feature(record['original'].decode(), not record['before']).encode()
                log({'kind': 'SWITCH_INTENT', 'path': str(path), 'desired': not record['before'], 'desired_sha256': sha(data)})
                _replace_owned(path, record['original'], data, record['mode'])
                record['owned'] = data
                # ACode's supported home override is ACODE_HOME. Never change CODEX_HOME.
                env = dict(os.environ, ACODE_HOME=record['home'])
                process = subprocess.run(['/Applications/AStudio.app/Contents/Resources/bin/acode-darwin-x64',
                                          'features', 'list'], env=env, capture_output=True, timeout=20)
                selected = [line for line in process.stdout.decode().splitlines() if line.startswith('memories\t') or line.startswith('memories ')]
                require(process.returncode == 0 and len(selected) == 1, 'ASTUDIO_FEATURE_READBACK', 'Installed kernel did not report exactly one memories feature')
                require(selected[0].split()[-1] == str(not record['before']).lower(), 'ASTUDIO_FEATURE_READBACK', selected[0])
                log({'kind': 'SWITCH_VERIFIED', 'path': str(path), 'kernel_feature': selected[0], 'sha256': sha(path.read_bytes())})
    except Exception as exc:
        error = str(exc)
    finally:
        for record in reversed(records):
            if record['owned'] != record['original']:
                try:
                    log({'kind': 'RESTORE_INTENT', 'path': record['path']})
                    _replace_owned(Path(record['path']), record['owned'], record['original'], record['mode'])
                    log({'kind': 'RESTORE_VERIFIED', 'path': record['path'], 'sha256': sha(record['original'])})
                except Exception as exc:
                    error = (error + '; ' if error else '') + str(exc)
    restored = all(Path(r['path']).read_bytes() == r['original'] for r in records)
    result = {'contract': 'wildclawbench.memory-config/v1', 'harness': 'AstronStudio',
              'status': 'PASS' if error is None and restored else 'NEEDS_ATTENTION', 'action': 'roundtrip' if roundtrip else 'inspect',
              'identity': identity, 'baseline': [{k: r[k] for k in ['path', 'before', 'before_sha256']} for r in records],
              'restored': restored, 'error': error, 'verification': 'installed-kernel-feature-list-and-file-sha',
              'running_session_apply_verified': False, 'memory_write_verified': False,
              'global_memory_reset_performed': False, 'excluded_clients': ['Codex']}
    publish(folder / 'receipt.json', result)
    return result


def configuration_probe(output_dir, harnesses=None, roundtrip=False, preflight_dir=None):
    selected = list(HARNESS_PORTS) if harnesses is None else list(harnesses)
    # Scope rejection precedes all filesystem, config and transport operations.
    require(selected and len(selected) == len(set(selected)) and set(selected) <= set(HARNESS_PORTS),
            "HARNESS_SCOPE", "Only AStudio, WorkBuddy, QwenWork and DoubaoWork are evaluation targets; Codex is excluded")
    output = Path(output_dir).absolute()
    debug = Path('/Users/gzx/debug-workspace/e2e-evaluate/memory-e2e')
    require(output.is_relative_to(debug) and output.resolve() == output and not output.exists(),
            "CONFIG_OUTPUT", "Use a new directory under the memory-e2e debug root")
    require(not roundtrip or preflight_dir is not None, "CONFIG_PREFLIGHT_REQUIRED", "A fresh native preflight directory is required")
    output.mkdir(parents=True)
    script = Path(__file__).parent / 'native/configuration.mjs'
    source_checksum = sha(script.read_bytes())
    results = []
    for name in selected:
        folder = output / name
        if name == 'AstronStudio':
            result = astudio_configuration_probe(folder, roundtrip)
            result['evidence_dir'] = str(folder)
            results.append(result)
            continue
        raw = Path(preflight_dir) / name / 'probe.json' if preflight_dir else None
        request = {'harness': name, 'action': 'roundtrip' if roundtrip else 'inspect',
                   'output_dir': str(folder), 'preflight_file': str(raw) if raw else None}
        process = subprocess.run(['node', str(script)], input=json.dumps(request).encode(),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
        folder.mkdir(exist_ok=True)
        publish(folder / 'stdout.log', process.stdout)
        publish(folder / 'stderr.log', process.stderr)
        if (folder / 'receipt.json').exists():
            result = read_json(folder / 'receipt.json')
            require(result.get('harness') == name and (not roundtrip or result.get('restored') is True),
                    'CONFIG_RECEIPT_INVALID', name)
        else:
            result = {'harness': name, 'status': 'NEEDS_ATTENTION', 'returncode': process.returncode,
                      'reason': 'CONFIG_OPERATION_NOT_COMPLETED', 'restored': None}
        result['evidence_dir'] = str(folder)
        results.append(result)
    report = {'contract': 'wildclawbench.memory-config-probe/v1', 'created_at': timestamp(),
              'status': 'PASS' if all(r['status'] == 'PASS' for r in results) and sha(script.read_bytes()) == source_checksum else 'PARTIAL',
              'action': 'roundtrip' if roundtrip else 'inspect', 'clients': results,
              'evaluated_harnesses': list(HARNESS_PORTS), 'excluded_clients': ['Codex'],
              'source_sha256': source_checksum, 'source_after_sha256': sha(script.read_bytes()), 'memory_effectiveness_verified': False,
              'global_memory_reset_performed': False}
    publish(output / 'report.json', report)
    return report
