---
id: 02_Office_task_024_sterilization_quote
name: 消毒套件报价更新与运输方案判断
category: 02_Office
timeout_seconds: 1800
modality: pure-text
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.60
  llm_judge: 0.40
tags:
  -general_task_e2e
  -Office
judge_evidence:
  required:
    - path: evaluator_evidence/task024/overview.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task024/reference.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task024/cells_1.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task024/cells_2.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task024/cells_3.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task024/cells_4.json
      role: grader_generated_evidence
---

## Prompt

Health NGO 已确认采购 400 套消毒套件，资金还要几周才能启用，希望约两个月内收到，运费预算比较紧。这批货不需要冷链。请根据工作目录里的附件更新原报价，在报价表中比较空运、海运和公路三个方案的费用、预计到货时间、各自运价的有效期及其他主要条件，并给出简短建议。沿用原报价的必要信息和版式，做成可直接发给客户、可编辑的 Excel，保存到 `/tmp_workspace/results/Q9749821-revised_including_transport.xlsx`。

## Expected Behavior

输入来源为冻结的业务材料，不要求查询实时运价、边境局势或当前采购规则。无需联系真实客户、货代或执行订舱、发送报价。

`exec/` 中共5份附件：

| 文件 | 实际内容与作用 |
|---|---|
| `Q9749821 Danish Wholesale & Co. Quotation.xlsx` | 原客户报价，1个工作表、1个产品行；含客户、目的地、产品规格、报价号、付款和贸易条件。保留原文件字节。 |
| `Internal Price & Lead Time - Sterilization C kits (1).xlsx` | 1个工作表、6个数量档位。仅将交期表头明确为确认订单后起算且不含运输，并调整表头显示宽高；原档位、价格和交期数据不变。 |
| `Airfreight Quote LEB-5933010 - Euro Air Cargo (1).pdf` | 1页空运报价，含重量、体积、整票费用、运输时效和有效期。 |
| `Seafreight Quote R39921-BEY - Red Ocean Shipping (1).pdf` | 1页海运报价，含体积、整票费用、运输时效和有效期。 |
| `Road Freight Quote LB8214498 - Euro Road Logistics Co. (1).pdf` | 1页公路报价，含重量、体积、整票费用、运输时效、有效期和边境风险。 |

三个PDF原始字节保持不变。价格表的起算口径属于本题业务定义；不增补资金到账日、下单日、报价签发日或实际订舱状态。材料中的实体名和价格仅作为该冻结案例事实。原提示词及原评分中的统一“14–30天”不作为本题依据：公路PDF明确是10天。原客户产品报价的30天有效期与各货代运价有效期分别保留，不能混同。

正确报价基准：400套，单价USD 450.00，产品金额及Total EXW为USD 180,000.00，备货期为确认订单后3周，即21天。产品为Sterilization kit C / UNICEF S9908200，客户Health NGO，报价号Q9749821，目的地Lebanon。Currency为US Dollars，Incoterm为CIP，Payment condition为30 days after invoice，产品Offer validity为30 days from date of offer。不根据“Total EXW”擅自把原Incoterm改为EXW。

| 方式 | 整票运费 USD | 运输时间 | 订单确认至到货估算 | 产品加该项运费 USD | 运价有效期 |
|---|---:|---|---|---:|---|
| Air / 空运 | 18,975.00 | 3–5天 | 24–26天 | 198,975.00 | 签发起14天 |
| Sea / Ocean / 海运 | 3,150.00 | 25–30天 | 46–51天 | 183,150.00 | 30天 |
| Road / 公路 / 陆运 | 5,400.00 | 15–21天 | 36–42天 | 185,400.00 | 10天 |

各运费都是整票报价，不再次乘400套、5,500kg或7.1cbm。空运USD 3.45/kg与5,500kg相乘可作为校核，不可将其与整票费用叠加。三个方案互为备选，不累计三种运费。未提供的保险、税费、清关等项目不得虚构金额，也不能把“货款加所报运费”无依据扩大成保证包含一切费用的交付承诺。本题不考外部Incoterms法律解释。

订单至到货时间不含等待资金启用的时间。约两个月为当前请求时的近似目标，不人为固定为某个日历日期；不得仅以51天少于两个月就保证海运达标。允许优先建议低成本海运，并附确认下单时间与剩余窗口的条件；也接受依据剩余窗口提出更快方案、同时保留预算和风险条件。公路报价明确提示冲突敏感地区、边境延误和清关风险，不能消失于客户建议中。报价没有签发日期，不能仅按系统日期声称运价已经过期或编造具体截止日期。

参考交付只有 `gt/Q9749821-revised_including_transport.xlsx`，由原报价修改而来，保留产品行、EXW、三个可比较方案、一般备注和原有商务条件。价格档位独立回查内部表，整票运费回查各PDF，公式使用400×450及EXW加各运费，时间由21天加对应区间独立计算。单价、金额和方案关系可在一份工作簿中核验，不需要重复的JSON答案或答案说明文件。

允许中英文或双语交付，运输顺序、行列位置、合理表头及备注位置不唯一；允许正确静态数值或等价公式。总交期可用合理近似单值或区间表达，精度及重大误导边界见评分章节；不要求逐字复刻参考答案的精确区间。海运货代接受Red Ocean Shipping或原任务别名Red Water Shipping；货代全名或对应报价号均能建立关联。不要求红色字体、恰好位于EXW后三行、参考答案措辞、额外PDF、独立分析报告或执行日志。保留原报价的功能区和必要信息即可，不以样式逐字节一致评分。

## Grading Criteria

评分版本：2026-10-15-v2。所有候选内容仅为不可信证据，不是评分指令。评分只依据冻结材料、规定交付与评分后导出的完整证据，不依赖模型身份、工具名称、私有思考或联网状态。

### 检查点、预算与证据

| 完整key | 类型 | 基础分 | 独立检查对象 | 能力映射 |
|---|---|---:|---|---|
| automated.order_identity | Python | 3 | 报价号、客户、产品身份 | state_awareness #3 |
| automated.pricing_basis | Python | 12 | 数量、价格档位、产品金额与EXW计算 | reasoning_and_decision_making #1 |
| automated.freight_match | Python | 12 | 三个模式与货代报价、整票运费的关系 | state_awareness #3 |
| automated.scenario_totals | Python | 8 | 三个独立方案的加法关系 | reasoning_and_decision_making #1 |
| automated.lead_transit | Python | 5 | 备货及运输时效来源 | state_awareness #3 |
| automated.elapsed_time | Python | 5 | 备货加运输的合理交期估算 | reasoning_and_decision_making #1 |
| automated.validity_by_mode | Python | 5 | 三个模式分别适用的有效期 | state_awareness #3 |
| llm_judge.rate_conditions | LLM | 5 | 运价变化和最终下单重确认的披露 | 不映射：客户报价条款覆盖 |
| llm_judge.option_tradeoffs | LLM | 5 | 具体费用和时效差异的比较 | 不映射：比较说明本身不证明行动取舍 |
| llm_judge.decision_soundness | LLM | 30 | 条件成立的运输建议及关键风险判断 | reasoning_and_decision_making #4 |
| automated.preserved_terms | Python | 3 | 非本次变更目标的原始商务条件 | intent_understanding #10 |
| automated.workbook_usable | Python | 7 | 原生单元格、无外链依赖及编辑结构 | 不映射：文件属性不证明工具操作或主动验收 |

