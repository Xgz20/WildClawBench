#!/usr/bin/env python3
"""Relocate a verified final bundle into four stable Harness directories.

Frozen payload bytes are preserved. Generated indexes distinguish historical
scoring evidence from later supplements. Replay uses a disposable extraction of
the original archive, so obsolete controller directories are not dependencies.
"""
from pathlib import Path, PurePosixPath
import argparse, collections, contextlib, hashlib, html, json, os, shutil, stat, subprocess, sys, tempfile, time, zipfile
from urllib.parse import quote
from round_workspace import LABELS, SCHEMA, copy, extract_zip, load, relative, require, sha, write

ARCHIVE_SCHEMA='wildclawbench.general-e2e-archived-round/v1'

def write_index(root,tasks,report):
    def link(path,label):return '<a href="'+quote(path,safe='/')+'">'+html.escape(label)+'</a>' if path else '—'
    lines=['<!doctype html><meta charset="utf-8"><title>General E2E 最终归档</title>',
      '<style>body{font:14px/1.6 system-ui;margin:32px;color:#183044}table{border-collapse:collapse;width:100%}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:left}th{background:#edf3f8}a{margin-right:12px}small{display:block;color:#667}</style>',
      '<h1>General E2E 最终归档</h1><p>原评分证据与后来补采的轨迹分别保留。分数和执行身份保持原样。</p>',
      link('reports/final/'+report['artifact_filenames']['excel'],'Excel报告'),
      link('reports/final/通用场景端到端自动化评测报告.md','领导版报告'),
      '<table><tr><th>Harness</th><th>用例</th><th>分数</th><th>数据入口</th></tr>']
    for t in tasks:
        links=''.join(link(t.get(k),label) for k,label in [('candidate_workspace','产物'),('score_file','评分'),('as_scored_transcript','原评分轨迹'),('transcript','当前有效轨迹'),('rollout','rollout原件')])
        lines.append('<tr><td>'+html.escape(t['harness'])+'</td><td>'+html.escape(t['task_name'])+'<small>'+html.escape(t['task_id'])+'</small></td><td>'+format(t['score_100'],'.2f')+'</td><td>'+links+'</td></tr>')
    lines.append('</table>');(Path(root)/'INDEX.html').write_text('\n'.join(lines),encoding='utf-8')

def remove_replay_temp(path):
    """Only use for a disposable directory created by replay_workspace."""
    path=Path(path)
    for attempt in range(3):
        if not path.exists():return
        for base,dirs,files in os.walk(path,followlinks=False):
            os.chmod(base,stat.S_IMODE(os.stat(base).st_mode)|0o700)
            dirs[:]=[d for d in dirs if not Path(base,d).is_symlink()]
        try:shutil.rmtree(path);return
        except OSError:
            if attempt==2:raise
            time.sleep(0.1)

@contextlib.contextmanager
def replay_workspace(parent):
    path=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    try:yield path
    finally:remove_replay_temp(path)

def archive_inventory(archive):
    with zipfile.ZipFile(archive) as z:
        roots=[n for n in z.namelist() if n.count('/')==1 and n.endswith('/INTEGRITY.json')]
        require(len(roots)==1,'ARCHIVE_INTEGRITY_NOT_UNIQUE');prefix=roots[0].split('/')[0]+'/'
        doc=json.loads(z.read(roots[0]));entries=doc['entries'];names={e['path'] for e in entries}
        require(len(names)==len(entries),'ARCHIVE_DUPLICATE_MEMBER')
        actual=set()
        for i in z.infolist():
            require(i.filename.startswith(prefix),'ARCHIVE_ROOT');p=i.filename[len(prefix):].rstrip('/')
            if p:relative(p);require(p not in actual,'ARCHIVE_DUPLICATE_MEMBER');actual.add(p)
        require(actual==names|{'INTEGRITY.json'},'ARCHIVE_MEMBER_SET')
        links={e['path'] for e in entries if e['kind']=='symlink'}
        for e in entries:
            p=relative(e['path']);require(not any(x.as_posix() in links for x in p.parents),'ARCHIVE_SYMLINK_PARENT')
            info=z.getinfo(prefix+e['path']+('/' if e['kind']=='directory' else ''))
            kind='directory' if info.is_dir() else 'symlink' if stat.S_ISLNK(info.external_attr>>16) else 'file'
            require(kind==e['kind'],'ARCHIVE_TYPE')
            if e['kind']=='directory':continue
            info=z.getinfo(prefix+e['path']);require(info.file_size==e['size'],'ARCHIVE_SIZE')
            h=hashlib.sha256()
            with z.open(info) as f:
                for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
            require(h.hexdigest()==e['sha256'],'ARCHIVE_SHA:'+e['path'])
            if e['kind']=='symlink':
                target=z.read(info).decode('utf-8');require(target==e['link_target'] and not PurePosixPath(target).is_absolute() and '\\' not in target,'ARCHIVE_LINK')
                parts=list(p.parent.parts)
                for part in PurePosixPath(target).parts:
                    if part=='..':require(bool(parts),'ARCHIVE_LINK_ESCAPE');parts.pop()
                    elif part not in ('','.'):parts.append(part)
        return prefix,doc,json.loads(z.read(prefix+'TASK_INDEX.json'))['tasks'],json.loads(z.read(prefix+'Reports/general_e2e_report_data.json'))

