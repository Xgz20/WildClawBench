---
id: 03_Data_Analysis_task_003_batch_quality_available_inventory
name: Multiwarehouse Batch Quality Status and Available Inventory
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.78
  llm_judge: 0.22
tags:
  - custom
  - general_e2e
  - business
judge_evidence:
  required:
    - path: 评分证据/
      role: grader_generated_evidence
---

## Prompt

请还原月末各仓各批次库存，重点看质量冻结、部分解冻和质检状态变化后有多少真正可用，哪些仓品无法满足未来七日保障需求。材料在 `/tmp_workspace/`，请按其中《口径与交付说明.md》整理库存明细、仓品结构、事件和来源索引、未知范围及风险说明，保留实际核对记录。原始材料不要改，结果存到 `/tmp_workspace/results/批次质量库存分析.xlsx`。

## Expected Behavior

采用公开材料中指定期间和全部目标sheet，识别期初宽表日期、合并SKU、隐藏有效行、重复表头及小计。库存键为仓库、SKU、批次，事件ID全局去重后按业务时间和ID还原；撤销可指向事件或整张调拨，盘点为有符号差异，截止后事件不参与。

数量台账、冻结台账和质量状态分开维护，再按待检、拒收、合格及不适用规则生成互斥库存分类。部分解冻不能替代质检放行；未知期初不填零，未知质量不能从其他仓推断。仓品汇总公开已知范围、分母、未知批次数和保障缺口，完成八张公开要求表，并对事件完整性、调拨守恒、库存与分类、分析分母及证据实际核对。

## Grading Criteria

评分版本：2026-10-14-v1。场景S3-03，主题库存分析，business，L4。题目100分：规则78分、裁判22分。评分依据仅为Prompt及其明确采用的公开《口径与交付说明.md》；Expected Behavior、私有GT、作者记录和能力目录不能增加待测义务。参考答案只用于比对公开可确定事实，不要求同一算法或附加脚本。

| 检查点 | 场景点 | 方式/分值 | 公开依据及判定对象 | 档位 |
|---|---|---|---|---|
| automated.C1_scope | C1产物范围 | 规则10 | §1、§5：库存、仓品、事件、来源、调拨、未知六类应有主键集合 | 0/0.5/1 |
| llm_judge.C1_actual | C1实际处理 | 裁判4 | §1、§5及Prompt：真实操作覆盖指定资料、时点、仓库、全部有效sheet区块，原始材料只读 | 0/0.5/1 |
| automated.C2_state | C2状态还原 | 规则26 | §2、§3、§5：实物还原、事件有效状态、质量时间线、冻结台账四个完整业务单元 | 0/0.25/0.5/0.75/1 |
| automated.C3_classification | C3分类与阈值 | 规则18 | §3、§4：批次互斥分类；仓品已知数值、保障缺口、分母及风险阈值 | 0/0.5/1 |
| automated.C4_unknown | C4未知边界 | 规则12 | §3—§5：未知/零/不适用标记及汇总范围；缺期初与缺状态清单和影响字段 | 0/0.5/1 |
| automated.C5_trace | C5来源与守恒 | 规则12 | §2、§5：期初/状态/有效事件追溯、全部事件及原始来源关联、逐单双边调拨复算 | 0/0.5/1 |
| llm_judge.C6_risk | C6风险结论 | 裁判10 | §4、§5风险说明四个问题及可确认范围、证据与补证建议 | 0/0.25/0.5/0.75/1 |
| llm_judge.C7_audit | C7实际验收 | 裁判8 | §5交付前四领域实际核对；操作、回执和验收记录共同证明 | 0/0.25/0.5/0.75/1 |

C1_scope每表分母=GT公开应有主键数+额外主键数+多余重复行数+缺主键数，分子为唯一且命中应有集合的主键数。六表均完整为1，至少三表完整但未全部完整为0.5，其余0。缺少参考对象不能缩小分母；辅助字段与格式不算额外对象。实际读取另由C1_actual结合轨迹判定，产物正确不能推断处理行为。

