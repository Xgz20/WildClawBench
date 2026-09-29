#!/usr/bin/env python3
"""Stable round/Harness layout for fresh execution and independent scoring.

This controller validates frozen ZIPs before installation. Framework repairs use
new task attempts inside the same unit; they never prepare another whole round.
"""
from pathlib import Path, PurePosixPath
import argparse, hashlib, importlib.util, json, os, shutil, stat, subprocess, sys, uuid, zipfile

SCHEMA='wildclawbench.general-e2e-round-workspace/v1'
LABELS={'astronstudio':'AstronStudio','workbuddy':'WorkBuddy','qwenwork':'QwenWork','doubaowork':'DoubaoWork'}
load=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))

def require(ok,code):
    if not ok:raise ValueError(code)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def relative(p):
    require(isinstance(p,str) and p and '\\' not in p and '\0' not in p,'ROUND_PATH_INVALID')
    q=PurePosixPath(p);require(q.parts and not q.is_absolute() and not any(x in ('.','..') for x in q.parts),'ROUND_PATH_INVALID');return q

def copy(src,dst):
    src,dst=Path(src),Path(dst);dst.parent.mkdir(parents=True,exist_ok=True)
    if sys.platform=='darwin':subprocess.run(['/bin/cp','-c',str(src),str(dst)],check=True,capture_output=True)
    else:shutil.copy2(src,dst)

def extract_zip(archive,destination,*,strip_root=False):
    """Validate the whole namespace before writing; preserve safe relative links."""
    destination=Path(destination);require(not destination.exists(),'ROUND_EXTRACT_EXISTS')
    with zipfile.ZipFile(archive) as z:
        entries=[];names=set();links=set();roots=set()
        for info in z.infolist():
            p=relative(info.filename.rstrip('/'));name=p.as_posix();require(name not in names,'ROUND_ZIP_DUPLICATE');names.add(name);roots.add(p.parts[0])
            mode=info.external_attr>>16;kind='directory' if info.is_dir() else 'symlink' if stat.S_ISLNK(mode) else 'file'
            require(stat.S_IFMT(mode) in (0,stat.S_IFREG,stat.S_IFDIR,stat.S_IFLNK),'ROUND_ZIP_TYPE')
            if kind=='symlink':links.add(name)
            entries.append((info,p,mode,kind))
        require(len(roots)==1,'ROUND_ZIP_ROOT')
        for info,p,mode,kind in entries:
            require(not any(parent.as_posix() in links for parent in p.parents),'ROUND_ZIP_SYMLINK_PARENT')
            if kind=='symlink':
                target=z.read(info).decode('utf-8');require(target and not PurePosixPath(target).is_absolute() and '\\' not in target,'ROUND_ZIP_LINK')
                resolved=[]
                for part in (*p.parent.parts,*PurePosixPath(target).parts):
                    if part=='..':require(len(resolved)>1,'ROUND_ZIP_LINK_ESCAPE');resolved.pop()
                    elif part not in ('','.'):resolved.append(part)
        destination.mkdir(parents=True)
        for info,p,mode,kind in entries:
            parts=p.parts[1:] if strip_root else p.parts
            if not parts:continue
            q=destination.joinpath(*parts);q.parent.mkdir(parents=True,exist_ok=True)
            if kind=='directory':q.mkdir(exist_ok=True)
            elif kind=='symlink':q.symlink_to(z.read(info).decode('utf-8'))
            else:
                with z.open(info) as a,q.open('xb') as b:shutil.copyfileobj(a,b,4*1024*1024)
                q.chmod(mode&0o777 or 0o644)
    return destination if strip_root else destination/next(iter(roots))

def install_unit(round_root,execution_package,prepare_skill):
    root=Path(round_root).resolve();archive=Path(execution_package).resolve()
    script=Path(prepare_skill).resolve()/'scripts/prepare_general_e2e_workspaces.py'
    spec=importlib.util.spec_from_file_location('round_prepare_package_verifier',script);prepare=importlib.util.module_from_spec(spec);sys.modules[spec.name]=prepare;spec.loader.exec_module(prepare)
    _,members=prepare._read_zip(archive,label='EXECUTION_PACKAGE',allow_symlinks=True)
    manifest=json.loads(members['manifest.json'].data)
    prepare._verify_execution_archive(archive,{'dataset':manifest['dataset'],'release':manifest['release']})
    label=LABELS.get(manifest['unit']['harness']['id'],manifest['unit_id']);relative(label)
    marker=root/'.general-e2e/round.json';doc=load(marker) if marker.exists() else {'schema_version':SCHEMA,'kind':'live','batch_id':manifest['batch_id'],'dataset':manifest['dataset'],'units':[]}
    require(doc['kind']=='live' and doc['batch_id']==manifest['batch_id'],'ROUND_BATCH_MISMATCH')
    require(not any(u['unit_id']==manifest['unit_id'] or u['directory']==label for u in doc['units']),'ROUND_UNIT_EXISTS')
    require(not os.path.lexists(root/label),'ROUND_OUTPUT_COLLISION')
    root.mkdir(parents=True,exist_ok=True);stage=root/'.general-e2e'/('install-'+uuid.uuid4().hex)
    extract_zip(archive,stage,strip_root=True)
    cache=root/'.general-e2e/packages'/label;require(not cache.exists(),'ROUND_PACKAGE_COLLISION');copy(archive,cache/'execution.zip')
    row={'unit_id':manifest['unit_id'],'harness':manifest['unit']['harness']['id'],'directory':label,'task_ids':manifest['task_ids'],
         'execution_package':str((cache/'execution.zip').relative_to(root)),'execution_sha256':sha(archive)}
    write(stage/'.general-e2e/round-unit.json',{'schema_version':SCHEMA,'batch_id':doc['batch_id'],**row})
    (stage/'score/tasks').mkdir(parents=True,exist_ok=True);stage.rename(root/label)
    doc['units'].append(row);write(marker,doc)
    return {'status':'PASS','round_root':str(root),'unit_root':str(root/label),'private_scoring_installed':False}