def mapper(tasks):
    substitutions=[]
    for t in tasks:
        h=t['harness'];relative(h);tid=t['task_id'];relative(tid);sid=t['scoring_attempt_id'];relative(sid)
        substitutions += [(t['scoring_directory'],f'{h}/score/tasks/{tid}/attempts/{sid}'),
            (t['candidate_workspace'],f'{h}/execution/tasks/{tid}/workspace')]
        # The original execution trace is also reachable inside this case's
        # scoring directory, without mutating its original scoring attempt.
        ep=PurePosixPath(t['execution_record']).parent
        substitutions.append(((ep/'trace').as_posix(),f'{h}/score/tasks/{tid}/trace/as-executed'))
    substitutions.sort(key=lambda p:len(p[0]),reverse=True)
    def mapped(name):
        relative(name)
        if name.startswith('Reports/'):return 'reports/final/'+name[len('Reports/'):]
        p=PurePosixPath(name)
        if len(p.parts)>=5 and p.parts[:2]==('ResourceSupplements','supplements'):
            h=LABELS.get(p.parts[2]);require(h,'ARCHIVE_UNKNOWN_HARNESS');tid=p.parts[3]
            return '/'.join((h,'score','tasks',tid,'trace','supplemental',*p.parts[4:]))
        if name.startswith('ResourceSupplements/'):
            return '.general-e2e/resources/'+name[len('ResourceSupplements/'):]
        for src,dst in substitutions:
            if name==src or name.startswith(src+'/'):return dst+name[len(src):]
        if p.parts[0] in LABELS.values():
            h=p.parts[0]
            if len(p.parts)==1:return h
            if p.parts[1]=='unit' and len(p.parts)>=3 and p.parts[2]=='evidence':
                return '/'.join((h,'.general-e2e','evidence',*p.parts[3:]))
            return '/'.join((h,'.general-e2e','archive',*p.parts[1:]))
        return '.general-e2e/original-bundle/'+name
    return mapped

