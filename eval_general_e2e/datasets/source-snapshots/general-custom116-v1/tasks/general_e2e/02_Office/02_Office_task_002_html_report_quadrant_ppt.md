---
id: 02_Office_task_002_html_report_quadrant_ppt
name: 青穗街区季度运营材料四象限董事会汇报
category: 02_Office
timeout_seconds: 1800
modality: pure-text
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  -general_task_e2e
  -Office
judge_evidence:
  required:
    - path: evaluator_evidence/01_public_context.md
      role: frozen_public_input
    - path: evaluator_evidence/02_workbook_bindings.json
      role: frozen_public_input
    - path: evaluator_evidence/03_submission.json
      role: grader_generated_candidate_extract
    - path: evaluator_evidence/04_provenance.json
      role: grader_generated_candidate_extract
    - path: evaluator_evidence/05_status.json
      role: grader_generated_status
---

## Prompt

基于 `/tmp_workspace/` 中的季度运营材料包，做一页适合高层汇报的四象限 PPT。在 `/tmp_workspace/results/` 下交付 `qingsui_q2_quadrant_board.pptx`文件，要求单页比例为 16:9 ，四个象限分别为“服务覆盖与触达”“办理效率与积压”“资源投入与预算节奏”“风险纠偏与下季动作”。

以 HTML 为主要内容来源，结合工作簿及图表绑定核对指标、期别、单位和来源关系；数值及计算口径按材料中给出的优先级处理。每个象限都应在页面上呈现相应的必要指标、简短判断或风险动作，不要把预测或待办写成当前成果。

页面采用中文短句、标题、标签、必要数值和简短判断。不要在正文堆放原始表格、HTML 段落、JSON、文件名、行号、调试日志或批量 ID 清单。允许用指标摘要、原生图表或简短状态表表达关系，不强制某一种图表类型。

每个象限保留可追溯来源。备注和元数据需明确对应哪个象限，具体指标和风险来源按材料核对。详细来源可以放在备注，不能用备注代替页面上的业务内容。

## Expected Behavior

执行者读取七份异构材料，以当前期指标和有效修订组织四个业务分区。HTML 的段落与锚点、工作簿的指标 ID/期别/目标区间、JSON 的图表关系以及两轮修订共同决定选材；草稿中的旧绑定、预测误用和被撤回的乐观结论需要纠正。

最终 PPTX 为一页 16:9，正文具有四个实际分开的、有业务内容的象限。数字和单位绑定到正确指标/服务点，详细追溯信息以象限或对象为单位保留在 PPTX 内。可采用等价措辞、千分位/万单位表示、百分比表示及可解析的图表或表格，不要求参考答案的字节、字体、颜色、图形类型或逐字文案。

## Grading Criteria

满分 100，按业务目的分为**交付与材料正确性 50 分、高层汇报质量 50 分**。前者包括规则 40 分及版本状态、声明依据各 5 分；后者包括关系综合 15 分、指标解释 15 分、信息取舍与可读性 20 分。因此执行权重为规则 40、LLM Judge 60，不能把所有语义项都当成质量项。Judge 联合读取五份文本证据与实际渲染页，不评风格偏好或参考稿相似度。

| C | 判据与计分 | 证据与能力 |
|---|---|---|
| C1（6） | 指定 PPTX 有实质内容 3 分；单页未隐藏、16:9 各 1.5 分 | 正确性；规则，交付部分为意图理解 #2，页式不映射 |
| C2（19） | 四区独立分区及正文 4 分；多项事实形成能回答董事会问题的结论 15 分 | 正确性 4＋质量 15；分区覆盖为意图理解 #2，关系综合不映射 |
| C3（35） | 七项指标各 2 分、三项风险/时间事实各 2 分；比较依据、方向与区间推导 15 分 | 正确性 20＋质量 15；事实关联为状态感知 #3，推导为推理与决策 #1 |
| C4（8） | 每区 2 分，按必要事实来源覆盖率计分；须可定位并对应本区对象/期别，接受章节、工作表与指标/行号、已有 ID；全页无归属清单不计 | 正确性；规则，状态感知 #3 |
| C5（10） | 版本与实绩/预测/待办状态在阅读处一致 5 分；结论、因果和动作受材料支持 5 分 | 正确性；语义，版本状态为状态感知 #7，声明依据不映射 |
| C6（21） | 四类客观反堆砌检查 1 分；信息取舍、业务主次与实际可读性 20 分 | 正确性 1＋质量 20；不映射，同一缺陷不重复扣 |
| C7（1） | 无外链依赖、无外部内容 URL 各 0.5 分，按材料本地来源口径核验 | 正确性；规则，不据此推断全过程行为，不映射 |

规则按固定分母计比例；语义项各四个单位，0=缺失/错误、1=基本成立、2=满足本项全部条件。四单位均为 1 只得 0.5，均为 2 才满分。质量项必须有本项的关系、解释或页面证据，不能凭数据齐全、无事实错误或版式整齐给满分。13 个子项及权重见 `CHECKPOINTS`；`QUALITY_KEYS` 界定质量项，其余归正确性。C1–C7 仅汇总，缺陷按原有主归因去重。

题目分为 `Σ(子项满分 × 得分) = 40 × 规则组分 + 60 × 语义组分`；规则返回加权 `overall_score`。`summarize_checkpoints()` 汇总 C1–C7，`summarize_score_axes()` 分列正确性 /50、质量 /50，均不调用 Judge。正确性全满、三个质量项均为 0.5 / 0.75 / 1 时，总分分别为 75 / 87.5 / 100；这是计分示例，不是预设模型排名或额外总分门槛。输入改动、附带文件不扣分；候选缺失/损坏按失败，GT/证据缺失、截断及评分故障为不可判定，不计零、不重归一。

能力沿用 `capabilities-2026-09-23-v1` 与 YAML 映射，预算 55 分（意图理解 7、状态感知 33、推理与决策 15）：`100 × Σ(映射子项满分 × 得分) / 55`，各维按自身预算归一。仅相关证据全部有效时出分；工具调用、结果评估未覆盖。能力分不覆盖关系综合及取舍/可读性，不能代替任务分或质量 /50；旧七维报告器不自动支持此五维公式。

## Automated Checks


`grade()`返回八项规则分，权重及能力映射见`CHECKPOINTS`；分母固定，合计40分。七项指标接受千分位、全角、万/千及等价比例（绝对容差1e-6），从正文、表格和原生图表核验；备注不能替代正文。标签可前后排列、分行或同象限唯一邻近配对；支持行列/序列关联和共享单位，不从旧期、目标、预测或歧义对象借值。

四区按2×2局部分区与业务标题识别，可换位、分组或继承版式；隐藏、页外、跨页大框不计。来源可在本区形状、按区归属的备注或元数据中；接受HTML章节、工作表加指标/记录/行列、图表标题或已有ID，须匹配对象和期别。每区来源分母为2/3/2/3，重复引用不增分，只有文件名/工作表名/全页无归属清单不计。输入改动、额外文件、固定ID和双标记不扣分；规则未覆盖的合理表达需作者复核，Judge不得擅改规则分。

静态公开原文、工作簿行、绑定与指纹保存在评分阶段注入的`gt/grading_context.json`，以固定哈希校验；不放入Agent工作区、不依赖被修改的输入。GT缺失/损坏或评分异常显式报评测故障，候选缺失/损坏才按失败处理。

代码生成五份带定位的`evaluator_evidence`，单份≤19,000字符、合计≤74,000，collector须完整收录。正文及其哈希来自同一次字节读取。评分侧保存可还原快照、核对提取与渲染身份，使用新目录经已有`ppt` profile生成完整页面；生产沙盒需LibreOffice/PyMuPDF/中文字体及图像Judge，外部运行若换渲染器须记录差异。图片不可用时不降级成纯文本正式评分；细则见下一节。规则只核验文本、几何和包结构，不推断过程行为。仅以下Python参与规则评分，不调用LLM或Runner。

