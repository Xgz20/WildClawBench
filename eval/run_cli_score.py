"""Independent grading entry point for frozen Harness CLI executions."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cli_scoring import score

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--agentcube-config', type=Path)
    args = parser.parse_args()
    result = score(args.input_root, args.output_root, json.loads(args.config.read_text()), args.agentcube_config)
    print(json.dumps(result, ensure_ascii=False))
