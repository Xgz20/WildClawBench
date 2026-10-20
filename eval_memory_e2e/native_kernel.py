"""Reproducible private ACode controller build; never replace the installed app.

The upstream source and all edits/build caches live inside the memory worktree.
Only the small patch and this build driver are committed to the evaluation repo.
"""
import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from .io import publish, require, sha, timestamp

ROOT = Path(__file__).resolve().parents[1]
COPY = ROOT / '.kernel-source/acode'
TOOLS = ROOT / '.kernel-tools'
PATCH = ROOT / 'eval_memory_e2e/native_kernel_overlay/controller.patch'


def environment():
    result = dict(os.environ)
    for name in ('tmp', 'test-home', 'target'):
        (TOOLS / name).mkdir(parents=True, exist_ok=True)
    mirrored = (TOOLS / 'cargo-rsproxy/config.toml').exists()
    result.update(CARGO_HOME=str(TOOLS / ('cargo-rsproxy' if mirrored else 'cargo')), RUSTUP_HOME=str(TOOLS / 'rustup'),
                  CARGO_TARGET_DIR=str(TOOLS / ('target-rsproxy' if mirrored else 'target')), ACODE_HOME=str(TOOLS / 'test-home'),
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
    return result


def export_patch():
    changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=COPY, text=True).splitlines()
    extra = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=COPY, text=True).splitlines()
    allowed = ('codex-rs/sandboxing/src/', 'codex-rs/exec-server/src/')
    require(all(p.startswith(allowed) for p in changed + extra), 'KERNEL_PATCH_SCOPE', repr(changed + extra))
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


def run(action, evidence):
    evidence = Path(evidence).absolute()
    require(evidence.is_dir(), 'KERNEL_EVIDENCE', str(evidence))
    commands = {
        'build': ['cargo', 'build', '--locked', '-p', 'codex-exec-server', '--bin', 'acode-memory-executor'],
        'test-sandboxing': ['just', 'test', '-p', 'codex-sandboxing', '--lib'],
        'test-exec-server': ['just', 'test', '-p', 'codex-exec-server', '--lib'],
        'fmt': ['just', 'fmt'],
        'fix-sandboxing': ['just', 'fix', '-p', 'codex-sandboxing'],
        'fix-exec-server': ['just', 'fix', '-p', 'codex-exec-server'],
    }
    require(action in commands, 'KERNEL_BUILD_ACTION', action)
    sequence = max([int(p.stem[len(action)+1:]) for p in evidence.glob(action + '-*.json')
                    if p.stem[len(action)+1:].isdigit()] + [0]) + 1
    prefix = evidence / f'{action}-{sequence:02}'
    before = export_patch()
    publish(prefix.with_suffix('.before.patch'), PATCH.read_bytes())
    publish(prefix.with_suffix('.json'), {'status': 'STARTING', 'at': timestamp(), 'command': commands[action], 'source': before})
    runtime_env = environment()
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
            'command': commands[action], 'source': before}, indent=2) + '\n')
        code = process.wait()
    if action == 'fmt':
        modified = subprocess.check_output(['git', 'diff', '--name-only'], cwd=COPY, text=True).splitlines()
        unrelated = [p for p in modified if not p.startswith(('codex-rs/sandboxing/src/', 'codex-rs/exec-server/src/'))]
        if unrelated:
            publish(prefix.with_suffix('.unrelated-format.patch'), subprocess.check_output(['git', 'diff', '--', *unrelated], cwd=COPY))
            subprocess.run(['git', 'restore', '--', *unrelated], cwd=COPY, check=True)
    after = export_patch()
    publish(prefix.with_suffix('.after.patch'), PATCH.read_bytes())
    record = {'status': 'PASS' if code == 0 else 'FAIL', 'at': timestamp(), 'command': commands[action],
              'exit_code': code, 'source_before': before, 'source_after': after, 'log': str(prefix.with_suffix('.log'))}
    prefix.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False))
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['export-patch', 'approve-binary', 'build', 'test-sandboxing', 'test-exec-server', 'fmt', 'fix-sandboxing', 'fix-exec-server'])
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'export-patch':
        print(json.dumps(export_patch(), ensure_ascii=False))
    elif args.action == 'approve-binary':
        print(json.dumps(approve_binary(args.output), ensure_ascii=False))
    else:
        sys.exit(run(args.action, args.evidence))


if __name__ == '__main__':
    main()
