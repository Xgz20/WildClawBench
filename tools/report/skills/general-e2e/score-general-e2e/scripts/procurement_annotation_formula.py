"""Keep native-confirmed annotation formula errors visible without inventing values."""
import hashlib,json
from pathlib import Path
import sys

TASK='02_Office_task_015_procurement_reconciliation'
CONTRACT='64ba6743b737870353efc5aebec923ae82f018b6d8bf36583709b142d5515a34'
SOURCE='7117b998478660abcb33c78c87074e0f0e89b496cfb7beb632e37a61432c979b'
BASE='249c58ced38141fe9a1070ec004f338804f7cf993f5d04b8c55a7edcfa5c2c7e'
DATASET={'id':'general-custom70-v6','digest':'20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'}
PROFILE='procurement-native-annotation-errors-and-quantity-total/v1'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def probe_lock():
    root=Path(sys.executable).absolute().parent.parent
    validation=root/'native-calc-v1/validation.json'
    if not validation.is_file():return None
    import native_calc_probe
    v=json.loads(validation.read_text(encoding='utf-8'))
    config=Path(v['writer_configuration']);_,assets=native_calc_probe.assets(config)
    if (v.get('status')!='PASS' or v.get('profile')!=native_calc_probe.PROFILE
            or v.get('synthetic_only') is not True or v.get('known_good_and_error_cells_distinguished') is not True
            or v.get('assets')!=assets):raise ValueError('PROCUREMENT_NATIVE_CALC_VALIDATION_DRIFT')
    return {'python':str(Path(sys.executable).absolute()),'python_sha256':sha(sys.executable),
            'helper':str(Path(native_calc_probe.__file__).absolute()),'helper_sha256':assets['helper_sha256'],
            'java_source_sha256':assets['java_source_sha256'],'writer_configuration':str(config),
            'writer_configuration_sha256':assets['writer_configuration_sha256'],'javac_sha256':assets['javac_sha256'],
            'validation_sha256':sha(validation)}

def marker(contract,contract_sha,dataset,*,probe=None):
    if (contract.get('task_id')!=TASK or contract_sha!=CONTRACT
            or {k:dataset.get(k) for k in DATASET}!=DATASET
            or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=SOURCE):return None
    probe=probe_lock() if probe is None else probe
    if probe is None:return None
    helper=Path(__file__).with_name('native_calc_probe.py');java=helper.with_name('native_calc')/'NativeCalcObserve.java'
    if (set(probe)!={'python','python_sha256','helper','helper_sha256','java_source_sha256','writer_configuration',
                     'writer_configuration_sha256','javac_sha256','validation_sha256'}
            or probe.get('helper_sha256')!=sha(helper) or probe.get('java_source_sha256')!=sha(java)):
        raise ValueError('PROCUREMENT_NATIVE_CALC_LOCK_INVALID')
    return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE,
            'base_effective_source_sha256':BASE,'native_probe':probe}

