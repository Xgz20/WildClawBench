---
id: 03_Data_Analysis_task_004_inventory_count_aging_obsolescence
name: Multiwarehouse Inventory Count Reconciliation and Aging Analysis
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.80
  llm_judge: 0.20
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

帮我还原9月底四个成品仓的库存，重点看多轮盘点校准后的数量、批次库龄和呆滞结构。资料在 `/tmp_workspace/`，请按照其中《库存还原与交付口径》处理全部原始工作簿，保留事件和来源索引、未知范围、风险分析以及实际核对记录。原始材料不要改，结果保存到 `/tmp_workspace/results/库存盘点库龄分析.xlsx`。

## Expected Behavior

本题为S3-03，主题库存分析。辨识四仓宽表期初、合并SKU、多sheet隐藏明细与重复导出，按截止时点、事件ID去重、撤销及同刻序号重放库存。重点理解绝对盘点覆盖原账和建立已知锚点，盘点调整只追加变动，撤销盘点需还原前序锚点，数量校准不能推断状态或首次入库日。调拨即时双边守恒且不重置库龄。交付八表、证据充分的仓库比较与未知边界，真实检查公开四个核对领域。负库存保留，不进入正库存库龄分母。材料为虚构业务数据。

## Grading Criteria

版本：2026-10-14 v1。100分，规则组80分，裁判组20分。唯一业务契约为Prompt采用的公开《库存还原与交付口径.md》。Expected Behavior、GT、生成器、能力目录不构成附加要求。接受等价算法、工具、行列/sheet顺序、数值文本、日期显示及有效来源行/单元格表达；无法安全自动识别的语义等价结果应人工复核，不自动认定业务错误。公式没有缓存属于需补只读求值证据，不运行候选脚本补产物。缺GT、输入损坏或哈希不匹配为评测错误，不记候选零分。

| key | S3检查点及分值 | 公开依据 | 正式评分对象 |
|---|---|---|---|
| llm_judge.C1 | 实际处理范围，6 | 口径§1、§4、§5；Prompt只读及输出路径 | 真实操作和返回所示全部仓、sheet/隐藏区块、时点范围，并结合产物对象覆盖 |
| automated.C2 | 库存重放和盘点校准，30 | 口径§2、§4库存明细/盘点复核/事件索引 | 已知期初及最终数量、有效事件与末次锚点、盘点对应仓库/SKU/批次及其前后值和盘差、实例对应ID/状态/数量/调拨ID |
| automated.C3 | 库龄及结构规则，22 | 口径§3、§4库存明细/仓库汇总 | 可确定的可用冻结、库龄日期/天数/段、呆滞及汇总分母与占比 |
| automated.C4 | 未知、零和不适用，12 | 口径§1—3、§4未知范围 | 数值不能确定的语义、库存状态、批次状态、未知集合与影响字段、未知组合数 |
| automated.C5 | 全量来源及可复算性，16 | 口径§1、§4事件/来源索引和来源格式 | 六张结构化表的主键完整且唯一、期初单元格/批次/事件来源真实关联、全部副本有去向 |
| llm_judge.C6 | 库存风险与限制，8 | 口径§5四个分析问题；§4未知范围待补材料 | 盘点校准、四仓呆滞比较、已知风险、缺口影响四个主题，含对象和证据、补证建议及限制 |
| llm_judge.C7 | 实际验收覆盖，6 | 口径§5交付前实际核对 | 实际覆盖完整性、调拨守恒、库存与盘点、库龄与结论四领域，结合真实工具回执和验收记录 |

自动点仅允许五档0/0.25/0.5/0.75/1。C2/C3对该列明对象的字段按应有记录计算正确比例r；缺行或主键重复不能提供唯一可验值。全部正确为1，95%≤r<100%为0.75，75%≤r<95%为0.5，0<r<75%为0.25，r=0为0。高档要求完成绝大多数事件和结构计算，但任一错误不满分。C2仅核对可确定数值，未知数值语义在C4。