def import_final(archive,output_root,batch_root):
    archive=Path(archive).resolve();out=Path(output_root).resolve();batch=Path(batch_root).resolve()
    require(not out.exists(),'ARCHIVED_ROUND_EXISTS')
    prefix,inventory,tasks,report=archive_inventory(archive);map_path=mapper(tasks)
    require(sha(batch/'manifest.json')==report['lineage']['batch_manifest_sha256'],'ARCHIVE_BATCH_BINDING')
    require(sha(batch/'report-config.json')==report['lineage']['report_config_sha256'],'ARCHIVE_REPORT_CONFIG_BINDING')
    out.mkdir(parents=True);mapped=[];written=set()
    try:
        with zipfile.ZipFile(archive) as z:
            for e in inventory['entries']:
                if e['kind']=='directory':
                    (out/map_path(e['path'])).mkdir(parents=True,exist_ok=True)
                    continue
                name=map_path(e['path']);require(name not in written,'ARCHIVE_MAPPING_COLLISION');written.add(name)
                p=out/name;p.parent.mkdir(parents=True,exist_ok=True)
                if e['kind']=='symlink':p.symlink_to(e['link_target'])
                else:
                    with z.open(prefix+e['path']) as a,p.open('xb') as b:shutil.copyfileobj(a,b,4*1024*1024)
                    p.chmod((z.getinfo(prefix+e['path']).external_attr>>16)&0o777 or 0o644)
                mapped.append({**e,'original_path':e['path'],'path':name})
            # Preserve the original integrity document as evidence, unchanged.
            p=out/'.general-e2e/original-bundle/INTEGRITY.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(prefix+'INTEGRITY.json'))
        for name in ('manifest.json','report-config.json','release-catalog.json'):
            if (batch/name).is_file():copy(batch/name,out/'.general-e2e/frozen-batch'/name)
        new_tasks=[]
        path_fields=['execution_record','score_file','scoring_directory','score_audit','grading_contract','candidate_workspace','transcript','trace_index','raw_trace_directory','resource_metrics','resource_supplement','rollout','original_transcript','original_trace_index']
        for t in tasks:
            row=dict(t)
            for field in path_fields:
                if row.get(field):row[field]=map_path(row[field])
            row['raw_trace_files']=[map_path(p) for p in row['raw_trace_files']]
            attempt=out/row['scoring_directory'];m=load(attempt/'attempt-manifest.json');tr=m['paths'].get('transcript')
            row['as_scored_transcript']=(PurePosixPath(row['scoring_directory'])/tr).as_posix() if tr else None
            base=out/row['harness']/'score/tasks'/row['task_id'];base.mkdir(parents=True,exist_ok=True)
            (base/'current').symlink_to('attempts/'+row['scoring_attempt_id'],target_is_directory=True)
            (base/'workspace').symlink_to('current/candidate-original/workspace',target_is_directory=True)
            (base/'private-scoring').symlink_to('current/private',target_is_directory=True)
            if tr:
                (base/'trace').mkdir(exist_ok=True)
                (base/'trace/as-scored.jsonl').symlink_to(os.path.relpath(attempt/tr,base/'trace'))
            write(base/'evidence-selection.json',{'schema_version':'wildclawbench.case-evidence-selection/v1','execution_attempt_id':row['execution_attempt_id'],
                'scoring_attempt_id':row['scoring_attempt_id'],'original_scoring_transcript':os.path.relpath(out/row['as_scored_transcript'],base) if tr else None,
                'current_effective_transcript':os.path.relpath(out/row['transcript'],base) if row.get('transcript') else None,
                'rollout':os.path.relpath(out/row['rollout'],base) if row.get('rollout') else None,
                'supplements_used_for_original_scoring':False,'original_attempt_unchanged':True})
            (base/'README.md').write_text('# 单题评分归档\n\n`current/` 是原评分 attempt，原文件字节未改。`trace/as-executed/` 为执行归档；`trace/supplemental/` 为后补证据，不代表原裁判使用过。完整路径与SHA由本轮索引保存。\n')
            candidate=attempt/'candidate-original'
            for q in [candidate,*candidate.rglob('*')]:
                if not q.is_symlink():q.chmod(stat.S_IMODE(q.stat().st_mode)&~0o222)
            new_tasks.append(row)
        archive_target=out/'deliverables'/archive.name;copy(archive,archive_target)
        shutil.copy2(str(archive)+'.sha256',str(archive_target)+'.sha256') if Path(str(archive)+'.sha256').exists() else None
        write(out/'TASK_INDEX.json',{'schema_version':1,'kind':'archived-round','tasks':new_tasks})
        write_index(out,new_tasks,report)
        source_map_path=out/'.general-e2e/resources/SOURCE_MAP.json'
        if source_map_path.is_file():
            source_map=load(source_map_path)
            for entry in source_map['sources'].values():entry['archive_path']=map_path(entry['archive_path'])
            write(out/'.general-e2e/source-map-relocated.json',source_map)
        units=[{'harness':h,'directory':label,'task_ids':[t['task_id'] for t in new_tasks if t['harness']==label]} for h,label in LABELS.items()]
        units=[u for u in units if u['task_ids']]
        doc={'schema_version':ARCHIVE_SCHEMA,'kind':'archived','candidate_permission_policy':'restore-read-only-without-changing-bytes','source_archive':str(archive_target.relative_to(out)),
             'source_archive_sha256':sha(archive),'source_report_sha256':sha(out/'reports/final/general_e2e_report_data.json'),
             'batch_id':report['batch_id'],'units':units,'files':mapped,'task_index_sha256':sha(out/'TASK_INDEX.json')}
        write(out/'.general-e2e/round.json',doc)
        write(out/'.general-e2e/path-mapping.json',{'old_archive_root':prefix.rstrip('/'),'mapping':{r['original_path']:r['path'] for r in mapped}})
        rows=['# General E2E 最终结果',f"\n评测批次：{report['batch_id']}。",'','四个 Harness 目录分别提供 execution/tasks 和 score/tasks。当前为已完成评测的归档视图，禁止作为新执行队列恢复。','','- 最终报告：`reports/final/`','- 研发ZIP：`deliverables/'+archive.name+'`','- 单题索引：`TASK_INDEX.json`','- 评分使用的轨迹见每题 evidence-selection.json；后补轨迹不冒充当时评分输入。','']
        (out/'README.md').write_text('\n'.join(rows))
        return verify_round(out)
    except BaseException:
        # Keep a failed import for audit; it must never be published or cleaned
        # as a successful final round.
        raise

