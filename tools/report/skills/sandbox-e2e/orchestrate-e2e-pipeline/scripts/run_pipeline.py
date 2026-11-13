#!/usr/bin/env python3
"""Invoke pipeline actions through the evaluator's public CLI."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = args.repo_root.expanduser().resolve(strict=True)
    entry = root / "eval" / "run_e2e.py"
    if not entry.is_file():
        parser.error("EVALUATOR_ENTRYPOINT_MISSING")
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    return subprocess.run([sys.executable, str(entry), *arguments], cwd=root).returncode


if __name__ == "__main__":
    raise SystemExit(main())
