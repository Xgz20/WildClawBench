"""Archived source-build diagnostics. All build/mutation entry points are disabled.

load_kernel verifies historical artifacts without executing them. These artifacts
are not eligible for production-package evaluation, even when labelled unscored.
"""
import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from .io import publish, require, sha, timestamp
from .production import reject_source_build

ROOT = Path(__file__).resolve().parents[1]
COPY = ROOT / '.kernel-source/acode'
TOOLS = ROOT / '.kernel-tools'
PATCH = ROOT / 'eval_memory_e2e/native_kernel_overlay/controller.patch'
PATCH_PREFIXES = ('codex-rs/sandboxing/src/', 'codex-rs/exec-server/src/')
# Classic shell lacks the unified-exec remote route. Its adapter needs core's
# existing timeout/output types; no other core files are admitted to this patch.
PATCH_FILES = {'codex-rs/core/src/exec.rs', 'codex-rs/core/src/exec_remote.rs',
               'codex-rs/core/src/exec_remote_tests.rs', 'codex-rs/core/src/tools/runtimes/shell.rs'}


def allowed_source(path):
    return path.startswith(PATCH_PREFIXES) or path in PATCH_FILES


def environment(target='controller'):
    reject_source_build()
    require(target in ('controller', 'application'), 'KERNEL_BUILD_TARGET', target)
    result = dict(os.environ)
    # ACode builds/tests use the private ACODE_HOME below. Never inherit the
    # controller's home or credentials for a real model-service request.
    for key in ('CODEX_HOME', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'ACODE_API_KEY', 'OPENAI_BASE_URL'):
        result.pop(key, None)
    for name in ('tmp', 'test-home', 'target'):
        (TOOLS / name).mkdir(parents=True, exist_ok=True)
    mirrored = (TOOLS / 'cargo-rsproxy/config.toml').exists()
    result.update(CARGO_HOME=str(TOOLS / ('cargo-rsproxy' if mirrored else 'cargo')), RUSTUP_HOME=str(TOOLS / 'rustup'),
                  CARGO_TARGET_DIR=str(TOOLS / ('target-app-kernel' if target == 'application' else 'target-rsproxy' if mirrored else 'target')), ACODE_HOME=str(TOOLS / 'test-home'),
                  TMPDIR=str(TOOLS / 'tmp') + '/', CARGO_NET_GIT_FETCH_WITH_CLI='true',
                  SDKROOT=str(Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk').resolve()),
                  GIT_CONFIG_COUNT='3', GIT_CONFIG_KEY_0='http.version', GIT_CONFIG_VALUE_0='HTTP/1.1',
                  GIT_CONFIG_KEY_1='url.https://ghfast.top/https://github.com/.insteadOf', GIT_CONFIG_VALUE_1='https://github.com/',
                  GIT_CONFIG_KEY_2='url.https://ghfast.top/https://github.com/lemenkov/libyuv.insteadOf',
                  GIT_CONFIG_VALUE_2='https://chromium.googlesource.com/libyuv/libyuv',
                  UV_CACHE_DIR=str(TOOLS / 'uv-cache'), UV_PYTHON_INSTALL_DIR=str(TOOLS / 'uv-python'),
                  UV_PYTHON=str(Path(sys.executable).resolve()), DOTSLASH_CACHE=str(TOOLS / 'dotslash-cache'))
    result['PATH'] = os.pathsep.join([str(TOOLS / 'cargo/bin'), str(TOOLS / 'bin'),
                                    str(Path(sys.executable).parent), result.get('PATH', '')])
    result['ASTUDIO_EVAL_SOURCE_COMMIT'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=COPY, text=True).strip()
    result['ASTUDIO_EVAL_PATCH_SHA256'] = sha(PATCH.read_bytes()) if PATCH.exists() else 'unbound'
    result['ASTRON_VERSION'] = ('1.0.5-rc.3+memory-e2e.' + result['ASTUDIO_EVAL_SOURCE_COMMIT'][:8]
                                + '.' + result['ASTUDIO_EVAL_PATCH_SHA256'][:12])
    v8_manifest = TOOLS / 'artifacts/rusty-v8.json'
    if v8_manifest.exists():
        archive = json.loads(v8_manifest.read_text())
        lock = tomllib.loads((COPY / 'codex-rs/Cargo.lock').read_text())
        locked = next(p['version'] for p in lock['package'] if p['name'] == 'v8')
        official = archive['official_release']
        require(sha(Path(official['path']).read_bytes()) == official['sha256'], 'KERNEL_V8_RELEASE_DRIFT', str(v8_manifest))
        release = json.loads(Path(official['path']).read_text())
        require(archive['version'] == locked and release['tag_name'] == 'v' + locked
                and release['asset']['digest'] == 'sha256:' + archive['sha256']
                and sha(Path(archive['path']).read_bytes()) == archive['sha256'],
                'KERNEL_V8_ARCHIVE_DRIFT', str(v8_manifest))
        result['RUSTY_V8_ARCHIVE'] = archive['path']
    return result


def export_patch():
    reject_source_build()
    changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=COPY, text=True).splitlines()
    extra = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=COPY, text=True).splitlines()
    require(all(allowed_source(p) for p in changed + extra), 'KERNEL_PATCH_SCOPE', repr(changed + extra))
    patch = subprocess.check_output(['git', 'diff', '--binary'], cwd=COPY)
    for path in extra:
        result = subprocess.run(['git', 'diff', '--no-index', '--binary', '--', '/dev/null', path], cwd=COPY, capture_output=True)
        require(result.returncode == 1, 'KERNEL_NEW_SOURCE_PATCH', path)
        patch += result.stdout
    require(patch and b'CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR' not in patch and b'CODEX_SANDBOX_ENV_VAR' not in patch,
            'KERNEL_PATCH_SCOPE', 'Do not modify sandbox identity/environment switches')
    PATCH.parent.mkdir(exist_ok=True)
    PATCH.write_bytes(patch)
    return {'patch': str(PATCH), 'sha256': sha(patch), 'paths': sorted(changed + extra),
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=COPY, text=True).strip()}


