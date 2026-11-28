"""Prepare a credential-free npm cache for a target Linux CLI image."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def prepare_cli_cache(target: Path, *, platform: str, registry: str, versions: dict,
                      source: Path | None = None) -> dict:
    expected = {'schema_version': 'wildclawbench.scorer-cli-cache/v1',
                'platform': platform, 'registry': registry, 'versions': versions}
    if source is None:
        cpu = {'linux/amd64': 'x64', 'linux/arm64': 'arm64'}[platform]
        npm = shutil.which('npm')
        if not npm:
            raise ValueError('npm is required to prepare CLI cache; provide --npm-cache-dir on Python-only hosts')
        with tempfile.TemporaryDirectory(prefix='scorer-cli-cache-') as temporary:
            work = Path(temporary)
            for name in ['user.npmrc', 'global.npmrc']:
                (work / name).touch()
            env = {k: v for k, v in os.environ.items()
                   if not any(word in k.upper() for word in ['TOKEN', 'PASSWORD', 'API_KEY', 'SECRET', 'NPM_CONFIG'])}
            subprocess.run([npm, 'install', '--global', '--ignore-scripts', '--os=linux',
                '--cpu=' + cpu, '--libc=glibc', '--prefix', str(work / 'prefix'),
                '--cache', str(work / 'cache'), '--userconfig', str(work / 'user.npmrc'),
                '--globalconfig', str(work / 'global.npmrc'), '--registry=' + registry,
                *[name + '@' + version for name, version in versions.items()]], env=env, check=True)
            (work / 'cache/cache-info.json').write_text(json.dumps(expected, indent=2) + '\n')
            return prepare_cli_cache(target, platform=platform, registry=registry,
                                     versions=versions, source=work / 'cache')
    source = source.resolve(strict=True)
    if source.is_relative_to(target.resolve()) or target.resolve().is_relative_to(source):
        raise ValueError('SCORER_CLI_CACHE_CONTEXT_OVERLAP')
    metadata = json.loads((source / 'cache-info.json').read_text())
    if metadata != expected or not (source / '_cacache').is_dir():
        raise ValueError('SCORER_CLI_CACHE_INPUT_MISMATCH')
    if (source / '_cacache').is_symlink():
        raise ValueError('SCORER_CLI_CACHE_SYMLINK')
    payload = target / 'npm-cache'
    if payload.exists():
        shutil.rmtree(payload)
    payload.mkdir()
    shutil.copytree(source / '_cacache', payload / '_cacache',
                    ignore=shutil.ignore_patterns('tmp'), symlinks=True)
    shutil.copyfile(source / 'cache-info.json', payload / 'cache-info.json')
    digest = hashlib.sha256()
    count = size = 0
    for path in sorted(payload.rglob('*')):
        if path.is_symlink():
            raise ValueError('SCORER_CLI_CACHE_SYMLINK')
        if path.is_file():
            name = path.relative_to(payload).as_posix()
            digest.update(name.encode() + b'\0')
            with path.open('rb') as stream:
                digest.update(hashlib.file_digest(stream, 'sha256').digest())
            count += 1
            size += path.stat().st_size
    return {**expected, 'content_sha256': digest.hexdigest(), 'files': count, 'bytes': size}
