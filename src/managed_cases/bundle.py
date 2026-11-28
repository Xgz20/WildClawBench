"""Untrusted portable source archives and verified runner materialization."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
import io
import json
import re
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

from .contracts import SCHEMA, canonical, document, render_markdown, rubric, safe_path, sha, validate, compile_rules

MAX_FILES=10000
MAX_UNPACKED=2*1024**3
MAX_FILE=512*1024**2


def file_digest(path):
    import hashlib
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


class ArchiveMembers(dict):
    """Index only; each bounded member is streamed when consumed, never all ZIP bytes."""
    def __init__(self,path,infos):
        self.path=path
        self.identity=(path.stat().st_ino,path.stat().st_mtime_ns,path.stat().st_size)
        super().__init__((name,info) for name,info in infos.items())
    def __getitem__(self,name):
        current=self.path.stat()
        if (current.st_ino,current.st_mtime_ns,current.st_size)!=self.identity:raise ValueError('导入原包在读取中发生变化')
        info=super().__getitem__(name)
        chunks=[];size=0
        with zipfile.ZipFile(self.path) as archive,archive.open(info) as stream:
            while chunk:=stream.read(1024*1024):
                size+=len(chunk)
                if size>info.file_size or size>MAX_FILE:raise ValueError('压缩包实际解压体积超限')
                chunks.append(chunk)
        if size!=info.file_size:raise ValueError('压缩包文件大小不一致')
        return b''.join(chunks)
    def items(self):
        for name in self:yield name,self[name]
    def pop(self,name):
        value=self[name];super().pop(name);return value


def read_archive(path, *, expected=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('用例包必须是普通文件')
    if expected and file_digest(path)!=expected:raise ValueError('用例包摘要已变化')
    import os
    max_files=int(os.environ.get('WCB_CASE_MAX_FILES',MAX_FILES))
    max_unpacked=int(os.environ.get('WCB_CASE_MAX_UNPACKED',MAX_UNPACKED))
    infos={};folded=set();size=0
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>max_files:raise ValueError('压缩包文件数量超限')
        for info in entries:
            name=safe_path(info.filename.rstrip('/') if info.is_dir() else info.filename)
            mode=info.external_attr>>16
            allowed={0,stat.S_IFDIR} if info.is_dir() else {0,stat.S_IFREG}
            if stat.S_IFMT(mode) not in allowed:raise ValueError('压缩包不允许链接或特殊文件')
            if info.is_dir():continue
            if name.casefold() in folded:raise ValueError('压缩包存在重名或大小写冲突')
            folded.add(name.casefold());size+=info.file_size
            if size>max_unpacked or info.file_size>MAX_FILE:raise ValueError('压缩包解压体积超限')
            infos[name]=info
    return ArchiveMembers(path,infos)


def write_archive(manifest, files, destination):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    body=deepcopy(manifest);body['schema']=SCHEMA
    body['files']={safe_path(name):{'size':len(value),'sha256':sha(value)} for name,value in files.items()}
    body['content_sha256']=sha({k:v for k,v in body.items() if k!='content_sha256'})
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',canonical(body))
        for name,value in sorted(files.items()):archive.writestr(name,value)
    return {'sha256':sha(destination.read_bytes()),'manifest':body}


def load(path, expected):
    if not isinstance(expected,str) or not re.fullmatch(r'[a-f0-9]{64}',expected):raise ValueError('外部用例包必须提供有效 SHA-256')
    files=read_archive(path,expected=expected)
    body=json.loads(files.pop('manifest.json'))
    if body.get('schema')!=SCHEMA or body.get('content_sha256')!=sha({k:v for k,v in body.items() if k!='content_sha256'}):
        raise ValueError('用例包清单或内容摘要无效')
    if set(files)!=set(body.get('files',{})):raise ValueError('用例包文件清单不一致')
    for name,value in files.items():
        if body['files'][name]!={'size':len(value),'sha256':sha(value)}:raise ValueError('素材摘要已变化：'+name)
    ids=[]
    for row in body.get('cases',[]):
        result=validate(row['document'],body.get('scene'))
        if not result['valid']:raise ValueError('用例校验失败：'+json.dumps(result['issues'],ensure_ascii=False))
        ids.append(row['document']['metadata']['id'])
        for asset in row['document'].get('assets',[]):
            if asset['file'] not in files or body['files'][asset['file']]['sha256']!=asset['sha256']:
                raise ValueError('素材引用或摘要无效')
    if not ids or len(set(ids))!=len(ids):raise ValueError('用例编号为空或重复')
    if body.get('scene',{}).get('base_contract','general') not in {'general','web','ppt'}:
        raise ValueError('不支持的基础场景契约')
    return body,files


def compile_source(path, expected, output):
    """A small data tree, not a framework checkout or injected registry entry."""
    from eval_general_e2e.datasets.bundle import compile_dataset, write_dataset_bundle
    from eval_general_e2e.datasets.definition import DEFAULT_DEFINITION
    output=Path(output)
    manifest,files=load(path,expected)
    if output.is_symlink():raise ValueError('冻结运行缓存不能是符号链接')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.managed-source-',dir=output.parent))
    try:
        sources=stage/'sources';sources.mkdir()
        tasks=[];registry=[]
        for row in manifest['cases']:
            body=document(row['document']);meta=body['metadata'];identifier=meta['id'];category=meta['category']
            workspace=f'workspace/{category}/{identifier}'
            for key in ('exec','gt'):(sources/workspace/key).mkdir(parents=True,exist_ok=True)
            for asset in body['assets']:
                tree='exec' if asset['role']=='input' else 'gt'
                target=sources/workspace/tree/safe_path(asset['path'])
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(files[asset['file']])
            if body.get('rules'):
                body['sections']['Automated Checks']='```python\n'+compile_rules(body['rules'])+'\n```'
                helper=(Path(__file__).with_name('rule_checks.py')).read_bytes()
                (sources/workspace/'gt/managed_rule_checks.py').write_bytes(helper)
                # Import the fixed helper from the private GT tree in the grader.
                body['sections']['Automated Checks']=body['sections']['Automated Checks'].replace(
                    '    from managed_rule_checks import grade_rules',
                    '    import runpy\n    from pathlib import Path\n    grade_rules = runpy.run_path(str(Path(kwargs.get("workspace_path") or "/tmp_workspace") / "gt/managed_rule_checks.py"))["grade_rules"]')
            body['sections']['LLM Judge Rubric']=rubric(body)
            scoring=body.get('scoring') or manifest.get('scene',{}).get('scoring',{})
            meta['managed_scoring']={'schema':SCHEMA,'config':scoring,'scene':manifest.get('scene',{}),
                                     'source_sha256':expected,'authoring_sha256':sha(row['document']),'system_reference':body.get('system_reference'),
                                     'dependencies':body.get('dependencies',[]),
                                     'task_requirements':{key:body['sections'].get(key,'') for key in ('Expected Behavior','Grading Criteria')}}
            meta.setdefault('difficulty','L1');meta.setdefault('modality','pure-text');meta.setdefault('timeout_seconds',300)
            if meta['grading_type']=='automated':meta.setdefault('grading_weights',{'automated':1.0,'llm_judge':0.0})
            if meta['grading_type']=='llm_judge':meta.setdefault('grading_weights',{'automated':0.0,'llm_judge':1.0})
            task=sources/'tasks'/category/(identifier+'.md');task.parent.mkdir(parents=True,exist_ok=True)
            task.write_text(render_markdown(body,workspace),encoding='utf-8')
            tasks.append(meta);registry.append({'task_id':identifier,'source':'user-authored'})
        (sources/'registry.yaml').write_text(json.dumps({'tasks':registry}))
        definition=replace(DEFAULT_DEFINITION,dataset_id=manifest['dataset_id'],task_root='tasks',workspace_root='workspace',
            registry_path='registry.yaml',task_glob='*/*.md',include_tags=(),exclude_tags=(),expected_task_count=len(tasks),
            expected_category_counts=Counter(m['category'] for m in tasks),
            expected_grading_type_counts=Counter(m['grading_type'] for m in tasks),
            expected_difficulty_counts=Counter(m['difficulty'] for m in tasks),
            expected_timeout_counts=Counter(str(m['timeout_seconds']) for m in tasks),task_ids=tuple(m['id'] for m in tasks),
            source_revision=None,created_at='1970-01-01T00:00:00Z',revision_scope=('tasks','workspace'))
        compiled,members=compile_dataset(sources,definition=definition)
        write_dataset_bundle(compiled,members,stage/'dataset.zip')
        receipt={'schema':SCHEMA,'source_sha256':expected,'dataset_id':manifest['dataset_id'],
                 'dataset_digest':compiled['dataset_digest'],'scene':manifest.get('scene',{}),
                 'cases':manifest['cases'],'dataset_bundle_sha256':sha((stage/'dataset.zip').read_bytes())}
        shutil.copyfile(path,stage/'source.zip')
        receipt['compiled_files']={p.relative_to(stage).as_posix():sha(p.read_bytes()) for p in stage.rglob('*') if p.is_file()}
        (stage/'source-receipt.json').write_bytes(canonical(receipt))
        if output.exists():
            if not (output/'source-receipt.json').is_file():raise ValueError('冻结运行缓存不完整')
            previous=json.loads((output/'source-receipt.json').read_text())
            if previous!=receipt:raise ValueError('冻结运行缓存清单已变化')
            actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            if actual!=set(receipt['compiled_files'])|{'source-receipt.json'}:raise ValueError('冻结运行缓存文件清单不一致')
            for name,checksum in receipt['compiled_files'].items():
                file=output/safe_path(name)
                if file.is_symlink() or file_digest(file)!=checksum:raise ValueError('冻结运行输入已变化')
        else:
            try:stage.rename(output)
            except FileExistsError:return compile_source(path,expected,output)
        return receipt
    finally:
        if stage.exists():shutil.rmtree(stage)


def cli_tasks(path, expected, output):
    from src.utils.task_parser import parse_task_md
    receipt=compile_source(path,expected,output)
    source=Path(output)/'sources'
    return receipt,[parse_task_md(p,repo_root=source) for p in sorted((source/'tasks').glob('*/*.md'))]


def e2e_tasks(path, expected, output):
    from eval_general_e2e.datasets.bundle import BundleMember
    from eval_general_e2e.shared.dataset_bundle.verify import load_verified_dataset_bundle
    receipt=compile_source(path,expected,output);output=Path(output)
    verified=load_verified_dataset_bundle(output/'dataset.zip');compiled=verified.manifest
    with zipfile.ZipFile(output/'dataset.zip') as archive:
        prefix=verified.archive_root+'/'
        members={name[len(prefix):].rstrip('/'):BundleMember(name[len(prefix):],archive.read(name)) for name in archive.namelist()
                 if name.startswith(prefix) and not name.endswith('/') and name[len(prefix):]!='manifest.json'}
    rows=[{**row,'scene':'general','metric_profile':'general-e2e-contract-v1',
           'business_scene':receipt['scene'],'managed_source_sha256':expected,
           'dataset':{'id':compiled['dataset_id'],'digest':compiled['dataset_digest']}}
          for row in compiled['tasks']]
    return rows,members,compiled
