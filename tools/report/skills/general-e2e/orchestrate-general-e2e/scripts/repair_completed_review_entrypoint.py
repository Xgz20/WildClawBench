"""Run an exact frozen orchestrator with only the declared-review proof repair."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--legacy-cli',type=Path,required=True)
    parser.add_argument('--legacy-sha256',required=True)
    args,remaining=parser.parse_known_args()
    legacy=args.legacy_cli.resolve(strict=True)
    if (not remaining or args.legacy_cli.is_symlink() or not legacy.is_file()
        or hashlib.sha256(legacy.read_bytes()).hexdigest()!=args.legacy_sha256):
        raise ValueError('DECLARED_REVIEW_LEGACY_ENTRYPOINT_MISMATCH')
    metadata=json.loads((legacy.parents[1]/'skill-metadata.json').read_text())
    if metadata.get('name')!='orchestrate-general-e2e' or metadata.get('version')!='0.11.72':
        raise ValueError('DECLARED_REVIEW_LEGACY_VERSION_UNSUPPORTED')
    scripts=Path(__file__).resolve().parent
    repaired=load_module('_general_e2e_declared_review_repair',scripts/'unscored_rule_review.py')
    sys.path.insert(0,str(legacy.parent))
    original=load_module('_general_e2e_frozen_orchestrator',legacy)
    original.unscored_rule_review=repaired
    return original.main(remaining)


if __name__=='__main__':
    raise SystemExit(main())