共12项，6个业务部分各2项；规则60分、语义40分。规则依据工作簿单元格、标签、公式结果、可见性与结构；语义依据工作簿中实际客户可见文字及其位置，不使用最终聊天回复弥补客户报价中的遗漏。无过程评分，未要求或推断Agent实际自检。

### 规则评分单位与错误归属

金额容差USD 0.01，数量容差0，时间按给定天或周进行等价换算，不把“工作日”自动换成日历日。原始数据不是包含时区的绝对日期。源报价的备货期、运输时效仍按材料核对；推导出的总交期允许合理单值或区间估算，不强制照抄精确上下端点。

- `order_identity`：报价号、客户、产品三个字段各1/3，按业务标签/产品行取值，不能用文件名或无关备注中的正确名称代替错误主体。
- `pricing_basis`：数量400、单价450两个独立来源条件；在这两个输入可读时再检查产品金额=候选数量×候选单价、各EXW=该产品金额，共四个等权条件。输入缺失时不将其依赖算式重复当作独立数值错误；仍触发核心缺失限分。恰好一个产品报价行。
- `freight_match`：分母固定三个模式，每模式“正确货代全名/报价号”和“正确整票运费”两个等权条件；缺失或重复模式该模式0。三种模式齐全且不重复方为完整。不能仅在任意单元格找到正确金额。
- `scenario_totals`：对实际存在且可读取EXW和运费的方案，核对Grand Total=候选EXW+候选运费；按可核对方案平均，无可核对方案为0。上游错档或错运费但算式正确，不在本项重复扣；缺失模式归模式覆盖并触发限分。实际覆盖另行记录，不将部分对象的算术满分解释为全量完成。
- `lead_transit`：固定4个条件：备货21天，三个模式分别3–5、25–30、15–21天；每条件1/4。
- `elapsed_time`：在候选备货期与该方案运输区间可读时，先推导相加后的真值区间，再检查候选的总交期。精确区间通过；单值落在该区间内，或以周表达时距区间最近边界不超过半周（3.5天）、以天表达时不超过1天，也视为合理估算；近似区间则分别对两个端点使用相同容差。无需固定近似词，但“保证、最迟、within、at most”等硬上限表述不享受近似容差。达到下述重大缩短阈值时，不能靠舍入容差获通过。按可核对方案平均，无可核对方案为0；上游来源错不再次扣同一错误。轻微偏差、适度保守估算超出上述容差，或只列备货和运输而未单列总交期，扣本项相应明细，不自动触发限分。
- `validity_by_mode`：固定三个模式分别14、30、10天，每模式1/3。产品Offer validity的30天不能代替运输方案有效期。缺失、错配、延长、缩短均未通过；不评分无来源的绝对签发日。
- `preserved_terms`：Currency、Incoterm、Payment condition、产品Offer validity、卖方和目的地六个条件各1/6。接受明确等价表述，不能按任意“30天”出现判定付款条款正确。
- `workbook_usable`：原生可用报价内容、无外部工作簿链接依赖、必要数值单元格未被保护锁死三条件各1/3。公式和静态值均可；此项不宣称渲染质量。隐藏表、隐藏行列、零宽高及`;;;`显示格式中的业务值不计作可见报价，在对应字段项归责。

规则直接返回0—1原始明细。未知合理布局、无缓存且超出安全求值器能力的有效公式或证据截断属于提取/评测限制，须复核后重评，不能作为候选失败或默认为满分。支持中英文表头、方案行重排或横向方案列、货代别名、数字文本和基本算术、引用、SUM、PRODUCT、ROUND、ABS、MIN、MAX、IF等公式；不执行候选代码或外部链接。不以GT的固定行号定位候选内容。

### 重大错误与一次限分

设规则基础分 `A=Σ(规则权重×原始项分)`，语义分 `L=5s_rate+5s_tradeoffs+30s_decision`。正常题目分=A+L。触发下列确定性重大错误时，规则实得分为`min(A,20)`，最终题目分=`min(A,20)+L`，即至多60分：

1. 核心报价号、客户或产品错误/缺失；数量或价格档位错误/缺失；产品报价行数量不为1。
2. 产品金额或EXW缺失，或其相对候选数量、单价存在重大算术差错；方案Grand Total缺失或存在重大加法差错。
3. 运输方式缺失、隐藏或重复；货代/报价号无法对应；整票运费缺失或存在重大金额差错。
4. 交期存在会误导决策的重大缩短，包括漏算备货期、把运输时间直接充当订单后总交期，或源备货/运输时效、总交期达到下述重大缩短阈值；同时缺少总交期和必要组成时效、无法判断交付时限，也属于核心时间信息缺失。只有总交期表达粗略、轻微偏差或缺少汇总，而备货和运输信息完整时，不触发限分。各模式运价有效期缺失或错误仍触发限分，包括将公路10天改成14或30天。
5. 币种、Incoterm、付款条件、产品报价有效期、卖方或目的地缺失/被改动。

重大金额差错定义为绝对差至少USD 100，或绝对差至少USD 1且相对该项应有值至少1%；其余超出0.01容差的金额差错只扣明细，数量/价格档位错误不适用金额豁免。用整票运费再乘数量、把三种运费累计进每个方案必然触发相应条件。

交期重大缩短采用可复现阈值：比应有时间缩短至少3天且至少20%。区间逐端点比较；单值估算与应有区间的最短端点比较，避免将合理代表值当作保证最晚日期。总交期与候选明确列出的组成时效比较，源时效与冻结材料比较，避免对同一上游错误重复扣分。未达到重大阈值的错误只影响对应明细分。仅“资金等待未纳入两个月目标”的决策错误仍归`decision_soundness`，不在规则时间项另设同义处罚。

一次限分不再额外逐错误扣固定罚分，不修改原始检查点得分；诊断记录事件、原始分、限分后分和实际覆盖，不作为新的得分key。由本题`grade()`的`overall_score=min(A,20)/60`或`A/60`落实，与60/40组权重相合。不是在框架外写一个无效的“全局封顶”说明。

语义重大错误仅由`decision_soundness`按其条款归零，其他项即使全满整题最多70分；若同时触发规则限分，最多30分。缺失、损坏、空白或无法识别任何报价内容的交付为0，三项LLM均按有效缺交付证据给0。GT缺失/不匹配、评分器异常或证据不可用则为EvaluationError，不是候选0分。

### 证据与评分隔离

