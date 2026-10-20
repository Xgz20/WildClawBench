"""Observe a live same-unit automatic cycle; never sends, retries or edits stores."""
import argparse
import datetime
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from eval_memory_e2e.io import publish
from eval_memory_e2e.os_boundary import process_table


def observe(root, seconds):
    view=json.loads((root/'unit-view/scope.json').read_text())
    lease=json.loads((root/'lease/lease.json').read_text())
    identity=lease['launch']['identity']
    intent=json.loads((root/'ui-send-intent.json').read_text())
    cutoff=datetime.datetime.fromisoformat(intent['at'].replace('Z','+00:00')).timestamp()
    db=Path(view['paths']['overlay'])/'memories_1.sqlite'
    memory=Path(view['paths']['overlay'])/'memories'
    folder=root/'cycle-observations';folder.mkdir(mode=0o700)
    start=time.monotonic();previous=None;index=0
    while True:
        actor=process_table().get(identity['pid'])
        assert actor and all(actor[k]==identity[k] for k in ('pid','started_at','command')), 'Original Main exited/replaced; observation only'
        c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
        try:
            jobs=[dict(r) for r in c.execute('SELECT kind,job_key,status,worker_id,started_at,finished_at,lease_until,retry_at,retry_remaining,last_error,input_watermark,last_success_watermark FROM jobs')]
            outputs=[dict(r) for r in c.execute('SELECT * FROM stage1_outputs')]
        finally:c.close()
        files=[]
        if memory.is_dir():
            for file in sorted(memory.rglob('*')):
                if file.is_file() and not file.is_symlink():
                    files.append({'path':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'size':file.stat().st_size})
        snapshot={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'main_pid':identity['pid'],'jobs':jobs,'stage1_outputs':outputs,'files':files}
        signature=json.dumps({'jobs':jobs,'outputs':outputs,'files':files},sort_keys=True)
        if signature!=previous:
            index+=1;publish(folder/f'{index:04}.json',snapshot);previous=signature
            print(json.dumps({'snapshot':index,'stage1_outputs':len(outputs),'jobs':[(j['kind'],j['status']) for j in jobs]},ensure_ascii=False),flush=True)
        active=[j for j in jobs if j['status']=='running' or (j['lease_until'] or 0)>time.time()]
        global_job=next((j for j in jobs if j['kind']=='memory_consolidate_global'),None)
        if outputs and global_job and (global_job['started_at'] or 0)>=cutoff and global_job['status'] in ('done','error') and not active:
            result={'status':'CYCLE_COMPLETED' if global_job['status']=='done' else 'CYCLE_ERROR','snapshot':str(folder/f'{index:04}.json'),
                    'stage1_outputs':len(outputs),'ui_prompts_sent':1,'formal20_prompts':0}
            publish(root/'cycle-observer-result.json',result);print(json.dumps(result),flush=True);return
        if time.monotonic()-start>=seconds:
            result={'status':'OBSERVATION_WINDOW_EXPIRED','snapshot':str(folder/f'{index:04}.json'),'active_jobs':len(active),
                    'native_completion_unproven':True,'prompt_resend_authorized':False}
            publish(root/'cycle-observer-window-expired.json',result);print(json.dumps(result),flush=True);return
        time.sleep(5)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--seconds',type=int,default=600)
    args=p.parse_args();observe(args.root,args.seconds)