BRIDGE=r'''
import subprocess as _paf_subprocess
import tempfile as _paf_tempfile
import openpyxl as _paf_openpyxl
_paf_previous_scan=scan_workbook
_paf_native_annotations=[]
_paf_native_observation=None
def scan_workbook(path):
    global _paf_native_annotations,_paf_native_observation
    tables,unresolved=_paf_previous_scan(path)
    _paf_native_annotations=[];_paf_native_observation=None
    book=_paf_openpyxl.load_workbook(path,data_only=False,read_only=False,keep_links=False)
    selected=[]
    try:
        for table in tables:
            if table['kind']!='summary':continue
            sheet=book[table['sheet']]
            headings=[r for r in table['rows'] if tuple(r['values'])==('项目','数值','核对说明')]
            if len(headings)>1:raise EvaluationError('Ambiguous procurement annotation header')
            if not headings:continue
            start=headings[0]['row']
            for row in table['rows']:
                rn=row['row'];location=sheet.title+'!C'+str(rn)
                if rn<=start or location not in unresolved:continue
                value=sheet.cell(rn,2);annotation=sheet.cell(rn,3)
                if value.data_type!='n' or number(value.value) is None or annotation.data_type!='f':continue
                selected.append((table,row,location,annotation.value))
    finally:book.close()
    if selected:
        lock=_PAF_NATIVE_PROBE
        if (hashlib.sha256(Path(lock['helper']).read_bytes()).hexdigest()!=lock['helper_sha256']
                or hashlib.sha256(Path(lock['python']).read_bytes()).hexdigest()!=lock['python_sha256']
                or hashlib.sha256(Path(lock['writer_configuration']).read_bytes()).hexdigest()!=lock['writer_configuration_sha256']):
            raise EvaluationError('Native Calc observation helper drift')
        with _paf_tempfile.TemporaryDirectory(prefix='ge2e_calc_annotations_',ignore_cleanup_errors=True) as folder:
            output=Path(folder)/'probe'
            argv=[lock['python'],'-X','utf8',lock['helper'],'observe','--writer-configuration',
                  lock['writer_configuration'],'--source',str(path),'--output-root',str(output)]
            for _,_,location,_ in selected:argv+=['--cell',location]
            process=_paf_subprocess.run(argv,capture_output=True,text=True,encoding='utf-8',timeout=105)
            if process.returncode:raise EvaluationError('Native Calc annotation observation failed: '+process.stderr[-2000:])
            observed=json.loads(process.stdout)
            expected_assets={'helper_sha256':lock['helper_sha256'],'java_source_sha256':lock['java_source_sha256'],
                'writer_configuration_sha256':lock['writer_configuration_sha256'],'javac_sha256':lock['javac_sha256']}
            if (observed.get('status')!='PASS' or observed.get('profile')!='readonly-native-calc-cell-observation/v1'
                    or observed.get('assets')!=expected_assets or observed.get('read_only') is not True
                    or observed.get('macro_execution')!='NEVER_EXECUTE' or observed.get('external_link_updates')!='NO_UPDATE'
                    or observed.get('source_sha256')!=hashlib.sha256(Path(path).read_bytes()).hexdigest()
                    or observed.get('source_unchanged') is not True or observed.get('saved') is not False
                    or observed.get('residual_processes') is not False):
                raise EvaluationError('Native Calc annotation observation binding invalid')
            cells={c['location']:c for c in observed['cells']}
            if len(cells)!=len(selected) or set(cells)!={s[2] for s in selected}:
                raise EvaluationError('Native Calc annotation cell scope invalid')
            confirmed=set()
            for table,row,location,original in selected:
                cell=cells[location]
                if not isinstance(cell.get('error_code'),int) or cell['error_code']<=0:continue
                values=list(row['values'])
                while len(values)<3:values.append(None)
                values[2]=original;row['values']=values
                confirmed.add(location)
                _paf_native_annotations.append({'location':location,'original_data_type':'f',
                    'original_formula':original,'native_error':cell,'role':'grader_generated_after_execution',
                    'candidate_formula_corrected':False,'numeric_value_invented':False,
                    'interpretation':'Native-confirmed formula error in explicitly labelled annotation column; original Rubric still evaluates quality and process.'})
            _paf_native_observation=observed
            unresolved=[location for location in unresolved if location not in confirmed]
    return tables,unresolved

_paf_previous_view=_pl_matrix_view
def _pl_matrix_view(tables,records,metrics,numeric,truth,*args):
    converted,expected,locations,audit=_paf_previous_view(tables,records,metrics,numeric,truth,*args)
    ids={r['id'] for r in records['qty']};values={r['id']:number(r['values'].get('dq')) for r in records['qty']}
    quantity_total=(sum(values.values(),Decimal(0)) if ids==set(truth['qty']) and all(v is not None for v in values.values()) else None)
    for index,(source,view) in enumerate(zip(tables,converted)):
        if source['kind']!='summary' or source['sheet']!=view['sheet']:continue
        heads=[r for r in source['rows'] if tuple(r['values'])==('项目','数值','核对说明')]
        if len(heads)!=1:continue
        view={**view,'rows':[{**r,'values':list(r['values'])} for r in view['rows']]}
        converted[index]=view
        for row in view['rows']:
            vals=row['values']
            if (len(vals)!=3 or vals[0]!='数量差额合计' or number(vals[1]) is None
                    or re.sub(r'\s+','',str(vals[2]))!='=SUM(数量差异!数量差额)'):continue
            key='paf_quantity_delta_total';label='_paf/'+key
            SUMMARY_LABELS.setdefault(key,[]).append(label);expected[key]=quantity_total
            row['values']=[label,vals[1]]
            location=source['sheet']+'!B'+str(row['row'])
            locations[(source['sheet'],row['row'],label)]={'value_location':location,'extraction_profile':'literal-submitted-quantity-total/v1'}
            audit.append({'location':location,'key':key,'expected_unavailable':quantity_total is None,
                          'candidate_statement_synthesized':False,'scored_group':'original non-money summary group'})
    return converted,expected,locations,audit

_paf_previous_export=export_evidence
def export_evidence(root,status,tables,truth,metrics,diagnostics,unresolved,artifact):
    diagnostics=dict(diagnostics)
    diagnostics['native_formula_annotations']={'role':'grader_generated_after_execution',
        'cells':_paf_native_annotations,'native_observation':_paf_native_observation,
        'not_candidate_acceptance':True,'remaining_unresolved_formulas':unresolved,
        'candidate_bytes_rewritten':False,'automatic_formula_quality_score_assigned':False}
    return _paf_previous_export(root,status,tables,truth,metrics,diagnostics,unresolved,artifact)
'''

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('procurement_annotation_formula_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},
                    manifest['digests']['contract_sha256'],manifest['dataset'],probe=frozen.get('native_probe'))
    if expected is None or expected!=frozen or hashlib.sha256(current.encode()).hexdigest()!=BASE:
        raise ValueError('PROCUREMENT_ANNOTATION_PROFILE_MISMATCH')
    code=current+'\n_PAF_NATIVE_PROBE='+repr(frozen['native_probe'])+'\n'+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
             'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
             'effective_source_sha256':hashlib.sha256(code.encode()).hexdigest(),
             'candidate_rewritten':False,'numeric_decisions_assigned':False,'rubric_and_weights_changed':False,
             'reason':'仅将原生Calc确认错误且位于明确核对说明列的公式作为原始注释证据保全，不把它当有效计算或候选验收；其余未解析公式仍拒绝。对明确指向数量差异表数量差额之和的原数量合计，沿用原提交记录完整性与原非金额汇总比较、分母公式及80/20权重。真实公式错误留独立裁判按原Rubric评价。'}
    if prior:receipt['prior_correction']=prior
    return code,receipt
