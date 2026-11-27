"""Canonical authoring, safe path/template handling and static validation.

This module never evaluates user Python, shell, template expressions or imports.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import math
from pathlib import PurePosixPath
import re

import yaml

SCHEMA = 'wildclawbench.managed-cases/v1'
CONTEXT_SCHEMA = 'wildclawbench.scoring-context/v1'
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z')
VARIABLE = re.compile(r'{{\s*([a-z_][a-z0-9_.]*)\s*}}')
VARIABLES = {'task.prompt', 'task.name', 'rubric', 'materials', 'candidate', 'trajectory', 'rules', 'output_contract'}
SECTIONS = {'prompt': 'Prompt', 'expected_behavior': 'Expected Behavior', 'grading_criteria': 'Grading Criteria',
            'automated_checks': 'Automated Checks', 'llm_judge_rubric': 'LLM Judge Rubric',
            'env': 'Env', 'skills': 'Skills', 'warmup': 'Warmup'}
METADATA = ('id', 'name', 'category', 'difficulty', 'modality', 'timeout_seconds', 'grading_type',
            'grading_weights', 'tags', 'judge_evidence', 'scoring_runtime', 'dataset_report')
TRANSPORTS = ('api', 'docker-cli', 'agentcube-desktop')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def safe_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value or ':' in value:
        raise ValueError('素材路径必须是工作区内的相对路径')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('素材路径不能越过工作区')
    if any(p.endswith((' ', '.')) or p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for p in path.parts):
        raise ValueError('素材路径不兼容 Windows')
    return path.as_posix()


def parse_markdown(raw):
    text = raw.decode('utf-8-sig') if isinstance(raw, bytes) else raw.lstrip('\ufeff')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    match = re.match(r'\A---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)(.*)', text, re.S)
    if not match:
        raise ValueError('用例文档缺少 YAML frontmatter')
    metadata = yaml.safe_load(match[1]) or {}
    if not isinstance(metadata, dict):
        raise ValueError('YAML 必须是对象')
    chunks = re.split(r'^##[ \t]+([^\n]+)\n', match[2], flags=re.M)
    sections = list(zip(chunks[1::2], chunks[2::2]))
    if len({name.strip() for name, _ in sections}) != len(sections):
        raise ValueError('用例包含重复章节')
    result = {'metadata': metadata, 'sections': {name.strip(): body.strip() for name,body in sections},
              'preamble': chunks[0].strip(), 'section_order': [name.strip() for name,_ in sections]}
    return result


def document(body):
    """Form edits update recognized fields only; preserve unknown source fields."""
    result = deepcopy(body)
    result.setdefault('metadata', {}); result.setdefault('sections', {})
    result.setdefault('section_order', list(result['sections'])); result.setdefault('assets', [])
    result.setdefault('outputs', []); result.setdefault('rules', []); result.setdefault('scoring', {})
    return result


def render_markdown(body, workspace=None):
    body = document(body)
    metadata = deepcopy(body['metadata'])
    sections = deepcopy(body['sections'])
    if workspace is not None: sections['Workspace Path'] = workspace
    for name in sections:
        if '\n' in name or not isinstance(sections[name], str):
            raise ValueError('章节标题或正文无效')
    order = list(dict.fromkeys([*body.get('section_order', []), *sections]))
    return '---\n'+yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()+'\n---\n'+(
        body.get('preamble', '')+'\n\n' if body.get('preamble') else '')+'\n\n'.join(
            '## '+name+'\n\n'+sections[name] for name in order if name in sections)+'\n'


def validate_template(template):
    if not isinstance(template, dict): raise ValueError('评分模板必须是对象')
    for key in ('common', *TRANSPORTS):
        value = template.get(key, '')
        if not isinstance(value,str) or len(value)>100000: raise ValueError('评分模板正文无效或过大')
        unknown = set(VARIABLE.findall(value))-VARIABLES
        remaining = VARIABLE.sub('', value)
        if unknown or '{{' in remaining or '}}' in remaining or '{%' in value:
            raise ValueError('评分模板含未知变量或不支持的模板表达式：'+','.join(sorted(unknown)))
    return deepcopy(template)


def render_template(template, transport, context):
    validate_template(template)
    if transport not in TRANSPORTS: raise ValueError('评分方式无效')
    def substitute(match):
        key=match[1]
        value = context.get(key)
        if value is None: raise ValueError('评分上下文缺少变量：'+key)
        return value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
    text='\n\n'.join(VARIABLE.sub(substitute,template.get(key,'')) for key in ('common',transport)).strip()
    return text


def effective_scoring(scene=None, case=None, override=None):
    """Select one template layer, never concatenate competing template versions."""
    selected = deepcopy(override if override is not None else case if case else scene or {})
    validate_template(selected.get('template', {}))
    return selected


def rubric(body):
    rows=body.get('criteria', [])
    if not rows: return body.get('sections',{}).get('LLM Judge Rubric','')
    text=[]
    for i,row in enumerate(rows,1):
        anchors=row.get('anchors') or [{'score':0,'description':'未满足要求'},{'score':1,'description':'满足全部要求'}]
        text.append(f"### Criterion {i}: {row['key']} (weight: {float(row['weight']):g})\n\n{row.get('description','')}\n"+'\n'.join(
            f"**Score {a['score']}**: {a['description']}" for a in anchors))
    return '\n\n'.join(text)


def compile_rules(rules):
    # Only fixed framework operations. User expressions are never interpolated into Python.
    for row in rules:
        if row.get('kind') not in {'exists','json_equals','text_contains'}: raise ValueError('不支持的声明式检查')
        safe_path(row['path'])
        if not IDENTIFIER.fullmatch(row['key']): raise ValueError('检查点编号无效')
    return 'def grade(**kwargs):\n    from managed_rule_checks import grade_rules\n    return grade_rules('+repr(rules)+', kwargs)\n'


def validate(body, scene=None):
    body=document(body);meta=body['metadata'];sections=body['sections'];issues=[]
    def error(field,message): issues.append({'field':field,'message':message,'severity':'error'})
    for field in ('id','category'):
        if not isinstance(meta.get(field),str) or not IDENTIFIER.fullmatch(meta[field]): error('metadata.'+field,'请填写有效的英文编号')
    if not str(meta.get('name','')).strip():error('metadata.name','请填写用例名称')
    if not sections.get('Prompt','').strip():error('sections.Prompt','请填写执行 Prompt')
    if meta.get('grading_type') not in {'automated','hybrid','llm_judge'}:error('metadata.grading_type','请选择评分方式')
    try:
        if not 1<=int(meta.get('timeout_seconds',300))<=86400:raise ValueError()
    except (ValueError,TypeError):error('metadata.timeout_seconds','执行预算必须在 1–86400 秒内')
    paths={};input_paths=set()
    for i,row in enumerate(body['assets']):
        try:
            path=safe_path(row['path']);role=row['role']
            if role not in {'input','gt','support'}:raise ValueError('素材分区无效')
            namespace='exec' if role=='input' else 'gt'
            key=(namespace,path.casefold())
            if key in paths:raise ValueError('素材路径重复或存在 Windows 大小写冲突')
            paths[key]=row
            if role=='input':
                if set(PurePosixPath(path).parts)&{'gt','private-scoring','.grading'}:raise ValueError('输入素材不能放入评分目录')
                input_paths.add(path)
        except (ValueError,KeyError) as exc:error(f'assets.{i}',str(exc))
    outputs=set()
    for i,value in enumerate(body['outputs']):
        try:
            path=safe_path(value)
            if set(PurePosixPath(path).parts)&{'gt','private-scoring','.grading'}:raise ValueError('输出路径不能指向评分目录')
            outputs.add(path)
        except ValueError as exc:error(f'outputs.{i}',str(exc))
    prompt=sections.get('Prompt','')
    for match in re.finditer(r'/tmp_workspace/([^\s`"<>，。；、)]+)',prompt):
        path=match[1].rstrip('.,;:')
        if set(PurePosixPath(path).parts)&{'gt','private-scoring','.grading'}:
            error('sections.Prompt','执行 Prompt 不得引用 GT 或私有评分素材')
        elif path not in input_paths|outputs and not any(p.startswith(path.rstrip('/')+'/') for p in input_paths|outputs):
            error('sections.Prompt','素材或预期输出未声明：'+path)
    for field in ('Automated Checks','Env','Skills','Warmup'):
        source=sections.get(field,'').strip()
        if field=='Automated Checks' and source:
            source=re.sub(r'^```[^\n]*\n|\n```\s*$','',source).strip()
            try:ast.parse(source)
            except SyntaxError as exc:error('sections.'+field,'Python 语法错误：'+str(exc))
    try:
        checks=compile_rules(body.get('rules', [])) if body.get('rules') else sections.get('Automated Checks','')
        grading=meta.get('grading_type')
        if grading in {'automated','hybrid'} and not checks.strip():error('sections.Automated Checks','请添加自动检查或声明式规则')
        criteria=body.get('criteria',[])
        if criteria:
            keys=[r.get('key') for r in criteria]
            if len(set(keys))!=len(keys) or any(not isinstance(k,str) or not IDENTIFIER.fullmatch(k) for k in keys):raise ValueError('评分项编号无效或重复')
            weights=[float(r['weight']) for r in criteria]
            if any(not math.isfinite(w) or w<=0 for w in weights) or abs(sum(weights)-1)>1e-6:raise ValueError('评分项权重必须为正数，合计 1')
            for r in criteria:
                for anchor in r.get('anchors',[]):
                    score=anchor['score']
                    if type(score) not in (int,float) or not 0<=score<=1:raise ValueError('分值锚点必须在 0–1 内')
        if grading in {'hybrid','llm_judge'} and not rubric(body).strip():error('criteria','请填写语义评分标准')
        weights=meta.get('grading_weights') or ({'automated':1,'llm_judge':0} if grading=='automated' else {'automated':0,'llm_judge':1} if grading=='llm_judge' else {})
        if grading=='hybrid' and (set(weights)!= {'automated','llm_judge'} or abs(sum(weights.values())-1)>1e-6 or any(w<0 for w in weights.values())):error('metadata.grading_weights','混合评分需设置规则和语义权重，合计 1')
        validate_template(body.get('scoring',{}).get('template',{}))
        if scene and scene.get('base_contract') not in {'general','web','ppt'}:error('scene','场景基础契约不支持')
    except (ValueError,TypeError,KeyError) as exc:error('scoring',str(exc))
    return {'valid':not issues,'issues':issues,'source_sha256':sha(body)}