C2_state的四个独立单元分别要求全量一致：(a)公开可确定的期初、净变动和期末实物，(b)全部唯一事件的对象、时间、类型、撤销/去重/截止处理及有符号影响，(c)所有库存键的最终质量状态，(d)所有库存键的冻结台账。满足0/1/2/3/4个单元分别得0/0.25/0.5/0.75/1；各单元完整有独立业务价值。数量未知标记在C4核对。保存每单元正确对象数作为诊断，不按候选已交行数产生连续正式分。

C3_classification的两个单元是(a)全量可确定的可用、冻结受限、拒收数量，(b)全部仓品可确定数值及已知范围风险类别。两个都正确为1，一个正确为0.5，都不正确为0；未知及不适用标记在C4核对。C4_unknown两个单元是(a)所有库存及仓品的未知/零/不适用状态、未知批次数和对保障的影响，(b)缺口主键集合、类型、必要影响字段及真实来源完整正确；两个/一个/零个满足分别1/0.5/0。补证建议的语义交C6判断。

C5_trace三个单元是(a)全部库存的期初单元格、有效状态来源和有效事件ID，(b)所有唯一事件完整来源集合与全部原始来源对象关联，(c)每张调拨单双边、有效数量与净额。全部满足为1，满足一或两个为0.5，均不满足为0。真实但无关的源位置、伪造位置、错对象位置不计有效证据。其他数值义务与来源义务分别计分，不将一个来源错误描述为已观察到的数量错误。

规则组返回`Σ(各项题目分值×得分)/78`，Judge组`Σ(各项题目分值×得分)/22`，总分按0.78/0.22加权。只允许表中离散档位。数量容差1e-6；公开4位比例容差0.000050001；表/行/列顺序、数值文本、日期对象/文本、来源集合顺序及事件/维表同一行的单元格范围等价接受。使用公开固定字段与标记词；追加真实相关佐证允许。公式缺缓存及确有等价但当前识别受限时转评测复核，不直接计候选0，不执行候选脚本补交付。

缺交付是业务缺失，各规则项为0；GT或冻结原始资料缺失/损坏属于评测异常，抛EvaluationDataError。C1_actual及C7_audit依赖真实外部调用、对象、参数及返回。缺轨迹/关键回执或证据正文未送达应在Judge notes写“不可判定”并说明；框架必须数字时0仅作协议占位，不是业务0，不可合成正式总分或删项重归一。只有完整轨迹能证明未执行时才计有效0。规则提取文件是评测方结果，不能当候选过程证据。

能力目录capabilities-2026-09-23-v1：仅有真实轨迹及产物的C1_actual→intent_understanding#3；C2_state→state_awareness#4；C3_classification→reasoning_and_decision_making#1；C7_audit→result_evaluation#1；C1_scope、C4、C5、C6为不映射业务验收。映射预算56分，能力总分=100×(4×C1_actual+26×C2_state+18×C3_classification+8×C7_audit)/56；各维按本维权重归一，工具调用未覆盖。

## Automated Checks

