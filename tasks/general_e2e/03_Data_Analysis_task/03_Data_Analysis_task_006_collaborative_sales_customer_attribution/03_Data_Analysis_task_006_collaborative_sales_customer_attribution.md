---
id: 03_Data_Analysis_task_006_collaborative_sales_customer_attribution
name: Collaborative Sales Allocation and Customer Attribution
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.70
  llm_judge: 0.30
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

帮我整理8—9月的销售，看看三个部门的协销贡献、客户归属迁移，以及各地区和渠道的变化。资料都在 `/tmp_workspace/`，请按其中口径和交付说明做一份能核对的分析工作簿，保留明细、来源、缺口、图表和验收记录。原始材料不要改，结果放到 `/tmp_workspace/results/协销分析.xlsx`。

## Expected Behavior

采用公开《协销分析口径与交付说明》，处理2026年8—9月全部公开订单，退款观察截至2026年10月5日。有效业务来自三份地区订单簿、协销方案、退款流水、客户归属六个工作簿，共21个业务sheet；隐藏明细、重复标题、中间小计及页尾说明均按公开范围处理。

按客户ID及订单生效日期关联归属历史，按订单行ID关联退款及生效协销方案，选择订单日已生效的最大版本。客户同名不合并，不能把月末新归属覆盖此前订单。一单多部门不放大集团净额，退款沿原单月份及原方案归回。转换箱/件与文本数值；金额统一为元、单价为元/件，金额和单价固定显示两位小数，应用折扣、取消及退款状态。原始订单、退货及集团实物数量为整数；部门分摊净销量允许小数，明确标注为折算贡献量。部门分位尾差按公开排序分配；方案缺失或比例不闭合，整单保留在未分配池。渠道未知与归属缺口不抹掉可确认经济净额，真实零额与取消分别标示。

按交付说明核心字段形成订单净额、退款核对、协销贡献、月度汇总、渠道结构、客户迁移、缺口清单、来源索引、范围核对、分析说明与验收记录。交付两张可读、标明口径的图表。分析销售规模、地区渠道结构、部门贡献与客户迁移，保留缺口和因果边界，并实际核对范围、关联、守恒和图表结论。

## Grading Criteria

本题采用S3-01。总100分，规则70分、Judge30分；七个检查点各自只取以下预先声明档位。诊断计数不另计分。

| 检查点 | 内容与公开依据 | 题目分值 | 档位 | 方式与主能力 |
|---|---|---:|---|---|
| C1 | 公开期间、全部sheet和有效区块实际处理及输出覆盖，口径第一节及范围核对 | 10 | 0/0.5/1 | 轨迹+产物，Judge；意图理解#3 |
| C2 | ID、有效日期、方案版本和客户迁移关联，口径第二、三节 | 20 | 0/0.25/0.5/0.75/1 | 规则；状态感知#3 |
| C3 | 折扣、状态、原单退款、单位、分摊及汇总守恒，口径第三、四节 | 30 | 0/0.25/0.5/0.75/1 | 规则；推理与决策#1 |
| C4 | 缺渠道、归属/方案缺口、真实零额及不适用，口径第三节和缺口清单 | 12 | 0/0.5/1 | 规则；业务验收，不映射能力 |
| C5 | 来源与明细、汇总可回查，口径第四节来源索引及来源列 | 8 | 0/0.5/1 | 规则；业务验收，不映射能力 |
| C6 | 规模结构变化分析及图表与指标一致、因果边界，口径第四节 | 12 | 0/0.5/1 | 产物+回答，Judge；业务验收，不映射能力 |
| C7 | 实际核对范围、关联、净额与分摊守恒、图表依据，口径第四节验收记录 | 8 | 0/0.5/1 | 轨迹+产物，Judge；结果评估#1 |

C2有四个业务模块：订单ID及订单日归属、退款与原单事实、采用方案的部门/版本/比例、客户月末归属和迁移。各模块仅在公开应有键集合无遗漏/重复/额外且所核字段全部正确时满足，满足0、1、2、3、4个模块分别为0、0.25、0.5、0.75、1。

C3有四个业务模块：原单及退款金额数量、逐部门分摊金额数量、月度集团/部门/未分配池汇总、渠道占比及客户迁移净额变化。模块的全量键及所核数值须正确；满足0、1、2、3、4个模块分别为0、0.25、0.5、0.75、1。集团守恒不得靠重复订单产生的膨胀总额自洽。

C4分“订单与退款状态/未知/真实零额语义”和“三类缺口事项及影响字段与可确认金额”两个业务模块；均正确为1，仅一模块正确为0.5，均不满足为0。C5分“所有公开业务明细的来源索引”和“订单、退款、采用方案及迁移快照的来源关联”两个模块；均正确为1，仅一模块正确为0.5，均不满足为0。

