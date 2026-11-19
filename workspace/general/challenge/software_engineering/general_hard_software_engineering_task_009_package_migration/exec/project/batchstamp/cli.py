import argparse
import json
import sys
from .core import run
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--config')
    a=p.parse_args(argv)
    try:
        with open(a.input,encoding='utf-8') as f:records=json.load(f)
        config=json.load(open(a.config,encoding='utf-8')) if a.config else {}
        print(json.dumps(run(records,config),ensure_ascii=False,sort_keys=True));return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'error':'invalid_input'},sort_keys=True),file=sys.stderr);return 2