```python
"""正式题内grade的源文本。只在隔离评测副本读取GT、候选和公开输入。"""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
import math
import re
from openpyxl import load_workbook

class EvaluationDataError(RuntimeError): pass
class EvaluationReviewRequired(RuntimeError): pass

KEYS={"库存明细":["仓库","SKU","批次"],"仓品结构":["仓库","SKU"],"事件索引":["事件ID"],"来源索引":["来源定位"],"调拨核对":["调拨单号"],"未知范围":["仓库","SKU","批次","缺口类型"]}
WEIGHTS={"C1_scope":10,"C2_state":26,"C3_classification":18,"C4_unknown":12,"C5_trace":12}

def norm(value):
    if value is None: return ""
    if isinstance(value,datetime): return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value,date): return value.isoformat()
    return str(value).strip()

def source_norm(value):
    text=norm(value).replace("\\","/")
    parts=text.split("|")
    if len(parts)!=3: return text
    filename,sheet,ref=parts; filename=filename.split("/")[-1]
    ref=ref.replace("$","").strip()
    # 期初日期必须精确到单元格；事件/维表允许任意同一行的范围。
    if filename!="各仓期初矩阵.xlsx":
        m=re.fullmatch(r"(?:[A-Za-z]+)?(\d+)(?::(?:[A-Za-z]+)?\1)?",ref)
        if m: ref=str(int(m.group(1)))
    else: ref=ref.upper()
    return "|".join([filename,sheet,ref])

def tokens(value,source=False):
    vals=re.split(r"[;；\n]+",norm(value))
    return {source_norm(x) if source else x.strip() for x in vals if x.strip() and x.strip()!="无"}

def equivalent(actual,expected,field=""):
    if field=="业务时间":
        try:return datetime.fromisoformat(norm(actual))==datetime.fromisoformat(norm(expected))
        except ValueError:return False
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):
        try:
            v=float(norm(actual).replace(",","")); e=float(expected)
            return math.isfinite(v) and abs(v-e)<=(.000050001 if field.endswith("率") else .000001)
        except (ValueError,TypeError): return False
    return norm(actual)==norm(expected)

def rows_from_book(path,headers):
    if not path.exists(): return {},"缺少交付"
    try: wb=load_workbook(path,data_only=True)
    except Exception as exc: return {},"交付不可读取: "+type(exc).__name__
    result={}
    for name,heads in headers.items():
        if name not in wb: result[name]=[]; continue
        ws=wb[name]; hi=None
        for row in ws.iter_rows(min_row=1,max_row=min(25,ws.max_row)):
            vals=[norm(c.value) for c in row]
            required=KEYS.get(name,heads[:1])
            if all(x in vals for x in required): hi=row[0].row; pos={v:i for i,v in enumerate(vals) if v}; break
        if hi is None: result[name]=[]; continue
        table=[]
        for row in ws.iter_rows(min_row=hi+1):
            if all(c.value is None for c in row): continue
            table.append({h:row[pos[h]].value if h in pos and pos[h]<len(row) else None for h in heads})
        result[name]=table
    wb.close()
    # 无公式缓存是评测求值限制，转为复核，不偷运行候选代码。
    raw=load_workbook(path,data_only=False)
    for ws in raw:
        if ws.title in headers:
            if any(c.data_type=="f" for row in ws for c in row):
                evaluated=load_workbook(path,data_only=True)
                missing=[c.coordinate for row in ws for c in row if c.data_type=="f" and evaluated[ws.title][c.coordinate].value is None]
                evaluated.close()
                if missing: raw.close(); raise EvaluationReviewRequired(f"{ws.title}公式缺计算值，需只读计算证据：{missing[:5]}")
    raw.close()
    return result,"可读取"

def key_of(row,table):
    return tuple(source_norm(row.get(h)) if h=="来源定位" else norm(row.get(h)) for h in KEYS[table])

def unique_index(rows,table):
    buckets=defaultdict(list)
    for r in rows: buckets[key_of(r,table)].append(r)
    return {k:rs[0] for k,rs in buckets.items() if len(rs)==1 and all(k)},buckets

def grade(transcript:list,workspace_path:str)->dict:
    root=Path(workspace_path)
    gp=root/"gt"/"标准答案与来源.json"
    try: gt=json.loads(gp.read_text(encoding="utf-8"))
    except Exception as exc: raise EvaluationDataError("私有标准答案缺失或损坏，不能记候选0分") from exc
    if gt.get("schema_version")!=1 or not isinstance(gt.get("tables"),dict) or not isinstance(gt.get("headers"),dict):
        raise EvaluationDataError("标准答案schema不完整")
    expected=gt["tables"]; expidx={}; actidx={}; diag={}
    for table in KEYS:
        if table not in expected or not expected[table] or len(expected[table])!=gt.get("counts",{}).get(table):
            raise EvaluationDataError("标准答案表缺失或计数损坏: "+table)
        ix,bs=unique_index(expected[table],table)
        if len(ix)!=len(expected[table]): raise EvaluationDataError("标准答案主键损坏: "+table)
        expidx[table]=ix
    public=root
    hashes=gt.get("input_hashes")
    if not isinstance(hashes,dict) or len(hashes)!=4: raise EvaluationDataError("公开输入摘要缺失")
    for name,wanted in hashes.items():
        p=public/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=wanted:
            raise EvaluationDataError("公开输入缺失/损坏/被改写，先核实冻结材料及轨迹: "+name)
    actual,read_status=rows_from_book(root/"results"/"批次质量库存分析.xlsx",gt["headers"])
    scope_parts={}
    for table in KEYS:
        rows=actual.get(table,[])
        if table=="未知范围":rows=[r for r in rows if norm(r.get("缺口类型"))!="读取失败"]
        ix,bs=unique_index(rows,table); actidx[table]=ix
        target=set(expidx[table]); obtained=set(bs)
        extra=sum(1 for k in obtained-target if all(k)); duplicates=sum(len(v)-1 for k,v in bs.items() if all(k)); invalid=sum(len(v) for k,v in bs.items() if not all(k))
        hit=len(set(ix)&target); den=len(target)+extra+duplicates+invalid
        scope_parts[table]={"matched_unique":hit,"expected":len(target),"extra":extra,"duplicates":duplicates,"invalid_keys":invalid,"denominator":den,"coverage":hit/den}
    source_catalog={source_norm(r["来源定位"]):r for r in expected["来源索引"]}
    def related(loc,row,event_only=False):
        sr=source_catalog.get(loc)
        if not sr:return False
        if event_only:return sr["记录类型"]=="事件" and norm(sr["记录ID"])==norm(row.get("事件ID"))
        if sr["记录类型"]=="SKU规则":return sr["SKU"]==row.get("SKU")
        return all(not norm(sr.get(h)) or norm(sr[h])==norm(row.get(h)) for h in ["仓库","SKU","批次"])
    def field_ok(table,key,fields,known_only=False):
        exp=expidx[table][key]; act=actidx[table].get(key)
        if act is None:return False
        for h in fields:
            e=exp.get(h); a=act.get(h)
            if known_only and not isinstance(e,(int,float)):continue
            if h in ["期初来源","状态来源","来源集合"]:
                es=tokens(e,True); ass=tokens(a,True)
                if not es.issubset(ass) or not all(related(loc,exp,table=="事件索引") for loc in ass):return False
            elif h=="有效事件ID":
                if tokens(a)!=tokens(e):return False
            elif h=="影响字段":
                if not tokens(e).issubset(tokens(a)):return False
            elif h=="来源定位":
                if source_norm(a)!=source_norm(e):return False
            elif not equivalent(a,e,h):return False
        return True
    def check(table,fields,known_only=False,keys=None):
        keys=list(expidx[table]) if keys is None else list(keys)
        good=sum(field_ok(table,k,fields,known_only) for k in keys)
        return {"correct":good,"denominator":len(keys),"ratio":good/len(keys) if keys else 1,"passed":good==len(keys)}
    def passed(*tests):return all(t["passed"] for t in tests)
    # C1：六类必要对象覆盖；分母不可从候选提交行数构造。
    complete=sum(v["coverage"]==1 for v in scope_parts.values())
    score_scope=1 if complete==6 else .5 if complete>=3 else 0
    # C2四个独立业务单元，每个须全量一致，正式分为五档。
    physical=check("库存明细",["期初数量","有效净变动","期末数量"],True)
    event_state=check("事件索引",["事件类型","仓库","SKU","批次","业务时间","处理结果","实物影响","冻结影响","调拨单号","撤销对象"])
    quality=check("库存明细",["质量状态"])
    freeze=check("库存明细",["账面冻结量"])
    score_state=sum(t["passed"] for t in [physical,event_state,quality,freeze])/4
    # C3分类桶与仓品数值、阈值/分母分别作为两个交付单元。
    classify=check("库存明细",["可用数量","冻结受限量","拒收数量"],True)
    fields=[h for h in gt["headers"]["仓品结构"] if h not in ["仓库","SKU","期初未知批次数","分类未知批次数"]]
    summary=check("仓品结构",fields,True)
    risk_keys=[k for k,r in expidx["仓品结构"].items() if r["风险类别"]!="待补证"]
    risk=check("仓品结构",["风险类别"],keys=risk_keys)
    score_class=(int(classify["passed"])+int(passed(summary,risk)))/2
    # C4未知不能参与确定数值比较；单独检查其标记、缺口及分母影响。
    unknown_detail=[]
    for k,r in expidx["库存明细"].items():
        hs=[h for h in ["期初数量","期末数量","可用数量","冻结受限量","拒收数量"] if r[h]=="未知"]+["确认状态"]
        unknown_detail.append(field_ok("库存明细",k,hs))
    unknown_summary=[]
    for k,r in expidx["仓品结构"].items():
        hs=["期初未知批次数","分类未知批次数"]+[h for h in ["保障缺口","保障覆盖率","已知范围受限率","风险类别"] if not isinstance(r[h],(int,float))]
        unknown_summary.append(field_ok("仓品结构",k,hs))
    gaps=check("未知范围",["缺口类型","影响字段","来源集合"])
    gaps_complete=scope_parts["未知范围"]["coverage"]==1
    score_unknown=(int(all(unknown_detail) and all(unknown_summary))+int(gaps["passed"] and gaps_complete))/2
    # C5来源真实性与事件关联、双边调拨复算是三个证据单元。
    origin=check("库存明细",["期初来源","状态来源","有效事件ID"])
    event_origins=check("事件索引",["来源集合"])
    all_sources=check("来源索引",gt["headers"]["来源索引"])
    transfer=check("调拨核对",gt["headers"]["调拨核对"])
    trace_units=[origin["passed"],passed(event_origins,all_sources) and scope_parts["来源索引"]["coverage"]==1,transfer["passed"] and scope_parts["调拨核对"]["coverage"]==1]
    score_trace=1 if all(trace_units) else .5 if any(trace_units) else 0
    scores=dict(zip(WEIGHTS,[score_scope,score_state,score_class,score_unknown,score_trace]))
    if not actual: scores={k:0 for k in WEIGHTS}
    diag={"read_status":read_status,"C1_objects":scope_parts,"C2_units":{"实物还原":physical,"事件有效状态":event_state,"质量状态":quality,"冻结账":freeze},"C3_units":{"批次分类":classify,"仓品指标":summary,"已知风险分类":risk},"C4_units":{"明细标记全量正确":all(unknown_detail),"汇总标记全量正确":all(unknown_summary),"缺口表":gaps},"C5_units":{"期初状态与事件索引":origin,"事件来源":event_origins,"来源索引":all_sources,"双边调拨":transfer},"process_note":"规则不判断实际读取或主动验收；C1_actual与C7_audit须真实轨迹。"}
    evdir=root/"评分证据"; evdir.mkdir(exist_ok=True)
    # 全量候选摘要及差异定位：不把GT原值送入候选执行空间。
    evidence={"schema_version":1,"generated_after_candidate_completion":True,"candidate_file":"results/批次质量库存分析.xlsx","read_status":read_status,"rule_scores":scores,"diagnostics":diag,"trace_requirement":"Judge必须收到真实外部调用、实际对象、返回以及候选回答；本目录仅为产物提取，不能替代轨迹。","extraction_limitations":"保留全部库存业务值及初始/状态来源，省略长有效事件ID串；事件来源全量检查详见规则诊断，必要时回查候选原工作簿。矩阵行以业务主键定位。"}
    def emit(name,obj):
        (evdir/name).write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":"),default=str),encoding="utf-8")
    emit("00_规则诊断.json",evidence)
    # 每个声明证据文件低于20k字符；全量矩阵降低重复列名开销。
    for order,table in enumerate(["风险说明","验收记录","未知范围","仓品结构","库存明细"],1):
        headers=[h for h in gt["headers"][table] if h!="有效事件ID"]
        rows=[[r.get(h) for h in headers] for r in actual.get(table,[])]
        chunk=[];part=1
        for row in rows:
            test={"sheet":table,"columns":headers,"rows":chunk+[row],"truncated":False}
            if len(json.dumps(test,ensure_ascii=False,default=str))>17000 and chunk:
                emit(f"{order:02}_{table}_{part:02}.json",{"sheet":table,"columns":headers,"rows":chunk,"truncated":False});part+=1;chunk=[]
            chunk.append(row)
        emit(f"{order:02}_{table}_{part:02}.json",{"sheet":table,"columns":headers,"rows":chunk,"truncated":False})
    return {**scores,"overall_score":sum(WEIGHTS[k]*v for k,v in scores.items())/78,"diagnostics":diag}

```

