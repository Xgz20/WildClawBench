"""Publish the same versioned legal policy used by standalone report packages."""
from pathlib import Path
from .common import file_sha256, read_json

def snapshot():
    path = Path(__file__).resolve().parents[2] / 'tools/report/data/legal_acceptance_policy.json'
    return {'policy': read_json(path), 'sha256': file_sha256(path)}
