---
id: 02_Office_task_015_procurement_reconciliation
name: 采购订单与入库记录核对
category: 02_Office
timeout_seconds: 1800
modality: pure-text
difficulty: L1
grading_type: hybrid
grading_weights:
  automated: 0.80
  llm_judge: 0.20
tags:
  -general_task_e2e
  -Office
judge_evidence:
  semantic_status_profile: evidence-aware-v1
  required:
    - path: evaluator_evidence/task015/overview.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task015/reference.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task015/tables_a.json
      role: grader_generated_evidence
    - path: evaluator_evidence/task015/tables_b.json
      role: grader_generated_evidence
---

## Prompt

帮我核对 `/tmp_workspace/input/` 里的采购订单和入库记录，做一份《对账报告.xlsx》，供采购和仓库复核。分别用工作表整理数量差异、金额差异、未入库订单、无对应订单的入库记录，再附汇总。明细保留可回查的单号、已有数量和金额，差异列出双方数值及差额；汇总各类笔数、金额差额和两类未匹配金额，能与明细核对。简要说明统计口径、异常含义，以及优先复核事项、依据和要查的凭据，并说明据此判断或处理的条件。金额相差不超过0.01元按一致处理，差额方向请注明。文件放到 `/tmp_workspace/results/`。

## Expected Behavior

输入评测案例 `procurement-reconcile-L3-015` 的两份冻结 CSV，按原始字节保留：`input/采购订单.csv` 为300行、8列、25,633字节；`input/入库记录.csv` 为285行、8列、24,090字节。均为UTF-8文本且无缺失单元格，业务事实仅用于这批评测材料。字段异名、独立数量/金额差异的重叠、两侧未匹配记录共同构成处理复杂性。没有额外字段字典、关联步骤或异常提示附件。

应从记录内容发现：入库单号由采购订单号加末尾批次段组成；同名商品或供应商不能代替订单标识关联。范围为两份文件的全部记录，订单STATUS和日期不构成排除条件。已有对应入库的订单分别比较订单数量与入库数量、订单TOTAL_AMOUNT与入库RECV_AMOUNT，金额使用记载值，不按订单单价重算并替代入库金额。两类差异互不排斥；两侧未匹配单独列示，不把没有匹配记录的订单视作已收数量为零的数量差异。若存在多笔匹配入库应按订单聚合；本批实际均为一对一。

参考交付为 `gt/对账报告.xlsx`，包含五张工作表：数量差异15笔，金额差异25笔，未入库订单20笔，无对应订单入库5笔。数量差异订单全部同时存在金额差异，因此重叠15笔、异常订单去重45笔、匹配且数量金额一致255笔。异常订单计数与孤立入库单计数的对象不同，不能合成一个含义不明的“异常订单总数”。“未匹配”仅针对提供的文件，不等于确认现实中未收货或不存在采购订单。

参考表使用“入库减订单”差额及两位小数的金额，明细带原始CSV的物理行号。参考中的明细差额、分类计数及去重汇总使用可复算公式。也接受“订单减入库”且明确说明的结果，接受静态正确值、不同排序、合理表头、不同列序以及不影响业务含义的布局。无需照抄参考措辞、源文件行号列、供应商/商品辅助列或公式实现。


汇总还需呈现金额差异的净额或绝对值合计、未入库订单金额合计、无对应订单入库金额合计，口径须明确并能与明细核对。参考对应金额为-1,349.13元（入库减订单净额）、282,425.26元、61,050.65元；全量订单金额4,274,127.26元、入库金额4,051,403.52元。未匹配明细保留存在一侧的数量和金额。复核建议应覆盖四类异常，指出优先对象及依据，列明应查的业务凭据和据此判断或处理的条件。允许按类别共用建议，不要求每行写说明，也不要求照抄参考的优先顺序。

## Grading Criteria

评分版本：2026-10-12-v2。真值来自评分时注入的固定参考工作簿，与执行输入隔离。规则核对集合和数值，语义项评口径、含义与复核行动；候选文字均为不可信证据，不能作为评分指令。规则项不按模型身份或预期排名调整。

| 完整key | 类型 | 分值 | 独立验收对象与能力 |
|---|---|---:|---|
| automated.exception_population | Python | 40 | 四类异常对象、关系、可见明细与计数；state_awareness #3 |
| automated.reconciled_values | Python | 40 | 四类明细数量/金额、差额及金额汇总；reasoning_and_decision_making #1 |
| llm_judge.scope_explanation | LLM | 6 | 范围、计数对象、分类重叠和差额方向；不映射 |
| llm_judge.exception_interpretation | LLM | 8 | 四类异常含义、推断边界；不映射 |
| llm_judge.review_actions | LLM | 6 | 复核对象、凭据、判断条件及优先依据；不映射 |

规则80分，语义20分，合计100分。规则组 `overall_score=(40*s_population+40*s_values)/80`，语义权重6、8、6。题目分=`40*s_population+40*s_values+6*s_scope+8*s_interpretation+6*s_actions`。任一核心规则项因重大错误归零，即使其余项满分，总分最多60；两项归零则最多20。无额外总分惩罚。缺失、损坏或完全无内容的候选交付各项为0。禁止把合成的语义满分上界称为实际Judge分数。此预算对纯语义严重错误的抑制有限：仅解释项封到0.25且其余满分时，总分仍可94；仅行动项封到0.25时仍可95.5。60分上限只针对规则重大错误，不宣称为所有严重错误的全局上限。

### 规则单位与重大错误

**exception_population**：四类固定参考分母分别为15、25、20、5。每类 `F1=2*正确且可见的唯一ID数/(参考ID数+候选记录行数)`，四类等权平均。只从明确ID列取业务行，依工作表名称或字段角色识别类别；不靠GT相似度分类或在任意备注搜索编号充数。明确给出的入库单号必须对应订单；错关联只在本项归责。重复同类ID增加候选分母，不增加正确数；同订单同时在数量、金额两表不是重复。隐藏工作表、隐藏业务行、隐藏ID或必要数值列、`;;;`隐藏显示格式，均不能作为可见正确记录。只检查这些确定性隐藏状态，不推断字体配色或未经渲染的视觉效果。任一类漏报/不可访问数占参考数达到20%，或误报、额外重复及不可访问数占候选行数达到20%，本40分项归零。

**reconciled_values**：对正确类别中实际提交的GT已知ID核算；同类同ID仅取首行。数量表检查订单量、入库量、差量；金额表检查订单金额、入库金额、差额；未入库表检查订单量与金额；孤立入库表检查入库量与金额。完整结果至少65行、170个必查数值单元；候选自行增加且能识别的相关数量、金额或折算单价，也须与同一记录一致，计入该类分母，不因参考没有要求该列而接受错误辅助值。每类=正确数值单元/受核对单元，四个有记录的类别等权平均。遗漏、重复已由对象项处理，不再将未提交行加入数值错误分母；完全无可核对记录时本项0。必须报告实际覆盖，不能把少量已交付记录的数值满分称为完成全量核对。

数量容差0，金额及折算单价容差0.01元。缺列、空值、非数字或不能读取的数值为错误。某类有数值错误的行占该类实际核对行数达到20%，或任一数量误差达到 `max(5,参考绝对值*10%)`，或任一金额误差同时达到100元和参考绝对值10%，本40分项归零；其余错误按单元比例计。方向优先取表内说明，其次汇总；未解析出说明时，只能每类统一选“入库减订单”或反向中匹配较好的方向，不能逐行任选。是否讲清方向由scope_explanation判断。

### 汇总与明细核对

必要汇总为四类笔数，以及金额差异净额或绝对值合计、未入库订单金额合计、孤立入库金额合计。额外总数、去重、交集、源金额、匹配金额等若提供，同样核对。合理的净额/绝对值表述、明确反向差额均接受，不要求参考的全部辅助指标。

计数组=正确可见计数主张数/(可核对计数主张数+缺失必要计数种类数)，金额组同理。对象项取自身F1结果与计数组中的较小值，数值项取自身结果与金额组中的较小值，不另增评分键。任一计数主张误差达到 `max(1,期望计数绝对值*20%)` 时对象项0；金额主张达到上述重大金额阈值时数值项0。纯文字复核标题不当作数值主张；缺必要指标仍按缺失计入分母。

源订单/入库总数与总金额以冻结输入为准；分类、交集和去重计数与候选唯一ID集合核对。同一类别明细ID集合完整时，金额汇总与候选该类数值求和核对；若上游集合不完整或数值无法读取，则依赖它的金额主张记为upstream_unavailable，不再重复处罚遗漏或缺值。独立可评的金额义务继续评分，完全无可评金额义务时不默认满分。明细缺错、汇总不一致均须在诊断中列明位置和实际覆盖。

漏行主要归对象项；数值错主要归数值项；隐藏明细只影响对象项，不能再因隐藏重复判数值错误。规则已发现的数字错误不直接再扣语义。解释中的独立错误断言、范围混淆与复核建议缺失仍按各自公开义务计分。对象全对但金额全部错误，或数值全对但缺失一类，是两个规则项彼此独立的反例。

### 提取、等价结果及异常边界

读取`results/`中指定工作簿；指定文件不存在而目录仅有一份普通XLSX时接受该文件。拒绝越界、符号链接及直接引用GT。候选缺失或损坏属于候选失败；GT缺失、版本哈希错误、参考缓存不完整、评分器异常属于EvaluationError，不能按候选0分处理。候选未知的数值汇总标签、无法识别业务ID表头，须先解决提取覆盖并重评；明确报EvaluationError，不因“未识别所以不扣”放行，也不把合理别名认定为业务错误。不得将被框架兜底的占位0视为有效成绩。

接受静态值、合理行列重排、中英文角色表头、单位后缀和数字文本，不要求公式、来源行号或相同排版。公式优先读取缓存，无缓存时仅安全求值基本算术、引用、ROUND、ABS、SUM、MIN、MAX、COUNT、COUNTA、IF及等值条件COUNTIF/COUNTIFS；不执行任意代码。未支持且无缓存的公式位置单列，不能读取的必需数值不能判正确；如属合法公式但当前提取器能力不足，应补充正确缓存或复核提取后重评，不能把暂定得分当正式结果。未支持的合理等价汇总结构同样先补充提取适配，不改业务标准。

四份`evaluator_evidence/task015/`证据分别为overview、reference和tables_a/b。包括完整表值、表名、行号、字段角色、隐藏位置、数值诊断及未解析公式。参考与候选角色分开，不是执行轨迹。单文件不超过19,500字符、合计不超过76,000字符；超限或不安全写入路径报评测错误，不静默截断。`evidence_valid=false`、缺证据或截断时，语义项不可判定，补证后重评；完整缺交付证据可以判0。Judge不读取此前分数、模型身份或预期名次，不从产物正确推断主动自检、工具操作或内部思考。

### 能力映射与归一化

