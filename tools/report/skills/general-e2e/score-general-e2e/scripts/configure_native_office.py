"""Install an explicit native renderer into an unstarted macOS rule runtime.

This provisions dependencies only. Real rendering/editing must be smoke-tested
with synthetic documents under score_general_e2e._sanitized_environment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


LAUNCHER = '''import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
from xml.sax.saxutils import escape
root=Path(__file__).resolve().parent
receipt=json.loads((root/'native-office.json').read_text(encoding='utf-8'))
binary=Path(receipt['binary']['path'])
if hashlib.sha256(binary.read_bytes()).hexdigest()!=receipt['binary']['sha256']:
    raise SystemExit('NATIVE_OFFICE_BINARY_DRIFT')
with tempfile.TemporaryDirectory(prefix='general-e2e-native-office-') as temporary:
    work=Path(temporary);cache=work/'font-cache';cache.mkdir()
    config=work/'fonts.conf'
    config.write_text('<fontconfig>'+''.join('<dir>'+escape(p)+'</dir>' for p in receipt['font_directories'])+'<cachedir>'+escape(str(cache))+'</cachedir></fontconfig>',encoding='utf-8')
    environment=os.environ.copy()
    environment['FONTCONFIG_FILE']=str(config)
    arguments=sys.argv[1:]
    if not any(a.startswith('-env:UserInstallation=') for a in arguments):
        arguments=['-env:UserInstallation='+(work/'profile').as_uri(),*arguments]
    result=subprocess.run([str(binary),*arguments],env=environment)
    raise SystemExit(result.returncode)
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure(*, runtime_python: Path, binary: Path, support_root: Path,
              font_directories: list[Path]) -> dict:
    if sys.platform != 'darwin':
        raise ValueError('NATIVE_OFFICE_PLATFORM_UNSUPPORTED')
    # Preserve the virtualenv path: resolving its Python symlink loses bin/.
    python = runtime_python.expanduser().absolute()
    native = binary.expanduser().resolve(strict=True)
    support = support_root.expanduser().absolute()
    launcher = python.parent / 'soffice'
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError('RUNTIME_PYTHON_UNAVAILABLE')
    if not native.is_file() or not os.access(native, os.X_OK):
        raise ValueError('NATIVE_OFFICE_BINARY_UNAVAILABLE')
    if os.path.lexists(launcher) or os.path.lexists(support):
        raise ValueError('NATIVE_OFFICE_DESTINATION_EXISTS')
    if not font_directories:
        raise ValueError('NATIVE_OFFICE_FONT_DIRECTORIES_REQUIRED')
    fonts = list(dict.fromkeys(str(p.expanduser().resolve(strict=True)) for p in font_directories))
    if any(not Path(p).is_dir() for p in fonts):
        raise ValueError('NATIVE_OFFICE_FONT_DIRECTORY_INVALID')
    support.mkdir(parents=True, exist_ok=False)
    script = support / 'launcher.py'
    script.write_text(LAUNCHER, encoding='utf-8')
    wrapper = '#!/bin/sh\nexec '+shlex.quote(str(python))+' -I '+shlex.quote(str(script))+' "$@"\n'
    receipt = {
        'schema_version': 'wildclawbench.general-e2e-native-office/v1',
        'status': 'CONFIGURED_REAL_RENDER_SMOKE_REQUIRED',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'runtime_python': str(python),
        'binary': {'path': str(native), 'sha256': sha(native)},
        'font_directories': fonts,
        'profile_policy': 'preserve explicit UserInstallation; otherwise unique temporary profile',
        'font_cache_policy': 'unique temporary fontconfig and writable cache per invocation',
        'launcher_script_sha256': sha(script),
        'bin_launcher_sha256': hashlib.sha256(wrapper.encode('utf-8')).hexdigest(),
        'score_policy_changed': False,
    }
    (support / 'native-office.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    # Exclusive creation keeps existing runtime launchers and symlinks intact.
    with launcher.open('x', encoding='utf-8') as stream:
        stream.write(wrapper)
    launcher.chmod(0o755)
    environment = {'PATH': str(python.parent), 'PYTHONNOUSERSITE': '1',
                   'PYTHONUTF8': '1', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
    version = subprocess.run([str(launcher), '--version'], env=environment,
                             capture_output=True, text=True, encoding='utf-8',
                             timeout=30, check=True)
    receipt['version'] = version.stdout.strip()
    receipt['version_stderr'] = version.stderr
    (support / 'native-office.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-python', type=Path, required=True)
    parser.add_argument('--soffice-binary', type=Path, required=True)
    parser.add_argument('--support-root', type=Path, required=True)
    parser.add_argument('--font-dir', type=Path, action='append', required=True)
    args = parser.parse_args()
    try:
        result = configure(runtime_python=args.runtime_python, binary=args.soffice_binary,
                           support_root=args.support_root, font_directories=args.font_dir)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