def approve_binary(output):
    reject_source_build()
    source = export_patch()
    binary = Path(environment()['CARGO_TARGET_DIR']) / 'debug/acode-memory-executor'
    require(binary.is_file() and not binary.is_symlink(), 'KERNEL_BINARY_MISSING', str(binary))
    info = json.loads(subprocess.check_output([str(binary), '--version'], env=environment(), text=True))
    require(info.get('contract') == 'astudio-composed-native-executor/v2'
            and info.get('source_commit') == source['source_commit'] and info.get('patch_sha256') == source['sha256'],
            'KERNEL_COMPILED_SOURCE_DRIFT', 'Rebuild after all source/format changes before freezing a binary')
    architectures = subprocess.check_output(['/usr/bin/lipo', '-archs', str(binary)], text=True).split()
    require(architectures == ['arm64'], 'KERNEL_EXECUTOR_ARCH', repr(architectures))
    raw = binary.read_bytes(); digest = sha(raw)
    folder = TOOLS / 'approved' / digest; folder.mkdir(parents=True, exist_ok=True)
    approved = folder / binary.name
    if approved.exists():
        require(sha(approved.read_bytes()) == digest, 'KERNEL_APPROVED_BINARY_DRIFT', str(approved))
    else:
        publish(approved, raw); approved.chmod(0o555)
    record = {'contract': 'astudio-native-controller-build/v1', 'at': timestamp(), 'binary': str(approved),
              'sha256': digest, 'size': len(raw), 'architectures': architectures, 'version': info,
              'source': source, 'installed_astudio_modified': False, 'automatic_consolidation_admitted': False}
    publish(Path(output), record)
    return record