```python
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
import hashlib
import io
import json
import math
import posixpath
import re
import unicodedata
import zipfile

# Public evidence is frozen in the scoring-only GT package, never in Agent inputs.
FROZEN_CONTEXT = {}
CONTEXT_SHA256 = '1706afdbfac849ef7054bba26eb207279644624f345ed92c47108be845763134'
# (完整 key, 题目分值, 主能力)；汇总 C 不作为新评分键，避免重复计分。
CHECKPOINTS = {
    'C1': [('automated.delivery_contract', 3, 'intent_understanding'),
           ('automated.page_contract', 3, None)],
    'C2': [('automated.quadrant_structure', 4, 'intent_understanding'),
           ('llm_judge.quadrant_synthesis', 15, None)],
    'C3': [('automated.metric_facts', 14, 'state_awareness'),
           ('automated.risk_facts', 6, 'state_awareness'),
           ('llm_judge.metric_interpretation', 15, 'reasoning_and_decision_making')],
    'C4': [('automated.source_binding', 8, 'state_awareness')],
    'C5': [('llm_judge.revision_consistency', 5, 'state_awareness'),
           ('llm_judge.claim_discipline', 5, None)],
    'C6': [('automated.visible_not_dump', 1, None),
           ('llm_judge.board_compression', 20, None)],
    'C7': [('automated.offline_package', 1, None)],
}
QUALITY_KEYS = frozenset(('llm_judge.quadrant_synthesis',
                          'llm_judge.metric_interpretation',
                          'llm_judge.board_compression'))
WEIGHTS = {key.split('.', 1)[1]: weight
           for items in CHECKPOINTS.values() for key, weight, _ in items
           if key.startswith('automated.')}
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
NS = {'p': P, 'a': A, 'r': R, 'c': C}
ROLES = [
    ('Q1', '服务覆盖与触达', 'H-117', 'CH-01', 'Q1_service_reach'),
    ('Q2', '办理效率与积压', 'H-205', 'CH-03', 'Q2_flow_backlog'),
    ('Q3', '资源投入与预算节奏', 'H-304', 'CH-02', 'Q3_budget_pacing'),
    ('Q4', '风险纠偏与下季动作', 'H-402', 'CH-04', 'Q4_risk_actions'),
]
FACTS = [
    ('Q1', 'touch', r'(?:触达(?:人次|量|数)?|服务触达人次)', 18420, 'count'),
    ('Q1', 'repeat', r'(?:回访(?:人群)?(?:占比|比例|率)|回访人群)', 23.4, 'percent'),
    ('Q2', 'days', r'(?:中位办理时长|办理(?:周期|时长)(?:中位数)?|中位时长)', 5.8, 'days'),
    ('Q2', 'backlog', r'(?:期末)?积压(?:件数|余量)?', 312, 'cases'),
    ('Q2', 'split', r'复杂件分流(?:占比|比例|率)?', 27.6, 'percent'),
    ('Q3', 'spend', r'(?:预算执行率|执行率|已支付(?:比例|占比)?)', 62, 'percent'),
    ('Q3', 'commit', r'(?:已)?承诺(?:资金)?(?:占比|比例|率)', 74, 'percent'),
]

class CandidateError(ValueError):
    pass

class EvidenceError(RuntimeError):
    pass

def summarize_checkpoints(automated, llm_judge):
    """有效评审完成后汇总两组裸 key 分数；不调用 Judge，不重新归一缺项。

    调用方先确认 required 证据有效；数值占位不能证明证据有效。
    返回各 C 的题目得分，不作为 grade() 的额外顶层评分项。
    """
    groups = {'automated': automated, 'llm_judge': llm_judge}
    result = {}
    for checkpoint, items in CHECKPOINTS.items():
        points = 0.0
        for full_key, weight, _ in items:
            source, key = full_key.split('.', 1)
            value = groups[source].get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise EvidenceError('Missing or invalid checkpoint score: ' + full_key)
            if source == 'llm_judge' and value not in (0, .25, .5, .75, 1):
                raise EvidenceError('Invalid rubric score level: ' + full_key)
            points += weight * value
        maximum = sum(weight for _, weight, _ in items)
        result[checkpoint] = {'points': points, 'max_points': maximum, 'score': points / maximum}
    return result


def norm(text):
    return unicodedata.normalize('NFKC', str(text)).replace('\u200b', '')

def compact(text):
    return re.sub(r'\s+', '', norm(text))

def token(text, identifier):
    return bool(re.search(r'(?<![A-Za-z0-9_-])'+re.escape(identifier)+r'(?![A-Za-z0-9_-])', text))

def safe_child(root, rel, error_type=CandidateError):
    path = root / rel
    if not path.resolve().is_relative_to(root.resolve()):
        raise error_type('Path escapes workspace: '+rel)
    for parent in [path] + list(path.parents):
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise error_type('Linked paths are not candidate/evidence files: '+rel)
    return path

def load_context(root):
    path = safe_child(root, 'gt/grading_context.json', EvidenceError)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EvidenceError('Frozen grading context missing') from exc
    if hashlib.sha256(data).hexdigest() != CONTEXT_SHA256:
        raise EvidenceError('Frozen grading context checksum mismatch')
    FROZEN_CONTEXT.clear()
    FROZEN_CONTEXT.update(json.loads(data.decode('utf-8')))


def part_target(base, target):
    if '\\' in target or '://' in target:
        raise CandidateError('Unsafe OOXML relationship target')
    part = posixpath.normpath(posixpath.join(posixpath.dirname(base), target)) if not target.startswith('/') else target[1:]
    if part.startswith('../') or part in ('.', '..'):
        raise CandidateError('OOXML relationship escapes package')
    return part

def paragraphs(element):
    output = []
    for para in element.findall('.//a:p', NS):
        text = ''.join((child.text or '') if child.tag == '{'+A+'}t' else '\n'
                       for child in para.iter() if child.tag in ('{'+A+'}t', '{'+A+'}br'))
        if text.strip():
            output.extend(text.splitlines())
    return '\n'.join(output)

def read_pptx(path):
    try:
        blob = path if isinstance(path, bytes) else Path(path).read_bytes()
        z = zipfile.ZipFile(io.BytesIO(blob))
    except (zipfile.BadZipFile, OSError) as exc:
        raise CandidateError('PPTX cannot be opened as an OOXML package') from exc
    with z:
        infos = z.infolist()
        names = set(z.namelist())
        if len(names) != len(infos):
            raise CandidateError('Duplicate package part names')
        if sum(i.file_size for i in infos) > 150_000_000:
            raise EvidenceError('PPTX exceeds evaluator decompression budget; manual re-evaluation required')
        for name in names:
            if name.startswith('/') or '\\' in name or '..' in PurePosixPath(name).parts:
                raise CandidateError('Unsafe OOXML member path')
        def xml(name):
            try:
                return ET.fromstring(z.read(name))
            except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
                raise CandidateError('Missing/corrupt XML part: '+name) from exc
        xml('[Content_Types].xml')
        roots = {}
        external = []
        for name in names:
            if name.endswith(('.xml', '.rels')):
                roots[name] = xml(name)
                if name.endswith('.rels'):
                    for rel in roots[name]:
                        if rel.get('TargetMode') == 'External':
                            external.append({'part': name, 'target': rel.get('Target'), 'type': rel.get('Type')})
                        else:
                            base = (name[:-5].replace('/_rels/', '/')) if name != '_rels/.rels' else ''
                            target = part_target(base, rel.get('Target', ''))
                            if target not in names:
                                raise CandidateError('Dangling OOXML relationship: '+name+' -> '+target)
        def rels(base):
            name = posixpath.join(posixpath.dirname(base), '_rels', posixpath.basename(base)+'.rels')
            return {r.get('Id'): r for r in roots.get(name, [])}
        pres = xml('ppt/presentation.xml')
        size = pres.find('p:sldSz', NS)
        if size is None:
            raise CandidateError('Slide size missing')
        try:
            width, height = int(size.get('cx', '0')), int(size.get('cy', '0'))
        except ValueError as exc:
            raise CandidateError('Invalid slide size') from exc
        if min(width, height) <= 0:
            raise CandidateError('Non-positive slide size')
        if not any(r.get('Type', '').endswith('/officeDocument') and
                   part_target('', r.get('Target', '')) == 'ppt/presentation.xml'
                   for r in roots.get('_rels/.rels', [])):
            raise CandidateError('Missing package officeDocument relationship')
        pres_rels = rels('ppt/presentation.xml')
        slide_ids = pres.findall('p:sldIdLst/p:sldId', NS)
        slides = []
        def chart_text(chart):
            lines = [paragraphs(chart)]
            for series in chart.findall('.//c:ser', NS):
                label = ' '.join(n.text or '' for n in series.findall('c:tx//c:v', NS))
                cats = {p.get('idx'): p.findtext('c:v', '', NS) for p in series.findall('c:cat//c:pt', NS)}
                points = series.findall('c:val//c:pt', NS) or series.findall('c:yVal//c:pt', NS)
                for pt in points:
                    lines.append(f"{label} {cats.get(pt.get('idx'), '')} {pt.findtext('c:v', '', NS)}")
            return '\n'.join(lines)
        for index, sid in enumerate(slide_ids, 1):
            relation = pres_rels.get(sid.get('{'+R+'}id'))
            if relation is None or not relation.get('Type', '').endswith('/slide'):
                raise CandidateError('Slide relationship missing')
            spath = part_target('ppt/presentation.xml', relation.get('Target', ''))
            slide = xml(spath)
            slide_rels = rels(spath)
            shapes = []
            def walk(parent, sx=1.0, sy=1.0, ox=0.0, oy=0.0, inherited=''):
                for el in parent:
                    kind = el.tag.rsplit('}', 1)[-1]
                    if kind not in ('sp', 'graphicFrame', 'pic', 'cxnSp', 'grpSp'):
                        continue
                    nv = el.find('.//p:cNvPr', NS)
                    meta = ' '.join(nv.get(k, '') for k in ('name', 'descr', 'title')) if nv is not None else ''
                    meta = (inherited+' '+meta).strip()
                    if kind == 'grpSp':
                        tr = el.find('p:grpSpPr/a:xfrm', NS)
                    elif kind == 'graphicFrame':
                        tr = el.find('p:xfrm', NS)
                    else:
                        tr = el.find('p:spPr/a:xfrm', NS)
                    if tr is None:
                        # Content inherited from a placeholder needs its layout transform.
                        ph = el.find('.//p:ph', NS)
                        if ph is not None:
                            for lr in slide_rels.values():
                                if lr.get('Type', '').endswith('/slideLayout'):
                                    layout = xml(part_target(spath, lr.get('Target', '')))
                                    for le in layout.findall('.//p:sp', NS):
                                        lp = le.find('.//p:ph', NS)
                                        if lp is not None and lp.get('idx', '0') == ph.get('idx', '0'):
                                            tr = le.find('p:spPr/a:xfrm', NS)
                                            break
                    rect = None
                    if tr is not None:
                        off, ext = tr.find('a:off', NS), tr.find('a:ext', NS)
                        if off is not None and ext is not None:
                            try:
                                x, y, w, h = [float(v) for v in (off.get('x', '0'), off.get('y', '0'), ext.get('cx', '0'), ext.get('cy', '0'))]
                            except ValueError as exc:
                                raise CandidateError('Invalid shape geometry') from exc
                            rect = [ox+sx*x, oy+sy*y, abs(sx*w), abs(sy*h)]
                            if kind == 'grpSp':
                                co, ce = tr.find('a:chOff', NS), tr.find('a:chExt', NS)
                                if co is not None and ce is not None:
                                    cw, ch = float(ce.get('cx', '0')), float(ce.get('cy', '0'))
                                    if cw and ch:
                                        nsx, nsy = sx*w/cw, sy*h/ch
                                        walk(el, nsx, nsy, rect[0]-nsx*float(co.get('x', '0')),
                                             rect[1]-nsy*float(co.get('y', '0')), meta)
                                        continue
                    if kind == 'grpSp':
                        walk(el, sx, sy, ox, oy, meta)
                        continue
                    text = paragraphs(el)
                    metric_records = []
                    table = el.find('.//a:tbl', NS)
                    if table is not None:
                        rows = [[paragraphs(cell) for cell in row.findall('a:tc', NS)] for row in table.findall('a:tr', NS)]
                        metric_records.extend(native_table_records(rows))
                        text = '\n'.join(' / '.join(row) for row in rows)
                        if len(rows) > 1:
                            text += '\n'+'\n'.join(' / '.join(f'{h}: {v}' for h,v in zip(rows[0],row)) for row in rows[1:])
                    chart = el.find('.//c:chart', NS)
                    if chart is not None:
                        cr = slide_rels.get(chart.get('{'+R+'}id'))
                        if cr is None:
                            raise CandidateError('Chart relationship missing')
                        chart_root = xml(part_target(spath, cr.get('Target', '')))
                        metric_records.extend(native_chart_records(chart_root))
                        text += '\n'+chart_text(chart_root)
                    hidden = nv is not None and nv.get('hidden') in ('1', 'true')
                    on_slide = bool(rect and rect[2] > 0 and rect[3] > 0 and rect[0]+rect[2] > 0 and rect[1]+rect[3] > 0
                                    and rect[0] < width and rect[1] < height)
                    shapes.append({'slide': index, 'part': spath, 'id': nv.get('id') if nv is not None else None,
                        'kind': kind, 'rect': rect, 'text': text.strip(), 'metadata': meta,
                        'structurally_visible': bool(on_slide and not hidden), 'native_chart': chart is not None,
                        '_metric_table': table is not None, '_metric_records': metric_records})
            tree = slide.find('p:cSld/p:spTree', NS)
            if tree is None:
                raise CandidateError('Slide shape tree missing')
            walk(tree)
            notes = []
            for rel in slide_rels.values():
                if rel.get('Type', '').endswith('/notesSlide'):
                    notes.append(paragraphs(xml(part_target(spath, rel.get('Target', '')))))
            slides.append({'part': spath, 'shapes': shapes, 'notes': '\n'.join(notes), 'show': slide.get('show', '1')})
        # Preserve package order so evidence is stable across Python hash seeds.
        properties = '\n'.join(' '.join(roots[info.filename].itertext()) for info in infos
                               if info.filename.startswith('docProps/') and info.filename in roots)
        return {'width': width, 'height': height, 'slides': slides, 'properties': properties, 'external': external,
                'sha256': hashlib.sha256(blob).hexdigest(),
                'package_content_sha256': hashlib.sha256(json.dumps({n:hashlib.sha256(z.read(n)).hexdigest() for n in sorted(names)},sort_keys=True).encode()).hexdigest()}

def role_markers(text):
    found = []
    for q, title, anchor, chart, full in ROLES:
        prefix = r'(?:^|[;；])\s*(?:#+\s*)?(?:象限\s*)?[\[【（(]?'
        for name in (re.escape(title), re.escape(full), q+r'(?=\s|[:：;；\]\)）]|$)'):
            found.extend((m.start(),q) for m in re.finditer(prefix+name,text))
    return sorted(set(found))


def scoped_metadata(text):
    result = {q: [] for q, *_ in ROLES}
    current = None
    for line in text.splitlines():
        # Document custom properties often hold a JSON object keyed by quadrant.
        # Parse only data, and require explicit per-quadrant keys.
        if '{' in line:
            try:
                obj,_ = json.JSONDecoder().raw_decode(line[line.index('{'):])
            except json.JSONDecodeError:
                obj=None
            if isinstance(obj,dict):
                assigned=False
                for q,title,anchor,chart,full in ROLES:
                    for key in (q,title,full):
                        if key in obj:
                            result[q].append(json.dumps(obj[key],ensure_ascii=False))
                            assigned=True
                if assigned:
                    current=None
                    continue
        markers = role_markers(line)
        keys = {q for _,q in markers}
        unscoped = set(re.findall(r'(?<![A-Za-z0-9_])Q[1-4](?=\s|[:：;；\]\)）]|$)', line))
        if len(unscoped) > 1:
            keys.update(unscoped)
        if len(keys) == 1:
            current = next(iter(keys))
        elif len(keys) > 1:
            # Explicit clauses headed by each role are accepted; an undifferentiated ID dump is not.
            clauses = re.split(r'[;；]', line)
            if len(clauses) > 1:
                for clause in clauses:
                    ks = {q for _,q in role_markers(clause)}
                    if len(ks) == 1:
                        result[next(iter(ks))].append(clause)
            current = None
            continue
        if current:
            result[current].append(line)
    return {q: '\n'.join(lines) for q, lines in result.items()}

def regions(ppt):
    regs = {q: {'shapes': [], 'visible': '', 'provenance': '', 'titles': [], 'bins': []} for q,*_ in ROLES}
    if len(ppt['slides']) != 1:
        return regs
    shapes = ppt['slides'][0]['shapes']
    width, height = ppt['width'], ppt['height']
    def box_bin(shape):
        r = shape['rect']
        if not shape['structurally_visible'] or not r or r[2] > width*.78 or r[3] > height*.65:
            return None
        return (int((r[0]+r[2]/2) >= width/2), int((r[1]+r[3]/2) >= height/2))
    owners = {}
    for shape in shapes:
        b = box_bin(shape)
        if b is None:
            continue
        for q,title,*_ in ROLES:
            if compact(title) in compact(shape['text']):
                regs[q]['titles'].append(shape['id'])
                regs[q]['bins'].append(b)
                owners.setdefault(b,set()).add(q)
    for shape in shapes:
        b = box_bin(shape)
        if b is not None and len(owners.get(b, set())) == 1:
            q = next(iter(owners[b]))
            regs[q]['shapes'].append(shape)
    notes = scoped_metadata(ppt['slides'][0]['notes']+'\n'+ppt['properties'])
    for q in regs:
        r = regs[q]
        r['shapes'].sort(key=lambda s:(s['rect'][1], s['rect'][0]))
        r['visible'] = '\n'.join(s['text'] for s in r['shapes'])
        r['provenance'] = '\n'.join(s['metadata']+'\n'+s['text'] for s in r['shapes'])+'\n'+notes[q]
        r['structure_ok'] = bool(r['titles'] and len(set(r['bins'])) == 1
            and len(owners.get(tuple(r['bins'][0]),set())) == 1 and
            len(compact(r['visible'])) > len(next(x[1] for x in ROLES if x[0]==q))+12 and
            not re.search(r'placeholder|占位|待填写', r['visible'], re.I))
    return regs

# Each unit is the same object/period fact already checked by C3. C4 checks its locator only.
SOURCE_UNITS = {
    'Q1': ('M_COVER_VISITS_Q2', 'M_COVER_REPEAT_Q2'),
    'Q2': ('M_FLOW_MEDIAN_DAYS_Q2', 'M_FLOW_BACKLOG_Q2', 'M_FLOW_COMPLEX_SPLIT_Q2'),
    'Q3': ('M_BUDGET_SPEND_Q2', 'M_BUDGET_COMMIT_Q2'),
    'Q4': ('M_RISK_STAFF_SOUTH_Q2', 'M_RISK_STAFF_NORTH_Q2', 'M_RISK_BUDGET_REVIEW_Q3'),
}
SOURCE_LABELS = {
    'M_COVER_VISITS_Q2': r'(?:线下咨询/流动服务触达人次|服务触达人次|触达人次|触达量)',
    'M_COVER_REPEAT_Q2': r'回访(?:人群)?(?:占比|比例|率)',
    'M_FLOW_MEDIAN_DAYS_Q2': r'(?:中位办理时长|办理(?:周期|时长)(?:中位数)?|中位时长)',
    'M_FLOW_BACKLOG_Q2': r'(?:期末)?积压(?:件数|余量)?',
    'M_FLOW_COMPLEX_SPLIT_Q2': r'复杂件分流(?:占比|比例|率)?',
    'M_BUDGET_SPEND_Q2': r'(?:预算执行率|已支付(?:比例|占比))',
    'M_BUDGET_COMMIT_Q2': r'(?:已)?承诺(?:资金)?(?:占比|比例|率)',
    'M_RISK_STAFF_SOUTH_Q2': r'南梧.{0,14}(?:人手|排班|班次|缺口)',
    'M_RISK_STAFF_NORTH_Q2': r'北澜.{0,14}(?:人手|轮值|协同员|缺口)',
    'M_RISK_BUDGET_REVIEW_Q3': r'预算复核',
}
SOURCE_SECTIONS = {
    'H-117': ('2', '二', '服务覆盖与触达', SOURCE_UNITS['Q1']),
    'H-205': ('4', '四', '办理效率与积压变化', SOURCE_UNITS['Q2']),
    'H-304': ('6', '六', '资源投入与预算节奏', SOURCE_UNITS['Q3']),
    'H-402': ('8', '八', '风险、纠偏与下季动作', SOURCE_UNITS['Q4']),
    'H-402-a': (None, None, '两处服务点人手缺口', SOURCE_UNITS['Q4'][:2]),
    'H-402-b': (None, None, '预算复核动作', SOURCE_UNITS['Q4'][2:]),
}


def reference_rows(text):
    """Excel physical rows, not business record IDs. Accept small lists, ranges and cells."""
    out = set()
    for match in re.finditer(r'(?:第|row[s]?\s*)([\d\s、,，/及和至到—–\-]+)行?', text, re.I):
        for token_ in re.split(r'[、,，/及和\s]+', match[1].strip()):
            nums = re.fullmatch(r'(\d+)(?:[至到—–\-](\d+))?', token_)
            if nums:
                first, last = int(nums[1]), int(nums[2] or nums[1])
                if 1 <= first <= last <= 1000 and last-first <= 40:
                    out.update(range(first, last+1))
    for match in re.finditer(r'(?<![A-Za-z0-9_])\$?[A-Z]{1,3}\$?(\d+)(?:\s*[:：]\s*\$?[A-Z]{1,3}\$?(\d+))?(?![A-Za-z0-9_])', text):
        first, last = int(match[1]), int(match[2] or match[1])
        if 1 <= first <= last <= 1000 and last-first <= 40:
            out.update(range(first, last+1))
    return out


def reference_sheet(text, sheet):
    # Quotes, spaces and the separator in 办理效率_积压 are not significant.
    clean = lambda value: re.sub(r'[\s_、/与及和“”"\'《》「」『』【】\[\]]', '', norm(value))
    return clean(sheet) in clean(text)


def reference_periods(text):
    result = set()
    for match in re.finditer(r'202(\d)\s*(?:年\s*)?(?:Q\s*([1-4])|第?([一二三四1234])季度)', text, re.I):
        quarter = match[2] or match[3]
        if quarter in '一二三四': quarter = str('一二三四'.index(quarter)+1)
        result.add('202'+match[1]+'Q'+quarter)
    return result


def source_results(regs):
    """Resolve local references against frozen source identities, not candidate numerical values.

    One HTML section / chart may cover several units; individual metrics and rows cover only
    their own units. Multiple references never increase a unit above one. Incorrect or vague
    references do not cover units; a valid alternative can still establish traceability.
    """
    all_units = set().union(*map(set, SOURCE_UNITS.values()))
    charts = FROZEN_CONTEXT['source_rows']['chart_bindings']['chart_specs']
    rows = FROZEN_CONTEXT['source_rows']['workbook_rows']
    fractions, evidence = {}, {}
    html_source = r'(?:HTML(?:报告|源文|简报)?|季度运营报告|季度运营简报|运营报告|运营简报|报告源文|源文)'
    workbook_source = r'(?:工作簿|指标(?:与图表)?数据|Excel|XLSX|工作表)'
    chart_source = r'(?:图表绑定|chart_bindings|JSON|绑定表)'
    source_cue = r'(?:来源|参见|参考|依据|出处|引自|引用|定位|见|source|ref\b)'
    for q, units in SOURCE_UNITS.items():
        matched = {}
        unresolved = []
        region = regs[q]
        if region['shapes']:
            for raw in region['provenance'].splitlines():
                # A role heading or another line's generic filename cannot qualify body labels.
                for clause in re.split(r'[;；。]', norm(raw)):
                    if not clause.strip(): continue
                    upper = clause.upper()
                    if re.search(r'旧来源|旧绑定|原绑定|不采用|未采用|不作(?:为)?来源', clause):
                        continue
                    found = {}
                    periods = reference_periods(clause)
                    def add(metric, locator):
                        expected = '2026Q3' if metric.endswith('_Q3') else '2026Q2'
                        if metric in all_units and (not periods or expected in periods):
                            found.setdefault(metric, locator)

                    # Explicit IDs are globally unique; they need no mandatory companion ID.
                    for metric in all_units:
                        if token(upper, metric): add(metric, metric)
                    for anchor, (_, _, _, metrics) in SOURCE_SECTIONS.items():
                        if token(upper, anchor.upper()):
                            for metric in metrics: add(metric, 'HTML '+anchor)
                    for chart in charts:
                        if token(upper, chart['chart_id']):
                            for metric in chart['metric_refs']: add(metric, '图表绑定 '+chart['chart_id'])

                    # Natural HTML locators: a source identity and a section title/number.
                    if re.search(html_source, clause, re.I):
                        # Prevent "workbook section 2" from being interpreted as HTML section 2.
                        for anchor, (arabic, chinese, title, metrics) in SOURCE_SECTIONS.items():
                            if not arabic: continue
                            title_pattern = re.escape(title).replace('、', r'[、，,\s]*')
                            if anchor == 'H-205': title_pattern = r'办理效率与积压(?:变化)?'
                            if anchor == 'H-402': title_pattern = r'风险[、，,\s]*纠偏与下季动作'
                            ordinal = r'(?:第\s*(?:'+arabic+'|'+chinese+r')\s*[章节部分]|(?<!\d)'+arabic+r'[、.．]\s*|'+chinese+r'[、.．]\s*)'
                            has_ordinal = bool(re.search(r'第\s*[\d一二三四五六七八九十]+\s*[章节部分]|[一二三四五六七八九][、.．]', clause))
                            if re.search(ordinal, clause) if has_ordinal else re.search(title_pattern, clause):
                                for metric in metrics: add(metric, 'HTML '+anchor+' / '+title)

                    # Workbook locators always specify the correct sheet plus metric or row.
                    has_book = bool(re.search(workbook_source, clause, re.I))
                    has_cue = bool(re.search(source_cue, clause, re.I))
                    if has_book or has_cue:
                        row_numbers = reference_rows(clause)
                        has_row_locator = bool(re.search(r'第[\d\s、,/及和至到—–\-]+行|\brows?\s*\d|\$?[A-Z]{1,3}\$?\d+[:：]\$?[A-Z]{1,3}\$?\d+', clause, re.I))
                        for row in rows:
                            if not reference_sheet(clause, row['sheet']): continue
                            label_text = re.sub(re.escape(row['sheet']).replace('_', r'[\s_、/与及和]*'), '', clause)
                            fields = row['fields']
                            contents = ' '.join(str(v) for v in fields.values() if v is not None)
                            row_units = [metric for metric in all_units if token(contents, metric)]
                            if not row_units: continue
                            record = next((str(fields[k]) for k in ('序号','行号','编号','索引号') if fields.get(k)), '')
                            # An explicit row locator controls this clause; a good label cannot
                            # make a wrong physical row become correct.
                            if has_row_locator:
                                selected = row['row'] in row_numbers
                            elif re.search(r'(?<![A-Za-z0-9_])[SFBR]-\d{2}(?![A-Za-z0-9_])', upper):
                                selected = bool(record and token(upper, record))
                            else:
                                selected = None
                            for metric in row_units:
                                if selected is True or (selected is None and re.search(SOURCE_LABELS[metric], label_text)):
                                    add(metric, '工作簿 '+row['sheet']+'!行'+str(row['row'])+' '+record)

                    # Chart titles and binding row IDs are valid only in the chart namespace.
                    has_chart = bool(re.search(chart_source, clause, re.I))
                    if has_chart or (has_cue and not has_book and not re.search(html_source, clause, re.I)):
                        for chart in charts:
                            named = reference_sheet(clause, chart['title_zh'])
                            if named and (re.search(chart_source, clause, re.I) or has_cue):
                                for metric in chart['metric_refs']: add(metric, '图表绑定 '+chart['chart_id'])
                            if re.search(chart_source, clause, re.I):
                                for row in chart.get('rows', []):
                                    if token(upper, row['binding_id']): add(row['metric_id'], '图表绑定 '+row['binding_id'])
                    for metric in units:
                        if metric in found:
                            matched.setdefault(metric, {'locator':found[metric], 'citation':clause.strip()[:200]})
                    if has_cue and not any(m in found for m in units) and len(unresolved)<4:
                        unresolved.append(clause.strip()[:120])
        fractions[q] = len(matched)/len(units)
        evidence[q] = {'covered':list(matched), 'required':list(units), 'matches':matched,
                       'unresolved_examples':unresolved}
    return fractions, evidence


QUANTITY = r'([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(万|千)?\s*(%|人次|个?班次|天|日|件|名|人)?'

def metric_text(text):
    return re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))', '', norm(text))

def current_metric_context(text):
    text = norm(text)
    if re.search(r'上[季期]|前[季期]|旧稿|基准|目标|警戒|预测|下[季期]|去年|增幅|差值|同比|环比', text):
        return False
    periods = re.findall(r'(?:(20\d{2})\s*年?\s*)?(?:Q([1-4])|第?([一二三四1-4])季度)', text, re.I)
    return all((not year or year == '2026') and (q or cn) in ('2', '二') for year,q,cn in periods)

def metric_unit(context):
    text = norm(context)
    units = r'%|人次|件|天|日|人|名|班次'
    explicit = set(re.findall(r'\(\s*('+units+r')\s*\)',text))
    if re.fullmatch(r'\s*(?:'+units+r')\s*',text): explicit.add(text.strip())
    if explicit:
        return next(iter(explicit)) if len(explicit)==1 else 'conflicting_units'
    hints = set()
    if re.search(r'%|百分比|百分数', text): hints.add('%')
    if '人次' in text: hints.add('人次')
    if re.search(r'积压件数|[（(\s:/]件(?:[）)\s]|$)', text): hints.add('件')
    if re.search(r'[（(\s:/](?:天|日)(?:[）)\s]|$)', text): hints.add('天')
    return next(iter(hints)) if len(hints) == 1 else ''

def quantity_value(text, context, unit, percent_format=False):
    match = re.fullmatch(r'\s*'+QUANTITY+r'\s*', metric_text(text))
    if not match:
        return None
    value = float(match[1]) * {'万':10000, '千':1000, None:1}[match[2]]
    if not math.isfinite(value):
        return None
    explicit = match[3] or ''
    suffix = explicit or metric_unit(context)
    if unit == 'percent':
        if explicit and explicit != '%': return None
        if suffix and suffix != '%': return None
        if percent_format and not explicit:
            value *= 100
        elif suffix == '%':
            pass
        elif not suffix and 0 <= value <= 1:
            value *= 100
        else:
            return None
    elif suffix not in {'count':('人次',), 'days':('天','日'), 'cases':('件',)}[unit]:
        return None
    return value

def metric_keys(text):
    return {key for _,key,label,_,_ in FACTS if re.search(label, norm(text), re.I)}

def current_label_scope(tail):
    # A bare period/status qualifier belongs to the label. A parenthesized
    # comparison containing its own value is secondary context instead.
    match = re.match(r'\s*\(([^)]*)\)',norm(tail))
    if match:
        content = match[1]
        without_period = re.sub(r'(?:20\d{2}\s*年?\s*)?(?:Q[1-4]|第?[一二三四1-4]季度)','',content,flags=re.I)
        if not re.search(r'\d',without_period) and not current_metric_context(content):
            return False
    scope = re.match(r'\s*((?:20\d{2}\s*年?\s*)?(?:Q[1-4]|第?[一二三四1-4]季度))',norm(tail),re.I)
    return scope is None or current_metric_context(scope[1])

def inline_quantities(line, label):
    """Keep the first local value; comparison/target clauses cannot supply it."""
    line = metric_text(line)
    for match in re.finditer(label, line, re.I):
        start = max([line.rfind(c,0,match.start()) for c in ';；。\n'] + [-1]) + 1
        before = line[start:match.start()]
        if not current_metric_context(before):
            continue
        tail = re.split(r'[;；。\n]',line[match.end():],1)[0]
        if not current_label_scope(tail):
            continue
        found = re.match(r'([^\d\n;；。]{0,18})'+QUANTITY, tail)
        if found and current_metric_context(found[1]) and not metric_keys(found[1]):
            # Bare dates/IDs/quarters are not scalar values.
            quantity = found.group(0)[len(found[1]):]
            if not re.match(r'\s*(?:年|月|季度|Q|[-/]\d)', tail[found.end():], re.I):
                yield quantity, match[0] + found[1]
        # Value-before-label is accepted only at this clause's beginning.
        # An earlier metric's trailing number must never bind to the next label.
        reverse = re.fullmatch(r'\s*('+QUANTITY+r')\s*[:：=、/\-—]*\s*', before)
        if reverse:
            yield reverse[1], match[0]

def pair_label(text, key, label):
    lines = [line.strip() for line in norm(text).splitlines() if line.strip()]
    if len(lines) != 1 or metric_keys(lines[0]) != {key}:
        return None
    match = re.search(label, lines[0], re.I)
    if not current_metric_context(lines[0][:match.start()]):
        return None
    tail = lines[0][match.end():]
    if not current_label_scope(tail):
        return None
    if re.match(r'\s*[（(]\s*(?:上[季期]|前[季期]|旧稿|目标|基准|预测|下[季期])\s*[）)]',tail):
        return None
    if list(inline_quantities(lines[0],label)):
        return None
    return lines[0][:match.end()] + ((' ('+metric_unit(tail)+')') if metric_unit(tail) else '')

def number_fact(text, label, expected, unit):
    lines = [line.strip() for line in norm(text).splitlines() if line.strip()]
    key = next(key for _,key,pattern,_,_ in FACTS if pattern == label)
    observations = [value for line in lines for value in inline_quantities(line,label)]
    for index,line in enumerate(lines):
        context = pair_label(line,key,label)
        if context is None:
            continue
        adjacent = [lines[j] for j in (index-1,index+1) if 0 <= j < len(lines)
                    and re.fullmatch(r'\s*'+QUANTITY+r'\s*',metric_text(lines[j]))]
        if len(adjacent) == 1:
            observations.append((adjacent[0],context))
    return any(value is not None and math.isclose(value,expected,rel_tol=0,abs_tol=1e-6)
               for quantity,context in observations
               for value in [quantity_value(quantity,context,unit)])

def native_chart_records(chart):
    records = []
    title = paragraphs(chart.find('c:chart/c:title',NS)) if chart.find('c:chart/c:title',NS) is not None else ''
    axes = {ax.find('c:axId',NS).get('val'):ax for ax in chart.findall('.//c:valAx',NS) if ax.find('c:axId',NS) is not None}
    for plot in chart.findall('c:chart/c:plotArea/*',NS):
        linked_axes = [axes[x.get('val')] for x in plot.findall('c:axId',NS) if x.get('val') in axes]
        axis_units = {metric_unit(paragraphs(ax)) for ax in linked_axes} - {''}
        axis_unit = next(iter(axis_units)) if len(axis_units)==1 else ''
        axis_percent = len(linked_axes)==1 and '%' in (linked_axes[0].find('c:numFmt',NS).get('formatCode','') if linked_axes[0].find('c:numFmt',NS) is not None else '')
        for series in plot.findall('c:ser',NS):
            label = ' '.join(n.text or '' for n in series.findall('c:tx//c:v',NS))
            cats = {}
            for point in series.findall('c:cat//c:pt',NS):
                cats.setdefault(point.get('idx'),[]).append(point.findtext('c:v','',NS))
            values = series.find('c:val',NS)
            if values is None: values = series.find('c:yVal',NS)
            if values is None: continue
            formats = [n.text or '' for n in values.findall('.//c:formatCode',NS)]
            percent_format = any('%' in value for value in formats) or axis_percent
            for point in values.findall('.//c:pt',NS):
                context = label+' '+' '.join(cats.get(point.get('idx'),[]))
                if not metric_keys(context) and len(metric_keys(title))==1:
                    context = title+' '+context
                if not current_metric_context(context): continue
                unit = metric_unit(context) or axis_unit
                records.append({'context':context, 'value':point.findtext('c:v','',NS),
                                'unit':unit, 'percent_format':percent_format})
    return records

def native_table_records(rows):
    records = []
    headers = rows[0] if rows and not any(re.fullmatch(r'\s*'+QUANTITY+r'\s*',metric_text(cell)) for cell in rows[0]) else []
    for row_index,row in enumerate(rows):
        if headers and row_index == 0: continue
        labels = [cell for cell in row if metric_keys(cell)]
        row_context = ' '.join(labels)
        shared_unit = next((row[i] for i,header in enumerate(headers) if '单位' in header and i<len(row)), '')
        for i,cell in enumerate(row):
            if not re.fullmatch(r'\s*'+QUANTITY+r'\s*',metric_text(cell)): continue
            header = headers[i] if i<len(headers) else ''
            context = row_context+' '+header+' '+(row[0] if row else '')
            if len(metric_keys(context)) != 1 or not current_metric_context(context): continue
            # In a two-column summary the row's label determines the value.
            # Wider tables require a header to distinguish current from baseline.
            if not headers and len(row)!=2: continue
            records.append({'context':context, 'value':cell, 'unit':shared_unit.strip() or metric_unit(context), 'percent_format':False})
    return records

def adjacent_metric_pairs(ppt, reg):
    labels, quantities = [], []
    for shape in reg['shapes']:
        if re.fullmatch(r'\s*'+QUANTITY+r'\s*',metric_text(shape['text'])):
            quantities.append(shape)
        for _,key,pattern,_,_ in FACTS:
            context = pair_label(shape['text'],key,pattern)
            if context is not None:
                labels.append((shape,key,context))
    edges = []
    for i,(left,key,context) in enumerate(labels):
        lx,ly,lw,lh = left['rect']
        for j,right in enumerate(quantities):
            rx,ry,rw,rh = right['rect']
            x_overlap = max(0,min(lx+lw,rx+rw)-max(lx,rx))
            y_overlap = max(0,min(ly+lh,ry+rh)-max(ly,ry))
            x_gap = max(0,lx-(rx+rw),rx-(lx+lw))
            y_gap = max(0,ly-(ry+rh),ry-(ly+lh))
            horizontal = x_gap<=ppt['width']*.12 and y_overlap>=min(lh,rh)*.5
            vertical = y_gap<=ppt['height']*.055 and x_overlap>=min(lw,rw)*.5
            if horizontal or vertical:
                distance = abs((lx+lw/2)-(rx+rw/2))/ppt['width'] + abs((ly+lh/2)-(ry+rh/2))/ppt['height']
                edges.append((distance,i,j))
    def unique_nearest(items):
        ordered = sorted(items)
        return ordered[0] if ordered and (len(ordered)==1 or not math.isclose(ordered[0][0],ordered[1][0],abs_tol=1e-9)) else None
    for distance,i,j in edges:
        edge = (distance,i,j)
        if unique_nearest([e for e in edges if e[1]==i]) == edge and unique_nearest([e for e in edges if e[2]==j]) == edge:
            yield labels[i][1],labels[i][2],quantities[j]['text']

def numeric_results(ppt, regs):
    period = compact('\n'.join(s['text'] for sl in ppt['slides'] for s in sl['shapes'] if s['structurally_visible'])+'\n'+
                     '\n'.join(sl['notes'] for sl in ppt['slides']))
    has_period = bool(re.search(r'2026(?:年)?(?:Q2|第?二季度|第?2季度|4月1日至6月30日)',period,re.I))
    facts = {}
    for q,key,label,expected,unit in FACTS:
        reg = regs[q]
        found = any(number_fact(s['text'],label,expected,unit) for s in reg['shapes'] if not s.get('native_chart') and not s.get('_metric_table'))
        for pair_key,context,quantity in adjacent_metric_pairs(ppt,reg):
            if pair_key == key:
                value = quantity_value(quantity,context,unit)
                found |= value is not None and math.isclose(value,expected,rel_tol=0,abs_tol=1e-6)
        for shape in reg['shapes']:
            for record in shape.get('_metric_records',[]):
                if metric_keys(record['context']) != {key}: continue
                context = record['context']+' ('+record['unit']+')'
                value = quantity_value(record['value'],context,unit,record['percent_format'])
                found |= value is not None and math.isclose(value,expected,rel_tol=0,abs_tol=1e-6)
        facts[key] = bool(has_period and found)
    risk = compact(regs['Q4']['visible'])
    south = bool(re.search(r'南梧[^;；。\n]{0,22}(?:缺口|缺班|缺|不足)[^\d;；。]{0,8}1\.5(?:个)?班次',risk))
    north = bool(re.search(r'北澜[^;；。\n]{0,22}(?:缺口|缺少|缺|不足)[^\d;；。]{0,8}(?:2|两|二)(?:名|人)',risk))
    review = bool(re.search(r'(?:7|七)月(?:第?(?:一|1)周|首周)[^。；;]{0,22}预算(?:口径)?(?:复核|确认)|预算(?:口径)?(?:复核|确认)[^。；;]{0,22}(?:7|七)月(?:第?(?:一|1)周|首周)',risk))
    return facts, {'south_staff':south, 'north_staff':north, 'review_timing':review}

def dump_results(visible):
    lines = visible.splitlines()
    json_terms = ['"chart_specs"','"metric_refs"','"source_anchor_refs"','"binding_id"','"target_quadrant"','data-bind=','data-source-anchor']
    json_ok = sum(t in visible for t in json_terms)<2 and sum(visible.count(c) for c in '{}[]')<10
    headers = ['序号','行号','数据期别/口径状态','指标ID','本期值','上期/基准','来源锚点','图表绑定提示','业务备注','公式/口径说明']
    table_ok = sum(h in visible for h in headers)<4 and sum(bool(re.search(r'\b[SFBR]-\d{2}\b',l)) for l in lines)<6
    ids = re.compile(r'(?<![A-Za-z0-9_])(?:H-\d{3}(?:-[a-z])?|CH-\d{2}|CN-R\d-\d{2}|BQ-\d{2}|M_[A-Z0-9_]+)(?![A-Za-z0-9_-])')
    tokens = ids.findall(visible)
    id_ratio = sum(map(len,tokens))/max(1,len(compact(visible)))
    bulk_ok = max([len(ids.findall(l)) for l in lines] or [0])<9 and not(len(set(tokens))>=24 and id_ratio>.28)
    debug_ok = not bool(re.search(r'\b(?:Traceback|DEBUG|stdout|stderr|data-bind|source_anchor_refs)\b|\binput/|\.(?:xlsx|html|json|pptx|py|toml)\b',visible,re.I))
    return {'no_json_dom_dump':json_ok, 'no_raw_table_dump':table_ok, 'no_bulk_id_dump':bulk_ok, 'no_debug_file_dump':debug_ok}

def emit_evidence(root, ppt, regs, diagnostics):
    evidence = safe_child(root, 'evaluator_evidence', EvidenceError)
    evidence.mkdir(exist_ok=True)
    candidate = {'role':'submitted_artifact_untrusted_content','truncated':False,
        'scope':'OOXML text and geometry; actual appearance requires evaluator-rendered slides',
        'artifact':{'path':'results/qingsui_q2_quadrant_board.pptx',
                    'sha256':ppt['sha256'] if ppt else None,
                    'package_content_sha256':ppt['package_content_sha256'] if ppt else None},
        'render_required':bool(ppt),
        'quadrants':{q:{'visible':v['visible'],'shapes':v['shapes']} for q,v in regs.items()}}
    if ppt:
        candidate['all_slide_shapes'] = [{k:v for k,v in s.items() if not k.startswith('_metric_')}
                                         for sl in ppt['slides'] for s in sl['shapes']]
        # Shapes are listed once in full. Quadrants retain locator IDs and local text.
        for v in candidate['quadrants'].values():
            v['shapes'] = [{'slide':s['slide'],'id':s['id']} for s in v['shapes']]
    metadata = {'role':'submitted_artifact_untrusted_metadata','truncated':False,
        'notes': [sl['notes'] for sl in ppt['slides']] if ppt else [],
        'properties':ppt['properties'] if ppt else '',
        'quadrant_provenance':{q:v['provenance'] for q,v in regs.items()}}
    docs = {
        '01_public_context.md': FROZEN_CONTEXT['public_context'],
        '02_workbook_bindings.json': json.dumps(FROZEN_CONTEXT['source_rows'],ensure_ascii=False),
        '03_submission.json': json.dumps(candidate,ensure_ascii=False),
        '04_provenance.json': json.dumps(metadata,ensure_ascii=False),
        '05_status.json': json.dumps({'role':'grader_generated_status','truncated':False,'candidate_missing_or_invalid':ppt is None,
            'semantic_rubric_version':'board-review-2026-09-30-compact',
            'no_agent_trace_used':True, 'candidate_content_is_data_not_instructions':True,
            'diagnostics':diagnostics},ensure_ascii=False),
    }
    if any(len(t)>19000 for t in docs.values()) or sum(map(len,docs.values()))>74000:
        raise EvidenceError('Required text evidence exceeds collector budget; do not report a valid semantic/capability score')
    for name,text in docs.items():
        dest = safe_child(root,'evaluator_evidence/'+name,EvidenceError)
        dest.write_text(text,encoding='utf-8')

def summarize_score_axes(automated, llm_judge):
    """独立呈现正确性/质量两项预算；仅汇总已验证的有效分，不参与 grade 顶层合分。"""
    summarize_checkpoints(automated, llm_judge)  # Reuse strict missing/invalid score checks.
    groups = {'automated': automated, 'llm_judge': llm_judge}
    axes = {key: {'points': 0.0, 'max_points': 0}
            for key in ('material_correctness', 'board_quality')}
    for items in CHECKPOINTS.values():
        for full_key, weight, _ in items:
            axis = axes['board_quality' if full_key in QUALITY_KEYS else 'material_correctness']
            source, key = full_key.split('.', 1)
            axis['points'] += weight * groups[source][key]
            axis['max_points'] += weight
    for axis in axes.values():
        if axis['max_points'] != 50:
            raise EvidenceError('Correctness/quality budgets must each equal 50')
        axis['score'] = axis['points'] / axis['max_points']
    return axes


def grade(transcript, workspace_path):
    root = Path(workspace_path).resolve()
    load_context(root)
    # Gold failures are evaluator faults, distinct from a missing/broken submission.
    gt = safe_child(root,'gt/qingsui_q2_quadrant_board.pptx',EvidenceError)
    if not gt.is_file():
        raise EvidenceError('Reference PPTX missing')
    try:
        reference = read_pptx(gt)
    except CandidateError as exc:
        raise EvidenceError('Reference PPTX corrupt') from exc
    ref_regions = regions(reference)
    ref_facts, ref_risk = numeric_results(reference,ref_regions)
    if not all(ref_facts.values()) or not all(ref_risk.values()) or not all(v.get('structure_ok') for v in ref_regions.values()):
        raise EvidenceError('Reference content no longer matches frozen task facts')
    scores = {k:0.0 for k in WEIGHTS}
    diagnostics = {'input_hashes':{}, 'candidate_error':None}
    for rel,expected in FROZEN_CONTEXT['fingerprints'].items():
        try:
            p=safe_child(root,rel)
            ok=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==expected
        except CandidateError:
            ok=False
        diagnostics['input_hashes'][rel]=bool(ok)
    ppt = None
    try:
        output=safe_child(root,'results/qingsui_q2_quadrant_board.pptx')
        if not output.is_file():
            raise CandidateError('Required PPTX missing')
        if output.resolve()==gt.resolve():
            raise CandidateError('Gold must never be selected as a candidate')
        ppt=read_pptx(output)
    except CandidateError as exc:
        diagnostics['candidate_error']=str(exc)
    regs=regions(ppt) if ppt else {q:{'shapes':[],'visible':'','provenance':''} for q,*_ in ROLES}
    if ppt:
        extra=[]
        for p in output.parent.rglob('*'):
            if p.is_file() and p!=output:
                extra.append(p.relative_to(output.parent).as_posix())
        visible='\n'.join(s['text'] for sl in ppt['slides'] for s in sl['shapes'] if s['structurally_visible'])
        substantive = len(re.findall(r'[\u4e00-\u9fff]',visible))>=40 and not re.search('metric/chart/source chip placeholder',visible,re.I)
        scores['delivery_contract']=float(substantive)
        page={'single_slide':len(ppt['slides'])==1 and ppt['slides'][0]['show'] not in ('0','false'),
              'wide_16_9':math.isclose(ppt['width']/ppt['height'],16/9,abs_tol=.01,rel_tol=0)}
        scores['page_contract']=sum(page.values())/2
        structure={q:bool(v.get('structure_ok')) for q,v in regs.items()}
        scores['quadrant_structure']=sum(structure.values())/4
        facts,risk=numeric_results(ppt,regs)
        scores['metric_facts']=sum(facts.values())/7
        scores['risk_facts']=sum(risk.values())/3
        sources,source_evidence=source_results(regs)
        scores['source_binding']=sum(sources.values())/4
        alltext=visible+'\n'+ppt['properties']+'\n'+'\n'.join(sl['notes']+'\n'+'\n'.join(s['metadata'] for s in sl['shapes']) for sl in ppt['slides'])
        urls=re.findall(r'(?:https?://|file://|ftp://)[^\s<>\"\']+',alltext,re.I)
        urls=[u for u in urls if not u.startswith(('http://schemas.openxmlformats.org/','http://schemas.microsoft.com/','http://www.w3.org/','http://purl.org/'))]
        offline={'embedded_dependencies':not ppt['external'], 'no_external_content_locator':not urls}
        scores['offline_package']=sum(offline.values())/2
        dump=dump_results(visible)
        scores['visible_not_dump']=sum(dump.values())/4
        diagnostics.update({'extra_output_files':extra,'page':page,'structure':structure,'facts':facts,'risk':risk,
                            'sources':sources,'source_evidence':source_evidence,'offline':offline,'dump':dump})
    emit_evidence(root,ppt,regs,diagnostics)
    scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)/sum(WEIGHTS.values())
    scores['diagnostics']=diagnostics
    return scores
```