沿用`capabilities-2026-09-23-v1`。对象关联映射`state_awareness#3`，数量/金额比较映射`reasoning_and_decision_making#1`；各40分，有效映射预算W=80。语义解释和复核建议不证明实际执行过检查，不映射循环能力。能力总分=`100*(40*s_population+40*s_values)/80`；两个维度独立分为对应项乘100，各对能力总分贡献上限50，合计100。意图理解、工具调用、结果评估未覆盖。

所有映射项有效才出正式能力总分；不能删去不可判定项的分母再归一。实际覆盖与得分并报，最后展示时才舍入。原生overall_score为0—1、四位小数。沿用既有映射YAML结构；旧七维报告不原生实现本题五维加权公式，不修改框架或报告器。

## Automated Checks

```python
import ast
import hashlib
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.etree.ElementTree import ParseError

import openpyxl
from openpyxl.formula.tokenizer import Tokenizer, TokenizerError
from openpyxl.utils.cell import range_boundaries, get_column_letter, column_index_from_string
from openpyxl.utils.exceptions import InvalidFileException

REFERENCE_SHA256 = '39e880d6f50f1c9cc56c2e9810b97ca58220947682a806024b967851b67f3bb8'
CATEGORIES = ('qty', 'amount', 'missing', 'orphan')
NAMES = {'qty':'数量差异','amount':'金额差异','missing':'未入库订单','orphan':'无对应订单入库'}
MONEY_TOLERANCE = Decimal('0.01')

class EvaluationError(RuntimeError):
    """Missing/corrupt private reference or unavailable grading evidence."""

class CandidateError(ValueError):
    """The submitted artifact is absent, unsafe to read, or malformed."""

def norm(value):
    return re.sub(r'[\s_\-—–－:：/\\（）()\[\]【】,，。.]', '', unicodedata.normalize('NFKC', str(value or ''))).casefold()

ALIASES = {
 'id':['单号','订单号','采购订单号','订单编号','采购单号','订单ID','ORDER_ID','PO_ID','PO number','Order number'],
 'receipt':['入库单号','入库编号','收货单号','RECEIPT_NO','Receipt number','Receipt ID'],
 'oq':['订单数量','采购数量','采购订单数量','采购单数量','订单量','采购量','ORDER_QTY','ordered quantity','PO qty'],
 'rq':['入库数量','实收数量','收货数量','收货量','实际入库数量','入库数量合计','RECV_QTY','received quantity','receipt qty'],
 'dq':['差异数量','数量差异','数量差额','数量差值','数量差','QTY_DIFF','quantity difference','quantity variance','delta qty'],
 'oa':['订单总额','订单金额','采购金额','采购订单金额','采购总金额','订单总金额','TOTAL_AMOUNT','ORDER_AMOUNT','order amount','PO amount'],
 'ra':['入库金额','收货金额','实收金额','入库总金额','RECV_AMOUNT','receipt amount','received amount'],
 'da':['差异金额','金额差异','金额差额','金额差值','金额差','AMOUNT_DIFF','amount difference','amount variance','delta amount']
}
ALIASES.update(oprice=['订单单价','采购单价','UNIT_PRICE'],rprice=['入库折合单价','入库单价'])
ALIASES = {k:{norm(x) for x in values} for k,values in ALIASES.items()}

def number(value):
    if isinstance(value, bool) or value is None: return None
    if isinstance(value, str):
        text = unicodedata.normalize('NFKC', value).strip().replace(',', '').replace('，','')
        text = re.sub(r'^(?:RMB|CNY|人民币|¥|￥)\s*|\s*(?:元|件|个)$', '', text, flags=re.I)
        if re.fullmatch(r'\(\s*[0-9.]+\s*\)', text): text = '-'+text.strip('() ')
    else: text = str(value)
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError): return None
    return result if result.is_finite() else None

def matched_header(value, kind=None):
    text = norm(value)
    if kind=='orphan' and text in {norm(v) for v in ['入库单号/订单号','入库单号/采购订单号','入库编号/订单编号','入库对应订单号']}:return 'receipt'
    # Parenthesized unit/direction suffixes do not change the column's role.
    short = norm(re.split(r'[（(\[]', str(value or ''), maxsplit=1)[0])
    for key, aliases in ALIASES.items():
        if text in aliases or short in aliases: return key
    if kind in ('qty','amount'):
        tail='q' if kind=='qty' else 'a'
        for key,labels in [('o',{'订单','采购','采购订单','ordered'}),('r',{'入库','收货','实收','received'}),('d',{'差异','差额','差值','difference','variance','delta'})]:
            if short in labels:return key+tail
    return None

def safe_inside(path, base, error_cls):
    if not path.resolve().is_relative_to(base.resolve()):
        raise error_cls('Path escapes its allowed directory: '+str(path.name))
    probe=path
    while probe != base and probe != probe.parent:
        if probe.is_symlink(): raise error_cls('Symbolic link is not an artifact: '+str(path.name))
        probe=probe.parent
    if base.is_symlink(): raise error_cls('Linked artifact directory')

def flat(values):
    result=[]
    for value in values:
        result.extend(flat(value) if isinstance(value,list) else [value])
    return result

class Values:
    """Use stored results, with a bounded, non-executing formula fallback."""
    def __init__(self, formulas, cached):
        self.formulas=formulas; self.cached=cached; self.memo={}; self.active=set(); self.unresolved=[]

    def get(self, sheet, address):
        key=(sheet,address)
        if key in self.memo: return self.memo[key]
        cell=self.formulas[sheet][address]
        if cell.data_type!='f': return cell.value
        cached=self.cached[sheet][address].value
        if cached is not None: return cached
        if key in self.active or len(self.active)>40: return None
        self.active.add(key)
        try:
            result=self.calculate(sheet,cell.value)
            if isinstance(result,Decimal): result=float(result)
            if isinstance(result,list): raise ValueError('array result')
        except (ValueError, TypeError, KeyError, SyntaxError, ZeroDivisionError, InvalidOperation, IndexError, RecursionError, TokenizerError):
            result=None; self.unresolved.append(sheet+'!'+address)
        finally:
            self.active.remove(key)
        self.memo[key]=result
        return result

    def reference(self,sheet,ref):
        if '[' in ref or ']' in ref: raise ValueError('external reference')
        if '!' in ref:
            name,ref=ref.rsplit('!',1);sheet=name.strip("'").replace("''", "'")
        ref=ref.replace('$','')
        if ':' not in ref: return self.get(sheet,ref)
        a,b,c,d=range_boundaries(ref)
        if (c-a+1)*(d-b+1)>10000: raise ValueError('range too large')
        return [self.get(sheet,cell.coordinate) for row in self.formulas[sheet].iter_rows(min_row=b,max_row=d,min_col=a,max_col=c) for cell in row]

    def calculate(self,sheet,formula):
        pieces=[]
        for token in Tokenizer(formula).items:
            if token.type=='OPERAND' and token.subtype=='RANGE': pieces.append('REF('+repr(token.value)+')')
            elif token.type=='OPERAND' and token.subtype=='TEXT': pieces.append(repr(token.value[1:-1].replace('""','"')))
            elif token.type=='OPERAND' and token.subtype=='LOGICAL': pieces.append('True' if token.value=='TRUE' else 'False')
            elif token.type=='FUNC' and token.subtype=='OPEN': pieces.append(token.value.replace('_xlfn.','').upper())
            elif token.type=='OP_IN': pieces.append({'=':'==','<>':'!=','^':'**'}.get(token.value,token.value))
            elif token.type=='SEP': pieces.append(',')
            else: pieces.append(token.value)
        tree=ast.parse(''.join(pieces),mode='eval')
        if len(list(ast.walk(tree)))>500: raise ValueError('formula too complex')
        def ev(node):
            if isinstance(node,ast.Expression): return ev(node.body)
            if isinstance(node,ast.Constant): return Decimal(str(node.value)) if isinstance(node.value,(int,float)) and not isinstance(node.value,bool) else node.value
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
                v=ev(node.operand);return -v if isinstance(node.op,ast.USub) else v
            if isinstance(node,ast.BinOp):
                a,b=number(ev(node.left)),number(ev(node.right))
                if a is None or b is None: raise ValueError('non-numeric arithmetic')
                if isinstance(node.op,ast.Add): return a+b
                if isinstance(node.op,ast.Sub): return a-b
                if isinstance(node.op,ast.Mult): return a*b
                if isinstance(node.op,ast.Div): return a/b
            if isinstance(node,ast.Compare) and len(node.ops)==1:
                a,b=ev(node.left),ev(node.comparators[0]);op=node.ops[0]
                if isinstance(op,ast.Eq): return a==b
                if isinstance(op,ast.NotEq): return a!=b
                if isinstance(op,ast.Gt): return a>b
                if isinstance(op,ast.GtE): return a>=b
                if isinstance(op,ast.Lt): return a<b
                if isinstance(op,ast.LtE): return a<=b
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                name=node.func.id
                if name=='IF' and len(node.args)==3: return ev(node.args[1] if ev(node.args[0]) else node.args[2])
                args=[ev(a) for a in node.args]
                if name=='REF' and len(args)==1: return self.reference(sheet,args[0])
                if name=='ROUND' and len(args)==2:
                    n=number(args[0]);digits=int(args[1])
                    if n is None or abs(digits)>15: raise ValueError('unsupported rounding input')
                    return n.quantize(Decimal(1).scaleb(-digits),rounding=ROUND_HALF_UP)
                if name=='ABS' and len(args)==1:
                    n=number(args[0])
                    if n is None: raise ValueError('non-numeric ABS')
                    return abs(n)
                if name in ('SUM','MIN','MAX','COUNT','COUNTA'):
                    items=flat(args);nums=[number(x) for x in items if number(x) is not None]
                    if name=='SUM': return sum(nums,Decimal(0))
                    if name=='MIN': return min(nums) if nums else Decimal(0)
                    if name=='MAX': return max(nums) if nums else Decimal(0)
                    if name=='COUNT': return len(nums)
                    return sum(x is not None and x!='' for x in items)
                if name in ('COUNTIF','COUNTIFS','SUMIF'):
                    return _pl_conditional(name,args,number)
            raise ValueError('unsupported formula without cached result')
        return ev(tree)

def category(name, grid):
    text=norm(name)
    if any(x in text for x in ['无对应订单','无订单','孤立入库','孤儿入库','orphan','unmatchedreceipt','receiptswithoutorder']): return 'orphan'
    if any(x in text for x in ['未入库','未收货','未匹配订单','无入库','missingreceipt','unreceived','unmatchedorder','orderswithoutreceipt']): return 'missing'
    if ('数量' in text or 'quantity' in text or 'qty' in text) and any(x in text for x in ['差异','差额','variance','difference','mismatch','diff']): return 'qty'
    if ('金额' in text or 'amount' in text) and any(x in text for x in ['差异','差额','variance','difference','mismatch','diff']): return 'amount'
    if any(x in text for x in ['汇总','统计','summary','overview']): return 'summary'
    for row in grid[:60]:
        roles={matched_header(v) for v in row['values']}
        if {'id','oq','rq','dq'}<=roles: return 'qty'
        if {'id','oa','ra','da'}<=roles: return 'amount'
    return None

def cell_visible(ws, cell):
    if ws.sheet_state!='visible' or ws.row_dimensions[cell.row].hidden: return False
    for dim in ws.column_dimensions.values():
        if dim.hidden and (dim.min or column_index_from_string(dim.index))<=cell.column<=(dim.max or column_index_from_string(dim.index)): return False
    return cell.number_format.replace(' ','')!=';;;'

def scan_workbook(path):
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(x.file_size for x in archive.infolist())>128*1024*1024: raise CandidateError('Oversized workbook')
        formulas=openpyxl.load_workbook(path,data_only=False,keep_links=False)
        cached=openpyxl.load_workbook(path,data_only=True,keep_links=False)
    except (zipfile.BadZipFile,InvalidFileException,ParseError,KeyError,ValueError,EOFError) as exc:
        raise CandidateError('Workbook cannot be read: '+type(exc).__name__) from exc
    values=Values(formulas,cached);tables=[];count=0
    try:
        for ws in formulas:
            if ws.max_row>10000 or ws.max_column>128: raise CandidateError('Workbook exceeds bounded extraction dimensions')
            grid=[]
            for row in ws.iter_rows():
                occupied=[c for c in row if c.value is not None]
                if not occupied:continue
                count+=len(occupied)
                if count>100000:raise CandidateError('Workbook exceeds bounded extraction cells')
                vals=[values.get(ws.title,c.coordinate) for c in row]
                while vals and vals[-1] is None:vals.pop()
                item={'row':row[0].row,'values':vals}
                hidden=[i for i,c in enumerate(row[:len(vals)]) if not cell_visible(ws,c)]
                if hidden:item['hidden_columns']=hidden
                grid.append(item)
            kind=category(ws.title,grid)
            table={'sheet':ws.title,'kind':kind,'state':ws.sheet_state,'rows':grid,'header_row':None,'columns':{},'records':[]}
            if kind in CATEGORIES:
                required='receipt' if kind=='orphan' else 'id';best=None
                for row in grid[:60]:
                    cols={}
                    for i,v in enumerate(row['values']):
                        role=matched_header(v,kind)
                        if role and role not in cols:cols[role]=i
                    if required in cols and (best is None or len(cols)>best[0]):best=(len(cols),row,cols)
                if best:
                    _,hdr,cols=best;table['header_row']=hdr['row'];table['columns']=cols
                    critical={required,*REQUIRED[kind]}
                    for row in grid:
                        if row['row']<=hdr['row']:continue
                        vals=row['values'];idx=cols[required]
                        ident=str(vals[idx]).strip() if idx<len(vals) and vals[idx] is not None else ''
                        if not ident or matched_header(ident)==required:continue
                        if norm(ident) in {'合计','总计','小计','total','subtotal','说明','备注','无','none'}:continue
                        if ident.startswith(('备注：','说明：','注：','来源：','差额口径','统计口径','差异方向','差额为','Note:','Source:')):continue
                        invisible=[k for k in critical if k in cols and (cols[k] in row.get('hidden_columns',[]) or cols[k] in hdr.get('hidden_columns',[]))]
                        table['records'].append({'id':ident,'row':row['row'],'values':{k:vals[j] if j<len(vals) else None for k,j in cols.items()},'visible':not invisible,'hidden_roles':invisible,'location':ws.title+'!'+str(row['row'])})
                elif any(re.search(r'PO-\d{4}-\d+',str(v)) for r in grid for v in r['values']):
                    raise EvaluationError('Unrecognized ID header in populated business table: '+ws.title)
            tables.append(table)
    finally:formulas.close();cached.close()
    return tables,sorted(set(values.unresolved))

REQUIRED={'qty':('oq','rq','dq'),'amount':('oa','ra','da'),'missing':('oq','oa'),'orphan':('rq','ra')}

def reference(root):
    path=root/'gt/对账报告.xlsx'
    if not path.is_file():raise EvaluationError('Private reference is missing')
    safe_inside(path,root/'gt',EvaluationError)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=REFERENCE_SHA256:raise EvaluationError('Private reference version/checksum mismatch')
    try:wb=openpyxl.load_workbook(path,data_only=True,keep_links=False)
    except (zipfile.BadZipFile,InvalidFileException,ParseError,KeyError,ValueError) as exc:raise EvaluationError('Private reference is unreadable') from exc
    truth={};facts={}
    try:
        for kind,size in [('qty',15),('amount',25),('missing',20),('orphan',5)]:
            rows=[list(r) for r in wb[NAMES[kind]].iter_rows(min_row=6,max_row=5+size,values_only=True)]
            if len({r[0] for r in rows})!=size or any(r[0] is None for r in rows):raise EvaluationError('Invalid reference records')
            truth[kind]={r[0]:r for r in rows}
        for oid,r in truth['amount'].items():
            facts[oid]={'oa':number(r[2]),'ra':number(r[3]),'da':number(r[4]),'oq':number(r[8]),'rq':number(r[9])}
            facts[oid]['dq']=facts[oid]['rq']-facts[oid]['oq']
            facts[oid]['oprice']=(facts[oid]['oa']/facts[oid]['oq']).quantize(Decimal('.01'))
            facts[oid]['rprice']=(facts[oid]['ra']/facts[oid]['rq']).quantize(Decimal('.01'))
        for kind,keys in [('missing',('oq','oa')),('orphan',('rq','ra'))]:
            for oid,r in truth[kind].items():facts[oid]={keys[0]:number(r[3]),keys[1]:number(r[4])}
        s=wb['汇总'];metrics={'orders':number(s['B6'].value),'receipts':number(s['B7'].value),'orders_amount':number(s['B28'].value),'receipts_amount':number(s['B29'].value)}
        if list(metrics.values())!=list(map(Decimal,['300','285','4274127.26','4051403.52'])):raise EvaluationError('Reference totals missing or inconsistent')
        for kind in ('qty','amount'):
            for oid,r in truth[kind].items():
                if abs(number(r[3])-number(r[2])-number(r[4]))>Decimal('.000001'):raise EvaluationError('Reference difference inconsistent')
    finally:wb.close()
    return truth,facts,metrics

def direction(tables,kind):
    for group in ([t for t in tables if t['kind']==kind],[t for t in tables if t['kind']=='summary']):
        text=' '.join(str(v) for t in group for r in t['rows'] for v in r['values'] if isinstance(v,str))
        a=r'(?:入库|收货|实收|received|receipt)(?:数量|金额|量|额)?';b=r'(?:采购订单|采购|订单|ordered|order)(?:数量|金额|量|额)?';minus=r'\s*(?:减去|减|[-－−–—])\s*'
        pos=bool(re.search(a+minus+b,text,re.I));neg=bool(re.search(b+minus+a,text,re.I))
        if pos!=neg:return 1 if pos else -1
    return None

def population(records,truth):
    detail={};scores=[];major=[]
    for kind in CATEGORIES:
        expected=set(truth[kind]);actual=Counter(r['id'] for r in records[kind]);valid=set();bad=[];hidden=[]
        for r in records[kind]:
            oid=r['id']
            if oid not in expected:continue
            link=r['values'].get('receipt')
            if kind in ('qty','amount') and link is not None and str(link).strip() and str(link).strip()!=truth[kind][oid][1]:bad.append([oid,str(link),r['row']])
            elif not r['visible']:hidden.append([oid,r['row'],r['hidden_roles']])
            else:valid.add(oid)
        tp=len(valid);fn=len(expected-valid);fp=sum(actual.values())-tp
        f1=2*tp/(len(expected)+sum(actual.values()))
        if fn/len(expected)>=.2:major.append(kind+': missed/inaccessible >=20%')
        if fp/max(1,sum(actual.values()))>=.2:major.append(kind+': false/duplicate/inaccessible >=20%')
        detail[kind]={'expected':len(expected),'reported':sum(actual.values()),'correct_accessible_unique':tp,'missing':sorted(expected-valid),'extra':sorted(set(actual)-expected),'duplicates':{k:n for k,n in actual.items() if n>1},'wrong_links':bad,'inaccessible':hidden,'f1':f1}
        scores.append(f1)
    return (0. if major else sum(scores)/4),{'categories':detail,'major_errors':major}

def material(actual,expected,quantity):
    if actual is None:return False
    delta=abs(actual-expected)
    return delta>=max(Decimal(5),abs(expected)*Decimal('.1')) if quantity else delta>=100 and delta>=abs(expected)*Decimal('.1')

def numeric_score(records,truth,facts,tables):
    diag={};scores=[];major=[];assessed=0
    for kind in CATEGORIES:
        selected={}
        for r in records[kind]:
            if r['id'] in truth[kind]:selected.setdefault(r['id'],r)
        stated=direction(tables,kind);sign=stated or 1
        if stated is None and kind in ('qty','amount'):
            key='dq' if kind=='qty' else 'da'
            def errors(s):return sum(number(r['values'].get(key)) is None or abs(number(r['values'].get(key))-s*facts[oid][key])>(0 if kind=='qty' else MONEY_TOLERANCE) for oid,r in selected.items())
            sign=min((1,-1),key=errors)
        good=total=bad_rows=0;errors=[]
        for oid,r in selected.items():
            fields=list(REQUIRED[kind])+[k for k in r['values'] if k in facts[oid] and k not in REQUIRED[kind]];bad=False
            for key in fields:
                expected=facts[oid][key]*(sign if key in ('dq','da') else 1);actual=number(r['values'].get(key));quantity=key in ('oq','rq','dq')
                total+=1
                if actual is not None and abs(actual-expected)<=(0 if quantity else MONEY_TOLERANCE+Decimal('0.00000001')):good+=1;continue
                bad=True;errors.append([r['row'],key,None if actual is None else str(actual),str(expected)])
                if material(actual,expected,quantity):major.append(kind+': material value error '+oid+'/'+key)
            bad_rows+=int(bad)
        if selected:
            scores.append(good/total);assessed+=len(selected)
            if bad_rows/len(selected)>=.2:major.append(kind+': numeric errors in >=20% assessed rows')
        diag[kind]={'expected_rows':len(truth[kind]),'assessed_rows':len(selected),'correct_cells':good,'total_cells':total,'bad_rows':bad_rows,'direction':sign,'explicit_direction':stated,'error_columns':['row','field','actual','expected'],'errors':errors}
    return (0. if major else sum(scores)/len(scores) if scores else 0.),{'categories':diag,'major_errors':major,'assessed_rows':assessed,'expected_rows':65,'required_cells_if_complete':170}

SUMMARY_LABELS={
 'orders':['采购订单笔数','总采购订单数','采购订单总数','采购订单总笔数','总订单数','total orders','purchase order count'],
 'receipts':['入库记录笔数','入库记录总数','总入库单数','总入库数','入库单总数','入库记录总筆数','入库记录总笔数','total receipts','receipt count'],
 'matched':['已匹配笔数','已匹配订单数','匹配订单数','订单与入库成功匹配','匹配成功对数','matched orders'],
 'qty':['数量差异笔数','数量差异订单数','数量差异数','数量差异','quantity differences','qty mismatches'],
 'amount':['金额差异笔数','金额差异订单数','金额差异数','金额差异','amount differences','amount mismatches'],
 'missing':['未入库订单笔数','未入库订单数','未入库数','未入库订单','missing receipts','unreceived orders'],
 'orphan':['无对应订单入库笔数','无对应订单的入库','无对应订单入库单数','无对应订单入库数','孤立入库数','无对应订单入库','无对应订单的入库记录','orphan receipts'],
 'both':['数量及金额均有差异订单数','数量金额同时差异订单数','双重差异订单数','数量差异引起','overlap count'],
 'unique_orders':['异常订单去重数','异常订单总数','异常订单数','unique exception orders'],
 'qty_clean':['数量一致','数量一致订单数'], 'amount_clean':['金额视为一致','金额一致','金额一致订单数'],
 'clean':['数量金额一致','数量金额一致笔数','匹配且数量金额均一致订单数','正常订单数','一致订单数','matched clean orders'],
 'qty_up':['超收','多入','数量超收'],'qty_down':['欠收','少入','数量欠收'],
 'amount_up':['多收','金额高于订单'],'amount_down':['少收','金额低于订单'],
 'price_only':['数量一致的纯金额差异','纯单价差异','仅金额差异','数量一致但金额差异'],
 'orders_amount':['订单金额合计','订单总金额','采购订单金额合计','total order amount'],
 'receipts_amount':['入库金额合计','入库总金额','total receipt amount'],
 'matched_order_amount':['匹配订单金额合计','matched order amount'],
 'matched_receipt_amount':['匹配入库金额合计','matched receipt amount'],
 'net_amount':['金额差额净额','金额差异净额合计','金额差异合计','金额差额合计','差异金额合计','net amount difference'],
 'abs_amount':['金额差额绝对值合计','金额差异绝对值合计','absolute amount differences'],
 'matched_net':['匹配差额合计','matched net difference'],
 'missing_amount':['未入库订单金额合计','未入库金额合计','未匹配订单金额','unreceived order amount'],
 'orphan_amount':['无对应订单入库金额合计','孤立入库金额合计','orphan receipt amount']
}
MONEY_KEYS={'orders_amount','receipts_amount','matched_order_amount','matched_receipt_amount','net_amount','abs_amount','matched_net','missing_amount','orphan_amount'}
def summary_key(value):
    text=str(value or '').strip();text=re.sub(r'^(?:其中\s*[:：]?\s*|\d+[.、]\s*)+','',text)
    short=re.split(r'[（(\[]',text,maxsplit=1)[0]
    for k,labels in SUMMARY_LABELS.items():
        if norm(text) in {norm(x) for x in labels} or norm(short) in {norm(x) for x in labels}:return k
    return None

def summary_diagnostics(tables,records,metrics,numeric,truth):
    sets={k:{r['id'] for r in records[k]} for k in CATEGORIES};expected=dict(metrics);expected.update(_PL_EXPECTED)
    expected.update({k:Decimal(len(v)) for k,v in sets.items()});expected['both']=Decimal(len(sets['qty']&sets['amount']))
    expected['unique_orders']=Decimal(len(sets['qty']|sets['amount']|sets['missing']))
    expected['matched']=metrics['orders']-expected['missing'];expected['clean']=metrics['orders']-expected['unique_orders']
    expected['qty_clean']=expected['matched']-expected['qty'];expected['amount_clean']=expected['matched']-expected['amount'];expected['price_only']=expected['amount']-expected['both']
    for kind,field in [('qty','dq'),('amount','da')]:
        sign=numeric['categories'][kind]['direction'];vals={r['id']:number(r['values'].get(field)) for r in records[kind]}
        for name,op in [('up',lambda x:x>0),('down',lambda x:x<0)]:expected[kind+'_'+name]=Decimal(sum(v is not None and op(sign*v) for v in vals.values()))
    def total(kind,field,absolute=False):
        # Population omissions/extra IDs belong to the population item, not money.
        if sets[kind]!=set(truth[kind]):return None
        values={r['id']:number(r['values'].get(field)) for r in records[kind]}
        if any(v is None for v in values.values()):return None
        return sum((abs(v) if absolute else v for v in values.values()),Decimal(0))
    expected.update(net_amount=total('amount','da'),abs_amount=total('amount','da',True),missing_amount=total('missing','oa'),orphan_amount=total('orphan','ra'))
    for side,key in [('order','missing_amount'),('receipt','orphan_amount')]:expected['matched_'+side+'_amount']=None if expected[key] is None else metrics[side+'s_amount']-expected[key]
    expected['matched_net']=None if expected['matched_order_amount'] is None or expected['matched_receipt_amount'] is None else numeric['categories']['amount']['direction']*(expected['matched_receipt_amount']-expected['matched_order_amount'])
    claims=[];unknown=[];summary_present=False
    for t in tables:
        if t['kind']!='summary':continue
        summary_present=True;rows=t['rows']
        for ri,row in enumerate(rows):
            vals=row['values'];recognized=[];has_number=any(number(v) is not None for v in vals)
            for col,v in enumerate(vals):
                key=summary_key(v)
                if key is None:continue
                recognized.append(key);n=None;value_col=None
                for j in range(col+1,min(col+3,len(vals))):
                    n=number(vals[j])
                    if n is not None:value_col=j;break
                if n is None and ri+1<len(rows) and col<len(rows[ri+1]['values']) and summary_key(rows[ri+1]['values'][0]) is None:
                    n=number(rows[ri+1]['values'][col]);value_col=col
                    value_row=rows[ri+1]
                else:value_row=row
                # A category repeated as a narrative review heading is not a numeric claim.
                # Required metrics still fail the missing-required test if no numeric row exists.
                if n is None and any(isinstance(x,str) and x.strip() for x in vals[col+1:]):continue
                visible=col not in row.get('hidden_columns',[]) and value_col not in value_row.get('hidden_columns',[])
                claims.append({'sheet':t['sheet'],'row':row['row'],'label':str(v),'key':key,'value':None if n is None else str(n),'value_location':t['sheet']+'!'+get_column_letter((value_col or 0)+1)+str(value_row['row']),'expected':None if expected[key] is None else str(expected[key]),'visible':visible})
                # Embedded count alongside a monetary subtotal remains a count claim.
                count_key={'missing_amount':'missing','orphan_amount':'orphan','orders_amount':'orders','receipts_amount':'receipts','matched_order_amount':'matched','matched_receipt_amount':'matched'}.get(key)
                if count_key:
                    for j,extra in enumerate(vals[col+1:],col+1):
                        if not isinstance(extra,str):continue
                        m=re.search(r'(?<![\d.])(\d+)\s*(?:笔|张|单)',extra)
                        if m:claims.append({'sheet':t['sheet'],'row':row['row'],'label':extra,'key':count_key,'value':m.group(1),'value_location':t['sheet']+'!'+get_column_letter(j+1)+str(row['row']),'expected':str(expected[count_key]),'visible':j not in row.get('hidden_columns',[])})
            if has_number and not recognized:unknown.append({'sheet':t['sheet'],'row':row['row'],'values':vals})
    for c in claims:
        a=number(c['value']);e=number(c['expected']);tol=_PS_TOLERANCES.get(c['key'],MONEY_TOLERANCE+Decimal('0.00000001') if c['key'] in MONEY_KEYS else Decimal(0))
        c['matches']=None if e is None else bool(c['visible'] and a is not None and abs(a-e)<=tol)
        c['major']=bool(e is not None and a is not None and (material(a,e,False) if c['key'] in MONEY_KEYS else abs(a-e)>=max(Decimal(1),abs(e)*Decimal('.2'))))
    groups={'counts':({'qty'},{'amount'},{'missing'},{'orphan'}),'money':({'net_amount','abs_amount','matched_net'},{'missing_amount'},{'orphan_amount'})}
    results={}
    for group,required in groups.items():
        selected=[c for c in claims if (c['key'] in MONEY_KEYS)==(group=='money')]
        absent=[sorted(keys) for keys in required if any(expected[k] is not None for k in keys) and not any(c['key'] in keys for c in selected)]
        evaluable=[c for c in selected if c['matches'] is not None]
        denominator=len(evaluable)+len(absent);correct=sum(c['matches'] for c in evaluable)
        major=[c['value_location'] for c in selected if c['major']]
        score=correct/denominator if denominator else 0.
        if major:score=0.
        results[group]={'score':score,'correct_claims':correct,'evaluated_units':denominator,'missing_required':absent,'major_errors':major,'upstream_unavailable':[c['value_location'] for c in selected if c['matches'] is None]}
    return {'claims':claims,'groups':results,'unrecognized_numeric_rows':unknown,'summary_present':summary_present,'expected_basis':{k:None if v is None else str(v) for k,v in expected.items()},'basis':'Source totals are frozen. Other totals follow submitted records/values so upstream errors are not charged twice.'}

def export_evidence(root,status,tables,truth,metrics,diagnostics,unresolved,artifact):
    dest=root/'evaluator_evidence/task015';safe_inside(dest,root,EvaluationError)
    for p in (dest.parent,dest):
        if p.exists() and (p.is_symlink() or not p.is_dir()):raise EvaluationError('Unsafe evidence directory')
    dest.mkdir(parents=True,exist_ok=True)
    chunks=[[],[]]
    for table in tables:
        item={k:table[k] for k in ('sheet','kind','state','header_row','columns','rows')}
        chunks[min(range(2),key=lambda i:len(json.dumps(chunks[i],ensure_ascii=False,default=str)))].append(item)
    files={'overview.json':{'role':'grader_generated_evidence','rubric_revision':'2026-10-12-v2','artifact_status':status,'evidence_valid':status!='evaluator_error','truncated':False,'artifact':artifact,'diagnostics':diagnostics,'unresolved_formulas':unresolved},
      'reference.json':{'role':'private_reference_extraction','truncated':False,'columns':{'qty':['order_id','receipt_id','order_qty','recv_qty','delta','supplier','item','source_lines','also_amount'],'amount':['order_id','receipt_id','order_amount','recv_amount','delta','supplier','item','source_lines','order_qty','recv_qty'],'missing':['order_id','supplier','item','qty','amount','source','status'],'orphan':['receipt_id','supplier','item','qty','amount','source','status']},'rows':{k:list(v.values()) for k,v in truth.items()},'source_totals':metrics},
      'tables_a.json':{'role':'candidate_workbook_extraction','truncated':False,'tables':chunks[0]},'tables_b.json':{'role':'candidate_workbook_extraction','truncated':False,'tables':chunks[1]}}
    encoded={n:json.dumps(v,ensure_ascii=False,separators=(',',':'),default=str) for n,v in files.items()}
    if max(len(t.encode('utf-8')) for t in encoded.values())>4*1024*1024 or sum(len(t.encode('utf-8')) for t in encoded.values())>16*1024*1024:raise EvaluationError('Evidence budget exceeded; require complete export before scoring')
    for name,text in encoded.items():
        p=dest/name;safe_inside(p,root,EvaluationError)
        if p.exists() and (p.is_symlink() or not p.is_file() or p.stat().st_nlink>1):raise EvaluationError('Unsafe evidence file')
        p.write_text(text,encoding='utf-8')

def grade(transcript,workspace_path):
    global _PS_ROOT
    root=Path(workspace_path).resolve();_PS_ROOT=root;truth,facts,metrics=reference(root)
    tables=[];unresolved=[];status='ok';candidate_error=None;artifact='results/对账报告.xlsx'
    try:
        output=root/'results';path=output/'对账报告.xlsx';safe_inside(output,root,CandidateError)
        if not path.is_file():
            choices=sorted(p for p in output.glob('*.xlsx') if not p.name.startswith('~$')) if output.is_dir() else []
            if len(choices)!=1:raise CandidateError('One identifiable XLSX deliverable is required')
            path=choices[0]
        safe_inside(path,output,CandidateError);artifact=path.relative_to(root).as_posix()
        if path.samefile(root/'gt/对账报告.xlsx'):raise CandidateError('Candidate points to private reference')
        tables,unresolved=scan_workbook(path)
    except CandidateError as exc:status='candidate_failed';candidate_error=str(exc)
    records={k:[r for t in tables if t['kind']==k for r in t['records']] for k in CATEGORIES}
    pop,pd=population(records,truth);numeric,nd=numeric_score(records,truth,facts,tables)
    summary=summary_diagnostics(tables,records,metrics,nd,truth)
    pop=min(pop,summary['groups']['counts']['score']);numeric=min(numeric,summary['groups']['money']['score'])
    pd['summary_major_errors']=summary['groups']['counts']['major_errors'];nd['summary_major_errors']=summary['groups']['money']['major_errors']
    diagnostics={'candidate_error':candidate_error,'population':pd,'numeric':nd,'summary':summary}
    if summary['unrecognized_numeric_rows'] or unresolved:status='evaluator_error'
    if status=='candidate_failed':pop=numeric=0.
    export_evidence(root,status,tables,truth,metrics,diagnostics,unresolved,artifact)
    if status=='evaluator_error':raise EvaluationError('Unrecognized numeric summary claims or unresolved formulas; inspect complete evidence and resolve extraction before issuing a valid score')
    return {'exception_population':float(pop),'reconciled_values':float(numeric),'overall_score':(40*pop+40*numeric)/80,'diagnostics':diagnostics}
"""Read-only matrix/conditional-formula extraction; no scoring weights live here."""
from decimal import Decimal as _pl_decimal


def _pl_conditional(name,args,number):
    if name=='SUMIF' and len(args) in {2,3}:
        ranges=[args[0] if isinstance(args[0],list) else [args[0]]]
        criteria=[args[1]];sums=args[-1] if len(args)==3 else args[0]
        sums=sums if isinstance(sums,list) else [sums]
    elif name=='COUNTIF' and len(args)==2:
        ranges=[args[0] if isinstance(args[0],list) else [args[0]]];criteria=[args[1]];sums=None
    elif name=='COUNTIFS' and len(args)>=2 and len(args)%2==0:
        ranges=[v if isinstance(v,list) else [v] for v in args[::2]];criteria=args[1::2];sums=None
    else:raise ValueError('unsupported conditional formula')
    if len({len(v) for v in ranges})!=1 or (sums is not None and len(sums)!=len(ranges[0])):
        raise ValueError('conditional formula range mismatch')
    # The registered candidate uses literal criteria. Unsupported operators/wildcards
    # remain explicit extraction failures instead of approximate Excel semantics.
    if any(isinstance(v,(dict,list)) or (isinstance(v,str) and any(c in v for c in '*?~<>=')) for v in criteria):
        raise ValueError('conditional criteria require a supported literal')
    def match(value,criterion):
        a,b=number(value),number(criterion)
        return a==b if a is not None and b is not None else str(value or '').casefold()==str(criterion or '').casefold()
    chosen=[i for i,row in enumerate(zip(*ranges)) if all(match(v,c) for v,c in zip(row,criteria))]
    if sums is None:return len(chosen)
    return sum((number(sums[i]) or _pl_decimal(0) for i in chosen),_pl_decimal(0))


_PL_MATRIX_KEYS={f'matrix_{kind}_{field}' for kind in ['qty','amount','missing','orphan','clean','price_only']
                 for field in ['order','receipt','net']}
_PL_MATRIX_KEYS.add('matrix_total_net')


def _pl_matrix_view(tables,records,metrics,numeric,truth,norm,summary_key,number):
    sets={k:{r['id'] for r in records[k]} for k in records}
    complete=all(sets[k]==set(truth[k]) for k in records)
    expected={};locations={};projections=[];converted=[]
    def total(kind,field):
        if sets[kind]!=set(truth[kind]):return None
        values={r['id']:number(r['values'].get(field)) for r in records[kind]}
        return None if any(v is None for v in values.values()) else sum(values.values(),_pl_decimal(0))
    def sub(a,b):return None if a is None or b is None else a-b
    sign=numeric['categories']['amount']['direction']
    def signed(value):return None if value is None else sign*value
    for kind in ['qty','amount','missing','orphan']:
        order=total(kind,'oa') if kind!='orphan' else _pl_decimal(0)
        receipt=total(kind,'ra') if kind!='missing' else _pl_decimal(0)
        expected.update({f'matrix_{kind}_order':order,f'matrix_{kind}_receipt':receipt,
                         f'matrix_{kind}_net':signed(sub(receipt,order))})
    clean_order=sub(sub(number(metrics['orders_amount']),total('amount','oa')),total('missing','oa')) if complete and sets['qty']<=sets['amount'] else None
    clean_receipt=sub(sub(number(metrics['receipts_amount']),total('amount','ra')),total('orphan','ra')) if complete and sets['qty']<=sets['amount'] else None
    expected.update(matrix_clean_order=clean_order,matrix_clean_receipt=clean_receipt,
                    matrix_clean_net=signed(sub(clean_receipt,clean_order)),
                    matrix_total_net=sign*(number(metrics['receipts_amount'])-number(metrics['orders_amount'])))
    price=[r for r in records['amount'] if r['id'] not in sets['qty']]
    for field,role in [('order','oa'),('receipt','ra'),('net','da')]:
        values=[number(r['values'].get(role)) for r in price]
        expected['matrix_price_only_'+field]=sum(values,_pl_decimal(0)) if complete and all(v is not None for v in values) else None
    def cell(col,row):
        result='';n=col+1
        while n:n,r=divmod(n-1,26);result=chr(65+r)+result
        return result+str(row)
    def plain(value):
        text=str(value or '');text=text.split('（',1)[0].split('(',1)[0]
        return norm(text).removesuffix('元')
    for table in tables:
        if table['kind']!='summary':converted.append(table);continue
        headers=None;rows=[];matrix_values={};matrix_locs={};matrix_visible={};net_present=False;seen=set()
        for row in table['rows']:
            vals=row['values'];names=[plain(v) for v in vals]
            cats=[i for i,v in enumerate(names) if v in {'类别','对账类别','差异类型','异常类别'}]
            counts=[i for i,v in enumerate(names) if v in {'笔数','记录数','订单笔数'}]
            if len(cats)==1 and len(counts)==1:
                headers={'category':cats[0],'count':counts[0]}
                headers_hidden=set(row.get('hidden_columns',[]))
                sequence={i for i,n in enumerate(names) if n in {'序号','编号'}}
                for i,n in enumerate(names):
                    if n in {'订单金额合计','采购订单金额','订单金额','采购金额','订单总额'}:headers['order']=i
                    elif n in {'入库金额合计','入库记录金额','入库金额','实收金额'}:headers['receipt']=i
                    elif n in {'金额差额','金额差额合计','金额差异合计','金额差额净额'}:headers['net']=i
                if not {'order','receipt'}.issubset(headers):
                    # A mixed legacy summary with one generic money column is not a dual-domain matrix.
                    headers=None;rows.append(row)
                continue
            category=summary_key(vals[headers['category']]) if headers and headers['category']<len(vals) else None
            is_total=headers is not None and any(norm(v) in {'合计','总计','total'} for v in vals[:headers['category']+1])
            if headers is None or category not in {'qty','amount','missing','orphan','clean','price_only'} and not is_total:
                rows.append(row);continue
            kind='total' if is_total else category
            if kind in seen:raise ValueError('Duplicate matrix category; extraction review required')
            seen.add(kind)
            mapped=set(headers.values())|sequence
            if any(number(v) is not None and i not in mapped for i,v in enumerate(vals)):
                raise ValueError('Unrecognized numeric matrix column; extraction review required')
            def emit(key,col,value=None,derived_from=None):
                nonlocal net_present
                value=vals[col] if value is None and col<len(vals) else value
                if number(value) is None:return
                label={'qty':'数量差异订单数','amount':'金额差异订单数','missing':'未入库订单数',
                       'orphan':'无对应订单入库单数','clean':'匹配且数量金额均一致订单数','price_only':'纯单价差异',
                       'orders':'总采购订单数','receipts':'入库记录总数','orders_amount':'订单金额合计','receipts_amount':'入库金额合计',
                       'net_amount':'金额差异净额合计','missing_amount':'未入库订单金额合计','orphan_amount':'孤立入库金额合计'}.get(key,key)
                hidden=[i for i,source in [(0,headers['category']),(1,col)]
                        if source in set(row.get('hidden_columns',[]))|headers_hidden]
                new={'row':row['row'],'values':[label,value]}
                if hidden:new['hidden_columns']=hidden
                rows.append(new);location=table['sheet']+'!'+cell(col,row['row'])
                locations[(table['sheet'],row['row'],label)]={'value_location':location,'derived_from':derived_from}
                projections.append({'sheet':table['sheet'],'row':row['row'],'key':key,'value_location':location,'derived_from':derived_from})
                matrix_values[key]=number(value);matrix_locs[key]=location
                matrix_visible[key]=not hidden
                if key=='net_amount':net_present=True
            combined=re.fullmatch(r'采购订单\s*(\d+)\s*(?:笔|条|单)\s*[/／,，;；]\s*入库(?:关联|记录)?\s*(\d+)\s*(?:个订单|笔|条|单)',str(vals[headers['count']]).strip()) if is_total else None
            if combined:
                emit('orders',headers['count'],int(combined.group(1)))
                emit('receipts',headers['count'],int(combined.group(2)))
            else:emit('orders' if is_total else kind,headers['count'])
            for field in ['order','receipt','net']:
                if field not in headers:continue
                key=f'matrix_{kind}_{field}'
                if is_total:key={'order':'orders_amount','receipt':'receipts_amount','net':'matrix_total_net'}[field]
                elif kind=='amount' and field=='net':key='net_amount'
                elif kind=='missing' and field=='order':key='missing_amount'
                elif kind=='orphan' and field=='receipt':key='orphan_amount'
                elif field=='net' and 'order' not in headers and 'receipt' not in headers:
                    text=' '.join(str(v) for v in vals if v is not None)
                    if kind=='missing' and '按订单总额' in text:key='missing_amount'
                    elif kind=='orphan' and '按入库金额' in text:key='orphan_amount'
                    elif kind=='missing':
                        # An unlabeled signed/unmatched amount needs semantic extraction review.
                        raise ValueError('Unrecognized signed unmatched summary amount; extraction review required')
                emit(key,headers[field])
            if is_total:headers=None
        if (not net_present and {'matrix_qty_net','matrix_price_only_net'}<=set(matrix_values)
                and sets['qty']<=sets['amount'] and complete):
            # Explicit quantity-linked + price-only partitions cover matched differences once.
            originals=[matrix_locs['matrix_qty_net'],matrix_locs['matrix_price_only_net']]
            label='金额差异净额合计';value=matrix_values['matrix_qty_net']+matrix_values['matrix_price_only_net']
            source_row=table['rows'][0]['row']
            derived={'row':source_row,'values':[label,float(value)]}
            if not all(matrix_visible[k] for k in ['matrix_qty_net','matrix_price_only_net']):derived['hidden_columns']=[1]
            rows.append(derived)
            locations[(table['sheet'],source_row,label)]={'value_location':'derived: '+' + '.join(originals),'derived_from':originals}
            projections.append({'key':'net_amount','derived_from':originals,'candidate_statement_synthesized':False})
        item=dict(table);item['rows']=rows;converted.append(item)
    return converted,expected,locations,projections


def _pl_install_summary_view():
    global summary_diagnostics
    original=summary_diagnostics
    def wrapped(tables,records,metrics,numeric,truth):
        global _PL_EXPECTED
        view,expected,locations,projections=_pl_matrix_view(tables,records,metrics,numeric,truth,norm,summary_key,number)
        _PL_EXPECTED=expected
        try:result=original(view,records,metrics,numeric,truth)
        finally:_PL_EXPECTED={}
        for claim in result['claims']:
            location=locations.get((claim['sheet'],claim['row'],claim['label']))
            if location:claim.update(location,extraction_profile='procurement-matrix-formulas/v2')
        result['matrix_extraction_provenance']=projections
        return result
    summary_diagnostics=wrapped


_PL_EXPECTED={}

SUMMARY_LABELS.update({key:[key] for key in _PL_MATRIX_KEYS})
MONEY_KEYS.update(_PL_MATRIX_KEYS)
_pl_install_summary_view()

# Publicly equivalent matched orders; the original short-label parser retains qualifiers.
SUMMARY_LABELS['matched']=list(SUMMARY_LABELS['matched'])+['已匹配订单']
SUMMARY_LABELS['clean']=list(SUMMARY_LABELS['clean'])+['完全匹配']
"""Source-embedded procurement summary sections; preserve original scoring units."""


def _ps_sections(tables, records, metrics, numeric, truth, root):
    import csv
    import hashlib
    from collections import defaultdict
    from decimal import Decimal

    def literal(value):
        return re.sub(r'[\s\u3000:：()（）,，。;；]', '', str(value or '')).casefold()

    with (root/'input/采购订单.csv').open(encoding='utf-8-sig', newline='') as stream:
        order_rows=list(csv.DictReader(stream))
    with (root/'input/入库记录.csv').open(encoding='utf-8-sig', newline='') as stream:
        receipt_rows=list(csv.DictReader(stream))
    orders={r['ORDER_ID']:r for r in order_rows}
    receipts={r['RECEIPT_NO']:r for r in receipt_rows}
    if (len(orders)!=len(order_rows) or len(receipts)!=len(receipt_rows)
            or number(len(orders))!=metrics['orders'] or number(len(receipts))!=metrics['receipts']
            or sum((number(r['TOTAL_AMOUNT']) for r in orders.values()),Decimal(0))!=metrics['orders_amount']
            or sum((number(r['RECV_AMOUNT']) for r in receipts.values()),Decimal(0))!=metrics['receipts_amount']):
        raise EvaluationError('Procurement source rows/totals do not match frozen reference')
    by_kind={k:{r['id']:r for r in rows} for k,rows in records.items()}
    complete={k:set(rows)==set(truth[k]) for k,rows in by_kind.items()}
    sign=numeric['categories']['amount']['direction']
    priorities={k:defaultdict(set) for k in by_kind}
    for table in tables:
        kind=table['kind']
        if kind not in by_kind or table.get('header_row') is None:continue
        header=next((r for r in table['rows'] if r['row']==table['header_row']),None)
        if header is None:continue
        columns=[i for i,v in enumerate(header['values']) if literal(v) in {'优先级','复核优先级','处理优先级'}]
        if len(columns)>1:raise EvaluationError('Ambiguous priority columns')
        if not columns:continue
        col=columns[0];rows={r['row']:r for r in table['rows']}
        for item in table.get('records',[]):
            vals=rows[item['row']]['values'];value=literal(vals[col] if col<len(vals) else None)
            # Priority labels are candidate text, not a prescribed enum.
            # Preserve exact categories without inferring 高=P1 or a business rank.
            # Only explicitly supported summary claims are interpreted below.
            if value:priorities[kind][value].add(item['id'])

    def total(kind, role, subset=None, absolute=False):
        if not complete[kind]:return None
        rows=by_kind[kind]
        chosen=set(rows) if subset is None else set(subset)
        values=[]
        for key in chosen:
            row=rows[key];value=number(row['values'].get(role))
            # Quantity rows may legitimately omit money. The same submitted ID
            # in the amount table is an explicit candidate source, not GT fill.
            if value is None and kind=='qty' and key in by_kind['amount']:
                value=number(by_kind['amount'][key]['values'].get(role))
            if value is None:return None
            values.append(abs(value) if absolute else value)
        return sum(values,Decimal(0))

    def difference(a,b):return None if a is None or b is None else a-b
    def subject(label,parent):
        text=literal(label);short=re.split(r'[（(]',str(label or ''),maxsplit=1)[0]
        aliases={'orders':['采购订单','全部采购订单','采购订单全部状态'],
                 'receipts':['入库记录','全部入库记录','入库记录全部'],
                 'matched':['已匹配','已匹配组数','已匹配订单'],
                 'clean':['已匹配且数量金额一致','匹配且数量金额均一致','完全匹配'],
                 'qty':['由数量差异传导','数量差异'],
                 'amount':['金额差异合计','金额差异'],
                 'price_only':['数量一致、仅单价差异','纯单价差异'],
                 'missing':['未入库订单','未入库订单金额','未入库订单金额合计'],
                 'orphan':['无对应订单入库','无对应订单入库金额','无订单入库金额','孤立入库金额合计'],
                 'unmatched_net':['两类未匹配金额净额'],
                 'unmatched_sum':['两类未匹配金额合计'],
                 'source_net':['差额合计','总差额','恒等式：总差额 ＝ 未入库 － 无订单 ＋ 已匹配差']}
        text=re.sub(r'^其中', '',text)
        for kind,values in aliases.items():
            if text in {literal(x) for x in values} or literal(short) in {literal(x) for x in values}:
                return kind,None
        if parent=='missing':
            match=re.fullmatch(r'状态[“”"\']?(.+?)[“”"\']?',text)
            if match:
                status=match.group(1)
                if status not in {literal(r['STATUS']) for r in orders.values()}:
                    raise EvaluationError('Unknown source order status in summary')
                ids={key for key in by_kind['missing'] if key in orders and literal(orders[key]['STATUS'])==status}
                return 'missing',ids
        match=re.fullmatch(r'去重后(p[123])合计',text)
        return ('priority_union',match.group(1)) if match else (None,None)

    def expected(kind,field,subset):
        selected=set(by_kind[kind]) if kind in by_kind and subset is None else subset
        if field=='count':
            if kind in by_kind:return Decimal(len(selected))
            if kind in {'orders','receipts'}:return metrics[kind]
            if kind=='matched':return metrics['orders']-len(by_kind['missing'])
            if kind=='clean':return metrics['orders']-len(set().union(*(set(by_kind[k]) for k in ('qty','amount','missing'))))
            if kind=='price_only':return Decimal(len(set(by_kind['amount'])-set(by_kind['qty'])))
            if kind in {'unmatched_net','unmatched_sum'}:return Decimal(len(by_kind['missing'])+len(by_kind['orphan']))
        if kind=='unmatched_sum' and field=='unmatched_amount':
            a=total('missing','oa');b=total('orphan','ra')
            return None if a is None or b is None else a+b
        if kind=='price_only':kind='amount';selected=set(by_kind['amount'])-set(by_kind['qty'])
        if kind in by_kind:
            if field=='reported_difference':return total(kind,'da',selected)
            if field=='order_amount':return Decimal(0) if kind=='orphan' else total(kind,'oa',selected)
            if field=='receipt_amount':return Decimal(0) if kind=='missing' else total(kind,'ra',selected)
            if field in {'net','abs'}:
                a=Decimal(0) if kind=='orphan' else total(kind,'oa',selected)
                b=Decimal(0) if kind=='missing' else total(kind,'ra',selected)
                if field=='abs':return total(kind,'da',selected,absolute=True) if kind in {'qty','amount'} else (a if kind=='missing' else b)
                return None if a is None or b is None else sign*(b-a)
            if field in {'order_quantity','receipt_quantity','quantity'}:
                role='rq' if field=='receipt_quantity' or field=='quantity' and kind=='orphan' else 'oq'
                return total(kind,role,selected)
            if field in {'less','more'}:
                if kind not in {'qty','amount'}:return None
                role='dq' if kind=='qty' else 'da'
                # These headers describe receipt vs order, independent of the
                # candidate's chosen signed-difference convention.
                values=[number(r['values'].get(role)) for k,r in by_kind[kind].items() if k in selected]
                if any(v is None for v in values):return None
                direction=numeric['categories'][kind]['direction']
                return Decimal(sum((direction*v<0 if field=='less' else direction*v>0) for v in values))
        if kind in {'orders','receipts'}:
            if field==('order_amount' if kind=='orders' else 'receipt_amount'):return metrics[kind+'_amount']
            if field==('order_quantity' if kind=='orders' else 'receipt_quantity'):
                return sum((number(r['ORDER_QTY'] if kind=='orders' else r['RECV_QTY']) for r in (orders if kind=='orders' else receipts).values()),Decimal(0))
        if kind in {'matched','clean'}:
            if not all(complete.values()):return None
            if kind=='clean' and field in {'less','more'}:return Decimal(0)
            if field in {'order_amount','receipt_amount','order_quantity','receipt_quantity'}:
                is_order=field.startswith('order');source='orders' if is_order else 'receipts'
                base=expected(source,field,None)
                role={'order_amount':'oa','receipt_amount':'ra','order_quantity':'oq','receipt_quantity':'rq'}[field]
                excluded='missing' if is_order else 'orphan'
                value=difference(base,total(excluded,role))
                if kind=='clean':value=difference(value,total('amount',role))
                return value
            if field in {'net','abs'}:
                if kind=='clean':return Decimal(0)
                return expected('amount',field,None)
        if kind in {'source_net','unmatched_net'}:
            a=metrics['orders_amount'] if kind=='source_net' else total('missing','oa')
            b=metrics['receipts_amount'] if kind=='source_net' else total('orphan','ra')
            if field=='order_amount':return a
            if field=='receipt_amount':return b
            if field=='order_quantity':return expected('orders',field,None) if kind=='source_net' else None
            if field=='receipt_quantity':return expected('receipts',field,None) if kind=='source_net' else None
            if field=='net':return None if a is None or b is None else sign*(b-a)
        return None

    header_names={'笔数':'count','记录数':'count','订单笔数':'count',
        '订单金额元':'order_amount','订单金额':'order_amount','采购订单金额':'order_amount',
        '入库金额元':'receipt_amount','入库金额':'receipt_amount',
        '金额差额订单－入库':'net','金额差额元':'net','金额差额净额元':'net','差额元':'net',
        '金额差额/金额合计元':'unmatched_amount',
        '差额绝对值合计元':'abs','订单数量':'order_quantity','入库数量':'receipt_quantity',
        '数量订单':'order_quantity','数量入库':'receipt_quantity','数量':'quantity',
        '少于订单笔数':'less','多于订单笔数':'more','占订单总额':'ratio',
        'p1':'p1','p2':'p2','p3':'p3','跟踪':'跟踪','合计':'count',
        '表内值':'check','源数据复算值':'check','差异':'check_difference'}
    text_headers={'说明','说明与表间关系','备注','优先级判定规则','结论','校验方法','核对口径对应明细表'}
    converted=[];extra={};locations={};audit=[]
    for table in tables:
        if table['kind']!='summary':converted.append(table);continue
        rows=[];headers=None;parent=None;header_hidden=set()
        for row in table['rows']:
            vals=row['values'];names=[literal(v) for v in vals]
            if names and names[0] in {'项目','差异类型','工作表','校验项','类别'}:
                recognized={i:header_names[n] for i,n in enumerate(names[1:],1) if n in header_names}
                if recognized and all(not n or i==0 or i in recognized or n in text_headers for i,n in enumerate(names)):
                    headers=recognized;header_hidden=set(row.get('hidden_columns',[]));parent=None;continue
                headers=None
            if len(vals)==1 and isinstance(vals[0],str) and re.match(r'^[一二三四五六七八九十]+[、.]',vals[0]):
                headers=None;parent=None
            if headers is None or not any(number(v) is not None for v in vals):rows.append(row);continue
            kind,subset=subject(vals[0],parent)
            if kind is None and 'unmatched_amount' in headers.values():
                fallback=summary_key(vals[0])
                if fallback in CATEGORIES:kind=fallback
            if kind is None:rows.append(row);continue
            mixed_field=None
            if 'unmatched_amount' in headers.values():
                # A mixed amount header alone cannot decide sum versus signed net.
                # Bind each value to its declared submitted column or explicit
                # addition; preserve unknown meanings for the original failure gate.
                texts=[literal(v).replace('＋','+') for i,v in enumerate(vals)
                       if i not in headers and i!=0 and literal(v)]
                descriptions={
                    'qty': [('对应「数量差异」表，金额差额(订单-入库)列合计','reported_difference')],
                    'amount': [('对应「金额差异」表，金额差额(订单-入库)列合计','reported_difference')],
                    'missing': [('对应「未入库订单」表，订单金额列合计','order_amount')],
                    'orphan': [('对应「'+name+'」表，入库金额列合计','receipt_amount')
                               for name in ['无对应订单入库','无对应订单入库记录','无对应订单的入库记录']],
                    'unmatched_sum': [('未入库订单金额合计+无对应订单入库金额合计','unmatched_amount')],
                }
                if len(texts)==1:
                    mixed_field=next((field for note,field in descriptions.get(kind,[])
                                      if texts[0]==literal(note)),None)
                if (mixed_field is None or sorted(headers.values())!=['count','unmatched_amount']):
                    rows.append(row);continue
            if subset is None and kind in by_kind:parent=kind
            # Unknown numeric columns remain subject to the original failure gate.
            if any(number(v) is not None and i not in headers for i,v in enumerate(vals)):
                rows.append(row);continue
            emitted=[]
            subset_tag=(str(subset) if isinstance(subset,str) else
                        hashlib.sha256('\0'.join(sorted(subset)).encode()).hexdigest()[:12]
                        if subset is not None else 'all')
            for col,field in headers.items():
                if col>=len(vals) or number(vals[col]) is None:continue
                if field in {'p1','p2','p3','跟踪'} or kind=='priority_union':
                    if kind=='priority_union':
                        union=set().union(*(v.get(subset,set()) for v in priorities.values()))
                        e=Decimal(len(union)) if field in {subset,'count'} else Decimal(0)
                    elif kind in by_kind:e=Decimal(len(priorities[kind].get(field,set())))
                    else:raise EvaluationError('Unsupported priority summary subject')
                    group='counts';key=f'ps_{kind}_{subset or "all"}_{field}'
                else:
                    mapped=mixed_field if field=='unmatched_amount' else field
                    if field in {'check','check_difference'}:
                        mapped=('order_amount' if kind=='missing' or kind=='orders' and '金额' in str(vals[0]) else
                                'receipt_amount' if kind=='orphan' or kind=='receipts' and '金额' in str(vals[0]) else
                                'net' if kind=='source_net' else 'count')
                        # A label mentioning only counts must not become a money claim.
                        if kind in {'missing','orphan'} and '金额' not in str(vals[0]):mapped='count'
                    e=expected(kind,mapped,subset)
                    if field=='check_difference':e=Decimal(0)
                    if field=='ratio':
                        basis=expected(kind,'abs' if kind in {'qty','amount','price_only'} else 'order_amount' if kind=='missing' else 'receipt_amount' if kind=='orphan' else 'net',subset)
                        e=None if basis is None else abs(basis)/metrics['orders_amount']
                    group='money' if mapped in {'order_amount','receipt_amount','net','abs','unmatched_amount','reported_difference'} else 'counts'
                    key=(kind if mapped=='count' and kind in {'qty','amount','missing','orphan','orders','receipts','matched','clean','price_only'} and subset is None and field!='check_difference' else
                         'net_amount' if kind=='amount' and mapped in {'net','reported_difference'} else
                         'abs_amount' if kind=='amount' and mapped=='abs' else
                         'missing_amount' if kind=='missing' and mapped=='order_amount' and subset is None and field!='check_difference' else
                         'orphan_amount' if kind=='orphan' and mapped=='receipt_amount' and subset is None and field!='check_difference' else
                         f'ps_{kind}_{subset_tag}_{field}_{mapped}')
                extra[key]=e
                if group=='money':MONEY_KEYS.add(key)
                if field=='ratio':_PS_TOLERANCES[key]=Decimal('0.000000001')
                label=f'_ps/{key}/{col}'
                SUMMARY_LABELS.setdefault(key,[]).append(label)
                projection={'row':row['row'],'values':[label,vals[col]]}
                if 0 in row.get('hidden_columns',[]) or col in row.get('hidden_columns',[]) or col in header_hidden:projection['hidden_columns']=[1]
                emitted.append(projection)
                location=table['sheet']+'!'+get_column_letter(col+1)+str(row['row'])
                locations[(table['sheet'],row['row'],label)]={'value_location':location,'extraction_profile':'procurement-section-columns/v1'}
                audit.append({'location':location,'subject':kind,'field':field,'key':key,'expected_unavailable':e is None})
            rows.extend(emitted)
        copy=dict(table);copy['rows']=rows;converted.append(copy)
    return converted,extra,locations,audit


_PS_TOLERANCES={}
_ps_original_matrix_view=_pl_matrix_view


def _pl_matrix_view(tables,records,metrics,numeric,truth,*args):
    converted,expected,locations,projections=_ps_original_matrix_view(tables,records,metrics,numeric,truth,*args)
    converted,extra,new_locations,audit=_ps_sections(converted,records,metrics,numeric,truth,_PS_ROOT)
    expected.update(extra);locations.update(new_locations);projections.extend(audit)
    return converted,expected,locations,projections


_pt_previous_matrix_view = _pl_matrix_view


def _pl_matrix_view(tables, records, metrics, numeric, truth, *args):
    """Project explicit source totals and declared arithmetic; retain raw locations."""
    import csv
    from decimal import Decimal

    converted, expected, locations, audit = _pt_previous_matrix_view(
        tables, records, metrics, numeric, truth, *args)
    by_kind = {k: {r['id']: r for r in rows} for k, rows in records.items()}
    complete = {k: set(rows) == set(truth[k]) for k, rows in by_kind.items()}

    def total(kind, role, subset=None):
        if not complete[kind]:
            return None
        selected = set(by_kind[kind]) if subset is None else set(subset)
        values = [number(by_kind[kind][key]['values'].get(role)) for key in selected]
        return None if any(v is None for v in values) else sum(values, Decimal(0))

    def count(kind, subset=None):
        return None if not complete[kind] else Decimal(len(by_kind[kind] if subset is None else subset))

    def calc(left, right, subtract=False):
        return None if left is None or right is None else left-right if subtract else left+right

    with (_PS_ROOT/'input/采购订单.csv').open(encoding='utf-8-sig', newline='') as stream:
        orders = list(csv.DictReader(stream))
    with (_PS_ROOT/'input/入库记录.csv').open(encoding='utf-8-sig', newline='') as stream:
        receipts = list(csv.DictReader(stream))
    # The preceding section verifier binds source identities/counts/money.
    def source_quantity(rows, field):
        values = [number(row[field]) for row in rows]
        if any(v is None for v in values):
            raise EvaluationError('Invalid source quantity for declared totals')
        return sum(values, Decimal(0))

    oq = source_quantity(orders, 'ORDER_QTY')
    rq = source_quantity(receipts, 'RECV_QTY')
    missing_amount = total('missing', 'oa')
    orphan_amount = total('orphan', 'ra')
    amount_difference = total('amount', 'da')
    detail_net = calc(calc(amount_difference, orphan_amount), missing_amount, True)
    source_net = metrics['receipts_amount']-metrics['orders_amount']
    matched_oq = calc(oq, total('missing', 'oq'), True)
    matched_rq = calc(rq, total('orphan', 'rq'), True)
    price_ids = set(by_kind['amount'])-set(by_kind['qty'])
    price_count = count('amount', price_ids) if complete['qty'] else None
    price_amount = total('amount', 'da', price_ids) if complete['qty'] else None

    def text(value):
        value = str(value or '').strip().casefold()
        value = value.replace('＝', '=').replace('＋', '+').replace('－', '-')
        return re.sub(r'[\s\u3000:：()（）,，。;；]', '', value)

    ordinal_values = {
        ('①', text('已匹配金额差额（金额差异表净差额）')): ('amount_detail', amount_difference, True),
        ('②', text('加：无对应订单入库金额')): ('orphan_detail', orphan_amount, True),
        ('③', text('减：未入库订单金额（取绝对值）')): ('missing_detail', missing_amount, True),
        ('④', text('明细推算总差额 =①+②-③')): ('detail_net', detail_net, True),
        ('⑤', text('源表总差额 = 入库总额-订单总额')): ('source_net', source_net, True),
        ('⑥', text('校验差异 =⑤-④（应为 0.00）')): ('source_detail_difference', calc(source_net, detail_net, True), True),
        ('⑦', text('数量勾稽：已匹配两侧数量差（应为 0）')): ('matched_quantity_difference', calc(matched_rq, matched_oq, True), False),
    }
    output = []
    for table in converted:
        if table['kind'] != 'summary':
            output.append(table)
            continue
        rows = []
        context = None
        header_hidden = set()
        cause_parts = set()
        for row in table['rows']:
            vals = row['values']
            names = [text(v) for v in vals]
            contexts = {
                ('项目', '笔数', '数量', '金额元', '备注'): 'source',
                ('成因', '笔数', '金额差额元', '说明'): 'cause',
                ('类别', '订单状态', '笔数', '金额元', '处理提示'): 'status',
                ('勾稽项', '', '', '数值', '校验说明'): 'reconcile',
            }
            if tuple(names) in contexts:
                context = contexts[tuple(names)]
                header_hidden = set(row.get('hidden_columns', []))
                cause_parts = set()
                rows.append(row)
                continue
            if len(vals) == 1 and isinstance(vals[0], str) and re.match(r'^[一二三四五六七八九十]+[、.]', vals[0]):
                context = None
                cause_parts = set()
            claims = None
            label = names[0] if names else ''
            if context == 'source':
                if label == text('采购订单（源表）'):
                    claims = [(1, 'orders_count', metrics['orders'], False),
                              (2, 'orders_quantity', oq, False),
                              (3, 'orders_amount', metrics['orders_amount'], True)]
                elif label == text('入库记录（源表）'):
                    claims = [(1, 'receipts_count', metrics['receipts'], False),
                              (2, 'receipts_quantity', rq, False),
                              (3, 'receipts_amount', metrics['receipts_amount'], True)]
                elif label == text('其中：已匹配入库'):
                    claims = [(1, 'matched_receipts_count', calc(metrics['receipts'], count('orphan'), True), False),
                              (2, 'matched_receipts_quantity', matched_rq, False),
                              (3, 'matched_receipts_amount', calc(metrics['receipts_amount'], orphan_amount, True), True)]
                elif label == text('差额合计（入库-订单）'):
                    claims = [(2, 'source_quantity_difference', rq-oq, False),
                              (3, 'source_amount_difference', source_net, True)]
            elif context == 'cause':
                if label == text('数量差异导致（单价一致）'):
                    cause_parts.add('qty')
                    claims = [(1, 'qty_cause_count', count('qty'), False),
                              (2, 'qty_cause_amount', total('qty', 'da'), True)]
                elif label == text('单价差异导致（数量一致）'):
                    cause_parts.add('price')
                    claims = [(1, 'price_cause_count', price_count, False),
                              (2, 'price_cause_amount', price_amount, True)]
                elif label == '合计' and cause_parts == {'qty', 'price'}:
                    claims = [(1, 'cause_total_count', count('amount'), False),
                              (2, 'cause_total_amount', amount_difference, True)]
            elif context == 'status' and label == text('未入库订单 小计'):
                claims = [(2, 'missing_subtotal_count', count('missing'), False),
                          (3, 'missing_subtotal_amount', missing_amount, True)]
            elif context == 'reconcile' and vals and isinstance(vals[0], str):
                raw = vals[0].lstrip()
                item = ordinal_values.get((raw[:1], text(raw[1:])))
                if item is not None:
                    key, value, money = item
                    claims = [(3, key, value, money)]
            if not claims:
                rows.append(row)
                continue
            allowed = {col for col, _, _, _ in claims}
            if (any(number(v) is not None and i not in allowed for i, v in enumerate(vals))
                    or any(col >= len(vals) or number(vals[col]) is None for col in allowed)):
                rows.append(row)
                continue
            for col, key, value, money in claims:
                key = 'pt_'+key
                expected[key] = value
                if money:
                    MONEY_KEYS.add(key)
                projected_label = '_pt/'+key+'/'+str(col)
                SUMMARY_LABELS.setdefault(key, []).append(projected_label)
                projected = {**row, 'values': [projected_label, vals[col]]}
                if 0 in row.get('hidden_columns', []) or col in row.get('hidden_columns', []) or 0 in header_hidden or col in header_hidden:
                    projected['hidden_columns'] = [1]
                rows.append(projected)
                location = table['sheet']+'!'+get_column_letter(col+1)+str(row['row'])
                locations[(table['sheet'], row['row'], projected_label)] = {
                    'value_location': location, 'extraction_profile': 'procurement-declared-source-totals/v1'}
                audit.append({'location': location, 'key': key, 'expected_unavailable': value is None,
                              'candidate_statement_synthesized': False})
        output.append({**table, 'rows': rows})
    return output, expected, locations, audit
```

