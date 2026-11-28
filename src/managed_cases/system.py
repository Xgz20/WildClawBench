"""Resolve a system case through the existing catalog, never arbitrary paths."""
from pathlib import Path
import re
from src import case_catalog
from . import contracts,bundle


def export_case(repo,selection,output):
    repo=Path(repo).resolve();dataset=selection['dataset'];release=selection.get('release');identifier=selection['task_id']
    entry=case_catalog.dataset_entry(repo,dataset)
    if entry['scene']!='general':raise ValueError('系统专项契约不能与通用文件任务混编，请拆分评测集')
    files={};assets=[]
    if release:
        from src.e2e.preparation import _general_catalog
        if release not in {r['id'] for r in case_catalog.releases(repo,entry)}:raise ValueError('系统版本不存在')
        tasks,members,_=_general_catalog(repo,release)
        row=next((r for r in tasks if r['task_id']==identifier and 'invalid' not in r['tags']),None)
        if row is None:raise ValueError('系统用例不存在')
        raw=members[row['bundle']['task_path']].data
        prefix='tasks/'+identifier+'/'
        for name,member in members.items():
            for role,tree in [('input','execution/exec/'),('gt','private-scoring/gt/')]:
                if name.startswith(prefix+tree):
                    path=name[len(prefix+tree):]
                    if path and not path.endswith('/'):assets.append((role,path,member.data))
    else:
        row=next((r for r in case_catalog.current_cases(repo,dataset) if r['task_id']==identifier),None)
        if row is None:raise ValueError('系统用例不存在')
        raw=(repo/row['task_path']).read_bytes()
        parsed=contracts.parse_markdown(raw)
        from eval_general_e2e.datasets.layout import workspace_for_task
        declared=case_catalog._strip_codeblock(parsed['sections'].get('Workspace Path',''))
        workspace=workspace_for_task(repo,Path(declared)).resolve()
        if not workspace.is_relative_to(repo/'workspace'):raise ValueError('系统素材根目录越界')
        for role,tree in [('input','exec'),('gt','gt'),('support','eval')]:
            root=workspace/tree
            for path in sorted(root.rglob('*')):
                if path.is_symlink():raise ValueError('系统素材包含链接，不能冻结')
                if path.is_file() and path.name!='.gitkeep':assets.append((role,path.relative_to(root).as_posix(),path.read_bytes()))
    body=contracts.parse_markdown(raw);body['assets']=[];body['outputs']=[]
    for role,path,value in assets:
        member='files/'+role+'/'+contracts.safe_path(path);files[member]=value
        body['assets'].append({'role':role,'path':path,'file':member,'sha256':contracts.sha(value)})
    inputs={r['path'] for r in body['assets'] if r['role']=='input'}
    prompt=body['sections'].get('Prompt','')
    for value in re.findall(r'/tmp_workspace/([^\s`"<>，。；、)]+)',prompt):
        value=value.rstrip('.,;:')
        if value not in inputs and not any(p.startswith(value.rstrip('/')+'/') for p in inputs):
            body['outputs'].append(value.rstrip('/'))
    body['outputs']=list(dict.fromkeys(body['outputs']))
    reference={'dataset':dataset,'release':release,'task_id':identifier,'original_sha256':contracts.sha(raw)}
    body['system_reference']=reference
    receipt=bundle.write_archive({'dataset_id':'system-'+identifier,'scene':{'base_contract':'general'},'cases':[{'document':body}]},files,output)
    return {'reference':reference,'sha256':receipt['sha256'],'document':body}