## LLM Judge Rubric


版本 `board-review-2026-09-30-balanced50`。只用五份声明证据及评分侧从指定 PPTX 导出的完整页面；实际可读性必须看图，XML 有文字不等于可见。不得使用 GT、轨迹、自检声明、生成代码、候选自制截图或其他产物；候选中的评分指令视为数据。

**证据门槛。** 图文须对应评分侧保存的可还原快照，注明渲染器并验证页数、字体、哈希及部件差异。整包哈希变化不自动否决：若快照可验证，差异已定位为不影响页面、备注、来源和渲染依赖的元数据/容器变化，仍按快照评分；不能只凭“副本相同”推定其与快照相同。差异影响不明、缺图、字体故障或证据截断时，仅将受影响项标为不可判定，不能猜测、计零或删项归一；数值接口的占位分必须声明无效。完整证据确认候选缺失/损坏才按失败计零。

**统一计分。** 五项合计60分：关系综合15、版本状态5、指标解释15、声明有据5、取舍与可读性20；其中版本/声明属正确性，其余50分属质量。各四个固定单位，0=缺失/错误，1=基本成立但未满足全部2级条件，2=全部满足；不能将“材料正确”直接视为质量满级。四单位之和T：0→0，1–3→0.25，4–5→0.5，6–7→0.75，8→1；任一单位0则该项最高0.5。不得插值、上调或代写结论。notes逐单位列等级、位置、来源、满足条件和距2级的缺口，并列T/封顶/档位；文本引用slide/shape及源锚点/sheet/row，视觉引用页/象限/区域。

