"""Executed only inside a no-network, credential-free disposable container."""
import argparse
import json
import math
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--task',required=True);p.add_argument('--output',required=True)
a=p.parse_args();task=json.loads(Path(a.task).read_text());code=task.get('automated_checks','').strip()
if code.startswith('```'):code='\n'.join(code.splitlines()[1:-1])
namespace={'__name__':'managed_case_checker'}
exec(compile(code,'<user-check>','exec'),namespace)
if not callable(namespace.get('grade')):raise ValueError('检查代码必须提供 grade(**kwargs)')
result=namespace['grade'](workspace_path='/tmp_workspace')
if not isinstance(result,dict) or 'overall_score' not in result:raise ValueError('规则输出缺少 overall_score')
if any(type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1 for value in result.values()):raise ValueError('规则分数必须在 0–1 内')
Path(a.output).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
