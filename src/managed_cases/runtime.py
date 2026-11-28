"""Credential-free runtime probing. No uploaded code is evaluated by this probe."""
import json,re,subprocess
from .contracts import validate_capabilities

DEPENDENCIES={'python:openpyxl':'openpyxl','python:pandas':'pandas','python:numpy':'numpy','python:pillow':'PIL',
    'python:pymupdf':'fitz','python:python-docx':'docx','python:python-pptx':'pptx','python:playwright':'playwright'}


def check(config,scene,documents):
    validate_capabilities(scene,config['transport'])
    dependencies=set()
    for document in documents:
        values=document.get('dependencies',[])
        if not isinstance(values,list) or any(v not in DEPENDENCIES for v in values):raise ValueError('MANAGED_DEPENDENCY_UNSUPPORTED')
        dependencies.update(values)
        if document.get('system_reference') and config.get('judge_instructions'):raise ValueError('系统固定引用不能覆盖原评分模板，请复制为个人草稿')
    required=set(dependencies)
    if scene.get('base_contract')=='ppt':required.update(['python:pymupdf','python:pillow'])
    if scene.get('base_contract')=='web':required.add('python:playwright')
    modules={value:DEPENDENCIES[value] for value in sorted(required)}
    script='import importlib.util,json,os; modules=json.loads(__import__("sys").argv[1]); print(json.dumps({key:bool(importlib.util.find_spec(name)) for key,name in modules.items()}));'
    script+='print(json.dumps({"office":os.path.isfile("/opt/scoring-runtime/bin/soffice")}))'
    image=config.get('rule_image_id') or config.get('image_id')
    if not image:raise ValueError('MANAGED_RULE_IMAGE_REQUIRED')
    command=['docker','--context',config.get('docker_context','default'),'run','--rm','--network','none','--cap-drop=ALL',
        '--security-opt=no-new-privileges','--read-only','--entrypoint','/opt/scoring-runtime/bin/python',image,'-I','-c',script,json.dumps(modules)]
    from .scoring import isolated_container
    result=isolated_container(command,30)
    if result.returncode:raise ValueError('MANAGED_RUNTIME_NOT_READY: '+result.stderr[-500:])
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    missing=[name for name,available in rows[0].items() if not available]
    if scene.get('base_contract')=='ppt' and not rows[1]['office']:missing.append('office')
    if missing:raise ValueError('MANAGED_RUNTIME_CAPABILITY_MISSING: '+','.join(missing))
    return {'ready':True,'image_id':image,'dependencies':sorted(required),'base_contract':scene.get('base_contract','general')}