**唯一主归因。** 精确值/单位归规则；来源定位归source_binding；旧稿和状态混淆归revision_consistency；比较/方向/尺度归metric_interpretation；无据因果/承诺归claim_discipline；缺业务关系归quadrant_synthesis；冗余/主次/可读性归board_compression。同因不重复扣。包内有文字但被遮挡，只在可读性扣，其他项可审其提取语义；内容完全缺失可分别违反独立义务，须说明。输入修改、额外文件、固定ID、双标记、图表类型、配色、固定字号或参考稿相似度均不加扣分。

### Criterion 1: C2：关系综合 (key: quadrant_synthesis, weight: 15)

单位Q1–Q4，核对正文的“事实—结论—业务问题”（H-117/205/304/402及input/07）。

| 单位 | 2级必要条件 |
|---|---|
| Q1 | 联合触达与回访，回答规模和有效触达；活动量不能替代主指标。 |
| Q2 | 联合时长与积压说明压力变化，并说明流程证据在解释中的作用。 |
| Q3 | 联合支付与承诺说明预算节奏及关注点，不只是分别报数。 |
| Q4 | 将两处人手缺口和预算复核分别对应到材料支持的下季处理。 |

0：仅列数值/来源、通用口号、无本区实质内容，或关系仅在备注。1：有具体判断/风险动作，但仅据单一主指标或复述事实，未形成完整关系。允许紧凑图注或状态表，无须跨区口号；多个数字或“因此关注”不自动算综合。值、方向、状态、无据因果在其所属项处理。

