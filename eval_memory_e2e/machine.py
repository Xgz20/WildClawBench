"""Machine-local paths for the four memory targets; no configurable foreign home."""
import os
import json
import platform
import pwd
import socket
import subprocess
import sys
from pathlib import Path

from .io import require, sha


def paths_for_home(home):
    home = Path(home)
    acode = home / '.acode'
    debug = home / 'debug-workspace/e2e-evaluate/memory-e2e'
    return {'home': home, 'debug': debug, 'ui_lock': debug / '.memory-native-ui.lock',
            'acode': acode, 'overlay': acode / 'acode/acode-home-overlay',
            'astudio_db': acode / 'acode/userdata/state.sqlite',
            'qwen_db': home / 'Library/Application Support/QwenWorkCN/data/agents.db',
            'qwen_trace': home / '.qwenworkcn', 'workbuddy': home / '.workbuddy'}


def machine_paths():
    # HOME may be overridden by a launcher. Use the OS account, never another
    # account's directory or CODEX_HOME as an AStudio fallback.
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    require(home.is_absolute() and home.resolve() == home, 'MACHINE_HOME', str(home))
    return paths_for_home(home)


def machine_identity():
    return {'contract': 'wildclawbench.memory-machine/v1', 'host': socket.gethostname(),
            'architecture': platform.machine(), 'uid': os.getuid(),
            'paths': {k: str(v) for k, v in machine_paths().items()},
            'python': {'executable': str(Path(sys.executable).resolve()),
                       'version': platform.python_version(),
                       'sha256': sha(Path(sys.executable).resolve().read_bytes())}}


def node_identity():
    return json.loads(subprocess.check_output(['node', '-p',
        'JSON.stringify({version:process.version,architecture:process.arch,executable:process.execPath})'], text=True))


def astudio_kernel(app=Path('/Applications/AStudio.app'), *, architecture=None, inspect=None):
    architecture = architecture or platform.machine()
    suffix = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'x64'}.get(architecture)
    require(suffix is not None, 'ASTUDIO_KERNEL_ARCH', architecture)
    expected = 'arm64' if suffix == 'arm64' else 'x86_64'
    inspect = inspect or (lambda p: subprocess.check_output(['/usr/bin/lipo', '-archs', str(p)], text=True).split())
    for name in ('acode-darwin-' + suffix, 'acode-darwin-universal'):
        candidate = Path(app) / 'Contents/Resources/bin' / name
        if not candidate.is_file():
            continue
        require(candidate.resolve() == candidate and os.access(candidate, os.X_OK), 'ASTUDIO_KERNEL_PATH', str(candidate))
        require(expected in inspect(candidate), 'ASTUDIO_KERNEL_ARCH', str(candidate))
        return candidate
    require(False, 'ASTUDIO_KERNEL_MISSING', 'No native or universal AStudio kernel in ' + str(app))


def kernel_identity():
    path = astudio_kernel()
    result = subprocess.run([str(path), '--version'], capture_output=True, text=True, timeout=20)
    require(result.returncode == 0, 'ASTUDIO_KERNEL_VERSION', str(path))
    return {'path': str(path), 'sha256': sha(path.read_bytes()), 'version': result.stdout.strip(),
            'architecture': platform.machine()}
