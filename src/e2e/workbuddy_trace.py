"""WorkBuddy's untrimmed Windows project trace bound to one controller run."""
from pathlib import Path
import json,subprocess,re
from .common import E2EError

def normalize_workbuddy(path:Path,*,identity,prompt,guest_cwd,requested_model,requested_effort=None,report,product_report=None,diagnostics=None,requested_max_mode=False):
    module=Path(__file__).resolve().parents[2]/'tools/report/e2e-shared/general-resource-supplements/agentcube-workbuddy-binding.mjs'
    value={'identity':identity,'prompt':prompt,'guest_cwd':guest_cwd,'requested_model':requested_model,'requested_max_mode':requested_max_mode,'report':report,'product_report':product_report,'diagnostics':diagnostics,'raw_name':path.name}
    script="""import{readFileSync}from'node:fs';import{pathToFileURL}from'node:url';const m=await import(pathToFileURL(process.argv[1]).href),r=JSON.parse(readFileSync(0,'utf8'));console.log(JSON.stringify(m.analyzeWorkBuddy(readFileSync(process.argv[2]),r)));"""
    result=subprocess.run(['node','--input-type=module','-e',script,str(module),str(path)],input=json.dumps(value),capture_output=True,text=True,timeout=60)
    if result.returncode:raise E2EError('WORKBUDDY_NATIVE_BINDING_REJECTED: '+(re.search(r'WORKBUDDY_[A-Z0-9_]+',result.stderr).group(0) if re.search(r'WORKBUDDY_[A-Z0-9_]+',result.stderr) else 'NATIVE_PARSE_FAILED'))
    return json.loads(result.stdout)