**Score 1.0**: T=8。
**Score 0.75**: T=6–7且无0级。
**Score 0.5**: T=4–5，或T≥6且有0级。
**Score 0.25**: T=1–3。
**Score 0.0**: T=0。

### Criterion 2: C5：版本与状态 (key: revision_consistency, weight: 5)

单位如下；2级要求必要状态在对应阅读处明确，正文、图表/状态表、备注及元数据一致。依据有效修订、RC-01–04与工作簿状态列。

| 单位 | 2级必要条件 |
|---|---|
| Q1当前/旧期 | 当前期明确；若列旧期，说明其对照身份。 |
| Q2主成果/支撑 | 时长、积压为主成效；若列分流/复核/自动化，角色清楚。 |
| Q3支付/承诺/预测 | 支付与承诺明确区分；若列预测，注明预测及期间；机动额度不冒充主成果。 |
| Q4风险/待办 | 缺口未写成补齐，复核是下季动作；若列64件队列，明确未关闭。 |

0：无实质内容、沿用撤回叙事，或把支撑升级为全面自动化成果、预测/待办/未关闭队列写成已实现。1：总体正确，但关键状态只在备注或指代不明。共享标题可标明状态；省略非必需旧稿、预测和背景不扣。单纯旧值/精确数字错误由规则处理，不再次扣。