## LLM Judge Rubric

仅使用本次完整有效的四份评分器证据；以候选工作簿中的解释、标签及共享说明为语义证据，reference仅用于核实业务事实。表级说明可覆盖整类，无需逐行重写。每项固定分母4，不按只提交的类别缩小分母；同义重复说明不增加单位。缺数字/漏编号已由规则负责，不再次按这些数值错误扣语义分。纯标题或“未说错”不足以证明主动表达了下面要求的含义。可从明确标签组合和说明推得同等语义，不要求固定关键词。

每项notes须列4个单位的满足/不满足、候选表名及行号/单元位置、分子分母和任何上限触发事实。证据不完整、提取无效或合法公式无法求值时先标不可判定并补证，不用默认0或1替代正式评分；接口只接受数值时，不发布该次占位分为有效总分。缺交付且证据明确完整时各项0。只返回以下三个key，禁止自由插值。

### Criterion 1: 核对范围与统计口径 (key: scope_explanation, weight: 6)

以下四个独立单位各1：

1. 能明确确认范围为本批两份记录，并区分采购订单与入库记录两种总体对象；不能把入库单数直接称为已入库订单数。无依据的STATUS/日期过滤不满足，但单个总数算错不在此重复扣。
2. 四类汇总与明细的分类对象清楚，已匹配数量/金额差异与两侧未匹配类别分开，分类计数标签明确。只缺少个别数据行不影响本单位；缺乏对象定义或把未匹配都当成已收数量0则不满足。
3. 明确交代数量和金额类别可重叠、分类数不可直接相加作唯一订单数；同时区分异常订单与孤立入库的计数单位。可用清晰交集/去重表述证明，无须额外新增去重总数。只是未声称互斥，不能计满足；具体数字错误归规则。
4. 明确两类差额方向及金额一致容差，能继承到相应明细；各表方向不同时分别说明。单个计算错误不重复扣，但仅放正负数字、没有可辨口径不满足。