允许行列及工作表重排、中文百分比文本与相同比例值、来源集合顺序改变；保留公开交付核心表名及字段名。金额容差0.005001元，件数容差0.0000011，比例/占比容差0.00000005，计数和ID准确匹配。容差只吸收表示精度，不能替换公开舍入规则。参考GT缺失或损坏属于评测异常，抛出错误并阻断正式评分；候选缺交付或损坏按缺少实际内容计分。公式无缓存且评测器无法求值时须先补充只读求值证据，不能把评测器限制当成新业务义务；不得执行候选脚本来替其补交付。

组分：automated=(20×C2+30×C3+12×C4+8×C5)/70；Judge=(10×C1+12×C6+8×C7)/30。能力规范capabilities-2026-09-23-v1，映射预算68分：意图理解10、状态感知20、推理与决策30、结果评估8；工具调用未覆盖。能力总分=100×(10×C1+20×C2+30×C3+8×C7)/68。业务验收C4/C5/C6不另归入第六维。必要项不可判定不得用0占位合成正式总分，不能删项重归一。作者验证不冒充Agent/Judge实测。

## Automated Checks

```python
"""本文件全文嵌入正式题目Automated Checks；不依赖私有作者模块。"""
from pathlib import Path
from collections import Counter
import json, math, re, zipfile, xml.etree.ElementTree as ET
from openpyxl import load_workbook

def grade(transcript: list, workspace_path: str) -> dict:
    base=Path(workspace_path);ref=base/'gt'/'标准答案.json'
    if not ref.is_file():raise RuntimeError('EVALUATION_ERROR: 私有标准答案缺失，不计候选零分')
    try:
        truth=json.loads(ref.read_text(encoding='utf-8'))['tables']
        for name in ['订单净额','退款核对','协销贡献','客户迁移','月度汇总','渠道结构','缺口清单','来源索引','范围核对']:
            if not isinstance(truth[name],list) or not truth[name]:raise ValueError(name)
    except Exception as e:raise RuntimeError('EVALUATION_ERROR: 标准答案损坏') from e
    evidence=base/'评分证据';evidence.mkdir(exist_ok=True)
    target=base/'results'/'协销分析.xlsx';candidate={};errors=[];chartdata=[]
    def norm(x):
        if x is None:return ''
        if hasattr(x,'isoformat'):return x.isoformat()[:10]
        return str(x).strip()
    def eq(x,y,h):
        if y is None or y=='':return x is None or x==''
        if h.endswith('来源ID'):
            parts=lambda s:set(z.strip() for z in re.split(r'[;；\n]',str(s or '')) if z.strip())
            return parts(x)==parts(y)
        if h=='区块':
            expected=re.fullmatch(r'A(\d+):[A-Z]+\1',norm(y))
            if expected:
                rn=expected.group(1)
                if norm(x).replace('$','') in [rn,'A'+rn,rn+':'+rn]:return True
        if isinstance(y,(int,float)) and not isinstance(y,bool):
            try:
                val=float(str(x).replace(',','').replace('%',''))
                if '%' in str(x):val/=100
                tol=.005001 if h.endswith('元') else (0.0000011 if '销量' in h or '件数' in h else 0.00000005 if '比例' in h or '占比' in h else 1e-9)
                return math.isfinite(val) and abs(val-float(y))<=tol
            except Exception:return False
        return norm(x)==norm(y)
    def rows(wb, name):
        if name not in wb.sheetnames:return []
        data=list(wb[name].iter_rows(values_only=True))
        # 已公开表名与核心列名，允许前置说明和列重排。
        keys=list(truth.get(name,[{}])[0])
        if not keys:keys=['主题'] if name=='分析说明' else ['检查对象']
        headeridx=next((i for i,r in enumerate(data) if keys[0] in r),None)
        if headeridx is None:return []
        headers=[norm(x) for x in data[headeridx]]
        return [{h:(r[j] if j<len(r) else None) for j,h in enumerate(headers) if h} for r in data[headeridx+1:] if any(v is not None for v in r)]
    wb=None
    if target.is_file():
        try:
            with zipfile.ZipFile(target) as archive:
                ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for item in archive.namelist():
                    if item.startswith('xl/worksheets/') and item.endswith('.xml'):
                        tree=ET.fromstring(archive.read(item))
                        for cell in tree.findall('.//m:c',ns):
                            if cell.find('m:f',ns) is not None:
                                cached=cell.find('m:v',ns)
                                if cached is None or cached.text is None:
                                    raise RuntimeError('EVALUATION_ERROR: 公式缺少缓存，须补充安全只读求值证据：'+item+'!'+cell.get('r',''))
            wb=load_workbook(target,data_only=True)
            for name in truth:candidate[name]=rows(wb,name)
            for sh in wb:
                for i,ch in enumerate(sh._charts):
                    series=[]
                    for se in ch.series:
                        item={}
                        for a in ['val','cat','xVal','yVal']:
                            axis=getattr(se,a,None)
                            if axis is None:continue
                            for mode in ['numRef','strRef']:
                                node=getattr(axis,mode,None)
                                if node is not None:item[a]=str(node.f)
                        series.append(item)
                    chartdata.append({'sheet':sh.title,'chart_index':i+1,'type':type(ch).__name__,'series':series})
        except RuntimeError:raise
        except Exception as e:errors.append('候选工作簿不可读取: '+type(e).__name__)
    else:errors.append('缺少公开要求交付results/协销分析.xlsx')
    diagnostics={}
    def check(label,name,keys,fields):
        expected=truth[name];actual=candidate.get(name,[])
        def key(r):return tuple(norm(r.get(k)) for k in keys)
        refmap={key(r):r for r in expected};buckets={};dups=[]
        for r in actual:
            k=key(r)
            if k in buckets:dups.append(k)
            buckets[k]=r
        missing=set(refmap)-set(buckets);extra=set(buckets)-set(refmap);bad=[]
        for k in set(refmap)&set(buckets):
            wrong=[f for f in fields if not eq(buckets[k].get(f),refmap[k].get(f),f)]
            if wrong:bad.append({'key':k,'fields':wrong})
        ok=not(missing or extra or dups or bad)
        diagnostics[label]={'passed':ok,'expected':len(expected),'actual':len(actual),'missing':len(missing),'extra':len(extra),'duplicates':len(dups),'wrong_records':len(bad),'examples':bad[:4]}
        return ok
    keys={'订单净额':['订单行ID'],'退款核对':['退款ID'],'协销贡献':['订单行ID','部门'],'客户迁移':['客户ID'],'月度汇总':['月份','地区','部门'],'渠道结构':['月份','地区','渠道'],'缺口清单':['事项ID'],'来源索引':['来源ID'],'范围核对':['文件','工作表']}
    def ck(label,table,fields):return check(label,table,keys[table],fields)
    associations=[
        ck('订单与有效期归属','订单净额',['客户ID','生效日期','月份','地区','归属部门','归属记录ID']),
        ck('退款与原单','退款核对',['订单行ID','客户ID','原单月份','原单地区']),
        ck('采用协销方案','协销贡献',['月份','地区','方案版本','分摊比例']),
        ck('客户月末迁移','客户迁移',['地区','首月归属','次月归属','迁移状态'])]
    amountfields=['折后额元','退款额元','净额元','净销量件']
    oa=ck('原单金额数量','订单净额',amountfields);ra=ck('退款金额数量','退款核对',['金额元','退货件数'])
    pa=ck('协销贡献金额数量','协销贡献',amountfields)
    ma=ck('月度守恒汇总','月度汇总',amountfields)
    ca=ck('渠道同口径分母','渠道结构',['净额元','净销量件','净额占比']);mi=ck('客户迁移净额变化','客户迁移',['首月净额元','次月净额元','净额变化元'])
    semantic=ck('状态未知零额','订单净额',['渠道','订单状态','分摊状态','金额语义'])
    refundstate=ck('退款采用状态','退款核对',['采用状态'])
    gap=ck('缺口影响边界','缺口清单',['类型','对象ID','影响字段','已确认净额元'])
    source=ck('全量原始来源','来源索引',['文件','工作表','行号','记录类型','记录ID','区块'])
    lineage=[ck('订单来源关联','订单净额',['订单来源ID','归属来源ID','退款来源ID','方案来源ID']),ck('退款来源关联','退款核对',['来源ID']),ck('协销来源关联','协销贡献',['方案来源ID']),ck('迁移来源关联','客户迁移',['首月归属来源ID','次月归属来源ID'])]
    ck('范围表诊断','范围核对',['业务类型','明细行数','隐藏明细行数','非明细行数'])
    scores={'C2':sum(associations)/4,'C3':sum([oa and ra,pa,ma,ca and mi])/4,'C4':sum([semantic and refundstate,gap])/2,'C5':sum([source,all(lineage)])/2}
    def compact(table,cols=None):
        rr=candidate.get(table,[])
        cols=cols or list(truth.get(table,[{}])[0])
        return {'sheet':table,'headers':cols,'rows':[[r.get(c) for c in cols] for r in rr],'row_count':len(rr),'complete':True}
    def save(name,obj):
        txt=json.dumps(obj,ensure_ascii=False,separators=(',',':'),default=str)
        if len(txt)>19000:
            # 保留独立分片正文；不静默截断，collector取完整目录。
            if isinstance(obj,dict) and 'rows' in obj:
                rr=obj['rows'];mid=max(1,len(rr)//2)
                if len(rr)>1:
                    for j,part in enumerate([rr[:mid],rr[mid:]],1):save(name.replace('.json',f'_{j}.json'),{**obj,'rows':part,'part_rows':len(part),'complete':False,'part_of_complete_table':True})
                    return
            errors.append('证据提取预算超限:'+name)
            txt=json.dumps({'status':'不可判定','reason':'原表正文超限，需追加完整正文。','source':name},ensure_ascii=False)
        (evidence/name).write_text(txt,encoding='utf-8')
    save('01月度汇总.json',compact('月度汇总'))
    save('02渠道结构.json',compact('渠道结构'))
    save('03客户迁移.json',compact('客户迁移',['客户ID','地区','首月归属','次月归属','迁移状态','首月净额元','次月净额元','净额变化元']))
    save('04分析与核对.json',{'file':'results/协销分析.xlsx','分析说明':candidate.get('分析说明',[]),'验收记录':candidate.get('验收记录',[]),'charts':chartdata,'complete':True,'process_evidence_note':'这是产物正文与图表绑定信息，不证明Agent实际执行。C1和C7必须另结合真实工具调用与回执；缺轨迹不可判定。'})
    save('05范围诊断.json',{'file':'results/协销分析.xlsx','范围核对':compact('范围核对'),'diagnostics':diagnostics,'errors':errors,'candidate_sheets':wb.sheetnames if wb else [],'extraction':'规则评分阶段提取；不是候选验收','truncated':False})
    return {**scores,'overall_score':(20*scores['C2']+30*scores['C3']+12*scores['C4']+8*scores['C5'])/70,'diagnostics':diagnostics,'errors':errors}

```