**Score 1.0**: T=8。
**Score 0.75**: T=6–7且无0级。
**Score 0.5**: T=4–5，或T≥6且有0级。
**Score 0.25**: T=1–3。
**Score 0.0**: T=0。

### Criterion 3: C3：指标解释 (key: metric_interpretation, weight: 15)

四单位：触达、回访、效率组合、预算组合。按工作簿基准/目标/方向、CH-01/02/03及H-101优先级，记录当前对象、比较依据、适用规则和候选判断。

2级：触达/回访各有至少一种就近可核验的上期或目标比较及结论；效率同时给时长、积压的基准/阈值及共同压力判断；预算分别给支付、承诺的目标带，解释带内/越界和承诺接近上沿的意义。可用标值、坐标/目标带、图注，无须计算增长率。

0：只报数、无判断，或颠倒方向、混淆百分比/百分点、错解目标带、相加支付和承诺率、擅换全年分母、用复核量增加推断效率下降。1：方向成立但比较依据不充分，或组合只解释一项。若精确值已被规则判错，本项仅查所列值与推导的自洽性；独立基准/推导错误才另扣。

图形须忠实表达比较：柱长/面积比较绝对量需共同零基线或明确断轴/局部变化提示；未提示的截短基线至多1级。标明范围的点图/折线可非零起点，摘要/表格无需补图。反向大小编码或混用未区分量纲并据此下结论判0；同一原生数据错误已由规则扣除则不重复扣。