**Score 1.0**: 4个单位满足。
**Score 0.75**: 3个单位满足。
**Score 0.5**: 2个单位满足。
**Score 0.25**: 1个单位满足。
**Score 0.0**: 0个单位满足，或缺交付。

### Criterion 2: 异常解释与事实边界 (key: exception_interpretation, weight: 8)

四类各为一个单位，必须既说明可从记录得出的结论，也表达该类重要的推断边界：

1. 数量类说明记录中的多入/少入含义，且不将记录差直接确认为实物损失、供应商责任；共享“仅为两份记录差异、原因待查”可满足边界。
2. 金额类说明比较的是双方记载金额及高低，且不能直接推出欠款、退款义务或价格录入错误。数量相等且金额不同可推出折算单价不同，这一算术推导是合法的；把价格变更、错录等具体成因确认为事实则超出材料。
3. 未入库类说明是本批订单缺少可匹配的入库记录，不能确认现实未收货；“本批记录未匹配”足以表达范围边界。
4. 孤立入库类说明是本批入库缺少可匹配的订单记录，不能证明无审批或违规采购；“本批记录未匹配”足以表达范围边界。

每类内容完整记1，固定分母4。只有“数量差异”“未入库”之类标题而无上述明确语义不计完整。若把无材料支持的原因、责任、实物状态、付款退款义务或合规结论**确定为事实**，例如认定错录、退货、实物损失、现实未收货或违规采购，本项最高0.25；候选清楚标记“可能”“需核验”的假设不触发。按计数基础分和上限取小。规则中的漏行、数值误差不重复计入本项。

