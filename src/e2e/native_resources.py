"""Replay the canonical General Skill resource parser against a bound rollout."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from .common import E2EError, file_sha256


def replay_resources(path: Path, binding: dict) -> dict:
    repo = Path(__file__).resolve().parents[2]
    module = repo / 'tools/report/skills/general-e2e/collect-general-e2e/vendor/e2e-shared/general-resource-supplements/astronstudio-rollout.mjs'
    state = {'phase': 'COMPLETED', 'session': {**binding['session'], 'verified': True},
             'prompt': {'send_status': 'sent', 'sha256': binding['prompt_transport']['native_message_sha256']}}
    definition = {'path': str(path), 'expected': {'sha256': binding['raw_sha256'], 'size': path.stat().st_size}, 'state': state}
    script = """import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const moduleURL=pathToFileURL(process.argv[1]).href;
process.argv[1]='agentcube-native-resource-replay';
const m=await import(moduleURL),r=JSON.parse(readFileSync(0,'utf8'));
const file=await m.readRolloutFile(r.path,r.expected);
console.log(JSON.stringify(m.analyzeRollout(file.bytes,r.state)));"""
    try:
        result = subprocess.run(['node', '--input-type=module', '-e', script, str(module)],
            input=json.dumps(definition), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise E2EError('NATIVE_RESOURCE_REPLAY_UNAVAILABLE: ' + type(error).__name__) from None
    if result.returncode:
        # The parser's fixed error code is sufficient; do not copy arbitrary native payloads into logs.
        raise E2EError('NATIVE_RESOURCE_REPLAY_REJECTED')
    projection = json.loads(result.stdout)
    return {**projection, 'parser': {'profile': 'agentcube-bound-general-rollout/v1',
        'entry_sha256': file_sha256(module),
        'timing_helper_sha256': file_sha256(module.parent.parent / 'resource-metrics/flow-timing.mjs')},
        'raw_sha256': binding['raw_sha256']}