def init_round(round_root,batch_root,prepare_skill):
    root=Path(round_root).resolve();batch=Path(batch_root).resolve();skill=Path(prepare_skill).resolve()
    require(not (root/'.general-e2e/round.json').exists(),'ROUND_ALREADY_INITIALIZED')
    script=skill/'scripts/prepare_general_e2e_workspaces.py'
    run=subprocess.run([sys.executable,str(script),'verify-batch','--batch-root',str(batch)],capture_output=True,text=True)
    require(run.returncode==0,'ROUND_FROZEN_BATCH_INVALID:'+run.stderr[-1000:])
    manifest=load(batch/'manifest.json');stage=root.with_name('.'+root.name+'.staging-'+uuid.uuid4().hex);stage.mkdir(parents=True)
    try:
        copy(batch/'manifest.json',stage/'.general-e2e/batch/manifest.json')
        copy(batch/'report-config.json',stage/'.general-e2e/batch/report-config.json')
        units=[];seen=set()
        for unit in manifest['units']:
            label=LABELS.get(unit['harness']['id'],unit['unit_id']);relative(label);require(label not in seen,'ROUND_UNIT_LABEL_COLLISION');seen.add(label)
            uid=unit['unit_id'];prefix=manifest['batch_id']+'__'+uid
            matches=list(batch.rglob(prefix+'__execution.zip'));scores=list(batch.rglob(prefix+'__scoring.zip'))
            require(len(matches)==len(scores)==1,'ROUND_PACKAGE_AMBIGUOUS')
            archive=matches[0];scoring=scores[0];destination=stage/label
            extract_zip(archive,destination,strip_root=True)
            um=load(destination/'manifest.json');require(um['batch_id']==manifest['batch_id'] and um['unit_id']==uid,'ROUND_UNIT_IDENTITY')
            cache=stage/'.general-e2e/packages'/label;copy(archive,cache/'execution.zip');copy(scoring,cache/'scoring.zip')
            row={'unit_id':uid,'harness':unit['harness']['id'],'directory':label,
                 'execution_package':str((cache/'execution.zip').relative_to(stage)),
                 'scoring_package':str((cache/'scoring.zip').relative_to(stage)),
                 'execution_sha256':sha(archive),'scoring_sha256':sha(scoring),'task_ids':um['task_ids']}
            write(destination/'.general-e2e/round-unit.json',{'schema_version':SCHEMA,'batch_id':manifest['batch_id'],**row})
            (destination/'score/tasks').mkdir(parents=True,exist_ok=True);units.append(row)
        document={'schema_version':SCHEMA,'kind':'live','batch_id':manifest['batch_id'],'batch_manifest_sha256':sha(batch/'manifest.json'),
                  'report_config_sha256':sha(batch/'report-config.json'),'units':units}
        write(stage/'.general-e2e/round.json',document)
        for name in ('reports','deliverables'):(stage/name).mkdir()
        (stage/'README.md').write_text('# General E2E\n\n每个 Harness 使用 execution/tasks 和 score/tasks；队列、回执和修复记录保存在 .general-e2e。\n评分材料只在执行正式收口后由 prepare-score 消费。\n')
        # The control conversation can already contain received ZIPs and notes.
        # Publish only owned paths, never replace the user's project directory.
        for name in [u['directory'] for u in units]+['reports','deliverables']:
            require(not os.path.lexists(root/name),'ROUND_OUTPUT_COLLISION:'+name)
        for p in (stage/'.general-e2e').iterdir():
            require(not os.path.lexists(root/'.general-e2e'/p.name),'ROUND_CONTROL_COLLISION:'+p.name)
        root.mkdir(parents=True,exist_ok=True);(root/'.general-e2e').mkdir(exist_ok=True)
        for p in list(stage.iterdir()):
            if p.name=='.general-e2e':
                for q in list(p.iterdir()):q.rename(root/'.general-e2e'/q.name)
            elif p.name=='README.md' and (root/'README.md').exists():p.rename(root/'.general-e2e/README.md')
            else:p.rename(root/p.name)
        shutil.rmtree(stage)
        return {'status':'PASS','round_root':str(root),'units':units}
    except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def prepare_score(round_root,harness,skill_root,orchestration_id,task_ids=(),scoring_package=None,report_config=None):
    root=Path(round_root).resolve();doc=load(root/'.general-e2e/round.json');require(doc['kind']=='live','ROUND_HISTORY_NOT_EXECUTABLE')
    rows=[u for u in doc['units'] if harness in (u['harness'],u['directory'],u['unit_id'])];require(len(rows)==1,'ROUND_UNIT_NOT_UNIQUE');u=rows[0]
    unit=root/u['directory']
    if scoring_package:
        scoring=Path(scoring_package).resolve()
        if u.get('scoring_sha256'):require(sha(scoring)==u['scoring_sha256'],'ROUND_SCORING_PACKAGE_DRIFT')
    else:
        require(u.get('scoring_package'),'ROUND_SCORING_PACKAGE_REQUIRED');scoring=root/u['scoring_package']
        require(sha(scoring)==u['scoring_sha256'],'ROUND_SCORING_PACKAGE_DRIFT')
    config=Path(report_config).resolve() if report_config else root/'.general-e2e/batch/report-config.json'
    require(config.is_file(),'ROUND_REPORT_CONFIG_REQUIRED')
    if doc.get('report_config_sha256'):require(sha(config)==doc['report_config_sha256'],'ROUND_CONFIG_DRIFT')
    script=Path(skill_root)/'orchestrate-general-e2e/scripts/orchestrate_general_e2e.py'
    command=[sys.executable,str(script),'init','--unit-root',str(unit),'--scoring-package',str(scoring),
        '--report-config',str(config),'--score-skill-dir',str(Path(skill_root)/'score-general-e2e'),
        '--output-root',str(unit/'score/.orchestrations'),'--orchestration-id',orchestration_id,'--score-slots','3']
    for task in task_ids:command+=['--task-id',task]
    result=subprocess.run(command,capture_output=True,text=True);require(result.returncode==0,'ROUND_SCORING_HANDOFF_FAILED:'+result.stderr[-2000:])
    if not doc.get('report_config_sha256'):
        copy(config,root/'.general-e2e/batch/report-config.json');doc['report_config_sha256']=sha(config)
    if not u.get('scoring_package'):
        target=root/'.general-e2e/packages'/u['directory']/'scoring.zip';copy(scoring,target)
        u['scoring_package']=str(target.relative_to(root));u['scoring_sha256']=sha(target)
    write(root/'.general-e2e/round.json',doc)
    orch=unit/'score/.orchestrations'/orchestration_id;state=load(orch/'orchestration-state.json')
    for task in state['tasks']:
        if not task.get('attempt_path'):continue
        path=orch/task['attempt_path'];tid=task['task_id'];sid=task['scoring_attempt_id']
        target=unit/'score/tasks'/tid/'attempts'/sid;require(not os.path.lexists(target),'ROUND_SCORE_ALIAS_EXISTS');target.parent.mkdir(parents=True,exist_ok=True)
        target.symlink_to(os.path.relpath(path,target.parent),target_is_directory=True)
        current=target.parent.parent/'current'
        if not os.path.lexists(current):current.symlink_to('attempts/'+sid,target_is_directory=True)
        for name,ref in [('workspace','current/runtime/workspace'),('private-scoring','current/private'),('trace','current/trace')]:
            alias=current.parent/name
            if not os.path.lexists(alias):alias.symlink_to(ref,target_is_directory=True)
    return {'status':'PASS','orchestration_root':str(orch),'task_root':str(unit/'score/tasks'),'result':json.loads(result.stdout)}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('init');s.add_argument('--round-root',type=Path,default=Path.cwd(),help='Default: control conversation project cwd');s.add_argument('--batch-root',type=Path,required=True);s.add_argument('--prepare-skill',type=Path,required=True)
    s=sub.add_parser('install-unit');s.add_argument('--round-root',type=Path,default=Path.cwd());s.add_argument('--execution-package',type=Path,required=True);s.add_argument('--prepare-skill',type=Path,required=True)
    s=sub.add_parser('prepare-score');s.add_argument('--round-root',type=Path,default=Path.cwd());s.add_argument('--harness',required=True);s.add_argument('--skill-root',type=Path,required=True);s.add_argument('--orchestration-id',required=True);s.add_argument('--task-id',action='append',default=[]);s.add_argument('--scoring-package',type=Path);s.add_argument('--report-config',type=Path)
    a=p.parse_args(argv)
    result=init_round(a.round_root,a.batch_root,a.prepare_skill) if a.command=='init' else install_unit(a.round_root,a.execution_package,a.prepare_skill) if a.command=='install-unit' else prepare_score(a.round_root,a.harness,a.skill_root,a.orchestration_id,a.task_id,a.scoring_package,a.report_config)
    print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':main()