**Score 1.0**: 4类满足，且无重大无依据断言。
**Score 0.75**: 3类满足，且无重大无依据断言。
**Score 0.5**: 2类满足，且无重大无依据断言。
**Score 0.25**: 1类满足；或至少1类满足但触发重大断言上限。
**Score 0.0**: 0类满足，或缺交付。

### Criterion 3: 可执行复核建议 (key: review_actions, weight: 6)

四类异常各一个复核单位。每类同时满足以下三项才记1：说明核查的对象或问题；指定适合该问题的业务凭据及比对关系；说明凭据确认后怎样区分状态或何时才应更正/补录。固定分母4，类别共享建议可用，不要求逐行建议、指定部门、联系他人或真的执行操作。

可接受的证据关系举例：数量差异对照订单和签收/实收凭据并核对分批/退货；金额差异对照计价条款、价格变更批准与入库计价记录；未入库对照发运、签收和入库台账区分在途/漏记；孤立入库核对原始采购订单、审批或编号关系，确认缺单/错号后再处理。这些不是唯一答案，其他足以检验具体假设的凭据组合也可。泛泛“请采购核实”“检查原始数据”“尽快处理”缺少凭据关系或判断条件，不能计完整单位。

初评分=满足类数/4。要超过0.5，还必须至少给出一项可定位的优先对象或对象组和相应依据，例如金额/数量差异幅度、状态与登记缺口或关联缺口；明确排序或“先查某类”均可，没有依据的“全部优先”不满足。对同类给出20条同义建议仍只计1。

若建议在未核实差异来源或审批依据之前直接付款、退款、注销、改账或追责，本项最高0.25；“先核对凭据，确认后更正”不触发。只在解释中出现无依据原因而没有此类处置建议，归exception_interpretation；不要因同一句原因断言自动把两个语义项都封顶。建议缺失属于独立义务，不从表格可读或数据正确推断已完成。

**Score 1.0**: 4类建议完整，优先对象和依据明确，未触发不当处置上限。
**Score 0.75**: 3类建议完整，优先对象和依据明确，未触发不当处置上限。
**Score 0.5**: 2类建议完整；或3—4类完整但优先对象/依据缺失；均未触发不当处置上限。
**Score 0.25**: 1类建议完整；或至少1类完整但触发不当处置上限。
**Score 0.0**: 0类建议完整，或缺交付。

## Workspace Path

workspace/general_e2e/02_Office/task_015_procurement_reconciliation

## Skills

## Env

## Warmup
