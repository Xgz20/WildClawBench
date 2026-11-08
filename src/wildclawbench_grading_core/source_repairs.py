"""Exact-source implementation repairs shared by native E2E and the CLI."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from functools import lru_cache

_PROFILES = {'b80e8169171e514cc4902613e1cda020fb99076c6fe412d7c45b907f1dc29afe': {'task_id': '01_Information_Search_Organization_task_001_acl2024_long_context_qa',
                                                                      'profile': 'invalid-candidate-pdf-structure/v1',
                                                                      'reason': '仅将需要结构修复且未通过原等价签名的候选PDF归为交付未通过；原接受版本、完整未知版本复核及4分预算保持。',
                                                                      'changes': [('                page_texts = '
                                                                                   '[page.get_text("text") for page in '
                                                                                   'document]',
                                                                                   '                '
                                                                                   'record["requires_pdf_repair"] = '
                                                                                   'bool(document.is_repaired)\n'
                                                                                   '                page_texts = '
                                                                                   '[page.get_text("text") for page in '
                                                                                   'document]'),
                                                                                  ('                elif identified:\n'
                                                                                   '                    '
                                                                                   'record.update(status="pending_version_review", '
                                                                                   'possible_paper_ids=identified)',
                                                                                   '                elif identified '
                                                                                   'and '
                                                                                   'record.get("requires_pdf_repair"):\n'
                                                                                   '                    '
                                                                                   'record.update(status="non_equivalent_repaired_pdf", '
                                                                                   'possible_paper_ids=identified)\n'
                                                                                   '                elif identified:\n'
                                                                                   '                    '
                                                                                   'record.update(status="pending_version_review", '
                                                                                   'possible_paper_ids=identified)')],
                                                                      'current_source_sha256': 'be25eda7c74472bce30429d08e3b1fc10fb7e47c0f74dd149d571d76c07c43a7'},
 '5b734e764fc73422f656b579feed386d41c9bd49ec4437568a8e37e4363bb810': {'task_id': '02_Office_task_010_warranty_recovery_allocation',
                                                                      'profile': 'warranty-whole-column-and-summary-roles/v3',
                                                                      'reason': '支持合法整列聚合与COUNTA，按明确业务表头抽取已入账/计入暴露成本，并识别无业务ID的显式合计行；缺编号实际业务行保留，原金额、分母、重大错误和权重不变。',
                                                                      'changes': [('class Cells:\n',
                                                                                   'class '
                                                                                   '_WarrantyWholeColumnRange(list):\n'
                                                                                   '    def __init__(self, values, '
                                                                                   'logical_length):\n'
                                                                                   '        super().__init__(values)\n'
                                                                                   '        '
                                                                                   'self.logical_length=logical_length\n'
                                                                                   '\n'
                                                                                   'class Cells:\n'),
                                                                                  ('        if not '
                                                                                   "re.fullmatch(r'\\$?[A-Z]+\\$?\\d+(?::\\$?[A-Z]+\\$?\\d+)?',text,re.I):raise "
                                                                                   "EvaluationError('未支持的命名区域或外部引用')\n"
                                                                                   '        '
                                                                                   "x1,y1,x2,y2=range_boundaries(text.replace('$',''))",
                                                                                   '        if '
                                                                                   "re.fullmatch(r'\\$?[A-Z]+:\\$?[A-Z]+',text,re.I):\n"
                                                                                   '            '
                                                                                   "x1,_,x2,_=range_boundaries(text.replace('$',''))\n"
                                                                                   '            if not '
                                                                                   '1<=x1<=x2<=16384:raise '
                                                                                   "CandidateError('公式列引用不合法')\n"
                                                                                   "            if '[' in sheet or ']' "
                                                                                   'in sheet:raise '
                                                                                   "EvaluationError('未支持的外部工作簿引用')\n"
                                                                                   '            if sheet not in '
                                                                                   'self.formulas.sheetnames:raise '
                                                                                   "CandidateError('公式引用缺少的工作表')\n"
                                                                                   '            '
                                                                                   'ws=self.formulas[sheet];last=max(1,ws.max_row);width=x2-x1+1\n'
                                                                                   '            if '
                                                                                   'last*width>100000:raise '
                                                                                   "EvaluationError('公式区域过大')\n"
                                                                                   '            '
                                                                                   'values=[self.cell(sheet,ws.cell(r,c).coordinate) '
                                                                                   'for r in range(1,last+1) for c in '
                                                                                   'range(x1,x2+1)]\n'
                                                                                   '            return '
                                                                                   '_WarrantyWholeColumnRange(values,1048576*width)\n'
                                                                                   '        if not '
                                                                                   "re.fullmatch(r'\\$?[A-Z]+\\$?\\d+(?::\\$?[A-Z]+\\$?\\d+)?',text,re.I):raise "
                                                                                   "EvaluationError('未支持的命名区域或外部引用')\n"
                                                                                   '        '
                                                                                   "x1,y1,x2,y2=range_boundaries(text.replace('$',''))"),
                                                                                  ('            if '
                                                                                   "name=='SUMIFS':amounts=arr(args[0]);conditions=args[1:]\n"
                                                                                   '            elif '
                                                                                   "name=='SUMIF':conditions=args[:2];amounts=arr(args[2] "
                                                                                   'if len(args)>2 else args[0])\n'
                                                                                   '            '
                                                                                   'else:conditions=args;amounts=[1]*len(arr(args[0]))\n'
                                                                                   '            for region,criterion '
                                                                                   'in '
                                                                                   'zip(conditions[::2],conditions[1::2]):\n'
                                                                                   '                if '
                                                                                   'len(arr(region))!=len(amounts):raise '
                                                                                   "CandidateError('条件公式区域长度不一致')\n"
                                                                                   '            def '
                                                                                   'matches(value,criterion):\n'
                                                                                   '                if '
                                                                                   'isinstance(criterion,str) and '
                                                                                   "criterion[:1] in '<>=':raise "
                                                                                   "EvaluationError('未支持的条件公式比较字符串')\n"
                                                                                   '                return str(value '
                                                                                   "or '').casefold()==str(criterion "
                                                                                   "or '').casefold()\n"
                                                                                   '            return sum((v if '
                                                                                   'isinstance(v,(int,float)) else 0) '
                                                                                   'for i,v in enumerate(amounts) if '
                                                                                   'all(matches(arr(region)[i],criterion) '
                                                                                   'for region,criterion in '
                                                                                   'zip(conditions[::2],conditions[1::2])))',
                                                                                   '            counting=name in '
                                                                                   "('COUNTIF','COUNTIFS')\n"
                                                                                   '            if '
                                                                                   "name=='SUMIFS':amounts=arr(args[0]);conditions=args[1:]\n"
                                                                                   '            elif '
                                                                                   "name=='SUMIF':conditions=args[:2];amounts=arr(args[2] "
                                                                                   'if len(args)>2 else args[0])\n'
                                                                                   '            '
                                                                                   'else:conditions=args;amounts=None\n'
                                                                                   '            regions=[arr(region) '
                                                                                   'for region in conditions[::2]]\n'
                                                                                   '            logical=lambda '
                                                                                   "region:getattr(region,'logical_length',len(region))\n"
                                                                                   '            '
                                                                                   'length=logical(regions[0])\n'
                                                                                   '            if '
                                                                                   'any(logical(region)!=length for '
                                                                                   'region in regions) or not counting '
                                                                                   'and logical(amounts)!=length:raise '
                                                                                   "CandidateError('条件公式区域长度不一致')\n"
                                                                                   '            '
                                                                                   'stored=max([len(region) for region '
                                                                                   'in regions]+([] if counting else '
                                                                                   '[len(amounts)]))\n'
                                                                                   '            if stored>100000:raise '
                                                                                   "EvaluationError('公式区域过大')\n"
                                                                                   '            value_at=lambda '
                                                                                   'region,i:region[i] if '
                                                                                   'i<len(region) else None\n'
                                                                                   '            def '
                                                                                   'matches(value,criterion):\n'
                                                                                   '                if '
                                                                                   'isinstance(criterion,str) and '
                                                                                   'criterion and criterion[:1] in '
                                                                                   "'<>=':raise "
                                                                                   "EvaluationError('未支持的条件公式比较字符串')\n"
                                                                                   '                if '
                                                                                   "criterion=='':return value is None "
                                                                                   "or value==''\n"
                                                                                   '                return str(value '
                                                                                   "or '').casefold()==str(criterion "
                                                                                   "or '').casefold()\n"
                                                                                   '            result=0\n'
                                                                                   '            for i in '
                                                                                   'range(stored):\n'
                                                                                   '                if '
                                                                                   'all(matches(value_at(region,i),criterion) '
                                                                                   'for region,criterion in '
                                                                                   'zip(regions,conditions[1::2])):\n'
                                                                                   '                    v=1 if '
                                                                                   'counting else value_at(amounts,i)\n'
                                                                                   '                    result+=v if '
                                                                                   'isinstance(v,(int,float)) else 0\n'
                                                                                   '            if counting and '
                                                                                   'length>stored and '
                                                                                   'all(matches(None,criterion) for '
                                                                                   'criterion in '
                                                                                   'conditions[1::2]):result+=length-stored\n'
                                                                                   '            return result'),
                                                                                  ('            '
                                                                                   'value=self.node(tree,sheet,refs);self.memo[key]=value;return '
                                                                                   'value',
                                                                                   '            '
                                                                                   'value=self.node(tree,sheet,refs)\n'
                                                                                   '            if '
                                                                                   'isinstance(value,_WarrantyWholeColumnRange):raise '
                                                                                   "EvaluationError('全列引用必须用于聚合')\n"
                                                                                   '            '
                                                                                   'self.memo[key]=value;return value'),
                                                                                  ('            a,b=run(n.left) or '
                                                                                   '0,run(n.right) or 0',
                                                                                   '            '
                                                                                   'a,b=run(n.left),run(n.right)\n'
                                                                                   '            if '
                                                                                   'isinstance(a,_WarrantyWholeColumnRange) '
                                                                                   'or '
                                                                                   'isinstance(b,_WarrantyWholeColumnRange):raise '
                                                                                   "EvaluationError('未支持的全列数组运算')\n"
                                                                                   '            a,b=a or 0,b or 0'),
                                                                                  ('            '
                                                                                   "a,b=run(n.left),run(n.comparators[0]);a='' "
                                                                                   "if a is None else a;b='' if b is "
                                                                                   'None else b',
                                                                                   '            '
                                                                                   'a,b=run(n.left),run(n.comparators[0])\n'
                                                                                   '            if '
                                                                                   'isinstance(a,_WarrantyWholeColumnRange) '
                                                                                   'or '
                                                                                   'isinstance(b,_WarrantyWholeColumnRange):raise '
                                                                                   "EvaluationError('未支持的全列数组比较')\n"
                                                                                   "            a='' if a is None else "
                                                                                   "a;b='' if b is None else b"),
                                                                                  ("        if name=='IF':return "
                                                                                   'run(n.args[1] if run(n.args[0]) '
                                                                                   'else n.args[2])',
                                                                                   "        if name=='IF':\n"
                                                                                   '            '
                                                                                   'condition=run(n.args[0])\n'
                                                                                   '            if '
                                                                                   'isinstance(condition,_WarrantyWholeColumnRange):raise '
                                                                                   "EvaluationError('未支持的全列数组条件')\n"
                                                                                   '            return run(n.args[1] '
                                                                                   'if condition else n.args[2])'),
                                                                                  ("'REF','SUM','MIN'",
                                                                                   "'REF','SUM','COUNTA','MIN'"),
                                                                                  ("        if name=='SUM':return "
                                                                                   'sum(nums)',
                                                                                   "        if name=='SUM':return "
                                                                                   'sum(nums)\n'
                                                                                   "        if name=='COUNTA':return "
                                                                                   'sum(x is not None for x in '
                                                                                   'flat(args))'),
                                                                                  (" 'already':['已追偿汇总'",
                                                                                   " 'already':['已追偿（已入账）','已追偿汇总'"),
                                                                                  (" 'cost':['维修成本'",
                                                                                   " 'cost':['计入暴露维修成本','维修成本'"),
                                                                                  ("return name in {'分摊维修成本'",
                                                                                   'return name in '
                                                                                   "{'计入暴露维修成本','分摊维修成本'"),
                                                                                  ('def read_tables(path):',
                                                                                   'def '
                                                                                   '_warranty_explicit_aggregate(item,values,kind):\n'
                                                                                   '    def total_label(value):\n'
                                                                                   "        text=re.sub(r'\\s+', "
                                                                                   "'',str(value or '')).casefold()\n"
                                                                                   '        return '
                                                                                   "re.fullmatch(r'(?:合计|总计|小计|total|grandtotal)(?:[（(]\\d+(?:行|笔|条|rows?)[）)])?',text) "
                                                                                   'is not None\n'
                                                                                   "    if kind=='summary':return "
                                                                                   "total_label(item.get('supplier'))\n"
                                                                                   "    if item.get('supplier'):return "
                                                                                   'False\n'
                                                                                   '    return '
                                                                                   "total_label(item.get('claim')) or "
                                                                                   "(not item.get('claim') and "
                                                                                   'bool(values) and '
                                                                                   'total_label(values[0]))\n'
                                                                                   '\n'
                                                                                   'def read_tables(path):'),
                                                                                  ('                '
                                                                                   "anchor=item.get('supplier') if "
                                                                                   "kind=='summary' else "
                                                                                   "item.get('claim')",
                                                                                   '                '
                                                                                   "anchor=item.get('supplier') if "
                                                                                   "kind=='summary' else "
                                                                                   "item.get('claim')\n"
                                                                                   '                '
                                                                                   'raw_values=[cells.cell(ws.title,ws.cell(r,c).coordinate) '
                                                                                   'for c in '
                                                                                   'range(1,ws.max_column+1)]\n'
                                                                                   '                if '
                                                                                   '_warranty_explicit_aggregate(item,raw_values,kind):continue'),
                                                                                  ('                '
                                                                                   "item['_raw_values']=[cells.cell(ws.title,ws.cell(r,c).coordinate) "
                                                                                   'for c in range(1,ws.max_column+1)]',
                                                                                   '                '
                                                                                   "item['_raw_values']=raw_values")],
                                                                      'current_source_sha256': '3e1acfa74c962ac8ac1b1bd6f66fc8ddcea06170e1a49ab184f086ad989ff0a4'},
 '7117b998478660abcb33c78c87074e0f0e89b496cfb7beb632e37a61432c979b': {'task_id': '02_Office_task_015_procurement_reconciliation',
                                                                      'profile': 'procurement-date-and-section-extraction/v6',
                                                                      'reason': '严格投影明确来源合计、互斥分类小计与已声明加减勾稽算式；逐格保留原值和来源位置，缺明细保持未知、隐藏不可授正确，未知数值仍拒绝；原数字规则、容差、分母和80/20不变。',
                                                                      'changes': [('json.dumps(chunks[i],ensure_ascii=False)',
                                                                                   'json.dumps(chunks[i],ensure_ascii=False,default=str)'),
                                                                                  ("tol=MONEY_TOLERANCE+Decimal('0.00000001') "
                                                                                   "if c['key'] in MONEY_KEYS else "
                                                                                   'Decimal(0)',
                                                                                   "tol=_PS_TOLERANCES.get(c['key'],MONEY_TOLERANCE+Decimal('0.00000001') "
                                                                                   "if c['key'] in MONEY_KEYS else "
                                                                                   'Decimal(0))'),
                                                                                  ('    '
                                                                                   'root=Path(workspace_path).resolve();truth,facts,metrics=reference(root)',
                                                                                   '    global _PS_ROOT\n'
                                                                                   '    '
                                                                                   'root=Path(workspace_path).resolve();_PS_ROOT=root;truth,facts,metrics=reference(root)')],
                                                                      'current_source_sha256': 'b2ea6ca9c67a605e6ec95322a9d952d7bf7321488a5507ec3347a25fe79e26e2',
                                                                      'append_source': 'procurement_sections.py',
                                                                      'append_source_sha256': 'afda1e1f780b5369dfaa767d354e745bd72c75f255135a2b9915105fc6c4e35e'}}

_PROFILES.update({'13c5130e0292799e066d59c2076f3ed2a050650c61572fa3cec3266d97dca69a': {'task_id': '03_Data_Analysis_task_001_hr_worktime_reconciliation',
                                                                      'profile': 'hr-native-time-evidence-serialization/v1',
                                                                      'reason': '只补充Excel原生time值的ISO证据序列化；原日期、工时、业务字段、来源判定及评分权重不变。',
                                                                      'changes': [('from datetime import '
                                                                                   'date, datetime',
                                                                                   'from datetime import '
                                                                                   'date, datetime, time as '
                                                                                   '_ge2e_evidence_time'),
                                                                                  ('def to_jsonable(value):\n'
                                                                                   '    if isinstance(value, '
                                                                                   '(date, datetime)):',
                                                                                   'def to_jsonable(value):\n'
                                                                                   '    if isinstance(value, '
                                                                                   '(date, datetime, '
                                                                                   '_ge2e_evidence_time)):')],
                                                                      'current_source_sha256': '0dcea3cc4cc7d9dcdbd66e6824a3732ee7b5c98475cadecf2a26a175c4897cd4'},
 'e7500c47aec4d700e217546cb9efcbc25b06fa360586eaa79b0b191d68826dd5': {'task_id': '02_Office_task_003_news_event_multifile_extract',
                                                                      'profile': 'news-equivalent-headings-and-explicit-rollup-scope/v1',
                                                                      'reason': '仅识别公开等价中文表头，并从显式统计维度中选择全期类别行；日分项与合计保留完整原始单元格，未知类别和重复全期类别继续接受原规则判定，不改分母算法或权重。',
                                                                      'changes': [],
                                                                      'append_source': 'news_event_layout.py',
                                                                      'append_source_sha256': '727d4f832066442a84cd2f1f914d372e5cdc97a374079b4a6f5af448fc85e36d',
                                                                      'current_source_sha256': 'f93566fe176758953c40c63f1747a8248a864948588f7a02393f59e1b51f3702'}})

_PROFILES['13c5130e0292799e066d59c2076f3ed2a050650c61572fa3cec3266d97dca69a'] = {'task_id': '03_Data_Analysis_task_001_hr_worktime_reconciliation',
 'profile': 'hr-native-time-evidence-serialization/v2',
 'reason': 'Excel原生时间按原ISO策略同时序列化取证文件和规则返回诊断；原字段、数值计算、比较、分母和权重不变，不将时间改为零。',
 'changes': [('from datetime import date, datetime',
              'from datetime import date, datetime, time as _ge2e_evidence_time'),
             ('def to_jsonable(value):\n    if isinstance(value, (date, datetime)):',
              'def to_jsonable(value):\n    if isinstance(value, (date, datetime, _ge2e_evidence_time)):'),
             ('    scores["诊断"] = diagnostics\n    return scores',
              '    scores["诊断"] = diagnostics\n'
              '    return json.loads(json.dumps(scores, ensure_ascii=False, allow_nan=False, '
              'default=to_jsonable))')],
 'current_source_sha256': '0498e2fa704f07165ca736b9426286cdfea0fdf6db7327b67610965d8db45fd5'}

_PROFILES['a16b0e1b172dd17536f754d1f5c506a3220facfec584a0d6efc16ed85006c22d'] = {'task_id': '03_Data_Analysis_task_010_contract_escrow_refund_reconciliation',
 'profile': 'escrow-equivalent-row-prefix-locators/v1',
 'reason': '仅将明确文件/工作表后的第N行语法投影为原行N；原文件、工作表、正行号和存在性/相关性检查全部保持，不改来源内容或评分数值。',
 'changes': [("        part=str(part).strip().replace('！','!')",
              "        part=str(part).strip().replace('！','!')\n"
              "        part=re.sub(r'(?<=[|!])第([1-9]\\d*)行$',r'行\\1',part)")],
 'current_source_sha256': '47656f9572199c91454cd69bf31a8dc2506e621be645c4eea654c3a585b2a40e'}

@lru_cache(maxsize=1)
def _history():
    raw=Path(__file__).with_name('source_repair_history.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='ff75b1581a0960dea29dc7f4ae32d25d00124446eb3b1d60c55f2736fa9ac67e':
        raise ValueError('RULE_SOURCE_REPAIR_HISTORY_DRIFT')
    return json.loads(raw)


def profile_entry(digest, profile=None):
    current=_PROFILES.get(digest)
    if profile is None or current is not None and profile==current['profile']:return current
    historical=_history().get(digest,{}).get(profile)
    if historical is None:raise ValueError('RULE_SOURCE_REPAIR_PROFILE_UNKNOWN')
    return historical


def effective_source(task_id, original, effective=None, prior=None, *, profile=None):
    digest=hashlib.sha256(original.encode('utf-8')).hexdigest()
    entry=profile_entry(digest,profile)
    source=original if effective is None else effective
    if entry is None or task_id not in {None,entry['task_id']}:return source,prior
    for old,new in entry['changes']:
        if source.count(old)!=1:raise ValueError('RULE_SOURCE_REPAIR_MARKER_MISMATCH')
        source=source.replace(old,new,1)
    if entry.get('append_source') or entry.get('append_text'):
        extra=(entry['append_text'].encode('utf-8') if entry.get('append_text') is not None else
               Path(__file__).with_name(entry['append_source']).read_bytes())
        if hashlib.sha256(extra).hexdigest()!=entry['append_source_sha256']:
            raise ValueError('RULE_SOURCE_REPAIR_APPEND_DRIFT')
        source+='\n'+extra.decode('utf-8').rstrip()
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1',
      'correction_id':entry['profile'],'task_id':entry['task_id'],
      'original_source_sha256':digest,'effective_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
      'reason':entry['reason'],'candidate_rewritten':False,'rubric_and_weights_changed':False}
    if prior is not None:receipt['prior_correction']=prior
    return source,receipt


_PROFILES['0df6363a8bb5cc0f1f27fc30e6c62f02a84212e67cc43351eee5767ec6dc87c7'] = {'task_id': '02_Office_task_026_work_order_labor_reconciliation',
 'profile': 'work-order-lazy-iferror-reader/v1',
 'reason': '对受支持表达式惰性求值IFERROR，区分原生Excel错误、空单元格和合法0；记录已缓存错误以保持后续引用正确。未知函数、外部引用、循环及评测异常不被fallback掩盖；原字段、数字算法、分母和权重不变。',
 'changes': [('class Reader:',
              'class _LocalExcelValueError(ArithmeticError):\n'
              '    """An Excel value error in a supported local expression."""\n'
              '    pass\n'
              '\n'
              'class Reader:'),
             ('        self.cache={};self.stack=set()',
              '        self.cache={};self.stack=set()\n'
              '        self._formula_errors=set();self._iferror_depth=0'),
             ('        if key in self.cache:return self.cache[key]',
              '        if key in self.cache:\n'
              '            if key in self._formula_errors and self._iferror_depth:raise '
              '_LocalExcelValueError()\n'
              '            return self.cache[key]'),
             ("        if c.data_type=='e':return None",
              "        if c.data_type=='e':\n"
              '            self._formula_errors.add(key)\n'
              '            if self._iferror_depth:raise _LocalExcelValueError()\n'
              '            return None'),
             ('        except ZeroDivisionError:v=None',
              '        except (ZeroDivisionError,_LocalExcelValueError):\n'
              '            self._formula_errors.add(key)\n'
              '            if self._iferror_depth:raise _LocalExcelValueError()\n'
              '            v=None'),
             ('            if isinstance(n,ast.Constant):return n.value',
              '            if isinstance(n,ast.Constant):\n'
              '                if n.value is None:raise _LocalExcelValueError()\n'
              '                return n.value'),
             ("                if fun=='IF':return ev(n.args[1] if ev(n.args[0]) else n.args[2])",
              "                if fun=='IF':return ev(n.args[1] if ev(n.args[0]) else n.args[2])\n"
              "                if fun=='IFERROR':\n"
              "                    if len(n.args)!=2:raise EvaluationError('IFERROR requires two "
              "arguments')\n"
              '                    previous_depth=self._iferror_depth;self._iferror_depth+=1\n'
              '                    try:\n'
              '                        try:return ev(n.args[0])\n'
              '                        except '
              '(_LocalExcelValueError,ZeroDivisionError,TypeError,OverflowError):return ev(n.args[1])\n'
              '                    finally:self._iferror_depth=previous_depth')],
 'current_source_sha256': 'e70fa8f963704f5f48d4957abb8986d0ecc6145d0fc8142e252dc7896dcad8de'}