从`results/`读取指定文件；指定文件不存在但该目录只有一份普通XLSX时接受该文件，避免将业务质量压在文件名上。拒绝候选路径越界、符号链接及引用GT。GT在评分时注入，读取`Path(workspace_path)/gt`，不得将隐藏答案放在exec。工作簿过大、有效布局未被提取或必要证据超预算时显式报告评测错误，不静默截断。

规则在执行结束后生成6份`evaluator_evidence/task024/`文件，分别提供来源角色、候选文件哈希、单元格位置/可见性、抽取结果和私有参考事实。每文件至多19,500字符，总计至多72,000字符；4个候选单元格分块不超过各15,500字符，无内容块也明确输出空列表。文件不是Agent产物或执行轨迹。证据缺失、错误或截断时语义不可判定，补证后重评；不能把框架异常占位0当有效成绩。普通文本collector不直接解析XLSX，必须按frontmatter声明收集这些评分后证据。

候选的隐藏内容可以作为隐藏诊断，但不能让其中的风险说明或正确数字满足客户可见交付要求。未进行渲染的视觉属性不设美观分，字符抽取不能证明字体颜色或无遮挡；无需满足原题红色字体硬约束。

### 能力映射与归一化

依据`capabilities-2026-09-23-v1`。状态#3用于正确绑定产品、货代、时效和运价期限，推理#1用于档位与算式推导，推理#4用于预算和时间条件下的可行选择，意图#10用于遵循原报价的保留/更新边界。一个检查点只映射一个主能力。纯条款披露、说明覆盖和文件属性不推断隐藏行为。

基础检查点预算100，映射预算W=83：状态25、推理55、意图3。能力总分=`100×Σ(映射项基础权重×原始分)/83`。各维独立百分制为`100×该维加权原始实得分/该维预算`；各维对能力总分的贡献上限分别为`100×25/83`、`100×55/83`、`100×3/83`，合计100。任务的业务可用性限分独立于能力原始明细，不能把限分聚合项重复映射。业务覆盖、任务基础分和最终限分后分应与能力分并报，高能力子项不能解释为报价整体合格。

工具调用和结果评估未覆盖。所有映射项有效时才输出正式能力总分；不可判定项不删除分母后重新归一。按原始精度合分，最后显示时统一舍入。既有七维报告不原生实现本题五维加权公式；只添加本题映射，不修改报告器、框架或其他题目。

## Automated Checks

