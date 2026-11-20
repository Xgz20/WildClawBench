"""H005 deterministic values/structure; business interpretation stays semantic."""
import hashlib,json,math,os,re,runpy
from pathlib import Path
import pdfplumber

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(values):return sum(values)/len(values) if values else 0.0

def evaluate(root):
    root=Path(root).resolve();gt=root/'gt'
    truth=read(gt/'expected.json');contract=read(gt/'artifact_contract.json');oracle=read(gt/'business_oracle.json')
    boundary_spec=read(gt/'counterexamples.json');evidence=read(gt/'evidence_requirements.json');index=read(gt/'evidence_index.json')
    protected=read(gt/'protected_sha256.json')
    if len(truth['kpis'])!=12 or len(truth['additional_evidence_records'])!=10 or len(index['records'])<400:
        raise ValueError('H005 private GT incomplete')
    native=runpy.run_path(str(gt/'native_text.py'));office=runpy.run_path(str(gt/'office_runtime.py'));io=runpy.run_path(str(gt/'structured_io.py'))
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']);derived.mkdir(parents=True,exist_ok=True)
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    ledger_error=None
    try:ledger,ledger_meta=io['ledger'](root/contract['ledger'],contract)
    except (UnicodeError,ValueError) as exc:ledger,ledger_meta={},{'parseable':False,'complete':False};ledger_error=type(exc).__name__
    def project(path):
        if not path.is_file() or path.is_symlink():return None
        try:
            value=native['extract_native_text'](path,max_chars=2000000)
            if value['truncated']:raise RuntimeError('H005 native projection exceeds trusted limit')
            return value
        except native['NativeTextError'] as exc:
            if exc.code in {'NATIVE_TEXT_INVALID','NATIVE_TEXT_UNAVAILABLE'}:return None
            raise
    ppt=root/contract['pptx'];ppt_projection=project(ppt);records=io['unpack_records'](ppt_projection) if ppt_projection else []
    pages=io['slide_texts'](records);declared=next((x for x in records if x['locator']=='presentation'),{})
    notes_path=root/contract['notes'];notes_projection=project(notes_path)
    note_text='\n'.join(x.get('text','') for x in io['unpack_records'](notes_projection)) if notes_projection else ''
    ppt_values={};pdf_values={};pdf_pages={};pdf_info={};pdf_aging={};render_error=None
    for item in truth['kpis']:
        ppt_values.update(io['metric_values'](pages.get(item['slide'],''),[item]))
    content_errors={'OFFICE_INPUT_INVALID','OFFICE_EMBEDDED_SOURCE_INVALID','OFFICE_EMBEDDED_PART_INVALID','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}
    if ppt_projection:
        render_lock=read(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']))
        try:
            rendered=office['render_pptx_pdf'](ppt,render_lock,derived/'presentation')
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in content_errors:raise
            rendered=None;render_error=exc.code
        if rendered:
            all_chars=[];out_of_page=0;overlap_count=0
            with pdfplumber.open(rendered['path']) as document:
                for number,page in enumerate(document.pages,1):
                    pdf_pages[number]=page.extract_text() or ''
                    pdf_values.update(io['pdf_metric_values'](page,[item for item in truth['kpis'] if item['slide']==number]))
                    if number==7:pdf_aging=io['pdf_aging_values'](page)
                    chars=[char for char in page.dedupe_chars().chars if char['text'].strip()]
                    all_chars.extend(chars)
                    out_of_page+=sum(char['x0']<-.5 or char['x1']>page.width+.5 or char['top']<-.5 or char['bottom']>page.height+.5 for char in chars)
                    # Only strong conflicts between different glyphs count as
                    # automatic overlap. Full visual fit remains a Judge duty.
                    for left_index,left in enumerate(chars):
                        area=(left['x1']-left['x0'])*(left['bottom']-left['top'])
                        if area<=0:continue
                        for right in chars[left_index+1:]:
                            if left['text']==right['text']:continue
                            dx=max(0,min(left['x1'],right['x1'])-max(left['x0'],right['x0']))
                            dy=max(0,min(left['bottom'],right['bottom'])-max(left['top'],right['top']))
                            other=(right['x1']-right['x0'])*(right['bottom']-right['top'])
                            if min(area,other)>0 and dx*dy/min(area,other)>.8:overlap_count+=1
                font_min=min((char['size'] for char in all_chars),default=0)
                pdf_info={'page_count':len(document.pages),'min_font_pt':font_min,'out_of_page_glyphs':out_of_page,
                    'strong_overlapping_glyphs':overlap_count,'font_family_fraction':mean([float('heiti' in char['fontname'].lower()) for char in all_chars]),
                    'render_audit':rendered['audit']}
    note_values=io['metric_values'](note_text,truth['kpis'])
    # Shape creation order can differ from visual order. Use the actual PDF
    # anchor binding plus an editable source token to verify the same value.
    for item in truth['kpis']:
        identity=item['kpi_id'];value=pdf_values.get(identity)
        if re.search(item['kpi_id'],pages.get(item['slide'],''),re.I) and io['editable_value_present'](pages.get(item['slide'],''),value,item['unit']):
            ppt_values[identity]=value
    kpi_checks={}
    for item in truth['kpis']:
        identity=item['kpi_id'];row=ledger.get(identity,{})
        value=io['scalar'](row.get('value'),row.get('unit'),item['unit'])
        kpi_checks[identity]={'ledger':io['matches'](value,item['value'],contract['numeric_tolerance']),
            'pptx':io['matches'](ppt_values.get(identity),item['value'],contract['numeric_tolerance']),
            'rendered':io['matches'](pdf_values.get(identity),item['value'],contract['numeric_tolerance']),
            'notes':io['matches'](note_values.get(identity),item['value'],contract['numeric_tolerance'])}
    kpi_mean=mean([sum(fields[key]*weight for key,weight in oracle['per_kpi_weights'].items()) for fields in kpi_checks.values()])
    extras={item['kpi_id']:item for item in truth['additional_evidence_records']}
    extra_checks={}
    for identity,item in extras.items():
        row=ledger.get(identity,{})
        if identity.startswith('C'):
            try:
                actual=json.loads(row.get('value','null'));wanted=json.loads(item['value'])
                extra_checks[identity]=bool(isinstance(actual,list) and len(actual)==len(wanted) and all(type(x) in (float,int) and io['matches'](io['scalar'](x,row.get('unit'),item['unit']),y,contract['ratio_tolerance' if item['unit']=='ratio' else 'numeric_tolerance']) for x,y in zip(actual,wanted)))
            except (json.JSONDecodeError,TypeError,ValueError):extra_checks[identity]=False
        else:extra_checks[identity]=io['matches'](io['scalar'](row.get('value'),row.get('unit'),'万元'),item['value'],contract['numeric_tolerance'])
    groups=io['chart_groups'](records);chart_observations=[];chart_scores=[];editable_scores=[]
    office_lock=read(Path(os.environ['GENERAL_E2E_OFFICE_LOCK'])) if ppt_projection else None
    extracted={}
    for number,page in enumerate(contract['native_chart_pages'],1):
        expected_ids=[key for key,item in extras.items() if key.startswith('C') and item['slide']==page]
        candidates=[group for group in groups if group['page']==page]
        best={'score':0.0,'editable':0.0,'page':page,'series':[]}
        for group_index,group in enumerate(candidates):
            workbook_map={};errors=[]
            for part in group['workbook_parts']:
                if part not in extracted:
                    try:
                        item=office['extract_embedded_xlsx'](ppt,part,derived/f'embedded-{len(extracted)+1}'/'source')
                        result=office['recalculate_xlsx'](item['path'],office_lock,derived/f'embedded-{len(extracted)+1}'/'calculated')
                        extracted[part]={'values':io['workbook_values'](native['extract_native_text'](result['path'],max_chars=1000000)),
                                         'extraction':item['audit'],'calculation':result['audit']}
                    except office['OfficeRuntimeError'] as exc:
                        if exc.code not in content_errors:raise
                        extracted[part]={'error':exc.code}
                value=extracted[part]
                if 'values' in value:workbook_map[part]=value['values']
                else:errors.append(value['error'])
            matched=[];series_checks=[]
            for identity in expected_ids:
                desired=json.loads(extras[identity]['value']);tol=contract['ratio_tolerance' if extras[identity]['unit']=='ratio' else 'numeric_tolerance']
                choice=None
                for series_index,series in enumerate(group['series']):
                    if series_index in matched:continue
                    if len(series['values'])==len(desired) and all(io['matches'](io['scalar'](x,extras[identity]['unit'],extras[identity]['unit']),y,tol) for x,y in zip(series['values'],desired)):
                        choice=series_index;break
                check={'record_id':identity,'cache_correct':choice is not None,'category_count':False,'embedded_consistent':False}
                if choice is not None:
                    matched.append(choice);series=group['series'][choice]
                    check['category_count']=len(series['categories'])==len(desired)
                    addresses=io['formula_cells'](series['formula'])
                    if addresses and len(addresses)==len(desired):
                        check['embedded_consistent']=any(all(io['matches'](io['scalar'](values.get(cell),extras[identity]['unit'],extras[identity]['unit']),target,tol) for cell,target in zip(addresses,desired)) for values in workbook_map.values())
                series_checks.append(check)
            score=mean([.85*x['cache_correct']+.15*x['category_count'] for x in series_checks])
            editable=mean([float(x['embedded_consistent']) for x in series_checks])
            if (score,editable)>(best['score'],best['editable']):best={'page':page,'score':score,'editable':editable,'series':series_checks,'errors':errors}
        chart_observations.append(best);chart_scores.append(best['score']);editable_scores.append(best['editable'])
    chart_score=mean(chart_scores)
    aging_checks={key:io['matches'](pdf_aging.get(key),item['value'],contract['numeric_tolerance']) for key,item in extras.items() if key.startswith('A07')}
    aging_score=mean([.5*extra_checks[key]+.5*aging_checks[key] for key in aging_checks])
    business=oracle['business_weights']['kpi_mean']*kpi_mean+oracle['business_weights']['chart_values']*chart_score+oracle['business_weights']['aging_values']*aging_score
    mechanism_checks={group['key']:mean([float(all(kpi_checks[identity][key] for key in ('ledger','pptx','rendered'))) for identity in group['kpis']]) for group in boundary_spec['groups']}
    mechanism=mean(list(mechanism_checks.values()))
    font_pass=bool(pdf_info and pdf_info['min_font_pt']>=contract['min_font_pt']-contract['font_tolerance_pt'])
    unrendered_kpis=[item['kpi_id'] for item in truth['kpis'] if item['kpi_id'] in ppt_values and pdf_values.get(item['kpi_id']) is None]
    fit_pass=bool(pdf_info and not pdf_info['out_of_page_glyphs'] and not pdf_info['strong_overlapping_glyphs'] and not unrendered_kpis)
    editable=mean(editable_scores)
    layout=mean([float(font_pass),float(fit_pass),float(pdf_info.get('page_count')==contract['slides'])])
    boundary=oracle['boundary_weights']['numeric_mechanisms']*mechanism+oracle['boundary_weights']['editable_data_consistency']*editable+oracle['boundary_weights']['font_and_fit']*layout
    evidence_checks={}
    for identity,required in evidence['required_cells'].items():
        row=ledger.get(identity,{})
        refs=io['source_cells'](row['source_cells'],evidence['max_expanded_range_cells']) if 'source_cells' in row else None
        evidence_checks[identity]=bool(refs is not None and set(required)<=refs)
    evidence_score=mean([float(value) for value in evidence_checks.values()])
    descriptor_score=mean([float(all(clean for clean in (ledger.get(identity,{}).get('method',''),ledger.get(identity,{}).get('source_cells','')))) for identity in contract['required_ids']])
    page_score=mean([float(io['page_number'](ledger.get(item['kpi_id'],{}).get('slide',''))==item['slide']) for item in truth['kpis']+truth['additional_evidence_records']])
    slides_ok=bool(declared.get('slide_count')==8 and render_error is None and all(page in pages for page in range(1,9)) and all(row.get('show',True) for row in records if re.fullmatch(r'slide:\d+',row['locator'])))
    notes_ok=bool(notes_projection and note_text.strip())
    delivery=mean([float(slides_ok),float(ledger_meta.get('complete',False)),float(notes_ok),descriptor_score,page_score,float(intact)])
    if not ppt_projection and not ledger_meta.get('parseable') and not notes_projection:delivery=0.0
    if not intact:boundary=delivery=evidence_score=0.0
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence_score}
    scores['overall_score']=sum(scores[key]*weight for key,weight in oracle['checkpoint_weights'].items())
    observations={'schema_version':'h005-rule-observations/v1','scores':scores,'kpi_checks':kpi_checks,'extra_ledger_checks':extra_checks,
      'chart_checks':chart_observations,'aging_render_checks':aging_checks,'mechanism_checks':mechanism_checks,'editable_data_score':editable,'font_pass':font_pass,'fit_pass':fit_pass,
      'pdf':pdf_info,'unrendered_kpis':unrendered_kpis,'render_content_error':render_error,'ledger':ledger_meta,'ledger_error':ledger_error,'evidence_checks':evidence_checks,
      'pptx_parseable':bool(ppt_projection),'slides_ok':slides_ok,'notes_ok':notes_ok,'input_unchanged':intact,
      'observed_values':{'pptx':ppt_values,'pdf':pdf_values,'notes':note_values},
      'embedded_workbooks':{key:{k:v for k,v in value.items() if k!='values'} for key,value in extracted.items()},
      'source_bindings':{name:sha(root/path) if (root/path).is_file() else None for name,path in [('pptx',contract['pptx']),('ledger',contract['ledger']),('notes',contract['notes'])]},
      'semantic_limit':oracle['semantic_limit']}
    with (derived/'h005-analysis.json').open('x',encoding='utf-8') as handle:json.dump(observations,handle,ensure_ascii=False,indent=2);handle.write('\n')
    return scores

def grade(root):
    scores=evaluate(root);print(json.dumps({'kind':'h005-rule-summary/v1','scores':scores},ensure_ascii=False));return scores