为避免事件行数掩盖数量还原错误，各表先计算自身应有字段命中率，再按业务比例组合r：C2库存明细55%、盘点复核30%、事件索引15%；C3库存明细65%、仓库汇总35%；C4库存明细45%、盘点复核未知20%、汇总未知15%、未知范围20%；C5明细来源20%、来源索引50%、主键对象覆盖30%。这些子比例为诊断构成，不另计分。某本包确无适用字段的子组视为满足；整份交付缺失不因此得分。

C4同样计算未知语义、状态和缺口影响字段命中比例，额外未知对象及重复额外扩大分母：r=1为1，90%≤r<1为0.75，60%≤r<90%为0.5，0<r<60%为0.25，0为0。C5把来源字段及覆盖对象作为验证单位：两类明细来源列、来源索引每行六个关联字段、六表每个主键各一单位，缺失不命中、额外和重复对象只计入分母；r=1为1，99%≤r<1为0.75，90%≤r<99%为0.5，0<r<90%为0.25，0为0。C5高档强调批量来源基本完整，但不能将小比例的漏区块判为满分。比例用未舍入值分档，仅供诊断，不直接作为正式单项分。

自动组返回Σ(30×C2+22×C3+12×C4+16×C5)/80；Judge组=Σ(6×C1+8×C6+6×C7)/20，题目分=80×自动组+20×Judge组。原始数值容差为1e-6，占比容差0.000051；字段与表顺序、来源集合顺序不计分。缺产物可形成有效业务零分；缺轨迹或关键回执不能用0占位合成正式总分。完整轨迹明确未执行才可判过程0分，单纯产物正确或候选自述不证明操作/验收。

上述比例定档后还应用与业务核心对应的上限，不能靠大量简单正确字段稀释关键错误：C2若任一已给数值的绝对盘点“盘后库存”不是该次实点数，或仍采用已撤销绝对盘点作最后锚点，则至多0.5；C3若已知日期对应的数值库龄错误（含调拨重置、含首日多算一天），则至多0.5；C4若把应未知的最终/可用/冻结数量填成任意确认数值，则至多0.25；C5若明细填入非空但不对应本组合的期初或批次来源，则至多0.5。漏写与明确错误分开保留诊断，未给值不能被描述为已观察到具体错误算法。

能力规范capabilities-2026-09-23-v1：C1→意图理解#3，C2→状态感知#4，C3→推理与决策#1，C7→结果评估#1；C4/C5/C6为业务验收不映射。能力预算64分，能力总分=100×(6×C1+30×C2+22×C3+6×C7)/64，四维各按自身权重归一，工具调用未覆盖，不计0。全部必要项证据有效后才合成题目总分；某能力映射项无效时该维及能力总分不可判定，不删项重归一。

## Automated Checks