def load_kernel(path):
    """Read-only integrity check for historical artifacts; does not admit or run them."""
    path = Path(path).absolute()
    value = json.loads(path.read_text())
    require(value.get('contract') == 'astudio-compiled-app-kernel/v1' and value.get('diagnostic_only') is True
            and value.get('installed_astudio_modified') is False, 'KERNEL_OVERRIDE_MANIFEST', str(path))
    binary = Path(value['path'])
    require(binary.is_relative_to(TOOLS / 'approved-kernel') and binary.resolve() == binary
            and binary.name == 'acode' and sha(binary.read_bytes()) == value['sha256'],
            'KERNEL_OVERRIDE_BINARY_DRIFT', str(binary))
    for name in ('build', 'source_patch'):
        item = value[name]
        require(sha(Path(item['path']).read_bytes()) == item['sha256'], 'KERNEL_OVERRIDE_EVIDENCE_DRIFT', name)
    built = json.loads(Path(value['build']['path']).read_text())
    require(built['status'] == 'PASS' and built['command'] == ['cargo', 'build', '--locked', '-p', 'codex-cli', '--bin', 'acode']
            and built['source_before'] == built['source_after']
            and built['source_after']['sha256'] == value['source_patch']['sha256'],
            'KERNEL_OVERRIDE_BUILD_DRIFT', str(path))
    return value


def approve_kernel(output, evidence):
    reject_source_build()
    source = export_patch()
    records = sorted(Path(evidence).glob('build-kernel-*.json'))
    require(records, 'KERNEL_BUILD_RECEIPT_MISSING', str(evidence))
    receipt = records[-1]; built = json.loads(receipt.read_text())
    require(built['status'] == 'PASS' and built['source_before'] == built['source_after'] == source,
            'KERNEL_BUILD_SOURCE_DRIFT', str(receipt))
    source_patch = receipt.with_suffix('.after.patch')
    require(sha(source_patch.read_bytes()) == source['sha256'], 'KERNEL_BUILD_PATCH_DRIFT', str(source_patch))
    binary = Path(environment('application')['CARGO_TARGET_DIR']) / 'debug/acode'
    require(binary.is_file() and binary.resolve() == binary, 'KERNEL_BINARY_MISSING', str(binary))
    env = environment('application')
    version = subprocess.check_output([str(binary), '--version'], env=env, text=True).strip()
    require(version == 'astron-code ' + env['ASTRON_VERSION'], 'KERNEL_COMPILED_VERSION_DRIFT', version)
    architectures = subprocess.check_output(['/usr/bin/lipo', '-archs', str(binary)], text=True).split()
    require(architectures == ['arm64'], 'KERNEL_OVERRIDE_ARCH', repr(architectures))
    raw = binary.read_bytes(); digest = sha(raw)
    folder = TOOLS / 'approved-kernel' / digest; folder.mkdir(parents=True, exist_ok=True)
    approved = folder / 'acode'
    if approved.exists():
        require(sha(approved.read_bytes()) == digest, 'KERNEL_APPROVED_BINARY_DRIFT', str(approved))
    else:
        publish(approved, raw); approved.chmod(0o555)
    record = {'contract': 'astudio-compiled-app-kernel/v1', 'at': timestamp(), 'path': str(approved),
              'sha256': digest, 'size': len(raw), 'version': version, 'architecture': 'arm64',
              'source_commit': source['source_commit'], 'source_patch': {'path': str(source_patch), 'sha256': source['sha256']},
              'build': {'path': str(receipt), 'sha256': sha(receipt.read_bytes())},
              'diagnostic_only': True, 'installed_astudio_modified': False,
              'automatic_consolidation_admitted': False}
    publish(Path(output), record)
    return load_kernel(output)