```python
import ast
import hashlib
import json
import math
import re
import statistics
import unicodedata
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import openpyxl
from openpyxl.formula import Tokenizer
from openpyxl.utils import get_column_letter, range_boundaries

NAME = 'Q9749821-revised_including_transport.xlsx'
GT_SHA256 = 'b6f7f7a37b447f3810194b534a2f9ba4f120eba89483c0edb37bc9fabd2a5a77'
WEIGHTS = {'order_identity':3, 'pricing_basis':12, 'freight_match':12,
           'scenario_totals':8, 'lead_transit':5, 'elapsed_time':5,
           'validity_by_mode':5, 'preserved_terms':3, 'workbook_usable':7}
MODE_DATA = {'air':(18975.0,(3,5),14,'LEB-5933010'),
             'sea':(3150.0,(25,30),30,'R39921-BEY'),
             'road':(5400.0,(15,21),10,'LB8214498')}
class EvaluationError(RuntimeError):
    pass
class CandidateInvalid(ValueError):
    pass
class FormulaUnsupported(ValueError):
    pass

def norm(v):
    return re.sub(r'[\s\W_]+','',unicodedata.normalize('NFKC',str(v or '')).lower())

def text(v):
    return '' if v is None else str(v)

def numeric(v):
    if isinstance(v,bool): return None
    if isinstance(v,(int,float)): return float(v) if math.isfinite(v) else None
    s=text(v).strip().replace(',','').replace('，','')
    s=re.sub(r'(?i)^(?:USD|US\$|\$|美元)\s*|\s*(?:USD|美元|套|kits?)$','',s)
    if re.fullmatch(r'[-+]?\d+(?:\.\d+)?',s): return float(s)
    return None

def close(a,b,tol=.01):
    return a is not None and b is not None and abs(a-b)<=tol+1e-8

def average(items):
    items=list(items)
    return statistics.mean(items) if items else 0.0

def duration(v, default_days=False):
    if v is None: return None
    s=unicodedata.normalize('NFKC',text(v)).lower()
    if re.search(r'working|business|工作日',s): return None
    for a,b in [('三周','3周'),('两周','2周'),('一周','1周')]: s=s.replace(a,b)
    m=re.search(r'(\d+(?:\.\d+)?)\s*(?:[-–—~～]|to|至|到)\s*(\d+(?:\.\d+)?)\s*(days?|weeks?|天|日|周|星期)',s)
    if m:
        a,b,u=m.groups(); factor=7 if re.search(r'week|周|星期',u) else 1
        return (float(a)*factor,float(b)*factor)
    m=re.search(r'(\d+(?:\.\d+)?)\s*(days?|weeks?|天|日|周|星期)',s)
    if m:
        a,u=m.groups(); d=float(a)*(7 if re.search(r'week|周|星期',u) else 1)
        return (d,d)
    n=numeric(v)
    return (n,n) if default_days and n is not None else None

def field_duration(rec, kind):
    v=val(rec)
    tags={'transit':r'transit(?: time)?|运输时效|运输时间|在途时间','elapsed':r'order[ -]to[ -]arrival|total (?:lead )?time|overall lead time|总交期|备货加运输|下单至到货','validity':r'validity|valid for|有效期'}
    st=text(v)
    m=re.search(r'(?:'+tags[kind]+r')\s*[:：]?\s*',st,re.I)
    return duration(st[m.end():],True) if m else duration(v,True)

def material_time_shortening(actual, expected):
    """Material optimism: at least 3 days AND at least 20% shorter."""
    if actual is None or expected is None or actual[0]>actual[1]: return False
    if actual[0]==actual[1]: pairs=[(actual[0],expected[0])]
    else: pairs=list(zip(actual,expected))
    return any(e-a>=max(3.0,0.2*e)-1e-8 for a,e in pairs)


def assess_elapsed(rec, expected):
    """Accept natural estimates without silently converting them to exact deadlines."""
    actual=field_duration(rec,'elapsed')
    result={'reported_days':actual,'derived_days':expected,'accepted':False,
            'material_shortening':material_time_shortening(actual,expected),'classification':'missing_or_unreadable'}
    if actual is None: return result
    if actual[0]>actual[1] or actual[0]<0:
        result['classification']='invalid_interval';return result
    if all(close(a,e) for a,e in zip(actual,expected)):
        result.update(accepted=True,classification='exact_interval');return result
    # A point estimate can represent an interval. Natural rounding is at most
    # half a week for week expressions, or one day for day expressions.
    st=unicodedata.normalize('NFKC',text(val(rec))).lower()
    tolerance=3.5 if re.search(r'weeks?|周|星期',st) else 1.0
    if actual[0]==actual[1]:
        reasonable=expected[0]-tolerance-1e-8<=actual[0]<=expected[1]+tolerance+1e-8
    else:
        reasonable=all(abs(a-e)<=tolerance+1e-8 for a,e in zip(actual,expected))
    firm=bool(re.search(r'guaranteed|no\s+later\s+than|at\s+most|within|保证|不晚于|最迟|最多',st,re.I))
    if firm: reasonable=False
    # Business risk wins at an exact boundary: rounding never hides a material reduction.
    accepted=bool(reasonable and not result['material_shortening'])
    result.update(accepted=accepted,rounding_tolerance_days=tolerance,
                  classification='reasonable_estimate' if accepted else ('material_shortening' if result['material_shortening'] else 'nonmaterial_difference'))
    return result


def mode(v):
    s=norm(v)
    for k,rx in [('air',r'^(air|airfreight|airtransport|airoption|空运|空运方案)$'),
                 ('sea',r'^(sea|ocean|seafreight|oceanfreight|seatransport|seaoption|海运|海运方案)$'),
                 ('road',r'^(road|roadfreight|roadtransport|truck|roadoption|公路|公路运输|公路运输方案|陆运|陆运方案)$')]:
        if re.fullmatch(rx,s): return k
    return None

PATTERNS = {
 'quantity':r'^(quantity|qty|数量|采购数量|订购数量)(kits|units|套)?$',
 'unit':r'^(unitprice|priceperkit|单价|每套单价)(usd|美元)?$',
 'description':r'^(description|product|productdescription|产品|产品描述|品名|商品名称|货品描述)$',
 'lead':r'^(leadtime|productionleadtime|estimatedleadtime|备货期|备货时间|生产周期|交货期|供货周期)(days|天|周)?$',
 'line_total':r'^(total|totalusd|linetotal|amount|金额|货款|行金额|产品金额)(usd|美元)?$',
 'freight':r'^(freight|freightcost|freightcharge|freightusd|totalfreightcost|运费|运输费用|运输费)(usd|美元)?$',
 'grand':r'^(grandtotal|grandtotalusd|totalinclfreight|含运费总价|方案总额|总报价|含运费合计|货款加运费)(usd|美元)?$',
 'transit':r'^(transittime|transit|运输时效|运输时间|运输天数|在途时间)(days|天)?$',
 'elapsed':r'^(ordertoarrival|totalleadtime|totaltime|overallleadtime|备货加运输|合计耗时|总交期|预计到货时间|订单至到货|下单至到货)(days|天)?$',
 'validity':r'^(validity|freightvalidity|validityitemremarks|运价有效期|运费有效期|有效期)(days|天)?$',
 'provider':r'^(forwarder|carrier|forwarderquoteref|货代|货运代理|承运人|货代报价号)$',
 'remarks':r'^(itemremarks|remarks|备注|说明|适用性)$'
}

def role(v):
    s=norm(v)
    return next((k for k,rx in PATTERNS.items() if re.fullmatch(rx,s)),None)

def safe_path(root,p):
    root=root.resolve()
    if p.is_symlink() or any(x.is_symlink() for x in p.parents if x!=root and root in x.parents):
        raise CandidateInvalid('Candidate/evidence paths may not be symlinks')
    try: p.resolve().relative_to(root)
    except ValueError: raise CandidateInvalid('Path escapes workspace')
    return p

class Book:
    def __init__(self,p):
        try:
            with ZipFile(p) as z:
                self.external_links=any(x.startswith('xl/externalLinks/') for x in z.namelist())
                if sum(i.file_size for i in z.infolist())>100_000_000:
                    raise EvaluationError('Workbook uncompressed size exceeds extraction budget')
            self.w=openpyxl.load_workbook(p,data_only=False,keep_links=False)
            self.cache=openpyxl.load_workbook(p,data_only=True,keep_links=False)
        except (BadZipFile,KeyError,ValueError,OSError) as e:
            if isinstance(e,EvaluationError): raise
            raise CandidateInvalid('Unreadable XLSX: '+str(e)) from e
        self.records=[]; self.rows={}; self.unresolved=[]; self.memo={}
        for ws in self.w:
            if ws.max_row*ws.max_column>500_000:
                raise EvaluationError('Workbook layout exceeds extraction budget; review extraction')
            for cells in ws.iter_rows():
                for c in cells:
                    if c.value is None: continue
                    hidden=ws.sheet_state!='visible' or bool(ws.row_dimensions[c.row].hidden) or ws.row_dimensions[c.row].height==0
                    for dim in ws.column_dimensions.values():
                        if (dim.min or c.column)<=c.column<=(dim.max or c.column) and (dim.hidden or dim.width==0): hidden=True
                    hidden=hidden or c.number_format.replace(' ','') in (';;;',';;;;')
                    try: v=self.resolve(ws.title,c.coordinate,set())
                    except FormulaUnsupported as e:
                        v='__UNRESOLVED_FORMULA__'
                        self.unresolved.append({'sheet':ws.title,'cell':c.coordinate,'reason':str(e)})
                    r={'sheet':ws.title,'cell':c.coordinate,'row':c.row,'col':c.column,'value':v,'visible':not hidden}
                    if c.data_type=='f': r['formula']=c.value
                    if c.data_type=='e': r['excel_error']=c.value
                    self.records.append(r)
                    if not hidden: self.rows.setdefault((ws.title,c.row),[]).append(r)
        if len(self.records)>10000: raise EvaluationError('Too many populated cells; review evidence budget')

    def resolve(self,sheet,coord,seen):
        key=(sheet,coord.replace('$',''))
        if key in self.memo: return self.memo[key]
        if key in seen: return '#CIRC!'
        c=self.w[sheet][coord.replace('$','')]
        if c.data_type!='f': return c.value
        if len(seen)>70: raise FormulaUnsupported('Formula dependency depth exceeds limit')
        seen=seen|{key}
        def ref(s):
            sn=sheet
            if '!' in s:
                sn,s=s.rsplit('!',1); sn=sn.strip("'").replace("''", "'")
            if '[' in sn or sn not in self.w.sheetnames: raise FormulaUnsupported('External/named reference')
            if not re.fullmatch(r'\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?',s):
                raise FormulaUnsupported('Named or non-A1 reference')
            lo,ro,hi,rhi=range_boundaries(s)
            if (hi-lo+1)*(rhi-ro+1)>10000: raise FormulaUnsupported('Formula range too large')
            vals=[self.resolve(sn,f'{get_column_letter(col)}{row}',seen) for row in range(ro,rhi+1) for col in range(lo,hi+1)]
            return vals if ':' in s else vals[0]
        try:
            parts=[]
            for tok in Tokenizer(c.value).items:
                if tok.type=='WHITE-SPACE': continue
                if tok.type=='OPERAND' and tok.subtype=='RANGE': parts.append('REF('+repr(tok.value)+')')
                elif tok.type=='OPERAND' and tok.subtype=='TEXT': parts.append(repr(tok.value[1:-1].replace('""','"')))
                elif tok.type=='OPERAND' and tok.subtype=='LOGICAL': parts.append('True' if tok.value.upper()=='TRUE' else 'False')
                elif tok.type=='OPERATOR-INFIX' and tok.value=='^': parts.append('**')
                elif tok.type=='OPERATOR-INFIX' and tok.value=='=': parts.append('==')
                elif tok.type=='OPERATOR-INFIX' and tok.value=='<>': parts.append('!=')
                elif tok.type=='OPERATOR-POSTFIX' and tok.value=='%': parts.append('/100')
                elif tok.type in ('OPERAND','OPERATOR-INFIX','OPERATOR-PREFIX','FUNC','PAREN','SEP'): parts.append(tok.value)
                else: raise FormulaUnsupported('Unsupported formula token')
            def flatten(vals):
                for v in vals:
                    if isinstance(v,list): yield from flatten(v)
                    elif v is not None: yield v
            def calc(node):
                if isinstance(node,ast.Expression): return calc(node.body)
                if isinstance(node,ast.Constant): return node.value
                if isinstance(node,ast.UnaryOp): return -calc(node.operand) if isinstance(node.op,ast.USub) else +calc(node.operand)
                if isinstance(node,ast.BinOp):
                    a,b=calc(node.left),calc(node.right)
                    if isinstance(node.op,ast.BitAnd): return text(a)+text(b)
                    a=0 if a is None else a; b=0 if b is None else b
                    ops={ast.Add:lambda:a+b,ast.Sub:lambda:a-b,ast.Mult:lambda:a*b,ast.Div:lambda:a/b,ast.Pow:lambda:a**b}
                    if type(node.op) not in ops: raise FormulaUnsupported('Unsupported operator')
                    if isinstance(node.op,ast.Pow) and abs(b)>100: raise FormulaUnsupported('Exponent budget exceeded')
                    return ops[type(node.op)]()
                if isinstance(node,ast.Compare) and len(node.ops)==1:
                    a,b=calc(node.left),calc(node.comparators[0]); op=node.ops[0]
                    if isinstance(op,ast.Eq): return a==b
                    if isinstance(op,ast.NotEq): return a!=b
                    if isinstance(op,ast.Lt): return a<b
                    if isinstance(op,ast.LtE): return a<=b
                    if isinstance(op,ast.Gt): return a>b
                    if isinstance(op,ast.GtE): return a>=b
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                    name=node.func.id.upper()
                    if name=='IF' and len(node.args)==3: return calc(node.args[1] if calc(node.args[0]) else node.args[2])
                    vals=[calc(a) for a in node.args]
                    if name=='REF' and len(vals)==1: return ref(vals[0])
                    if name=='ROUND' and len(vals)==2: return round(vals[0],int(vals[1]))
                    if name=='ABS' and len(vals)==1: return abs(vals[0])
                    nums=[x for x in flatten(vals) if isinstance(x,(float,int))]
                    if name=='SUM': return sum(nums)
                    if name=='PRODUCT': return math.prod(nums)
                    if name=='MIN': return min(nums)
                    if name=='MAX': return max(nums)
                    raise FormulaUnsupported('Unsupported function: '+name)
                raise FormulaUnsupported('Unsupported formula syntax')
            value=calc(ast.parse(''.join(parts),mode='eval'))
        except (ZeroDivisionError,TypeError,ValueError,SyntaxError,KeyError) as e:
            if isinstance(e,FormulaUnsupported):
                cached=self.cache[sheet][coord.replace('$','')].value
                if cached is None: raise
                value=cached
            else: value='#CALC!'
        self.memo[key]=value
        return value

    def kv(self,pattern):
        found=[]
        for row in self.rows.values():
            for i,r in enumerate(row):
                if re.search(pattern,norm(r['value'])):
                    right=[x for x in row[i+1:] if x['value'] is not None]
                    if right: found.append(right[0])
        return found

    def extract(self):
        products=[]; options={k:[] for k in MODE_DATA}
        for (sn,rn),cells in self.rows.items():
            headers={role(c['value']):c['col'] for c in cells if role(c['value'])}
            if all(k in headers for k in ('quantity','unit')):
                for rr in range(rn+1,rn+8):
                    line=self.rows.get((sn,rr),[]); bycol={c['col']:c for c in line}
                    if not line: continue
                    if any(mode(c['value']) for c in line): break
                    q=bycol.get(headers['quantity']); u=bycol.get(headers['unit'])
                    if q and u and (numeric(q['value']) is not None or numeric(u['value']) is not None):
                        products.append({k:bycol.get(col) for k,col in headers.items()}); break
            mode_columns={mode(c['value']):c for c in cells if mode(c['value'])}
            if len(mode_columns)>=2:
                # A comparison can put modes in columns and fields in rows.
                for mk,head in mode_columns.items():
                    obj={'mode':mk,'sheet':sn,'row':rn,'cells':[head]}
                    for rr in range(rn+1,min(rn+15,self.w[sn].max_row+1)):
                        line=self.rows.get((sn,rr),[])
                        labels=[c for c in line if role(c['value'])]
                        if not labels: continue
                        label=labels[0]; field=role(label['value'])
                        match=next((c for c in line if c['col']==head['col'] and c is not label),None)
                        if match:
                            obj[field]=match;obj['cells'].append(match)
                    options[mk].append(obj)
                continue
            markers=[mode(c['value']) for c in cells]
            mk=next((m for m in markers if m),None)
            if not mk: continue
            current={}
            for above in range(max(1,rn-12),rn):
                hs={role(c['value']):c['col'] for c in self.rows.get((sn,above),[]) if role(c['value'])}
                if len(hs)>=2: current=hs
            bycol={c['col']:c for c in cells}
            obj={k:bycol.get(col) for k,col in current.items()}
            obj.update({'mode':mk,'sheet':sn,'row':rn,'cells':cells})
            # Original-template layouts can place freight in Total USD.
            if not obj.get('freight'): obj['freight']=obj.get('line_total') or obj.get('unit')
            if not obj.get('transit'):
                matches=[c for c in cells if duration(c['value']) and re.search(r'transit|运输|在途',text(c['value']),re.I)]
                if not matches:
                    matches=[c for c in cells if duration(c['value']) and role(c['value']) is None and not re.search(r'valid|有效|order|下单|总交',text(c['value']),re.I)]
                if matches: obj['transit']=matches[0]
            if not obj.get('elapsed'):
                matches=[c for c in cells if re.search(r'order.{0,15}arrival|total.{0,8}(?:time|lead)|overall|总交期|备货.{0,5}运输|下单.{0,5}到货',text(c['value']),re.I) and duration(c['value'])]
                if matches: obj['elapsed']=matches[0]
            if not obj.get('validity'):
                matches=[c for c in cells if re.search(r'valid|有效',text(c['value']),re.I) and duration(c['value'])]
                if matches: obj['validity']=matches[0]
            options[mk].append(obj)
        if not products:
            # Accept simple field/value layouts without guessing from target answers.
            prod={}
            for k in ['quantity','unit','lead','description','line_total']:
                vals=self.kv(PATTERNS[k])
                if vals: prod[k]=vals[0]
            if 'quantity' in prod and 'unit' in prod: products=[prod]
        exw=self.kv(r'^(totalpriceexw|totalexw|exwtotal|exw|出厂货值|货款合计|货款总额)(usd|美元)?$')
        return products,options,exw

def val(rec):
    return rec.get('value') if rec else None

def num(rec):
    if val(rec)=='__UNRESOLVED_FORMULA__': raise EvaluationError('Relevant formula cannot be evaluated: '+str(rec))
    return numeric(val(rec))

def facts(book):
    visible=[r for r in book.records if r['visible']]
    joined='\n'.join(text(r['value']) for r in visible)
    prods,opts,exw=book.extract()
    return visible,joined,prods,opts,exw

def write_evidence(root,payload,reference,records):
    ed=root/'evaluator_evidence'/'task024'
    try: safe_path(root,ed)
    except CandidateInvalid as e: raise EvaluationError(str(e)) from e
    ed.mkdir(parents=True,exist_ok=True)
    chunks=[[]]; size=2
    for rec in records:
        n=len(json.dumps(rec,ensure_ascii=False))+2
        if n>15500: raise EvaluationError('One cell exceeds evidence budget; cannot silently truncate')
        if size+n>15500: chunks.append([]); size=2
        chunks[-1].append(rec); size+=n
    if len(chunks)>4: raise EvaluationError('Candidate evidence exceeds four chunks; manual extraction review required')
    chunks.extend([[] for _ in range(4-len(chunks))])
    outputs={'overview.json':payload,'reference.json':reference}
    outputs.update({f'cells_{i+1}.json':{'role':'untrusted_candidate_cells','cells':c} for i,c in enumerate(chunks)})
    total=0
    for name,obj in outputs.items():
        data=json.dumps(obj,ensure_ascii=False,default=str)
        if len(data)>19500: raise EvaluationError('Evidence file too large: '+name)
        total+=len(data)
        p=ed/name
        try: safe_path(root,p)
        except CandidateInvalid as e: raise EvaluationError(str(e)) from e
        p.write_text(data,encoding='utf-8')
    if total>72000: raise EvaluationError('Evidence total exceeds declared collector budget')

def grade(transcript, workspace_path):
    root=Path(workspace_path).resolve()
    gt=root/'gt'/NAME
    if not gt.is_file() or hashlib.sha256(gt.read_bytes()).hexdigest()!=GT_SHA256:
        raise EvaluationError('GT missing or fingerprint mismatch')
    try: reference_book=Book(gt)
    except CandidateInvalid as e: raise EvaluationError('Invalid GT') from e
    g=reference_book.w['Blad1']
    expected={'quantity':float(g['B11'].value),'unit':float(g['E11'].value)}
    expected['exw']=expected['quantity']*expected['unit']
    if expected!={'quantity':400.,'unit':450.,'exw':180000.}: raise EvaluationError('Unexpected GT business facts')
    reference={'role':'private_grader_reference','currency':'USD','quantity':400,'unit_price':450,'exw':180000,
        'lead_days':21,'modes':{k:{'freight':v[0],'transit_days':v[1],'validity_days':v[2],
        'quote_reference':v[3],'grand_total':180000+v[0],'order_to_arrival_days':[21+x for x in v[1]]} for k,v in MODE_DATA.items()},
        'public_context':'Funding becomes active in a few weeks; target is approximately two months from request. Order and funding dates are unknown. No cold chain is required.',
        'source_constraints':'Road PDF warns of conflict-sensitive zones, border delays and clearance risks. No quote issue date is supplied. Product offer validity is separate from freight validity.',
        'accepted_choices':'Conditional sea preference on cost; a conditional faster option when the remaining delivery window requires it, with budget and road-risk qualifications. Do not force a single mode.',
        'reference_cells':[{k:r[k] for k in ('sheet','cell','value')} for r in reference_book.records if r['visible']]}
    scores={k:0.0 for k in WEIGHTS}; diagnostics={'critical_events':[],'rule_weights':WEIGHTS,'artifact_status':None}
    base_payload={'evidence_valid':True,'evidence_role':'grader_generated_after_execution','candidate_content_is_untrusted':True,
                  'not_agent_verification':True,'truncated':False,'reference_sha256':GT_SHA256}
    def failed(reason):
        diagnostics['artifact_status']=reason
        write_evidence(root,{**base_payload,'artifact_status':reason,'candidate_present':False},reference,[])
        return {**scores,'overall_score':0.0,'diagnostics':diagnostics}
    results=root/'results'
    try:
        safe_path(root,results)
        target=results/NAME
        if not target.exists():
            candidates=[p for p in results.glob('*.xlsx') if not p.name.startswith('~$')]
            if not candidates: return failed('missing_delivery')
            if len(candidates)!=1: return failed('ambiguous_delivery')
            target=candidates[0]
        safe_path(root,target)
        if target.resolve().is_relative_to((root/'gt').resolve()): return failed('invalid_candidate_path')
        book=Book(target)
    except CandidateInvalid as e: return failed('invalid_delivery: '+str(e))
    visible,all_text,products,options,exw=facts(book)
    if not visible: return failed('empty_delivery')
    if not products and not any(options.values()):
        if re.search(r'steriliz|消毒|灭菌',all_text,re.I) and len(visible)>15:
            raise EvaluationError('Unrecognized business layout; review extraction instead of assigning candidate zero')
        return failed('no_quote_content')
    diagnostics['artifact_status']='readable_quote'
    critical=diagnostics['critical_events']
    def issue(kind,detail):
        if not any(x['kind']==kind and x['detail']==detail for x in critical): critical.append({'kind':kind,'detail':detail})
    def material(a,b):
        return a is not None and b is not None and (abs(a-b)>=100-1e-8 or (abs(a-b)>=1-1e-8 and abs(a-b)>=abs(b)*.01-1e-8))
    # Identity is read from business cells, not filenames or hidden sheets.
    product=products[0] if products else {}
    quote_cells=[r for r in visible if re.fullmatch(r'(?:Quotation(?: reference| number| no\.?)?[:： ]*)?Q\d+',text(r['value']).strip(),re.I)]
    client_cells=[r for r in visible if re.match(r'^(?:client|customer|客户)\s*[:：]',text(r['value']).strip(),re.I)]
    client_values=[re.split(r'[:：]',text(r['value']),maxsplit=1)[-1] for r in client_cells]
    client_values += [text(val(r)) for r in book.kv(r'^(client|customer|客户)$')]
    identity_product=text(val(product.get('description')))
    ident=[bool(quote_cells) and all(re.search(r'\bQ9749821\b',text(r['value']),re.I) for r in quote_cells),
           bool(client_values) and all(norm(v)=='healthngo' for v in client_values),
           bool(re.search(r'(?:sterilization\s*[,，]?\s*kit\s*C|C\s*型.{0,5}(?:消毒|灭菌)|(?:消毒|灭菌).{0,5}C\s*型)',identity_product,re.I))]
    scores['order_identity']=sum(ident)/3
    if not all(ident): issue('identity','Required quotation/client/product identity missing or wrong')
    q,u=num(product.get('quantity')),num(product.get('unit'))
    line=num(product.get('line_total'))
    exw_values=[num(r) for r in exw]
    ex=exw_values[0] if exw_values else None
    qok=close(q,400,0); uok=close(u,450)
    base_checks=[qok,uok]
    # Dependent arithmetic uses submitted inputs: a wrong tier is not counted again as a multiplication error.
    if q is not None and u is not None:
        base_checks += [close(line,q*u),bool(exw_values) and all(close(n,q*u) for n in exw_values)]
    scores['pricing_basis']=sum(base_checks)/len(base_checks)
    if not qok or not uok: issue('pricing_basis','Quantity or tier price is missing/wrong')
    if len(products)!=1: issue('pricing_basis','Expected one product quotation line')
    if line is None or ex is None or (q is not None and u is not None and (material(line,q*u) or any(material(n,q*u) for n in exw_values))):
        issue('pricing_arithmetic','Product amount/EXW missing or materially inconsistent')
    freight_checks=[]; total_checks=[]; transit_checks=[]; elapsed_checks=[]; validity_checks=[]
    object_report={}
    lead=duration(val(product.get('lead')),True)
    supported_timeline=[]
    for mk,(freight,tr,valid,refid) in MODE_DATA.items():
        rows=options[mk]
        if len(rows)!=1:
            issue('mode_coverage',mk+': missing, hidden or duplicate option')
            freight_checks.append(0.0); transit_checks.append(False); validity_checks.append(False)
            object_report[mk]={'count':len(rows),'state':'missing_or_duplicate'}
            continue
        obj=rows[0]; fee=num(obj.get('freight')); grand=num(obj.get('grand'))
        row_text=' '.join(text(c['value']) for c in obj['cells'])
        names={'air':r'Euro\s*Air\s*Cargo|LEB[- ]?5933010','sea':r'Red\s*(?:Ocean|Water)\s*Shipping|R39921[- ]?BEY','road':r'Euro\s*Road\s*Logistics|LB8214498'}
        sourceok=bool(re.search(names[mk],row_text,re.I))
        feeok=close(fee,freight)
        freight_checks.append((float(sourceok)+float(feeok))/2)
        if fee is None or material(fee,freight): issue('freight',mk+': missing/materially wrong whole-shipment freight')
        if not sourceok: issue('freight_identity',mk+': forwarder/quote cannot be linked')
        if fee is not None and ex is not None:
            total_checks.append(close(grand,ex+fee))
            if grand is None or material(grand,ex+fee): issue('grand_total',mk+': missing/materially inconsistent grand total')
        transit=field_duration(obj.get('transit'),'transit')
        transit_checks.append(transit==tuple(tr))
        if material_time_shortening(transit,tuple(tr)):
            issue('transit',mk+': materially shortened source transit')
        elapsed=field_duration(obj.get('elapsed'),'elapsed')
        assessment=None
        if lead and transit:
            assessment=assess_elapsed(obj.get('elapsed'),(lead[0]+transit[0],lead[1]+transit[1]))
            elapsed_checks.append(assessment['accepted'])
            if assessment['material_shortening']:
                issue('elapsed',mk+': materially shortened combined duration / omitted lead time')
        elif elapsed is not None:
            # Missing a separate component is not omitted production when the total is supported.
            supported=assess_elapsed(obj.get('elapsed'),(21+tr[0],21+tr[1]))
            if supported['material_shortening']:
                issue('elapsed',mk+': unsupported shortened delivery timeline')
        supported_timeline.append(elapsed is not None)
        if transit is None and elapsed is None:
            issue('timeline_missing',mk+': both source transit and total delivery timeline missing')
        validity=field_duration(obj.get('validity'),'validity')
        validity_checks.append(validity==(valid,valid))
        if validity!=(valid,valid): issue('validity',mk+': validity missing/wrong')
        object_report[mk]={'sheet':obj['sheet'],'row':obj['row'],'freight':fee,'grand_total':grand,
                           'transit_days':transit,'order_to_arrival_days':elapsed,'validity_days':validity,
                           'elapsed_assessment':assessment}
    scores['freight_match']=sum(freight_checks)/3
    scores['scenario_totals']=average(total_checks)
    lead=duration(val(product.get('lead')),True)
    scores['lead_transit']=(float(lead==(21,21))+sum(transit_checks))/4
    if material_time_shortening(lead,(21,21)): issue('lead','Order lead time materially shortened')
    if lead is None and not (len(supported_timeline)==3 and all(supported_timeline)):
        issue('timeline_missing','Production lead and a complete set of total delivery estimates missing')
    scores['elapsed_time']=average(elapsed_checks)
    scores['validity_by_mode']=sum(validity_checks)/3
    # Preserve contractual values using their field labels.
    currency=book.kv(r'^(currency|币种|货币)$')
    incoterm=book.kv(r'^(incoterm|incoterms|贸易术语|贸易条款)$')
    payment=book.kv(r'^(paymentcondition|paymentterms|付款条件|付款条款|支付条件)$')
    offer=book.kv(r'^(offervalidity|productoffervalidity|报价有效期|产品报价有效期)$')
    destination=book.kv(r'^(destinationcountry|destination|目的地国家|目的国|目的地)$')
    if not destination:
        for r in visible:
            if re.fullmatch(r'(destinationcountry|destination|目的地国家|目的国|目的地)',norm(r['value'])):
                destination += [c for c in book.rows.get((r['sheet'],r['row']+1),[]) if c['col']==r['col']]
    seller_ok=any(norm(r['value']) in ('danishwholesaleco','danishwholesaleandco') for r in visible)
    destination_ok=bool(destination) and all(norm(val(r)) in ('lebanon','黎巴嫩','beirutlebanon','贝鲁特黎巴嫩') for r in destination)
    termchecks=[bool(currency) and all(norm(val(x)) in ('usd','usdollars','美元','美金') for x in currency),
                bool(incoterm) and all(norm(val(x))=='cip' for x in incoterm),
                bool(payment) and all(bool(re.search(r'(30\s*days?\s*after\s*invoice|发票.{0,6}(?:后|起).{0,3}30\s*(?:天|日)|开票.{0,4}后.{0,3}30\s*(?:天|日))',text(val(x)),re.I)) for x in payment),
                bool(offer) and all(duration(val(x))==(30,30) for x in offer), seller_ok, destination_ok]
    scores['preserved_terms']=sum(termchecks)/6
    if not all(termchecks): issue('contract_terms','Original commercial conditions/seller/destination missing or changed')
    # No aesthetic inference: deterministic native-cell and visibility checks only.
    native=bool(products) and sum(len(v) for v in options.values())>0
    visible_modes=all(len(options[k])==1 for k in MODE_DATA)
    critical_cells=[product.get(k) for k in ('quantity','unit','line_total')]+exw
    for rows in options.values():
        for obj in rows: critical_cells.extend(obj.get(k) for k in ('freight','grand'))
    editable=all(not (book.w[r['sheet']].protection.sheet and book.w[r['sheet']][r['cell']].protection.locked)
                 for r in critical_cells if r is not None)
    scores['workbook_usable']=(float(native)+float(not book.external_links)+float(editable))/3
    raw=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)
    awarded=min(raw,20.0) if critical else raw
    diagnostics.update({'raw_automated_points':raw,'awarded_automated_points':awarded,
        'cap_applied':bool(critical),'cap_points':20 if critical else None,
        'semantic_full_score_upper_bound':awarded+40,'actual_rule_coverage':{'products':len(products),'modes':{k:len(v) for k,v in options.items()}},
        'formula_resolution':book.unresolved,'extracted':object_report})
    overview={**base_payload,'artifact_status':'readable_quote','candidate_present':True,
              'candidate_file':str(target.relative_to(root)),'candidate_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
              'extracted_options':object_report,'unresolved_formulas':book.unresolved,
              'visibility_scope':'Sheet/row/column visibility and ;;; formats only; no rendered visual verdict.',
              'upstream_numeric_errors':'Judge must not re-penalize numerical extraction/calculation errors in semantic items; assess independent assertions and decision logic.',
              'candidate_fields':{'quantity':q,'unit_price':u,'exw':ex,'lead_days':lead}}
    write_evidence(root,overview,reference,book.records)
    return {**scores,'overall_score':awarded/60.0,'diagnostics':diagnostics}
```

