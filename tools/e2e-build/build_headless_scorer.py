#!/usr/bin/env python3
"""Prepare/build a standalone, hash-locked headless scoring image."""
from __future__ import annotations

import argparse
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


def prepare(args: argparse.Namespace) -> dict:
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
    for name in ('Dockerfile', 'native-office.Dockerfile', 'configure_linux_office.py',
                 'validate_runtime.py', 'build-prepared.sh'):
        shutil.copyfile(ROOT / 'docker/e2e-scorer' / name, target / name)
    shutil.copyfile(ROOT / 'docker/deepseek-harness/v3/wcb-dsh', target / 'wcb-dsh')
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
        'WITH_OFFICE': '1' if args.with_office else '0',
    }
    (target / 'build-inputs.env').write_text(
        ''.join(f'{key}={shlex.quote(value)}\n' for key, value in inputs.items()), encoding='utf-8')
    manifest = {'schema_version': 'wildclawbench.headless-scorer-build/v1',
                'inputs': inputs, 'skill': result['skills'][0],
                'source_revision': result['source_revision']}
    (target / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--docker-context', default='default')
    parser.add_argument('--eval-base-image', default='python:3.11-bookworm')
    parser.add_argument('--node-runtime-image', default='node:24-bookworm-slim')
    parser.add_argument('--codex-version', default='0.171.0')
    parser.add_argument('--dsh-version', default='0.1.2-rc.1')
    parser.add_argument('--npm-registry', default='https://registry.npmmirror.com')
    parser.add_argument('--pip-index-url', default='https://pypi.org/simple')
    parser.add_argument('--http-proxy')
    parser.add_argument('--with-office', action='store_true')
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
