from pathlib import Path
import importlib.util,json,hashlib,subprocess
root=Path('/opt/scoring-runtime');python=root/'bin/python';binary=Path('/usr/lib/libreoffice/program/oosplash')
spec=importlib.util.spec_from_file_location('native_office','/opt/runtime-score-skill/scripts/configure_native_office.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
support=root/'native-office';support.mkdir();launcher=support/'launcher.py';launcher.write_text(module.LAUNCHER)
wrapper='#!/bin/sh\nexec '+str(python)+' -I '+str(launcher)+' "$@"\n';target=root/'bin/soffice';target.write_text(wrapper);target.chmod(0o755)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt={'schema_version':'wildclawbench.general-e2e-native-office/v1','status':'CONFIGURED_LINUX_REAL_SMOKE_REQUIRED','runtime_python':str(python),'binary':{'path':str(binary),'sha256':sha(binary)},'font_directories':['/usr/share/fonts/truetype','/usr/share/fonts/opentype'],'launcher_script_sha256':sha(launcher),'bin_launcher_sha256':sha(target),'score_policy_changed':False}
(support/'native-office.json').write_text(json.dumps(receipt,indent=2)+'\n')
env={'PATH':str(root/'bin'),'PYTHONUTF8':'1','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
v=subprocess.run([str(target),'--version'],env=env,capture_output=True,text=True,check=True);receipt['version']=v.stdout.strip();(support/'native-office.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