## LLM Judge Rubric

只依据实际投递的Prompt、公开口径、候选产物和真实执行轨迹。自动提取的产物全文位于judge_evidence，含96行仓品摘要、未知清单、风险说明和验收记录，原工作簿可用于核查。按本包实际规模判断，不以私有参考措辞作唯一答案。真实轨迹缺失、正文缺失或关键工具回执缺失时按上述不可判定协议，不猜测候选行为，不索取隐藏思考。

### Criterion 1: 实际处理覆盖公开库存范围 (key: C1_actual, weight: 4)

**Score 1.0**: 真实操作及返回证明采用本次公开资料全部目标仓、公开列出的全部sheet及有效区块（含隐藏行），按公开时间界限处理，产物与对应对象一致；未观察到源文件改写。只读判断须结合真实操作，不凭首尾哈希相同推断全过程。
**Score 0.5**: 真实操作及产物证明至少一个目标仓的期初、事件和质量资料已实际处理，但可观察证据显示遗漏部分目标范围或有效区块；未将已知无关资料作为本包事实。仅缺评测采集证据须不可判定，不落此档。
**Score 0.0**: 完整轨迹及产物证明没有实际处理上述最小关联范围、混用非目标材料，或明确改写原始输入。仅产物缺失且轨迹完整显示未完成此范围亦为0；轨迹缺失按不可判定协议。

