"""Offline adapter for mixed CLI/desktop General reports; never runs a judge."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import unified_reports as reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--describe', action='store_true')
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.describe:
        result = reports.describe()
    else:
        if bool(args.spec) == bool(args.snapshot) or args.output is None:
            parser.error('provide --spec or --snapshot and --output')
        value = json.loads((args.spec or args.snapshot).read_text(encoding='utf-8-sig'))
        snapshot = reports.prepare(value) if args.spec else value
        if args.prepare_only:
            reports.validate_snapshot(snapshot)
            reports.atomic_json(args.output, snapshot)
            result = {'snapshot_sha256': snapshot['snapshot_sha256']}
        else:
            result = reports.generate(snapshot, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
