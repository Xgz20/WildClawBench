"""Expose native read-only formula results to the original data-only reader."""
import hashlib,json,sys
from pathlib import Path

TASK='03_Data_Analysis_task_007_promotion_discounts_sales_margin'
CONTRACT='d9dc7cbb2f558326a419ccc40318761b83f50e45b8c91fec3e97077562cd336b'
SOURCE='b0e0cabf28c9edba2e8ac6eee88f8b8b0f528fa75cbab843c8ab98a8b1962a88'
DATASET={'id':'general-custom70-v6','digest':'20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'}
PROFILE='promotion-readonly-native-formula-values/v1'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def probe_lock():
    root=Path(sys.executable).absolute().parent.parent;pointer=root/'general-e2e-native-calc-values.json'
    if not pointer.is_file():return None
    import native_calc_values
    p=json.loads(pointer.read_text(encoding='utf-8'));validation=Path(p['validation'])
    if validation.is_symlink() or not validation.resolve().is_relative_to(root.resolve()):raise ValueError('PROMOTION_CALC_VALIDATION_PATH')
    v=json.loads(validation.read_text(encoding='utf-8'));config=Path(v['writer_configuration'])
    _,assets=native_calc_values.assets(config)
    if (p.get('schema_version')!='general-e2e-native-calc-values-runtime/v1'
        or p.get('validation_sha256')!=sha(validation) or p.get('assets')!=assets
        or v.get('status')!='PASS' or v.get('profile')!=native_calc_values.PROFILE
        or v.get('synthetic_only') is not True or v.get('more_than_64_cells_validated') is not True
        or v.get('numeric_zero_text_empty_and_error_distinguished') is not True or v.get('assets')!=assets):
        raise ValueError('PROMOTION_CALC_VALIDATION_DRIFT')
    invoker=Path(__file__).with_name('native_calc_values_file.py')
    return {'python':str(Path(sys.executable).absolute()),'python_sha256':sha(sys.executable),
        'helper':str(invoker.absolute()),'helper_sha256':sha(invoker),'assets':assets,
        'writer_configuration':str(config),'pointer_sha256':sha(pointer),'validation_sha256':sha(validation)}

def marker(contract,contract_sha,dataset,*,probe=None):
    if (contract.get('task_id')!=TASK or contract_sha!=CONTRACT or dataset!=DATASET
        or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=SOURCE):return None
    probe=probe_lock() if probe is None else probe
    if probe is None:return None
    core=Path(__file__).with_name('native_calc_values.py');java=core.with_name('native_calc')/'NativeCalcValues.java'
    invoker=Path(__file__).with_name('native_calc_values_file.py')
    if (set(probe)!={'python','python_sha256','helper','helper_sha256','assets','writer_configuration','pointer_sha256','validation_sha256'}
        or probe.get('helper_sha256')!=sha(invoker)
        or probe['assets'].get('helper_sha256')!=sha(core) or probe['assets'].get('java_source_sha256')!=sha(java)):
        raise ValueError('PROMOTION_CALC_PROFILE_LOCK_INVALID')
    return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE,'native_probe':probe}

