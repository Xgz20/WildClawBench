"""Real locked Writer PDF observations; not complete visual/semantic judgment."""
from pathlib import Path
import hashlib,json,re,runpy
import pdfplumber
from pypdf import PdfReader
OFFICE=runpy.run_path(str(Path(__file__).with_name('office_runtime.py')))

def render_and_measure(source,lock_path,output,expected,canon,candidate_model=None):
    helper=OFFICE
    lock=json.loads(Path(lock_path).read_text(encoding='utf-8'))
    # This precondition is checked even for malformed/missing deliveries by the
    # caller; an absent/drifted engine/font lock must not become a task zero.
    helper['validate_office_render_lock'](lock)
    if lock['profile']!=helper['DOCX_RENDER_PROFILE']:raise RuntimeError('H009 requires the frozen DOCX render profile')
    result=helper['render_docx_pdf'](source,lock,output,timeout_seconds=75)
    pdf=Path(result['path']);reader=PdfReader(pdf,strict=True)
    if not reader.pages:raise RuntimeError('Trusted rendering returned an unreadable empty PDF')
    outside=[];small=[];chars=[];font_names=set();numeric_visible={};page_reports=[]
    numeric_expected={row[1]:(i+len(expected['tables']['T02']['header_rows']),row) for i,row in enumerate(expected['tables']['T02']['rows'])}
    with pdfplumber.open(pdf) as document:
        for number,page in enumerate(document.pages,1):
            page_chars=[c for c in page.chars if c['text'].strip()]
            labels=page.search(r'\[F\d{2}\]') or []
            # Native note labels occur in note text. Take the last occurrence
            # of each label, so a retained inline source marker is not assumed
            # to be the start of the actual footnote area.
            label_bottom={}
            for label in labels:label_bottom[label['text']]=max(label['top'],label_bottom.get(label['text'],-1))
            note_top=min(label_bottom.values(),default=page.height)
            for c in page_chars:
                out=c['x0']<-.75 or c['x1']>page.width+.75 or c['top']<-.75 or c['bottom']>page.height+.75
                if out:outside.append({'page':number,'text':c['text'],'bbox':[c['x0'],c['top'],c['x1'],c['bottom']]})
                superscript=False
                if c['text'].isdigit() and c['size']<8.5:
                    for near in page_chars:
                        horizontal=min(abs(near['x1']-c['x0']),abs(c['x1']-near['x0']))
                        if near['size']>=8.5 and horizontal<5 and .5<near['bottom']-c['bottom']<near['size']*.9:
                            superscript=True;break
                minimum=8.5 if c['top']>=note_top-3 else 9.
                if c['size']+.15<minimum and not superscript:small.append({'page':number,'text':c['text'],'size':c['size'],'minimum':minimum})
                if not out and not (c['text'].isdigit() and c['size']<8):chars.append(c['text'])
                font_names.add(str(c.get('fontname','')))
            # Obvious ruled paths outside the PDF page are an independent
            # clipping signal. It does not prove every occlusion/contrast case.
            for edge in page.edges:
                if edge.get('linewidth',0)>0 and (edge['x0']<-.75 or edge['x1']>page.width+.75 or edge['top']<-.75 or edge['bottom']>page.height+.75):
                    outside.append({'page':number,'kind':'stroked_edge','bbox':[edge['x0'],edge['top'],edge['x1'],edge['bottom']]})
            for table in page.find_tables():
                if len(table.rows)<2 or len(table.rows[0].cells)!=6:continue
                for row in table.rows:
                    texts=[]
                    for bbox in row.cells:
                        if bbox is None:texts.append('');continue
                        contained=[c for c in page.chars if bbox[0]-.1<=c['x0'] and c['x1']<=bbox[2]+.1 and bbox[1]-.1<=c['top'] and c['bottom']<=bbox[3]+.1
                            and not (c['text'].isdigit() and c['size']<8)]
                        texts.append(canon(''.join(c['text'] for c in contained)))
                    ids=[value.upper() for value in texts if re.fullmatch(r'R\d{2}',value,re.I)]
                    if len(ids)!=1 or ids[0] not in numeric_expected:continue
                    source_row,source_values=numeric_expected[ids[0]]
                    for col in [2,3,4]:numeric_visible[f'{source_row}:{col}']=float(texts[col]==canon(source_values[col]))
            page_reports.append({'page':number,'width':page.width,'height':page.height,'characters':len(page_chars)})
    visible=canon(''.join(chars));unit_visible={};cell_visible={}
    for identity,p in expected['paragraphs'].items():unit_visible[identity]=float(bool(canon(p['text'])) and canon(p['text']) in visible)
    for identity,table in expected['tables'].items():
        observations=[float(canon(a['text']) in visible) for a in table['anchors'] if canon(a['text'])]
        cell_visible[identity]=observations;unit_visible[identity]=sum(observations)/len(observations)
    for note in expected['footnotes']:unit_visible[note['id']]=float(canon(note['text']) in visible)
    native_texts=[]
    if candidate_model:
        native_texts=[p['text'] for p in candidate_model['paragraphs'] if canon(p['text'])]
        native_texts.extend(n['text'] for n in candidate_model['notes'].values() if n['type']=='normal' and canon(n['text']))
    native_visibility=[float(canon(text) in visible) for text in native_texts]
    missing_native=[text for text,present in zip(native_texts,native_visibility) if not present]
    bounds_and_font=float(not outside and not small)
    return {'status':'rendered','pdf':str(pdf),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
        'receipt':result['audit'],'page_count':len(reader.pages),'page_observations':page_reports,
        'out_of_page_count':len(outside),'out_of_page_examples':outside[:30],
        'small_text_count':len(small),'small_text_examples':small[:30],'pdf_font_names':sorted(font_names),
        'visible_units':unit_visible,'cell_visibility':cell_visible,
        'numeric_cell_visibility':numeric_visible,
        'page_bounds_and_font_ok':bounds_and_font,'native_text_visibility':native_visibility,
        'missing_native_text_count':len(missing_native),'missing_native_text_examples':missing_native[:20],
        'basic_fit':bounds_and_font*float(bool(native_visibility) and not missing_native),'source_unchanged':result['audit']['source_unchanged'],
        'limit':'Actual PDF text/size/page-bound observations only. Complete visual fit, contrast, occlusion and semantic faithfulness require the independent Judge.'}