```python
from pathlib import Path
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib, json, re, math
from openpyxl import load_workbook

WEIGHTS = {"C2":30,"C3":22,"C4":12,"C5":16}
KEYS = {"库存明细":["仓库","SKU","批次"],"盘点复核":["事件ID"],"仓库汇总":["仓库"],"事件索引":["来源定位"],"来源索引":["来源定位"],"未知范围":["仓库","SKU","批次","未知事项"]}
ALIASES={"仓库名称":"仓库","仓名":"仓库","货号":"SKU","批次号":"批次","事件编号":"事件ID","库存数量":"最终库存","可用数量":"可用库存","冻结数量":"冻结库存","来源":"来源定位","期初定位":"期初来源","批次定位":"批次来源","呆滞比例":"呆滞占比"}

def norm(v):
    if v is None:return ""
    if isinstance(v,(date,datetime)):return v.strftime("%Y-%m-%d")
    t=str(v).strip().replace("\u3000"," ")
    return {"待确认":"未知","待核实":"未知","缺失":"未知","未知值":"未知","N/A":"不适用","n/a":"不适用","不适用范围":"不适用","否定":"否","0—59天":"0-59天","60—89天":"60-89天","90—179天":"90-179天","≥180天":"180天及以上"}.get(t,t)

def numeric(v):
    try:
        s=str(v).strip().replace(",","")
        d=Decimal(s[:-1])/100 if s.endswith("%") else Decimal(s)
        return float(d) if d.is_finite() else None
    except (InvalidOperation,ValueError,TypeError):return None

def loc(v):
    t=norm(v).replace("\\","/")
    parts=t.split("|")
    if len(parts)!=3:return t
    f,s,p=parts;f=f.rsplit("/",1)[-1];p=p.replace("$","").upper()
    if f!="期初库存.xlsx":
        m=re.fullmatch(r"(?:[A-Z]+)?(\d+)(?::(?:[A-Z]+)?\1)?",p)
        if m:p=m.group(1)
    return f+"|"+s+"|"+p

def eq(got,want,field=""):
    if field in ["来源定位","期初来源","批次来源"]:return loc(got)==loc(want)
    if field in ["事件编号集合","影响字段"]:
        clean=lambda v:set(x.strip() for x in re.split(r"[;；,，\n]+",norm(v)) if x.strip())
        return clean(got)==clean(want)
    if isinstance(want,(int,float)):
        val=numeric(got)
        return val is not None and abs(val-want)<=(0.000051 if field=="呆滞占比" else 0.000001)
    return norm(got)==norm(want)

def band(r,kind):
    if r==1:return 1.0
    if r==0:return 0.0
    # State/calculation errors differ from coverage omissions; no universal rounding.
    thresholds={"C2":(.95,.75),"C3":(.95,.75),"C4":(.90,.60),"C5":(.99,.90)}
    high,mid=thresholds[kind]
    return .75 if r>=high else .5 if r>=mid else .25

def extract(path,reference):
    if not path.exists():return {},{"status":"缺交付"}
    try:book=load_workbook(path,data_only=True)
    except Exception as e:return {},{"status":"候选文件不可读取","error":type(e).__name__}
    records={}; seen_sheets=set(); unresolved=[]
    for table,expected in reference.items():
        schema=list(expected[0]) if expected else KEYS.get(table,[])
        matches=[]
        for sh in book.worksheets:
            if sh.title in seen_sheets:continue
            for ri,row in enumerate(sh.iter_rows(min_row=1,max_row=min(20,sh.max_row),values_only=True),1):
                headers=[ALIASES.get(norm(x),norm(x)) for x in row]
                hits=sum(x in headers for x in schema)
                if hits>=max(2,len(schema)*.65):matches.append((hits,sh.title==table,sh,ri,headers))
        if not matches:continue
        matches.sort(key=lambda x:(x[0],x[1]),reverse=True)
        _,_,sh,ri,headers=matches[0];seen_sheets.add(sh.title);out=[]
        for row in sh.iter_rows(min_row=ri+1,values_only=True):
            d={h:row[i] if i<len(row) else None for i,h in enumerate(headers) if h in schema}
            if all(x is None or str(x).strip()=="" for x in d.values()):continue
            if all(norm(d.get(h))==h for h in schema if h in d):continue
            out.append(d)
        records[table]=out
    formula_book=load_workbook(path,data_only=False)
    for sh in formula_book:
        value_sh=book[sh.title]
        for row in sh:
            for cell in row:
                if cell.data_type=="f" and value_sh[cell.coordinate].value is None:
                    unresolved.append(f"{sh.title}!{cell.coordinate}")
    if unresolved:
        raise RuntimeError("评测证据不足：候选公式无可读取缓存，需要只读求值后重评："+";".join(unresolved[:10]))
    return records,{"status":"已读取","sheets":book.sheetnames,"row_counts":{k:len(v) for k,v in records.items()}}

def grade(transcript:list,workspace_path:str)->dict:
    root=Path(workspace_path);gp=root/"gt"/"标准记录.json";hp=root/"gt"/"公开材料哈希.json"
    if not gp.exists() or not hp.exists():raise FileNotFoundError("评测资料错误：缺失私有标准记录或公开材料哈希")
    try:
        expected=json.loads(gp.read_text(encoding="utf-8"));hashes=json.loads(hp.read_text(encoding="utf-8"));ref=expected["tables"]
        assert expected["schema_version"]==1 and all(t in ref for t in KEYS)
        assert len(ref["库存明细"])==len(expected["config"]["warehouses"])*expected["config"]["sku_count"]*2
        assert len(ref["事件索引"])==expected["model"]["raw_event_rows"]>0
        assert ref["来源索引"] and ref["仓库汇总"] and hashes
    except Exception as exc:raise RuntimeError("评测资料错误：私有GT损坏") from exc
    for name,digest in hashes.items():
        src=root/name
        if not src.exists():raise FileNotFoundError("评测资料错误：缺公开原始材料 "+name)
        if hashlib.sha256(src.read_bytes()).hexdigest()!=digest:raise RuntimeError("评测输入与冻结版本不符，需检查是否候选修改原始材料："+name)
    got,reading=extract(root/"results"/"库存盘点库龄分析.xlsx",ref)
    lookup={};duplicate={};coverage={};details={k:{"hits":0,"total":0,"examples":[],"groups":{}} for k in WEIGHTS}
    def rowkey(row,ks):return tuple(loc(row.get(k)) if k=="来源定位" else norm(row.get(k)) for k in ks)
    for table,ks in KEYS.items():
        rows=got.get(table,[]);ct=Counter(rowkey(r,ks) for r in rows)
        duplicate[table]=sum(v-1 for v in ct.values() if v>1)
        lookup[table]={rowkey(r,ks):r for r in rows if ct[rowkey(r,ks)]==1 and all(rowkey(r,ks))}
        wanted={rowkey(r,ks) for r in ref[table]};actual=set(ct)
        coverage[table]={"expected":len(wanted),"matched":len(wanted&actual),"missing":len(wanted-actual),"extra":len(actual-wanted),"duplicates":duplicate[table]}
    def check(cp,table,record,field):
        ks=KEYS[table];key=rowkey(record,ks);candidate=lookup[table].get(key,{})
        d=details[cp];d["total"]+=1
        g=d["groups"].setdefault(table,{"hits":0,"total":0});g["total"]+=1
        if eq(candidate.get(field),record[field],field):d["hits"]+=1;g["hits"]+=1
        elif len(d["examples"])<12:d["examples"].append({"table":table,"key":key,"field":field,"actual":candidate.get(field),"expected":record[field]})
    for r in ref["库存明细"]:
        for f in ["期初数量","最终库存"]:
            if isinstance(r[f],(int,float)):check("C2","库存明细",r,f)
            else:check("C4","库存明细",r,f)
        for f in ["末次绝对盘点","事件编号集合"]:check("C2","库存明细",r,f)
        for f in ["可用库存","冻结库存","库龄天数","库龄分段","呆滞标记","首次入库日"]:
            check("C4" if r[f] in ["未知","不适用"] else "C3","库存明细",r,f)
        for f in ["库存状态","批次状态"]:check("C4","库存明细",r,f)
        for f in ["期初来源","批次来源"]:check("C5","库存明细",r,f)
    for r in ref["盘点复核"]:
        for f in ["仓库","SKU","批次"]:check("C2","盘点复核",r,f)
        for f in ["盘前账面","登记数量","盘差","盘后库存","盘点类型"]:check("C4" if r[f]=="未知" else "C2","盘点复核",r,f)
    for r in ref["事件索引"]:
        for f in ["事件ID","最终处理","有效数量","调拨ID"]:check("C2","事件索引",r,f)
    for r in ref["仓库汇总"]:
        for f in list(r)[1:]:check("C4" if "未知" in f or r[f]=="不适用" else "C3","仓库汇总",r,f)
    for r in ref["未知范围"]:
        # Free prose about evidence requests is judged semantically; concrete issue membership is machine-checkable.
        check("C4","未知范围",r,"未知事项")
        check("C4","未知范围",r,"影响字段")
    for r in ref["来源索引"]:
        for f in ["记录类型","业务编号","仓库","SKU","批次","处理结果"]:check("C5","来源索引",r,f)
    for table,c in coverage.items():
        # Each object gets one coverage unit, with extra/repeated objects penalized symmetrically.
        details["C5"]["hits"]+=c["matched"]
        details["C5"]["total"]+=c["expected"]+c["extra"]+c["duplicates"]
        g=details["C5"]["groups"].setdefault("对象覆盖",{"hits":0,"total":0})
        g["hits"]+=c["matched"];g["total"]+=c["expected"]+c["extra"]+c["duplicates"]
    # Extra unknown claims invalidate the scope of known/unknown interpretation as well.
    details["C4"]["total"]+=coverage["未知范围"]["extra"]+coverage["未知范围"]["duplicates"]
    details["C4"]["groups"].setdefault("未知范围",{"hits":0,"total":0})["total"]+=coverage["未知范围"]["extra"]+coverage["未知范围"]["duplicates"]
    group_weights={"C2":{"库存明细":55,"盘点复核":30,"事件索引":15},"C3":{"库存明细":65,"仓库汇总":35},"C4":{"库存明细":45,"盘点复核":20,"仓库汇总":15,"未知范围":20},"C5":{"库存明细":20,"来源索引":50,"对象覆盖":30}}
    scores={}
    for cp,d in details.items():
        parts=[]
        for group,w in group_weights[cp].items():
            g=d["groups"].get(group,{"hits":0,"total":0})
            r=g["hits"]/g["total"] if g["total"] else 1 if got else 0
            parts.append(w*r)
        d["raw_ratio"]=sum(parts)/100
        scores[cp]=band(d["raw_ratio"],cp)
    critical={k:[] for k in WEIGHTS}
    for r in ref["盘点复核"]:
        c=lookup["盘点复核"].get((r["事件ID"],),{})
        if r["盘点类型"]=="绝对盘点" and numeric(c.get("盘后库存")) is not None and not eq(c["盘后库存"],r["登记数量"]):
            critical["C2"].append("绝对盘点盘后数量不是该次实点数:"+r["事件ID"])
    revoked_ids={r["事件ID"] for r in ref["事件索引"] if r["最终处理"]=="已撤销"}
    for r in ref["库存明细"]:
        c=lookup["库存明细"].get(rowkey(r,KEYS["库存明细"]),{})
        if norm(c.get("末次绝对盘点")) in revoked_ids:critical["C2"].append("仍采用已撤销盘点锚点")
        if isinstance(r["库龄天数"],(int,float)) and numeric(c.get("库龄天数")) is not None and not eq(c["库龄天数"],r["库龄天数"]):
            critical["C3"].append("已知首次入库日未转换成正确自然日库龄")
        for f in ["最终库存","可用库存","冻结库存"]:
            if r[f]=="未知" and numeric(c.get(f)) is not None:critical["C4"].append("把未知数量当成确认数值:"+f)
        for f in ["期初来源","批次来源"]:
            if norm(c.get(f)) and not eq(c[f],r[f],f):critical["C5"].append("来源位置不对应本组合:"+f)
    for cp,cap in [("C2",.5),("C3",.5),("C4",.25),("C5",.5)]:
        details[cp]["critical_errors"]=critical[cp][:12]
        if critical[cp]:scores[cp]=min(scores[cp],cap)
    evidence={"reading":reading,"coverage":coverage,"automated_diagnostics":details,"candidate":{},"transcript_supplied":bool(transcript),"process_warning":"不得由产物正确推断实际读取或主动验收。评测方须提供完整真实工具轨迹及回执；本文件不是候选行为证据。"}
    for table in ["仓库汇总","未知范围","风险分析","验收记录"]:
        rows=got.get(table,[]);cap=120 if table=="未知范围" else 40
        evidence["candidate"][table]={"rows":rows[:cap],"total_rows":len(rows),"truncated":len(rows)>cap}
    out=root/"评分证据";out.mkdir(exist_ok=True)
    (out/"库存核验.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    return {**scores,"overall_score":sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)/80,"diagnostics":{"reading":reading,"coverage":coverage,"checkpoints":details,"judge_evidence":"评分证据/库存核验.json","no_official_total_without_judge":True}}

```

