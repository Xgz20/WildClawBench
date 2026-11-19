"""Trusted actual replay in private copies, with candidate SHA and run receipts."""
from pathlib import Path
import hashlib,json,os,runpy,shutil,signal,subprocess,sys,time

def probe(root,expected,protected):
    io=runpy.run_path(str(root/'gt/native_io.py'));evidence_text=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not evidence_text:raise RuntimeError('H038_RULE_EVIDENCE_CONTEXT_UNAVAILABLE')
    evidence=Path(evidence_text).resolve()
    if not evidence.is_dir() or evidence.is_symlink():raise RuntimeError('H038_RULE_EVIDENCE_CONTEXT_INVALID')
    if os.name!='posix':raise RuntimeError('H038_RESTRICTED_PYTHON_PROFILE_UNAVAILABLE')
    runner=root/'gt/restricted_runner.py'
    if not runner.is_file():raise RuntimeError('H038_TRUSTED_RUNNER_UNAVAILABLE')
    out=evidence/('h038-recovery-probe-'+str(time.time_ns()));out.mkdir()
    before=io['tree'](root,True);binding={'algorithm':'h038.sha256-file-and-directory-map/v1','candidate_content_tree_sha256':io['tree_sha'](root,True),'candidate_files_before':before,'python_executable':sys.executable,'python_version':sys.version.split()[0],'runner_sha256':io['digest'](runner),'profile':'h038-python-audit/v1','profile_boundary':'Python audit restrictions, not OS security sandbox'}
    descriptor=root/'results/resume_entry.json';entry=None;args=[];parse_error=None
    try:
        if (root/'results').is_symlink() or not (root/'results').resolve().is_relative_to(root.resolve()) or descriptor.is_symlink():raise ValueError('unsafe results/descriptor')
        if any(p.is_symlink() for p in (root/'results').rglob('*')):raise ValueError('candidate results contains forbidden link; do not materialize it into private evidence')
        d=io['read_json'](descriptor)
        if not isinstance(d,dict) or d.get('api')!='h038-resume/v1' or d.get('language')!='python':raise ValueError('invalid entry descriptor')
        rel=d.get('script');args=d.get('args',[])
        if not isinstance(rel,str) or not rel.endswith('.py') or rel.startswith('/') or '\\' in rel or any(s in ('','..','.') for s in rel.split('/')):raise ValueError('script must be local Python')
        entry=root/'results'/rel
        if entry.is_symlink() or not entry.is_file() or not entry.resolve().is_relative_to((root/'results').resolve()):raise ValueError('entry script unavailable/unsafe')
        if not isinstance(args,list) or any(not isinstance(v,str) or '\0' in v for v in args):raise ValueError('bad fixed args')
        binding.update(descriptor_sha256=io['digest'](descriptor),entry_relative_path=rel,entry_sha256=io['digest'](entry),fixed_args=args)
    except (ValueError,UnicodeError,OSError,TypeError) as exc:parse_error={'type':type(exc).__name__,'message':str(exc)}
    (out/'candidate-binding.json').write_text(json.dumps(binding,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    records=[]
    def run(ws,case,iteration):
        logdir=out/case/f'run-{iteration}';logdir.mkdir(parents=True);request=logdir/'request.json';request.write_text(json.dumps({'workspace':str(ws),'script':str(ws/'results'/binding['entry_relative_path']),'args':args}));stdout=logdir/'stdout.log';stderr=logdir/'stderr.log';cmd=[sys.executable,'-I','-S',str(runner),str(request)];record={'command':cmd,'entry_sha256':binding['entry_sha256'],'actual_entry_sha256_before':io['digest'](ws/'results'/binding['entry_relative_path']),'candidate_content_tree_sha256':binding['candidate_content_tree_sha256'],'workspace':str(ws),'before_tree':io['tree'](ws),'timeout_seconds':4}
        with stdout.open('wb') as so,stderr.open('wb') as se:
            p=subprocess.Popen(cmd,cwd=ws,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC'},stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
            try:p.wait(timeout=4);record['timed_out']=False
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait();record['timed_out']=True
        current_entry=ws/'results'/binding['entry_relative_path'];current_descriptor=ws/'results/resume_entry.json'
        record.update(returncode=p.returncode,after_tree=io['tree'](ws),actual_entry_sha256_after=io['digest'](current_entry) if current_entry.is_file() and not current_entry.is_symlink() and current_entry.resolve().is_relative_to(ws.resolve()) else None,actual_descriptor_sha256_after=io['digest'](current_descriptor) if current_descriptor.is_file() and not current_descriptor.is_symlink() else None,stdout_sha256=io['digest'](stdout),stderr_sha256=io['digest'](stderr));(logdir/'receipt.json').write_text(json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)+'\n');return record
    if parse_error:records=[{'case':n,'status':'candidate_entry_unavailable','passed':False,'parse_error':parse_error} for n in ('final_replay','fresh_interruption','repair_replay')]
    else:
        for case in ('final_replay','fresh_interruption','repair_replay'):
            case_root=out/case;ws=case_root/'workspace';ws.mkdir(parents=True)
            for rel in protected:
                src=root/rel;dst=ws/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
            shutil.copytree(root/'results',ws/'results',symlinks=True)
            if case=='fresh_interruption':
                if (ws/'results/archive').is_symlink():(ws/'results/archive').unlink()
                else:shutil.rmtree(ws/'results/archive',ignore_errors=True)
                for name in ('manifest.tsv','recovery.json'):(ws/'results'/name).unlink(missing_ok=True)
            baseline=None
            try:baseline=io['semantic'](ws)
            except (ValueError,UnicodeError,OSError,TypeError,AttributeError):pass
            original_final_valid=io['validate_final'](ws,expected,protected)
            if case=='repair_replay':
                try:
                    rows=io['read_manifest'](ws/'results/manifest.tsv');target=io['path_value'](rows[0].get('archive_path'))
                    if target:(ws/'results'/target).write_bytes(b'Controlled probe corrupts completed copy; must repair.\n')
                    import csv
                    with (ws/'results/manifest.tsv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=io['COLS'],delimiter='\t');w.writeheader();w.writerows([{k:r.get(k,'') for k in io['COLS']} for r in rows]+[{k:rows[0].get(k,'') for k in io['COLS']}])
                except (ValueError,UnicodeError,OSError,TypeError,IndexError):pass
            rec={'case':case,'runs':[],'candidate_content_tree_sha256':binding['candidate_content_tree_sha256'],'entry_sha256':binding['entry_sha256'],'original_final_valid':original_final_valid,'unchanged_from_original_required':case=='final_replay' and original_final_valid};first_state=None;passed=True
            for iteration in (1,2):
                rr=run(ws,case,iteration);rec['runs'].append({'receipt':str((case_root/f'run-{iteration}/receipt.json').relative_to(out)),'returncode':rr['returncode'],'timed_out':rr['timed_out']})
                ok=rr['returncode']==0 and not rr['timed_out'] and rr['actual_entry_sha256_before']==binding['entry_sha256'] and rr['actual_entry_sha256_after']==binding['entry_sha256'] and rr['actual_descriptor_sha256_after']==binding['descriptor_sha256'] and io['validate_final'](ws,expected,protected)
                input_unchanged=all((ws/rel).is_file() and not(ws/rel).is_symlink() and io['digest'](ws/rel)==h for rel,h in protected.items());ok=ok and input_unchanged
                try:state=io['semantic'](ws)
                except (ValueError,UnicodeError,OSError,TypeError,AttributeError):state=None
                if case=='final_replay' and original_final_valid:ok=ok and baseline is not None and state==baseline
                if iteration==1:first_state=state
                else:ok=ok and state is not None and state==first_state
                passed=passed and ok
                if not ok:break
            rec.update(passed=passed,status='verified_actual_replay' if passed else 'candidate_recovery_failed',semantic_initial_sha256=hashlib.sha256(json.dumps(baseline,ensure_ascii=False,sort_keys=True).encode()).hexdigest() if baseline is not None else None,semantic_final_sha256=hashlib.sha256(json.dumps(first_state,ensure_ascii=False,sort_keys=True).encode()).hexdigest() if first_state is not None else None);records.append(rec)
    unchanged=before==io['tree'](root,True)
    if not unchanged:raise RuntimeError('H038_TRUSTED_PROBE_MUTATED_ORIGINAL_CANDIDATE')
    result={'schema':'h038.actual-recovery-probe/v1','binding':binding,'cases':records,'original_candidate_unchanged':unchanged,'score':sum(r['passed'] for r in records)/3,'scope':'actual restricted child-process entry calls; not static set comparison or self-report'};(out/'probe-result.json').write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n');return result