## LLM Judge Rubric

必须同时阅读公开口径、规则生成的评分证据、最终回答，以及C1/C7所需真实工具调用与回执。证据提取记录发生在评分阶段，不能当作Agent验收。产物正确和自述“已检查”不能单独证明执行。完整轨迹证明未做才可有效0；缺轨迹/缺正文/提取超限导致不能判断时，在notes明确“不可判定”、缺失材料及受影响key。框架被迫数字占位时只能写0并明确占位，正式总分与能力总分仍阻断。不要从缺证推断行为失败，不强制特定工具或解题步骤。有效评分仅用声明档位。

### Criterion 1: 范围实际覆盖 (key: C1, weight: 10)

**Score 1.0**: 真实调用、参数、返回及产物证明处理全部六工作簿21个业务sheet、两个月三地区和隐藏明细，未混入范围外对象或非明细；范围记录可回查。
**Score 0.5**: 充分轨迹证明实际处理两个月且至少两个地区，产物保留可用业务明细，但有部分sheet/隐藏区块遗漏或混入非明细；不能满足完整范围。
**Score 0.0**: 充分证据显示未形成上述部分覆盖，或输出不是本次销售期间及对象。仅在证据充分时有效计0，缺轨迹按不可判定处理。

### Criterion 2: 结构变化分析及图表依据 (key: C6, weight: 12)

