from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import hashlib, json, re, shutil

WORK=Path(__file__).resolve().parent
CASE=WORK.parent.parent
SOURCE=CASE/'exec'
ORIGINAL=WORK/'original'
DRAFT=WORK/'draft'
for d in [ORIGINAL,DRAFT]: d.mkdir(parents=True,exist_ok=True)
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
audit={}

def text(e, namespace=W):
    return ''.join(e.xpath('.//x:t/text()',namespaces={'x':namespace}))

def set_text(e,value,namespace=W):
    ts=e.findall('.//{'+namespace+'}t')
    assert ts
    ts[0].text=value
    for t in ts[1:]: t.text=''

def xml(root):return E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)

def rewrite(source,changes):
    with ZipFile(source) as src,ZipFile(DRAFT/source.name,'w') as dst:
        for entry in src.infolist():dst.writestr(entry,changes.get(entry.filename,src.read(entry.filename)))

for source in sorted(SOURCE.iterdir()):
    if not source.is_file():continue
    original=ORIGINAL/source.name
    if not original.exists():shutil.copyfile(source,original)
    assert original.read_bytes()==source.read_bytes(),'Original changed during revision'
    changes={};edits=[]
    with ZipFile(original) as z:
        if source.suffix=='.docx':
            r=E.fromstring(z.read('word/document.xml'));body=r.find('{'+W+'}body')
            if source.name.startswith('06_'):
                replacements={
                    '填写 24 项任务进展及统计口径，保留未知状态。':'概述各项任务的进展、工作量和验收情况。',
                    '按任务 ID 保留备注中的适用范围和前置条件。':'说明影响结论的适用范围和前置条件。',
                    '逐项列出缺失状态或原因，注明任务/问题 ID、来源位置和待确认责任人。':'列出待确认事项、相关来源和待确认责任人。',
                    '在注释或附录中注明对应任务/表图、来源文件、版本及具体位置，可按共用口径合并说明。':'注明报告内容对应的来源文件、版本及位置。',
                }
                for para in body.findall('{'+W+'}p'):
                    before=text(para)
                    if before in replacements:
                        set_text(para,replacements[before]);edits.append([before,replacements[before]])
                assert len(edits)==4
            else:
                appendix=False
                for para in list(body):
                    if para.tag=='{'+W+'}sectPr':continue
                    before=text(para)
                    if before=='附录 B 交接口径和归档位置':
                        appendix=True
                        prev=para.getprevious()
                        if prev is not None and prev.tag=='{'+W+'}p' and not text(prev):body.remove(prev)
                    if appendix:
                        body.remove(para);edits.append([before,None]);continue
                    if para.tag!='{'+W+'}p':continue
                    after=before
                    if '本阶段负责八项工作。' in before:
                        after=before.split('本阶段负责')[0]+'本阶段围绕试点运行验证开展工作，当前工作不构成全网推广批准。'
                    elif before=='本材料的阅读口径' or before.startswith('二级标题按任务 ID 定位；'):
                        after=None
                    elif before.startswith('现行版本 v1.0 于'):
                        after='现行版本 v1.0 于 2026-09-15 固定。v0.9 为 2026-09-12 的历史快照。'
                    elif before.startswith('作业记录表示一次处理或核对动作'):
                        after='作业记录表示一次处理或核对动作，同一任务可能有多个样本。作业量与独立验收样本量采用不同口径。'
                    elif before.startswith('图 1 三部门记录完成比例示意'):
                        after='图 1 三部门记录完成比例'
                    elif before.startswith('该比例只表示已记录作业的完成量'):
                        after='记录完成比例为已完成记录量占计划记录量的比例，不表示正式任务验收结论。'
                    elif '记录分布在指标明细和隐藏补录表。' in before:
                        after=before.split('，记录分布在')[0]+'。'
                    elif re.match(r'跟进IS-\d{3}-01时，',before) or before.startswith('本项的详细采样顺序、区域核对与移交记录'):
                        after=None
                    elif before.startswith('本表连续记录 96 次不同的作业动作'):
                        after='下表为各区域的采样、核对和移交操作履历。'
                    elif before.startswith('以上日期为已确认的下一步计划时间'):
                        after='以上日期为已确认的后续计划日期。'
                    if after!=before:
                        edits.append([before,after])
                        if after is None:body.remove(para)
                        else:set_text(para,after)
                assert len(edits)==37,(source.name,len(edits))
            changes['word/document.xml']=xml(r)
        elif source.suffix=='.xlsx':
            shared=E.fromstring(z.read('xl/sharedStrings.xml')) if 'xl/sharedStrings.xml' in z.namelist() else None
            shared_items=list(shared) if shared is not None else []
            descriptions=[
                ('星桥客服平台升级项目及相关项目业务记录。','数量单位：条；空白字段表示未提供。'),
                ('任务基本信息与正式状态。','状态日期为本次台账确认日期。'),
                ('各项目作业记录。','计划量、完成量单位：条。'),
                ('各项目独立验收样本。','验收结果：通过 / 不通过；有效性：有效 / 无效。'),
                ('各项目问题登记。','问题状态：未关闭 / 已关闭；原因以登记内容为准。'),
                ('2026-09-12 台账历史快照。','历史版本：v0.9。'),
                ('当期新增作业记录。','补录性质为新增独立记录，不是原记录替换。'),
            ]
            for i,(d2,d3) in enumerate(descriptions,1):
                member=f'xl/worksheets/sheet{i}.xml';r=E.fromstring(z.read(member))
                updates={'A2':d2,'A3':d3}
                if i==1:updates.update(D5='试点运行验证',D6='独立项目',D7='历史快照')
                for ref,value in updates.items():
                    cell=r.find('.//{'+S+'}c[@r="'+ref+'"]');assert cell is not None
                    before=text(shared_items[int(cell.find('{'+S+'}v').text)],S) if cell.get('t')=='s' else text(cell,S)
                    edits.append([f'sheet{i}!{ref}',before,value])
                    for child in list(cell):cell.remove(child)
                    cell.set('t','inlineStr');E.SubElement(E.SubElement(cell,'{'+S+'}is'),'{'+S+'}t').text=value
                changes[member]=xml(r)
            if shared is not None:
                used=set()
                for member in z.namelist():
                    if re.fullmatch(r'xl/worksheets/sheet\d+.xml',member):
                        r=E.fromstring(changes.get(member,z.read(member)))
                        used.update(int(c.find('{'+S+'}v').text) for c in r.findall('.//{'+S+'}c') if c.get('t')=='s')
                for i,si in enumerate(shared_items):
                    if i not in used:
                        for child in list(si):si.remove(child)
                        E.SubElement(si,'{'+S+'}t').text=''
                changes['xl/sharedStrings.xml']=xml(shared)
        elif source.suffix=='.pptx':
            for i in range(1,25):
                member=f'ppt/slides/slide{i}.xml';r=E.fromstring(z.read(member))
                for shape in list(r.findall('.//{'+P+'}sp')):
                    before=text(shape,A)
                    if before=='统计口径与适用范围详见本页演讲者备注。':
                        shape.getparent().remove(shape);edits.append([member,before,None])
                    elif '完整口径以工作簿为准' in before:
                        paras=shape.findall('.//{'+A+'}p')
                        for para in paras:
                            pt=text(para,A)
                            if pt in ['不替代正式状态','完整口径以工作簿为准']:para.getparent().remove(para)
                            elif pt=='仅反映作业记录':set_text(para,'统计对象：作业记录',A)
                        edits.append([member,before,text(shape,A)])
                changes[member]=xml(r)
                member=f'ppt/notesSlides/notesSlide{i}.xml';r=E.fromstring(z.read(member))
                for para in r.findall('.//{'+A+'}p'):
                    before=text(para,A);after=before
                    if before.startswith('必要范围限定 '):
                        after=before.removeprefix('必要范围限定 ').replace('此限定应随对应任务进入报告，即使本页视觉标题展示的是另一项工作。','')
                    elif '的图中计划量和完成量含独立补录' in before:
                        after=before[:6]+'：计划量和完成量单位为条，包含当期新增作业记录。'
                    if after!=before:set_text(para,after,A);edits.append([member,before,after])
                changes[member]=xml(r)
        else:raise ValueError(source)
    rewrite(original,changes)
    audit[source.name]={'edits':edits,'changed_parts':list(changes),'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'draft_sha256':hashlib.sha256((DRAFT/source.name).read_bytes()).hexdigest()}
(WORK/'edits.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:len(v['edits']) for k,v in audit.items()},ensure_ascii=False))