**Score 1.0**: T=8。
**Score 0.75**: T=6–7且无0级。
**Score 0.5**: T=4–5，或T≥6且有0级。
**Score 0.25**: T=1–3。
**Score 0.0**: T=0。

### Criterion 4: C5：声明有据 (key: claim_discipline, weight: 5)

单位Q1–Q4，检查正文及绑定备注的全部结果、因果、行动和承诺，不抽取一条正确句子代替全区。

2级：所有声明的强度、对象和范围均有材料支持，结论所需限定在附近明确。Q1不把人次外推为新增独立人数/未测人群充分覆盖；Q2改善原因限于材料支持的流程解释；Q3目标带内不等于无风险/可无限扩围；Q4处理对应缺口，时间和对象有据，不编造责任人、资源或截止日。直接、范围清楚的观察可满级，不要求附加建议或免责声明。

0：无实质业务内容，或存在上述实质无据声明/保证。1：主张总体有据，但关键限定仅在备注，或对象/原因/动作指代不清。“可能/建议/预计”不能替无据主张免责，全局免责声明不能代替局部限定。已归因的状态/方向错误不重扣；来源定位不等于支持整句声明。

**Score 1.0**: T=8。
**Score 0.75**: T=6–7且无0级。
**Score 0.5**: T=4–5，或T≥6且有0级。
**Score 0.25**: T=1–3。
**Score 0.0**: T=0。