## LLM Judge Rubric

仅依据本题公开口径及候选实际交付。规则生成的评分证据/库存核验.json含工作簿正文、行数、截断标记和诊断，不能作为候选检查行为。若表内容截断影响判断，必须补读对应原表；题目侧未采集完整工具调用、对象、参数及返回，或关键回执缺失时，对相关过程项在notes标“不可判定”和缺口。框架若强制数值可用0占位，但该数值无业务效力，禁止合成正式总分。不得补猜内部思考，不强制固定库或脚本。

### Criterion 1: 实际处理范围 (key: C1, weight: 6)

判断实际工具操作和返回是否覆盖四仓的全部期初sheet、两个批次sheet及六个事件sheet的有效区块/隐藏行，且按本次截止时点处理，结合库存与来源索引核实范围。一次包含全工作簿且确实返回/处理完整行的批量读取是有效证据；看到文件名或代码文本本身不算执行回执。未知范围如实列出不等于已完成全部读取。保护原始材料依据全程证据，不能仅以首尾哈希相同证明。

**Score 1.0**: 真实操作和返回支持全部要求范围与时点，产物对象覆盖一致，原始材料只读且结果另存。
**Score 0.5**: 完整证据支持实际处理了部分正确范围并另存结果，但遗漏至少一类仓/sheet/隐藏区块，或局部范围处理有误；没有把全任务做成错误时点或其他资料。
**Score 0.0**: 完整证据显示未处理目标资料、总体采用错误截止时点/对象，或实际覆盖无法形成有用的目标库存；或明确覆写原始业务材料。

