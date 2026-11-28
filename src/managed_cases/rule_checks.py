"""Fixed declarative operations run inside the isolated grading container."""
import json
from pathlib import Path


def grade_rules(rules, arguments):
    root=Path(arguments.get('workspace_path') or '/tmp_workspace').resolve()
    scores={}
    for row in rules:
        source=root/row['path']
        try:
            if source.is_symlink() or not source.resolve().is_relative_to(root):raise ValueError()
            if row['kind']=='exists':value=source.is_file()
            elif row['kind']=='text_contains':value=str(row['value']) in source.read_text(encoding='utf-8-sig')
            else:
                value=json.loads(source.read_text(encoding='utf-8-sig'))
                for part in row.get('pointer','').strip('/').split('/') if row.get('pointer') else []:
                    value=value[int(part)] if isinstance(value,list) else value[part]
                value=value==row['value']
        except (OSError,ValueError,KeyError,IndexError,TypeError):value=False
        scores[row['key']]=float(bool(value))
    scores['overall_score']=sum(scores.values())/len(scores) if scores else 0.0
    return scores