def verify_round(root):
    root=Path(root).resolve();doc=load(root/'.general-e2e/round.json');require(doc['schema_version']==ARCHIVE_SCHEMA,'ARCHIVED_ROUND_SCHEMA')
    require(sha(root/doc['source_archive'])==doc['source_archive_sha256'],'ARCHIVED_ZIP_DRIFT')
    require(sha(root/'TASK_INDEX.json')==doc['task_index_sha256'],'ARCHIVED_INDEX_DRIFT')
    restored=[]
    if doc.get('frozen_member_restoration'):
        ref=doc['frozen_member_restoration'];p=root/relative(ref['path'])
        require(sha(p)==ref['sha256'],'ARCHIVED_RESTORATION_RECEIPT_DRIFT')
        restored=load(p)['restored']
    for e in [*doc['files'],*restored]:
        p=root/relative(e['path']);require(p.resolve().is_relative_to(root),'ARCHIVED_PATH_ESCAPE')
        if e['kind']=='directory':require(p.is_dir() and not p.is_symlink(),'ARCHIVED_DIRECTORY_DRIFT');continue
        if e['kind']=='symlink':require(p.is_symlink() and os.readlink(p)==e['link_target'],'ARCHIVED_LINK_DRIFT')
        else:require(p.is_file() and not p.is_symlink() and p.stat().st_size==e['size'] and sha(p)==e['sha256'],'ARCHIVED_FILE_DRIFT:'+e['path'])
    tasks=load(root/'TASK_INDEX.json')['tasks'];require(len({(r['harness'],r['task_id']) for r in tasks})==len(tasks),'ARCHIVED_TASK_DUPLICATE')
    for t in tasks:
        ex=load(root/t['execution_record']);score=load(root/t['score_file'])
        require(ex['identity']['attempt_id']==t['execution_attempt_id']==score['execution']['attempt_id'],'ARCHIVED_EXECUTION_IDENTITY')
        require(sha(root/t['execution_record'])==t['execution_record_sha256']==score['execution']['record_sha256'],'ARCHIVED_EXECUTION_SHA')
        require(sha(root/t['score_file'])==t['score_sha256'] and score['result']['total_score']==t['score_0_1'],'ARCHIVED_SCORE_SHA')
        for field in ('candidate_workspace','scoring_directory','transcript','trace_index','rollout','as_scored_transcript'):
            if t.get(field):require((root/t[field]).exists(),'ARCHIVED_TASK_PATH_MISSING')
    return {'status':'PASS','root':str(root),'units':len(doc['units']),'selected_runs':len(tasks),
            'files_verified':len(doc['files']),'standard_transcripts':sum(bool(t.get('transcript')) for t in tasks),
            'original_scoring_transcripts':sum(bool(t.get('as_scored_transcript')) for t in tasks),'rollouts':sum(bool(t.get('rollout')) for t in tasks)}

