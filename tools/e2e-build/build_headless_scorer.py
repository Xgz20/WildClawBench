#!/usr/bin/env python3
"""Prepare/build a standalone, hash-locked headless scoring image."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.e2e.common import load_script
from src.e2e.artifacts import extract_zip


def resolve_version(args: argparse.Namespace) -> dict:
    directory = ROOT / 'docker/e2e-scorer'
    catalog = json.loads((directory / 'versions.json').read_text())
    version = args.version or catalog['default']
    if version not in catalog['versions']:
        raise ValueError('Unknown scorer image version: ' + version)
    entry = catalog['versions'][version]
    args.version = version
    platforms = entry.get('platform_images', {})
    if platforms:
        args.platform = args.platform or entry['default_platform']
        if args.platform not in platforms:
            raise ValueError('Unsupported scorer platform: ' + args.platform)
        official_image = platforms[args.platform]
    else:
        if args.platform:
            raise ValueError('Platform selection requires a version with platform_images (v0.2 or later)')
        official_image = entry['image']
    args.tag = args.tag or official_image
    references = {ref for row in catalog['versions'].values()
                  for ref in [row['image'], *row.get('platform_images', {}).values()]}
    reserved = {ref + suffix for ref in references if ref != official_image for suffix in ['', '-runtime']}
    if args.tag in reserved:
        raise ValueError('Refusing to overwrite another scorer version: ' + args.tag)
    for key, value in entry['build_args'].items():
        attribute = key.lower()
        supplied = getattr(args, attribute)
        if supplied is not None and supplied != value:
            raise ValueError(f'{key} must be {value} for {version}; add a new version to versions.json')
        setattr(args, attribute, value)
    if 'claudecode' not in entry['harnesses'] and args.claude_code_version is not None:
        raise ValueError('This scorer version does not include ClaudeCode')
    if args.context is None:
        args.context = ROOT / '.cache/headless-scorer-build' / version
        if platforms:
            args.context /= args.platform.split('/')[1]
    return entry


def prepare(args: argparse.Namespace) -> dict:
    entry = resolve_version(args)
    target = args.context.resolve()
    # Packaging replaces only generated files in this dedicated directory.
    if target == ROOT or ROOT.is_relative_to(target) or (target / '.git').exists():
        raise ValueError('Use a dedicated build context outside the repository source')
    target.mkdir(parents=True, exist_ok=True)
    builder = load_script(ROOT / 'tools/e2e-build/build_skill_packages.py', 'headless_skill_builder')
    with tempfile.TemporaryDirectory(prefix='.skill-packages-', dir=target) as temporary:
        packages = Path(temporary)
        result = builder.build_skill_packages(ROOT, packages, skill_names=['score-general-e2e'])
        skill = target / 'runtime-skill'
        if skill.exists():
            shutil.rmtree(skill)
        extract_zip(packages / result['skills'][0]['archive'], skill, strip_root=True)
    source = ROOT / 'docker/e2e-scorer' / entry['context']
    assets = ('Dockerfile', 'native-office.Dockerfile', 'configure_linux_office.py',
              'validate_runtime.py', 'build-prepared.sh', 'wcb-dsh')
    for name in assets:
        shutil.copyfile(source / name, target / name)
    (target / '.dockerignore').write_text(
        '*\n!Dockerfile\n!native-office.Dockerfile\n!runtime-skill/\n!wcb-dsh\n'
        '!configure_linux_office.py\n!validate_runtime.py\n!build-manifest.json\n', encoding='utf-8')
    inputs = {
        'IMAGE_TAG': args.tag,
        'DOCKER_CONTEXT': args.docker_context,
        'EVAL_BASE_IMAGE': args.eval_base_image,
        'NODE_RUNTIME_IMAGE': args.node_runtime_image,
        'CODEX_VERSION': args.codex_version,
        'DSH_VERSION': args.dsh_version,
        'NPM_REGISTRY': args.npm_registry,
        'PIP_INDEX_URL': args.pip_index_url,
        'DEBIAN_MIRROR': args.debian_mirror,
        'DEBIAN_SECURITY_MIRROR': args.debian_security_mirror,
        'WITH_OFFICE': '1' if args.with_office else '0',
    }
    if 'claudecode' in entry['harnesses']:
        inputs['CLAUDE_CODE_VERSION'] = args.claude_code_version
        inputs['PLATFORM'] = args.platform
    (target / 'build-inputs.env').write_text(
        ''.join(f'{key}={shlex.quote(value)}\n' for key, value in inputs.items()), encoding='utf-8')
    manifest = {'schema_version': 'wildclawbench.headless-scorer-build/v1',
                'image_version': args.version, 'harnesses': entry['harnesses'],
                'build_files_sha256': {name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in assets},
                'inputs': inputs, 'skill': result['skills'][0],
                'source_revision': result['source_revision']}
    (target / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', help='Version from docker/e2e-scorer/versions.json')
    parser.add_argument('--platform', choices=['linux/amd64', 'linux/arm64'],
                        help='Target platform; v0.2 defaults to Linux AMD64 for servers')
    parser.add_argument('--context', type=Path)
    parser.add_argument('--tag', help='Separate release tag; cannot overwrite another catalog version')
    parser.add_argument('--docker-context', default='default')
    parser.add_argument('--eval-base-image')
    parser.add_argument('--node-runtime-image')
    parser.add_argument('--codex-version')
    parser.add_argument('--dsh-version')
    parser.add_argument('--claude-code-version')
    parser.add_argument('--npm-registry', default='https://registry.npmmirror.com')
    parser.add_argument('--pip-index-url', default='https://pypi.org/simple')
    parser.add_argument('--debian-mirror', default='https://mirrors.tuna.tsinghua.edu.cn/debian')
    parser.add_argument('--debian-security-mirror', default='https://mirrors.tuna.tsinghua.edu.cn/debian-security')
    parser.add_argument('--http-proxy')
    parser.add_argument('--with-office', action='store_true', default=True, help='Included in all catalog versions')
    parser.add_argument('--prepare-only', action='store_true', help='Package on one machine, build on another without host Python')
    args = parser.parse_args()
    result = prepare(args)
    if not args.prepare_only:
        import os
        environment = os.environ.copy()
        if args.http_proxy:
            environment['HTTP_PROXY_INNER'] = args.http_proxy
            environment['HTTPS_PROXY_INNER'] = args.http_proxy
        subprocess.run(['bash', str(args.context.resolve() / 'build-prepared.sh')],
                       env=environment, check=True)
    print(json.dumps({'image': args.tag, 'context': str(args.context.resolve()),
                      'prepared_only': args.prepare_only, 'skill': result['skill']}))


if __name__ == '__main__':
    main()