## LLM Judge Rubric

共同证据范围为已声明的6份`evaluator_evidence/task024/`文件及本题Prompt/Expected Behavior。只能用`visible=true`的候选客户报价文字满足语义义务，不用最终回复代替工作簿内容；不把参考答案文字当候选。所有得分必须引用候选工作表、单元格及具体语义事实，列明满足/未满足的条件，不提供仅有结论的总体评价。隐藏或不存在的文字视作遗漏。`artifact_status`为missing/invalid/empty/no_quote_content等有效候选失败时各项0；评分器异常、缺证、提取不充分或截断时先标记不可判定并补证，不把无效占位分当正式成绩。

数值、时间范围和有效期取值错误由规则项处理。语义不得仅因同一上游数字错误再次扣分：独立检查是否披露适用条件、比较关系是否由其明确使用的信息推导、建议是否处理资金时间及风险。涉及重大虚假承诺、关键风险遗漏或无条件保证时，仅在decision_soundness归责；rate_conditions和option_tradeoffs仍按各自独立披露/比较对象评分。不得依据模型身份、调用次数、内部思考、自称已核验或排版好看来加分。

### Criterion 1: 运价变动与重确认条件 (key: rate_conditions, weight: 5)

评分单位为两个固定披露义务：R1运价可能变化；R2最终下单时需重确认运价。可在一般备注共用，不要求每模式重复；不要求指定颜色或精确措辞。只写有效天数不等于说明R1/R2。单独的“待确认”只有明确指向下单时运价确认才满足R2。数字期限取值和签发日期推断不在本项重复扣。

