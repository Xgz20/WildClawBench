import json
from pathlib import Path
def run(records,config=None):
    defaults=json.loads(Path('batchstamp/resources/defaults.json').read_text())
    cfg={**defaults,**(config or {})}
    cfg['min_amount']=cfg.get('min_amount') or cfg.pop('threshold',0)
    cfg['label']=cfg.get('label') or cfg.pop('prefix','default')
    rows=[r for r in records if r['amount']>=cfg['min_amount'] and (r['region'] is not None or cfg['include_null_region'])]
    return {'ids':sorted(r['id'] for r in rows),'total':sum(r['amount'] for r in rows)*cfg['scale'],'label':cfg['label'],
            'config':cfg,'banner':Path('batchstamp/resources/banner.txt').read_text().rstrip('\n')}