### Criterion 2: 已知库存结构与保障风险说明 (key: C6_risk, weight: 10)

本项有四个公开问题单元，每个必须给出正确结论及可回查依据才算满足：①各仓可用、冻结受限及拒收结构，同时限定已知范围；②正确定位可确认仓品的优先保障缺口，避免未知按0排序；③正确解释部分解冻、待检和拒收的两轴关系，允许由公开口径或结果依据支撑，不强制具体案例数量；④列清影响判断的期初或状态缺口，并提出针对其影响的补证材料。接受等价有据结论及排序并列；不要求固定图表、字数或参考措辞。错误因果或把未知总量说成完整量，会使相关单元不满足，不另加扣分项。

**Score 1.0**: 四个问题单元均满足。
**Score 0.75**: 满足三个问题单元。
**Score 0.5**: 满足两个问题单元。
**Score 0.25**: 满足一个问题单元。
**Score 0.0**: 四个问题单元均不满足，或完整证据证明未交付风险分析。正文未采集时不可判定。

### Criterion 3: 实际库存验收覆盖 (key: C7_audit, weight: 8)

核对四个公开领域：①全目标sheet及事件来源完整性；②全部调拨双边及跨仓守恒；③全部批次库存恒等式、互斥分类和未知边界；④仓品汇总分母、风险结论及证据。领域满足须真实操作/返回及验收记录共同证实确有比较判断、范围、结果和证据位置；查出差异且诚实记录同样算执行核对，不要求每次结果通过。只有代码未运行、读取行数、声称通过或评分器后来得到正确结果均不能证明主动核对。允许任何等价方法，不要求另交脚本。

**Score 1.0**: 四个领域均有实际核对证据。
**Score 0.75**: 三个领域有实际核对证据。
**Score 0.5**: 两个领域有实际核对证据。
**Score 0.25**: 一个领域有实际核对证据。
**Score 0.0**: 完整轨迹证明四领域均未实际核对；或只有泛化验收声明而真实操作没有比较判断。轨迹或回执缺失须不可判定。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_003_batch_quality_available_inventory

## Skills

## Env

## Warmup