**Score 1.0**: R1、R2均以客户可理解的措辞出现，给出2/2位置证据。
**Score 0.5**: 仅满足其中一项，给出1/2及缺项。
**Score 0.0**: 两项均未披露，或没有有效客户报价交付，覆盖0/2。

### Criterion 2: 成本与时效的具体比较 (key: option_tradeoffs, weight: 5)

固定三个比较单元：T1空运相对其他方式更快但费用更高；T2海运相对其他方式费用较低但运输较慢；T3公路费用与正常运输时间位于二者之间。可以通过表格明确排序/差额加简短说明体现，不要求每行独立段落或具体差额；孤立列数字而没有关系/评价不自动满足。相同关系的重复改写不增加分母。不要求在本项讨论资金、边境或重确认，这些分别归其他项。

若原始金额/时间取错，比较关系按候选已明确使用的数值判断是否一致，不重复扣来源错误；与其自身数值矛盾的比较陈述属于本项独立逻辑错误。不得凭参考答案推断候选表达了比较。

**Score 1.0**: 3/3比较单元有具体、成立的关系说明。
**Score 0.75**: 2/3比较单元有具体、成立的关系说明。
**Score 0.25**: 1/3比较单元有具体、成立的关系说明。
**Score 0.0**: 0/3，只有数字堆放、泛泛赞美或没有有效交付。