def replay(root,report_skill,node):
    root=Path(root).resolve();doc=load(root/'.general-e2e/round.json');verify_round(root)
    work=root/'.general-e2e/replay';work.mkdir(exist_ok=True)
    with replay_workspace(work) as temp:
        temp=Path(temp);extracted=temp/'unpacked';original=extract_zip(root/doc['source_archive'],extracted)
        batch=temp/'batch';batch.mkdir()
        for p in (root/'.general-e2e/frozen-batch').iterdir():copy(p,batch/p.name)
        sources=load(original/'Reports/developer-source-index.json');selection=load(original/'Reports/developer-task-index.json');old_targets={uid:Path(v['target']) for uid,v in sources['imports'].items()}
        for uid,row in sources['imports'].items():
            row['original_target']=row['target'];h=next(t['harness'] for t in load(original/'TASK_INDEX.json')['tasks'] if t['unit_id']==uid);row['target']=str(original/h)
        for row in selection['selected_tasks']:
            for k in ('execution_record','score_file'):
                if row.get(k):row[k]=str(Path(sources['imports'][row['unit_id']]['target'])/Path(row[k]).relative_to(old_targets[row['unit_id']]))
        write(temp/'sources.json',sources);selection['source_index_sha256']=sha(temp/'sources.json');write(temp/'tasks.json',selection)
        resource=original/'ResourceSupplements'
        if resource.is_dir():
            sm=load(resource/'supplement-manifest.json');sm['source_execution_selection_sha256']=sha(temp/'tasks.json');write(resource/'supplement-manifest.json',sm)
            if (resource/'SOURCE_MAP.json').is_file():
                mapping=load(resource/'SOURCE_MAP.json')
                for entry in mapping['sources'].values():entry['archive_path']=(original.relative_to(temp)/entry['archive_path']).as_posix()
                write(resource/'SOURCE_MAP.json',mapping)
        prior=load(original/'Reports/general_e2e_report_data.json');write(temp/'display.json',prior.get('display_overrides',{}))
        command=[sys.executable,str(Path(report_skill)/'scripts/selected_report.py'),'--workspace-root',str(temp),'--batch-root',str(batch),
            '--source-index',str(temp/'sources.json'),'--task-index',str(temp/'tasks.json'),
            '--display-config',str(temp/'display.json'),'--node',str(node),'--data-output',str(temp/'replayed.json')]
        if resource.is_dir():command+=['--resource-root',str(resource)]
        p=subprocess.run(command,capture_output=True,text=True);require(p.returncode==0,'ARCHIVED_REPORT_REPLAY_FAILED:'+p.stderr[-2000:])
        result=load(temp/'replayed.json');old={r['run_id']:r for r in prior['tasks']};new={r['run_id']:r for r in result['tasks']};require(old.keys()==new.keys(),'ARCHIVED_REPLAY_SCOPE')
        for key,row in new.items():
            for field in ('execution_attempt_id','scoring_attempt_id','execution_status','score_status','total_score','human_assistance','resource'):
                require(row[field]==old[key][field],'ARCHIVED_REPLAY_DIFFERENCE:'+key+':'+field)
            require(row['tool_calls']['by_tool']==old[key]['tool_calls']['by_tool'],'ARCHIVED_REPLAY_TOOL_DIFFERENCE')
        return {'status':'PASS','selected_runs':len(new),'scores_resources_and_attempts_identical':True,'live_controller_dependencies':False}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('import-final');a.add_argument('--archive',type=Path,required=True);a.add_argument('--output-root',type=Path,required=True);a.add_argument('--batch-root',type=Path,required=True)
    a=s.add_parser('verify');a.add_argument('--round-root',type=Path,default=Path.cwd())
    a=s.add_parser('replay');a.add_argument('--round-root',type=Path,default=Path.cwd());a.add_argument('--report-skill',type=Path,required=True);a.add_argument('--node',required=True)
    a=p.parse_args(argv);result=import_final(a.archive,a.output_root,a.batch_root) if a.command=='import-final' else verify_round(a.round_root) if a.command=='verify' else replay(a.round_root,a.report_skill,a.node)
    print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':main()