**Score 1.0**: 三组分析均有正确数值及可回查位置：集团与地区规模变化、部门协销贡献/未分配池及客户迁移、渠道结构和同口径分母；两张公开要求图表可读且数据与对应结论一致。分析说明渠道/归属/方案缺口的影响，迁移相关性不作已证实原因。
**Score 0.5**: 至少两组分析有正确量化依据且至少一张要求图表可用，关键结论不因重复金额或错误分母反向；缺少其余分析/图表或缺口解释不完整，但没有将未知归属、强制分摊或迁移因果写成已证实事实。
**Score 0.0**: 充分证据显示未达到上述部分交付，或关键结论依赖重复放大、强制分摊、错误分母或未经证明的因果判断。正文未实际送达时按不可判定处理。

### Criterion 3: 实际业务验收 (key: C7, weight: 8)

**Score 1.0**: 真实操作与回执显示实际检查全部四类对象：跨sheet及隐藏明细范围、ID/日期/版本关联、净额及部门加未分配池守恒、图表与结论依据；验收记录写明方法、实际结果和可回查位置。发现缺口且保留限制同样可满足验收，不要求所有业务问题消失。
**Score 0.5**: 充分证据显示实际检查其中两或三类，并有相应结果记录；其余未核对或仅有笼统自述。
**Score 0.0**: 充分证据显示至多检查一类，或只做文件存在/行数检查而没有相应业务对账。代码文本未执行、评分器后来提取、正确产物均不能代替实际验收；缺轨迹按不可判定处理。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_006_collaborative_sales_customer_attribution

## Skills

## Env

## Warmup