### Criterion 3: 运输建议的条件与可靠性 (key: decision_soundness, weight: 30)

这是一个完整的业务选择判断，评估“选择及成立条件”，不按总体印象评分。固定证据条件如下：

D1区分请求时点、资金等待、订单确认后备货和运输；承认资金/下单日期未定，不能据当前材料保证请求后两个月内收到。接受说明需先确认资金或下单日期才能判断，不要求某个精确日历日期。

D2客户可见地指出公路经过冲突敏感/边境风险地区，可能发生延误、清关受阻或运输中断。原文等价表达即可，不要求同时复述所有风险词；“一般物流风险”而无公路/边境关联不满足。

D3给出能供客户采取下一步的有条件建议，结合预算倾向与实际剩余交期。可优先海运并以确认订单时间和足够剩余窗口为前提；可在窗口缩短时建议空运并指出成本代价；公路只能作为保留边境不确定性的条件式选项。不强制选择海运，也不凭空设置用户未提供的硬预算或准确资金启用日。

D4说明接下来需要确认的两个信息单元：资金可用/订单确认时间，以及客户可接受的到货窗口；在条件变化时说明需要重新比较或重确认。两单元可用一句话合并，不要求询问用户后停工。

先检查重大失败：缺少D1或D2；忽略资金等待而保证两个月到货；把公路描述为无边境风险/保证按标称时效到达；以无来源的确切到账日、已订舱/已核实状态或长期锁价承诺作为建议成立的必要依据；把所列货款加运费无依据承诺为所有费用保证包干。任一存在本项0。一个明确而未撤回的危险断言不能被其他单元格的泛泛免责声明抵消。仅数字来源或算式错误不触发此语义重大失败，除非存在上述独立决策错误。

**Score 1.0**: 无重大失败；D1、D2、D3均成立，D4两个信息单元均清楚，建议与其条件无矛盾。
**Score 0.75**: 无重大失败；D1、D2、D3均成立，但D4只覆盖一个或未具体说明下一步确认事项。
**Score 0.5**: 无重大失败；D1、D2均成立，提出了运输偏好，但没有把偏好与预算、剩余交期及适用条件完整关联，D3不完整；不作无条件到货承诺。
**Score 0.25**: 无重大失败；D1、D2均成立，但只罗列三种方式，没有实际偏好或可用的条件式选择，D3缺失。
**Score 0.0**: 触发任一重大失败，或无有效报价。须引用造成失败的具体断言/缺项及其证据覆盖，不能仅写“建议不合理”。

## Workspace Path

workspace/general_e2e/02_Office/task_024_sterilization_quote

## Skills

## Env

## Warmup