BRIDGE=r'''
import subprocess as _pfv_subprocess
import tempfile as _pfv_tempfile
import shutil as _pfv_shutil
import zipfile as _pfv_zipfile
import hashlib as _pfv_hashlib
import math as _pfv_math
_pfv_original_load_workbook=load_workbook
def load_workbook(filename,*args,**kwargs):
    values=_pfv_original_load_workbook(filename,*args,**kwargs)
    if kwargs.get('data_only') is not True:return values
    path=Path(filename).resolve(strict=True)
    if path.name!='促销毛利分析.xlsx' or path.parent.name!='results':return values
    formulas=_pfv_original_load_workbook(path,read_only=True,data_only=False,keep_links=False)
    try:locations=[ws.title+'!'+cell.coordinate for ws in formulas for row in ws for cell in row if cell.data_type=='f']
    finally:formulas.close()
    missing=[location for location in locations if values[location.rsplit('!',1)[0]][location.rsplit('!',1)[1]].value is None]
    if not missing:return values
    lock=_PFV_NATIVE_PROBE
    for file,expected in [(lock['python'],lock['python_sha256']),
        (lock['helper'],lock['helper_sha256']),
        (lock['writer_configuration'],lock['assets']['writer_configuration_sha256'])]:
        if _pfv_hashlib.sha256(Path(file).read_bytes()).hexdigest()!=expected:raise GradingIndeterminate('Native formula evaluation asset drift')
    source_sha=_pfv_hashlib.sha256(path.read_bytes()).hexdigest()
    target=path.parent.parent/'评分证据'/'原生公式求值'
    if target.exists() or target.is_symlink():raise GradingIndeterminate('Native formula evidence collision')
    with _pfv_tempfile.TemporaryDirectory(prefix='ge2e_promotion_values_',ignore_cleanup_errors=True) as td:
        output=Path(td)/'probe';request=Path(td)/'locations.json'
        request.write_text(json.dumps(locations,ensure_ascii=False),encoding='utf-8')
        argv=[lock['python'],'-X','utf8',lock['helper'],'observe','--writer-configuration',
            lock['writer_configuration'],'--source',str(path),'--locations-json',str(request),'--output-root',str(output)]
        process=_pfv_subprocess.run(argv,capture_output=True,text=True,encoding='utf-8',timeout=960)
        if process.returncode:raise GradingIndeterminate('Native formula evaluation failed: '+process.stderr[-2000:])
        observed=json.loads(process.stdout)
        if (observed.get('status')!='PASS' or observed.get('profile')!='readonly-native-calc-bulk-values/v2'
            or observed.get('assets')!=lock['assets'] or observed.get('source_sha256')!=source_sha
            or observed.get('read_only') is not True or observed.get('saved') is not False
            or observed.get('source_unchanged') is not True or observed.get('disposable_copy_unchanged') is not True
            or observed.get('calculated_all') is not True or observed.get('residual_processes') is not False
            or observed.get('macro_execution')!='NEVER_EXECUTE' or observed.get('external_link_updates')!='NO_UPDATE'
            or observed.get('cell_count')!=len(locations)
            or _pfv_hashlib.sha256(path.read_bytes()).hexdigest()!=source_sha):
            raise GradingIndeterminate('Native formula evaluation binding invalid')
        mapping={}
        for page in observed['pages']:
            name=page['path']
            if not re.fullmatch(r'values-[0-9]{4}\.json',name):raise GradingIndeterminate('Native formula evidence path invalid')
            file=output/name
            if (file.is_symlink() or file.stat().st_size!=page['size']
                or _pfv_hashlib.sha256(file.read_bytes()).hexdigest()!=page['sha256']):raise GradingIndeterminate('Native formula evidence drift')
            payload=json.loads(file.read_text(encoding='utf-8'))
            if payload.get('profile')!=observed['profile'] or len(payload['rows'])!=page['cell_count']:
                raise GradingIndeterminate('Native formula page scope invalid')
            for location,kind,value,error in payload['rows']:
                if location in mapping:raise GradingIndeterminate('Native formula duplicate cell')
                if (kind=='number' and (type(value) not in (float,int) or not _pfv_math.isfinite(value) or error!=0)
                    or kind=='string' and (not isinstance(value,str) or error!=0)
                    or kind=='error' and (not isinstance(value,str) or type(error) is not int or error<=0)
                    or kind not in {'number','string','error'}):raise GradingIndeterminate('Native formula scalar invalid')
                mapping[location]=(kind,value,error)
        if set(mapping)!=set(locations):raise GradingIndeterminate('Native formula scope incomplete')
        target.mkdir(parents=True)
        with _pfv_zipfile.ZipFile(target/'native-raw.zip','x',compression=_pfv_zipfile.ZIP_DEFLATED) as archive:
            names=['observation.json','requested-locations.txt','native-values.jsonl','native.properties','compile.stdout','compile.stderr','server.stdout','server.stderr','java.stdout','java.stderr']+[p['path'] for p in observed['pages']]
            for name in names:
                archive.write(output/name,name)
        view={'role':'grader_generated_native_formula_view','source_file':'results/促销毛利分析.xlsx',
            'source_sha256':source_sha,'formula_cells_observed':len(locations),'missing_cache_cells_filled_in_memory':len(missing),
            'missing_cache_scope_sha256':_pfv_hashlib.sha256('\n'.join(sorted(missing)).encode()).hexdigest(),
            'existing_cached_values_replaced':False,'candidate_workbook_saved':False,'not_candidate_self_check':True,
            'native_raw_archive_sha256':_pfv_hashlib.sha256((target/'native-raw.zip').read_bytes()).hexdigest(),
            'native_observation':observed,
            'all_native_error_cells':[[location,entry[2],entry[1]] for location,entry in mapping.items() if entry[0]=='error'],
            'raw_storage':'native-raw.zip contains the complete original observation, pages, raw values, request and logs; nothing is truncated.'}
        (target/'内存视图说明.json').write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for location in missing:
        kind,value,error=mapping[location];sheet,address=location.rsplit('!',1)
        values[sheet][address]=value if kind!='error' else value or ('#NATIVE_CALC_ERROR['+str(error)+']')
    return values
'''

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('promotion_formula_value_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},
        manifest['digests']['contract_sha256'],manifest['dataset'],probe=frozen.get('native_probe'))
    if expected is None or frozen!=expected or hashlib.sha256(current.encode()).hexdigest()!=SOURCE:
        raise ValueError('PROMOTION_FORMULA_VALUE_PROFILE_MISMATCH')
    effective=current+'\n_PFV_NATIVE_PROBE='+repr(frozen['native_probe'])+'\n'+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'candidate_rewritten':False,
        'numeric_decisions_assigned':False,'rubric_and_weights_changed':False,
        'reason':'对缺缓存公式一次原生只读求值，完整区分数值、文本空串与真实错误，仅填充data_only内存视图；原工作簿/公式/图表不保存、不改写。原全部比较、检查点及权重不变，原生环境错误不转能力零分，求值不计候选自主验收。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
