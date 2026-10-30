#!/usr/bin/env python3
"""Publish append-only, source-bound Qwen trace transport recaptures."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/e2e-shared/general-contracts'))
from utf8_redecode import publish
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--unit-root',type=Path,required=True);p.add_argument('--captures',type=Path,required=True);p.add_argument('--repair-id',required=True);p.add_argument('--process-stop-proof',type=Path,required=True);p.add_argument('--output-selection',type=Path,required=True)
a=p.parse_args();assert not a.output_selection.exists();result=publish(a.unit_root,json.loads(a.captures.read_text()),a.repair_id,a.process_stop_proof);a.output_selection.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
