from pathlib import Path
import argparse
import hashlib
import json
import tempfile
import sys
from package_matrix import collect,find_interpreters

root=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--python311');p.add_argument('--python312');a=p.parse_args()
interpreters=find_interpreters()
if a.python311:interpreters[0]['path']=a.python311
if a.python312:interpreters[1]['path']=a.python312
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='h049-candidate-install-') as directory:
    result=collect(root,json.loads((root/'fixtures/configs.json').read_text())['cases'],json.loads((root/'fixtures/records.json').read_text()),interpreters,Path(directory)/'matrix')
    import shutil
    for version in result['versions']:
        if version['wheel']:
            source=Path(version['wheel']);target=root/'results/install_artifacts'/version['version']/source.name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            version['preserved_wheel']={'path':target.relative_to(root).as_posix(),'sha256':sha(target)}
paths=json.loads((root/'mutable_paths.json').read_text())['mutable']
result.update(source_sha256={r:sha(root/r) for r in paths if (root/r).is_file()},input_sha256={'fixtures/configs.json':sha(root/'fixtures/configs.json'),'fixtures/records.json':sha(root/'fixtures/records.json')})
output=root/'results/install_matrix.json';output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':'results/install_matrix.json','versions':[r['version'] for r in result['versions']],'build_returncodes':[r['build']['returncode'] for r in result['versions']]}))