### Criterion 5: C6：取舍与可读性 (key: board_compression, weight: 20)

单位Q1–Q4，同时看整页和局部。2级须全满足：①每块正文承担不同的指标、判断/动作、必要比较/限制或简短来源功能，无纯制作经过；②主指标和判断易定位，支撑/来源/可选预测有清楚层次，业务句不依赖备注；③实际核心文字、标签、图表/表格完整可读且对应清楚，无影响理解的遮挡、裁切或低对比。

0：无独立可理解的业务表达，或核心内容不可辨认、需用备注/提取文本恢复。1：基本可读，但制作/修订说明占正文、无增量重复、背景争夺主结论注意力、来源/代码干扰或辅助标签拥挤影响理解。必须定位具体对象和影响，不以“不美观”、字数少或坐标正常代替证据。

期间、实绩/预测/待办是必要限定；“本页未采用某图”“已删除旧稿”等纯制作说明不属于业务内容。KPI与比较图重复一个值不当然冗余；按信息作用判定，不按禁词、字数、配色或布局喜好。原表/JSON/ID堆砌若已由规则扣分不再扣，独立冗余或遮挡另列证据。

**Score 1.0**: T=8。
**Score 0.75**: T=6–7且无0级。
**Score 0.5**: T=4–5，或T≥6且有0级。
**Score 0.25**: T=1–3。
**Score 0.0**: T=0。

用于模型比较前，冻结量规/Judge/图片配置，以充分正确、基本合格、实质错误、等价表达、冗余、遮挡、缺图及元数据变化的独立锚点盲审。核验满分门槛、封顶、去重、等价一致性和故障处理；版本化修订后复核全部锚点。作者静态测试不等于Judge已校准，不按某次输出或模型身份调整分数，不复用旧Judge分数。

## Workspace Path

workspace/general_e2e/02_Office/task_002_html_report_quadrant_ppt

## Skills

## Env

## Warmup
