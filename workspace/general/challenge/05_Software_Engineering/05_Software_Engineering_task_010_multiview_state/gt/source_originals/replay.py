"""Run fixed public tapes using actual candidate sources and frozen bundled Node."""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--output',default='results/scenarios.json');args=parser.parse_args()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
runtime=json.loads((ROOT/'runtime.json').read_text())['node'];node=Path(runtime['path'])
if not node.is_file() or sha(node)!=runtime['sha256']:raise RuntimeError('H050_NODE_RUNTIME_UNAVAILABLE_OR_DRIFT_UNASSESSED')
request={'fixture':json.loads((ROOT/'fixtures/records.json').read_text()),'scenarios':json.loads((ROOT/'fixtures/public_scenarios.json').read_text()),'fixture_sha256':sha(ROOT/'fixtures/records.json'),'scenarios_sha256':sha(ROOT/'fixtures/public_scenarios.json')}
out=Path(args.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='h050-public-') as tmp:
 p=Path(tmp);(p/'request.json').write_text(json.dumps(request))
 command=[str(node),'--experimental-vm-modules','--disable-warning=ExperimentalWarning',str(ROOT/'engine.mjs'),str(ROOT),str(p/'request.json'),str(p/'response.json'),sys.executable]
 result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=45)
 if result.returncode or not (p/'response.json').is_file():raise RuntimeError('H050_PUBLIC_REPLAY_INFRASTRUCTURE: '+result.stderr)
 out.write_bytes((p/'response.json').read_bytes());print(json.dumps({'output':str(out),'sha256':sha(out),'returncode':result.returncode}))