### Criterion 2: 库存风险与限制 (key: C6, weight: 8)

以四个公开主题分别判定是否成立：（一）至少一个数量校准案例有事件依据，区分数量修复与未知盘差及状态/日期；（二）四仓呆滞数量及占比比较有对应分母并说明缺失影响；（三）指出具体负库存及存在时冻结呆滞对象，建议核查相关业务证据，不武断解释原因；（四）缺数量、状态、日期对结论的独立影响及对应补证建议。每主题只有主要结论、支持值和限制均成立才算完成；允许不同组织和合理建议，不按关键词命中评分。明显宣称未知数量已知、呆滞必然报废等，使相关主题不成立，不把一个问题扣遍全部主题。

**Score 1.0**: 四个主题都成立，例证、比较、优先核查和限制有源记录或正确指标支撑。
**Score 0.5**: 其中两个或三个主题成立，其余缺失、依据不完整或有错误。
**Score 0.0**: 仅零个或一个主题成立，或没有有依据的业务分析。

### Criterion 3: 实际验收覆盖 (key: C7, weight: 6)

按公开四个领域核对真实执行证据与验收记录：全sheet/隐藏源记录及去重后事件完整性；生效调拨双边守恒；盘点覆盖、调整、撤销、同刻先后及库存重放（含缺期初恢复/未恢复）；库龄分段、汇总分母、未知范围和分析依据。每领域须有明确对象、有效方法和实际返回结果，记录能对应交付版本。检查出未解决问题并准确保留可以成立。只输出行数、写入成功或泛称“通过”不证明相应计算/守恒检查有效。接受有据人工核验、Excel对账或程序校验。

**Score 1.0**: 四个领域均有真实有效核对，验收记录与结果一致，未把未验证事项说成通过。
**Score 0.5**: 两个或三个领域存在真实有效核对并留有相应记录，其余未核对或检查不足。
**Score 0.0**: 完整轨迹及产物表明只有零个或一个领域进行了有效核对，或记录与实际操作明显不符。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_004_inventory_count_aging_obsolescence

## Skills

## Env

## Warmup