def run(action, evidence):
    reject_source_build()
    evidence = Path(evidence).absolute()
    require(evidence.is_dir(), 'KERNEL_EVIDENCE', str(evidence))
    commands = {
        'build': ['cargo', 'build', '--locked', '-p', 'codex-exec-server', '--bin', 'acode-memory-executor'],
        'build-kernel': ['cargo', 'build', '--locked', '-p', 'codex-cli', '--bin', 'acode'],
        'check-core': ['cargo', 'check', '--locked', '-p', 'codex-core'],
        'test-core': ['just', 'test', '-p', 'codex-core', '--lib', 'exec_remote'],
        'test-sandboxing': ['just', 'test', '-p', 'codex-sandboxing', '--lib'],
        'test-exec-server': ['just', 'test', '-p', 'codex-exec-server', '--lib'],
        'fmt': ['just', 'fmt'],
        'fix-sandboxing': ['just', 'fix', '-p', 'codex-sandboxing'],
        'fix-exec-server': ['just', 'fix', '-p', 'codex-exec-server'],
        'fix-core': ['just', 'fix', '-p', 'codex-core'],
    }
    require(action in commands, 'KERNEL_BUILD_ACTION', action)
    sequence = max([int(p.stem[len(action)+1:]) for p in evidence.glob(action + '-*.json')
                    if p.stem[len(action)+1:].isdigit()] + [0]) + 1
    prefix = evidence / f'{action}-{sequence:02}'
    before = export_patch()
    publish(prefix.with_suffix('.before.patch'), PATCH.read_bytes())
    publish(prefix.with_suffix('.json'), {'status': 'STARTING', 'at': timestamp(), 'command': commands[action], 'source': before})
    runtime_env = environment('application' if action in ('build-kernel', 'test-core', 'fix-core') else 'controller')
    if action == 'fmt' and (evidence / 'ruff-locked-wheels.json').exists():
        for project in ('sdk/python', 'scripts'):
            lock = tomllib.loads((COPY / project / 'uv.lock').read_text())
            package = next(p for p in lock['package'] if p['name'] == 'ruff')
            wheel = next(w for w in package['wheels'] if 'macosx_11_0_arm64.whl' in w['url'])
            require(sha((TOOLS / 'wheels' / wheel['url'].split('/')[-1]).read_bytes()) == wheel['hash'].split(':')[1],
                    'KERNEL_FORMATTER_HASH', project)
            version = subprocess.check_output([str(COPY / project / '.venv/bin/ruff'), '--version'], text=True).strip()
            require(version == 'ruff ' + package['version'], 'KERNEL_FORMATTER_VERSION', project)
        runtime_env['UV_NO_SYNC'] = '1'
    with prefix.with_suffix('.log').open('xb') as log:
        process = subprocess.Popen(commands[action], cwd=COPY / 'codex-rs', env=runtime_env, stdout=log, stderr=subprocess.STDOUT)
        prefix.with_suffix('.json').write_text(json.dumps({'status': 'RUNNING', 'at': timestamp(), 'pid': process.pid,
            'command': commands[action], 'source': before, 'target': runtime_env['CARGO_TARGET_DIR'],
            'v8_archive': runtime_env.get('RUSTY_V8_ARCHIVE')}, indent=2) + '\n')
        code = process.wait()
    if action == 'fmt' or action.startswith('fix-'):
        modified = subprocess.check_output(['git', 'diff', '--name-only'], cwd=COPY, text=True).splitlines()
        unrelated = [p for p in modified if not allowed_source(p)]
        if unrelated:
            publish(prefix.with_suffix('.unrelated-format.patch'), subprocess.check_output(['git', 'diff', '--', *unrelated], cwd=COPY))
            subprocess.run(['git', 'restore', '--', *unrelated], cwd=COPY, check=True)
    after = export_patch()
    publish(prefix.with_suffix('.after.patch'), PATCH.read_bytes())
    record = {'status': 'PASS' if code == 0 else 'FAIL', 'at': timestamp(), 'command': commands[action],
              'exit_code': code, 'source_before': before, 'source_after': after, 'log': str(prefix.with_suffix('.log')),
              'target': runtime_env['CARGO_TARGET_DIR'], 'v8_archive': runtime_env.get('RUSTY_V8_ARCHIVE')}
    prefix.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False))
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['export-patch', 'approve-binary', 'approve-kernel', 'build', 'build-kernel', 'check-core',
                                         'test-core', 'test-sandboxing', 'test-exec-server', 'fmt',
                                         'fix-sandboxing', 'fix-exec-server', 'fix-core'])
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'export-patch':
        print(json.dumps(export_patch(), ensure_ascii=False))
    elif args.action == 'approve-binary':
        print(json.dumps(approve_binary(args.output), ensure_ascii=False))
    elif args.action == 'approve-kernel':
        print(json.dumps(approve_kernel(args.output, args.evidence), ensure_ascii=False))
    else:
        sys.exit(run(args.action, args.evidence))


if __name__ == '__main__':
    main()
