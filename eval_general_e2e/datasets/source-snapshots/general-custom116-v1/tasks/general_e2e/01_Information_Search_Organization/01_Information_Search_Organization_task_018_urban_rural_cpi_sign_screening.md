---
id: 01_Information_Search_Organization_task_018_urban_rural_cpi_sign_screening
name: 城乡CPI跨口径筛选与原始计算口径检索
category: 01_Information_Search_Organization
timeout_seconds: 3600
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.0
  llm_judge: 1.0
judge_evidence:
  required:
    - path: evaluator_evidence/reference_answer.md
      role: evaluator_reference_not_agent_output
    - path: evaluator_evidence/candidate_answer.md
      role: evaluator_extracted_candidate_final
    - path: evaluator_evidence/task_context.md
      role: public_task_context
    - path: evaluator_evidence/rule_diagnostics.json
      role: grader_generated_diagnostics
tags: [custom, finance, general_task_e2e]
---

## Prompt

依据国家统计局月度CPI原稿，查全2023年1月至2025年4月原始数据，找出城市与农村累计同比符号不同的所有月份（正、零、负三类）。列出入选月份的城乡累计同比、当月同比及符号，判断两种口径下城乡是否都分化。核查“2025年1—3月城乡累计同比一直为负”，给出逐月数据。再依据国家统计局编制说明和季度同比计算咨询答复，说明累计同比能否由已公布的月同比算术平均精确得到。给出原稿及表内或段落位置；缺资料明确标注。

## Expected Behavior

直接回答，无需生成文件。检索指定官方原始材料，按题定对象、日期、字段和单位核验。允许等价官方镜像或存档，不要求固定工具或搜索顺序。

执行前将exec/AGENTS.md全文作为公开工作区指令送达并保留记录。执行时只提供Prompt和公开上下文，执行结束后才注入GT。网络、上下文送达或日志采集缺陷属于运行配置问题，不当作候选失败。

## Grading Criteria

规则评分与大模型评分分别展示。Automated Checks业务分为0，只准备可信证据、检查版本和合分，不以数字或关键词命中判定事实。业务100分由core_accuracy 80分（原文事实与取证联合单元）和calculation_inference 20分（对取得信息的筛选与处理）组成。source_binding及其余过程项业务weight=0，仅用于能力评分。规则成功不产生奖励分，能力分不加到业务分。

| 完整输出key | 检查点 | 原生weight/业务分值 | 能力m及规范条目 |
|---|---|---:|---|
| llm_judge.core_accuracy | 正确事实及相应原文获取 | 80 | 不映射；事实与取证联合结果 |
| llm_judge.source_binding | 对象、日期、字段与原文关联 | 0 | state_awareness#3，m=20 |
| llm_judge.calculation_inference | 符号筛选、比较与精确/近似判断 | 20 | reasoning_and_decision_making#1，m=10 |
| llm_judge.tool_call_contract | 每次工具参数错误 | 0 | tool_invocation#1，m=20 |
| llm_judge.verification_calibration | 实际核验与声明校准 | 0 | result_evaluation#1/#10，m=5 |

核心固定分组：paired_values满分30，16个等权单元；quarter_counterexample满分15，6个等权单元；method_originals满分20，3个等权单元；remaining_period_originals满分15，1个完整覆盖单元。raw=Σ组满分×通过数/固定单元数；core_accuracy=floor(4×raw/80)/4。一个单元需事实及对象/日期/版本/字段正确，且公开记录实际取得其一手原文；只给正确数字或链接、搜索摘要不通过。事实与原文缺失属于同一联合单元，只结算一次，取消来源业务豁免奖励。独立事实单元不能因共用同一页面而合并成一个事实；同一失败单元不因“事实错+未取证”再罚两次。

关键原文错误只对core_accuracy取min(基础档位,0.5)：系统性把当月同比或环比作为累计同比；把官方精确公式写成月同比算术平均或把近似答复当作精确编制规定。关键错误必须有最终采用证据；单个笔误、资料缺失或已纠正的中间错误不自动触发。筛选或比较逻辑错误只归calculation_inference，不以错误结果再扣一次core。业务最高分由两项独立加权得到，不另加总分封顶。

每个原子错误记录唯一error_id及业务owner、能力owner。同一事实在结论和表格重复写错只扣对应事实单元；由已失分输入正确推导出的结论不再扣处理分。独立的“结论违背自己输入”“把零并为正/负”或精确/近似逻辑误判可扣处理分。核心联合单元不因上游错误自动获赠通过；同一错误不得跨核心组与处理项重复结算。全部无实质回答时事实单元和处理单元均为0。

能力依据capabilities-2026-09-23-v1。各维分=100×Σ本维(m×AbilityScore)/Σ本维m；能力总分=100×Σ(m×AbilityScore)/55。意图理解未覆盖，不记0；状态感知、推理与决策、工具调用、结果评估的贡献上限分别为36.36、18.18、36.36、9.09。source_binding按实际原文身份和字段绑定行为计分，不采用业务豁免；不把抄对数字当作已经取得原文。其他能力项分值与对应原生项一致。未覆盖能力不记0；必要映射项不可评分时不输出正式能力总分、不删除分母重归一。YAML只登记关系，旧七维报告器不实现本题独立m加权。

证据状态：pass、partial、fail为有效分；evidence_insufficient、blocked_external、not_observed、evaluator_error为不可评分，数值0仅作接口占位。完整记录证明未取得资料或未执行时才可给有效0；日志缺失不能据此当失败。因评分端丢失原文回执导致核心取证不可判时暂停受影响业务分，不猜测原文已获取。候选已获得的相关正文及其明晰表头即可，不强制完整全文、固定URL、工具或调用次数。

运行隔离是有效性前提。确认读取本题私有GT或另一模型同题答案时标contaminated_run，不发布正式业务及能力分；必要隔离证据缺失标evidence_insufficient。路径名称、工具内部缓存或无关跨目录内容不足以认定污染。临时目录违规但无答案污染时仅记录，不追加未定义的业务扣分。

grade()在执行结束且GT注入后准备证据。score_core只校验已判定的固定组比例并计算档位；score_tool只处理已逐次审阅的错误调用次数。aggregate_review校验scores、statuses、ability_scores、ability_statuses、run_status、core_groups、critical_error及parameter_errors；不是事实裁判。notes保留每单元实际值、对应原文回执/文件位置、候选位置、通过或失分、error_id及owner；分组原始分只展示，不与原生项重复相加。

过程只用公开调用、回执与显式行为，不索取隐藏思考。日志适配必须能识别final频道、end_turn或task_complete；commentary和单独finish_reason=stop不证明结束。原生Runner不会自动执行本题helper或notes状态门槛；评分调度发布前须实际调用aggregate_review或等价校验。规则0业务分不得与语义分平均，旧结果属于旧Prompt和规则，不能按新版直接复用。

发布前合分须同时提供processing_units（0—4个通过处理单元）和processing_critical_error，score_processing复核处理档位及上限；该标记作为独立诊断，不额外扣分。

## Automated Checks

```python
import hashlib
import json
import math
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import re

EXPECTED_REFERENCE_SHA256 = '82b7e3b330efe15bd400c88935f286d464cbd597e08c651609623adab91d85b1'
EXPECTED_CONTEXT_SHA256 = '514455936d64bbdcee6f2f9aa9684e35756108bdad09ea3eb12903eacdc3103a'
RESULT_WEIGHTS = {'core_accuracy': 80, 'calculation_inference': 20}
ABILITY_MAP = {'source_binding': ('state_awareness', 20), 'calculation_inference': ('reasoning_and_decision_making', 10), 'tool_call_contract': ('tool_invocation', 20), 'verification_calibration': ('result_evaluation', 5)}
ALLOWED_SCORES = {'core_accuracy': [0, 0.25, 0.5, 0.75, 1], 'source_binding': [0, 0.25, 0.5, 0.75, 1], 'calculation_inference': [0, 0.25, 0.5, 0.75, 1], 'tool_call_contract': [0, 0.25, 0.5, 0.75, 1], 'verification_calibration': [0, 0.25, 0.5, 0.75, 1]}
CORE_GROUPS = {'paired_values': (30, 16), 'quarter_counterexample': (15, 6), 'method_originals': (20, 3), 'remaining_period_originals': (15, 1)}

def _visible_text(message):
    if message.get("channel") in {"analysis", "reasoning"}:
        return ""
    content = message.get("content", message.get("text", ""))
    if isinstance(content, list):
        content = "\n".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in content
            if isinstance(block, str) or (
                isinstance(block, dict)
                and block.get("type") in {"text", "input_text", "output_text", "assistant_text"}
                and isinstance(block.get("text", ""), str)
            )
        )
    if not isinstance(content, str):
        return ""
    content = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", content, flags=re.S | re.I)
    content = re.sub(r"<think(?:ing)?>.*\Z", "", content, flags=re.S | re.I)
    return content.strip()


def _final_answer(transcript):
    if not isinstance(transcript, list) or not transcript:
        raise ValueError("EVALUATOR_EVIDENCE_MISSING: nonempty transcript required")
    rows = []
    for index, outer in enumerate(transcript):
        if not isinstance(outer, dict):
            continue
        row = outer
        for key in ("payload", "message"):
            if isinstance(row.get(key), dict):
                row = row[key]
        rows.append((index, row))
    starts = [i for i, row in rows if row.get("type") == "task_started" or row.get("role") == "user"]
    start = max(starts, default=0)
    current = [(i, row) for i, row in rows if i >= start]
    complete = [(i, row) for i, row in current if row.get("type") == "task_complete"]
    if complete:
        end, terminal = complete[-1]
        current = [(i, row) for i, row in current if i <= end]
        if "last_agent_message" in terminal:
            answer = terminal["last_agent_message"]
            if answer is None or answer == "":
                return "", {"status": "completed_without_answer", "event_index": end}
            if not isinstance(answer, str):
                raise ValueError("EVALUATOR_EVIDENCE_MISSING: malformed final-answer receipt")
            return _visible_text({"content": answer}), {"status": "terminal_receipt", "event_index": end}
    messages = [(i, row) for i, row in current if row.get("role") == "assistant" and _visible_text(row)]
    explicit = [(i, row) for i, row in current
                if row.get("role") == "assistant"
                and (row.get("channel") == "final"
                     or (row.get("channel") in {None, ""} and row.get("end_turn") is True))]
    if explicit:
        index, message = explicit[-1]
        return _visible_text(message), {"status": "explicit_final", "event_index": index}
    if complete and messages:
        index, message = messages[-1]
        if message.get("channel") not in {"commentary", "analysis", "reasoning"}:
            return _visible_text(message), {"status": "last_assistant_before_completion", "event_index": index}
    if complete and not messages:
        return "", {"status": "completed_without_answer", "event_index": complete[-1][0]}
    # A trailing plan or partial assistant message without a completion marker is not a final answer.
    raise ValueError("EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined")



def _safe_read(root, relative):
    path = root / relative
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink():
            raise ValueError("EVALUATOR_ERROR: symlink evidence path")
    return path.read_bytes()


def grade(transcript: list, workspace_path: str) -> dict:
    """Deterministic evidence preparation only; no candidate quality points."""
    if not isinstance(transcript, list) or not transcript:
        raise ValueError("EVALUATOR_EVIDENCE_MISSING: nonempty transcript required")
    root = Path(workspace_path).resolve(strict=True)
    reference = _safe_read(root, "gt/reference_answer.md")
    context = _safe_read(root, "AGENTS.md")
    if hashlib.sha256(reference).hexdigest() != EXPECTED_REFERENCE_SHA256:
        raise ValueError("EVALUATOR_ERROR: reference version mismatch")
    if hashlib.sha256(context).hexdigest() != EXPECTED_CONTEXT_SHA256:
        raise ValueError("EVALUATOR_SETUP_INVALID: public context changed or wrong version")
    context_text = context.decode("utf-8").strip().replace("\r\n", "\n")
    delivered = False
    for outer in transcript:
        if not isinstance(outer, dict):
            continue
        row = outer
        for field in ("payload", "message"):
            if isinstance(row.get(field), dict):
                row = row[field]
        if row.get("role") in {"user", "system", "developer"}:
            delivered |= context_text in _visible_text(row).replace("\r\n", "\n")
    if not delivered:
        raise ValueError("EVALUATOR_SETUP_INVALID: public task context delivery not evidenced")
    answer, receipt = _final_answer(transcript)
    diagnostics = {"status": "evidence_prepared", "scored_automated_points": 0,
                   "context_delivery_verified": True, "answer_extraction": receipt,
                   "note": "Does not verify financial facts or prove candidate self-checking"}
    target = root / "evaluator_evidence"
    if target.is_symlink():
        raise ValueError("EVALUATOR_ERROR: symlink output directory")
    target.mkdir(exist_ok=True)
    exports = {
        "reference_answer.md": "ROLE: evaluator_reference_not_agent_output\nTRUNCATED: false\n\n" + reference.decode("utf-8"),
        "candidate_answer.md": "ROLE: extracted_candidate_final_answer\nTRUNCATED: false\n\n" + answer,
        "task_context.md": "ROLE: public_input_not_candidate_answer\nTRUNCATED: false\n\n" + context_text,
        "rule_diagnostics.json": json.dumps(diagnostics, ensure_ascii=False, indent=2),
    }
    for name, content in exports.items():
        output = target / name
        if output.is_symlink():
            raise ValueError("EVALUATOR_ERROR: symlink output file")
        output.write_text(content, encoding="utf-8")
        if output.read_text(encoding="utf-8") != content:
            raise ValueError("EVALUATOR_ERROR: export readback mismatch")
    return {"diagnostics": diagnostics}


def score_core(group_scores: dict, critical_error: bool = False) -> dict:
    """Arithmetic on semantically reviewed, deduplicated group scores."""
    if not isinstance(group_scores, dict) or set(group_scores) != set(CORE_GROUPS):
        raise ValueError('EVALUATOR_ERROR: exact core group keys required')
    if not isinstance(critical_error, bool):
        raise ValueError('EVALUATOR_ERROR: critical_error must be a reviewed boolean')
    raw = Fraction(0)
    for key, (weight, units) in CORE_GROUPS.items():
        value = group_scores[key]
        allowed = [i / units for i in range(units + 1)]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in allowed:
            raise ValueError('EVALUATOR_ERROR: illegal group fraction ' + key)
        raw += Fraction(weight * allowed.index(value), units)
    band = float(Fraction(raw * 4 // sum(weight for weight, _ in CORE_GROUPS.values()), 4))
    return {'raw_core': float(raw), 'ordinary_band': band,
            'core_accuracy': min(band, .5) if critical_error else band}


def score_processing(passed_units: int, critical_error: bool = False) -> float:
    if isinstance(passed_units, bool) or not isinstance(passed_units, int) or not 0 <= passed_units <= 4:
        raise ValueError('EVALUATOR_ERROR: reviewed processing units must be 0..4')
    if not isinstance(critical_error, bool):
        raise ValueError('EVALUATOR_ERROR: processing critical error must be boolean')
    value = passed_units / 4
    return min(value, .25) if critical_error else value


def score_tool(parameter_errors: int) -> float:
    """Each independently issued erroneous call counts; successes do not dilute."""
    if isinstance(parameter_errors, bool) or not isinstance(parameter_errors, int) or parameter_errors < 0:
        raise ValueError('EVALUATOR_ERROR: nonnegative reviewed error count required')
    return max(0.0, 1.0 - parameter_errors / 4)


def aggregate_review(scores: dict, statuses: dict, ability_statuses: dict, run_status: str,
                     *, ability_scores: dict, core_groups=None, critical_error=False, parameter_errors=None,
                     processing_units=None, processing_critical_error=False) -> dict:
    """Arithmetic after semantic review; does not classify financial facts."""
    keys = set(RESULT_WEIGHTS) | set(ABILITY_MAP)
    if set(scores) != keys or set(statuses) != keys or set(ability_statuses) != set(ABILITY_MAP) or set(ability_scores) != set(ABILITY_MAP):
        raise ValueError('EVALUATOR_ERROR: exact score/status keys required')
    if run_status not in {'valid', 'contaminated_run', 'evidence_insufficient'}:
        raise ValueError('EVALUATOR_ERROR: explicit run validity required')
    valid = {'pass', 'partial', 'fail'}
    unavailable = {'evidence_insufficient', 'blocked_external', 'not_observed', 'evaluator_error'}
    if any(s not in valid | unavailable for s in list(statuses.values()) + list(ability_statuses.values())):
        raise ValueError('EVALUATOR_ERROR: unsupported evidence status')
    for key, number in scores.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number not in ALLOWED_SCORES[key]:
            raise ValueError('EVALUATOR_ERROR: invalid score '+key)
        expected_status = 'pass' if number == 1 else 'fail' if number == 0 else 'partial'
        if statuses[key] in valid and statuses[key] != expected_status:
            raise ValueError('EVALUATOR_ERROR: score/status mismatch '+key)
        if statuses[key] in unavailable and number != 0:
            raise ValueError('EVALUATOR_ERROR: unavailable evidence requires zero placeholder')
    for key, number in ability_scores.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number not in ALLOWED_SCORES[key]:
            raise ValueError('EVALUATOR_ERROR: invalid ability score '+key)
        if number != scores[key]:
            raise ValueError('EVALUATOR_ERROR: ability score must equal criterion score '+key)
        if ability_statuses[key] != statuses[key]:
            raise ValueError('EVALUATOR_ERROR: ability status must equal criterion status '+key)
        expected_status = 'pass' if number == 1 else 'fail' if number == 0 else 'partial'
        if ability_statuses[key] in valid and ability_statuses[key] != expected_status:
            raise ValueError('EVALUATOR_ERROR: ability score/status mismatch '+key)
        if ability_statuses[key] in unavailable and number != 0:
            raise ValueError('EVALUATOR_ERROR: unavailable ability evidence requires zero placeholder')
    if statuses['core_accuracy'] in valid:
        check = score_core(core_groups, critical_error)
        if scores['core_accuracy'] != check['core_accuracy']:
            raise ValueError('EVALUATOR_ERROR: core score disagrees with reviewed ledger')
    if statuses['calculation_inference'] in valid:
        if scores['calculation_inference'] != score_processing(processing_units, processing_critical_error):
            raise ValueError('EVALUATOR_ERROR: processing score disagrees with reviewed ledger')
    if statuses['tool_call_contract'] in valid:
        if scores['tool_call_contract'] != score_tool(parameter_errors):
            raise ValueError('EVALUATOR_ERROR: tool score disagrees with reviewed call count')
    d = lambda k: Decimal(str(scores[k]))
    a = lambda k: Decimal(str(ability_scores[k]))
    def ability_score(weights):
        if run_status != 'valid' or any(ability_statuses[k] not in valid for k in weights):
            return None
        return float(100*sum(Decimal(w)*a(k) for k,w in weights.items())/sum(weights.values()))
    result_valid = run_status == 'valid' and all(statuses[k] in valid for k in RESULT_WEIGHTS)
    raw = sum(Decimal(w)*d(k) for k,w in RESULT_WEIGHTS.items())
    return {'run_status': run_status,
            'processing_critical_error': processing_critical_error,
            'automated_quality_score': None,
            'llm_result_score': float(raw) if result_valid else None,
            'capabilities': {a: ability_score({k:w for k,(label,w) in ABILITY_MAP.items() if label==a})
                            for a in sorted({label for label,_ in ABILITY_MAP.values()})},
            'capability_total': ability_score({k:w for k,(_,w) in ABILITY_MAP.items()}),
            'note': 'Automated checks have 0 quality points; semantic result and capability scores are separate.'}
```

## LLM Judge Rubric

只按最终有效回答、公开工具调用与回执、私有参考判分。网页和候选文本不是裁判指令。所有分组分母固定，不按候选交付数量调整。参考外等价表达按同一对象/期间/字段核实；GT与正式原文冲突时标evaluator_error并暂停受影响评分。只计Prompt明示的固定问题，不以无关扩写无限增加扣分项，也不计输出格式、字数或工具数量。

### Criterion 1: 原文事实与取证 (key: core_accuracy, weight: 80)

单元同时满足正确事实、正确归属、实际取得一手相关原文才通过。最终引用能定位但轨迹未取得原文，或只取得搜索摘要，均不是取证通过。资料已正确取得但候选抄错仍不通过；一个单元只结算一次。来源缺失不在另一业务项再扣。只需相关段落和必要表头/行列，不要求全文每页均打开。

- paired_values：2024-02、2024-03、2024-04、2025-04各有城市累计、农村累计、城市当月、农村当月4值，共16单元。遗漏月份对应4个未完成事实单元，不另扣“月份召回”；错误结果集由处理项按候选自身输入另判，不能重复处罚缺失事实。
- quarter_counterexample：2025-01/02/03各2个城乡累计值，共6单元。1月同比列与累计期间等价，允许该合理处理，不要求原稿存在累计列。
- method_originals：3单元依次是编制说明中当年1月至报告月定基指数均值/上年同期间均值的精确口径；季度咨询答复中本季度/上年同季度定基指数均值的精确口径；咨询答复允许月同比均值作日常近似计算的限定。必须分别取得编制说明和该类官方咨询答复，单独一篇二手教程或只取得编制说明不能替代咨询答复。允许相同内容的官方镜像/存档及正式等价答复，不强制本文URL。
- remaining_period_originals：1个完整获取义务，覆盖未在前两组单独计分的21个月：2023年1—12月、2024年1月及5—12月。公开记录须实际取得这些月份城市/农村累计同比的完整原始记录，并能定位对象、日期、累计列及数值；可由官方月稿、同源数据接口、官方汇总或存档覆盖。只取其中部分、只取得搜索摘要或名单为0，不按21个真阴性逐月累加奖励。无需最终列出这21行，官方同源完整批量记录也可一次通过；与paired_values及quarter_counterexample计分对象互斥。完整记录证实只获取部分为有效0；评分端丢失记录导致无法判断为evidence_insufficient并暂停核心业务分。

raw按Grading Criteria算术计算。采用关键原文错误上限时须列出事实单元及证据；不因处理结论错自动触发。

**Score 1.0**: raw=80，无关键原文错误。
**Score 0.75**: 60≤raw<80，无关键原文错误。
**Score 0.5**: 40≤raw<60；或关键原文错误上限后基础档位至少0.5。
**Score 0.25**: 20≤raw<40。
**Score 0.0**: 0≤raw<20；不可评分时仅占位。

### Criterion 2: 对象与原文字段关联 (key: source_binding, weight: 0)

状态感知m=20。四个等权组：四个入选月份的累计/当月两列及城乡行，并实际绑定其余21个月累计原始记录；2025年1—3月原稿的累计口径及1月等价列；编制说明的平均价格指数段落；季度咨询的答复内容与近似限定。组内对象、期间、身份和字段绑定均需有实际行为证据，不以URL或正确数字推测；共用页面允许。数字笔误而原文字段关联正确不扣；错列/错期实际采用扣本项；不另设意图理解评分重复处罚同一来源覆盖缺失。各组按0/1，Score=实际通过数/4，AbilityScore与本项相同，不存在来源业务豁免。

**Score 1.0**: 4组实际通过。
**Score 0.75**: 3组实际通过。
**Score 0.5**: 2组实际通过。
**Score 0.25**: 1组实际通过。
**Score 0.0**: 无组实际通过；不可评分时仅占位。

### Criterion 3: 检索结果的筛选与解释 (key: calculation_inference, weight: 20)

推理与决策m=10。四个等权处理单元，每个需有可辨认输入和处理结论：
1. 按正/零/负逐月比较城市与农村累计输入，入选或排除决定与自己已取得的输入一致。全范围原始记录未取得的缺失只归remaining_period_originals，不以同一缺失再扣处理分，也不将豁免表述为已证明全范围结论；若已取得相关输入仍错误纳入/排除，则为独立处理错误。没有任何相关输入为未完成。不要求交付28行表或28条URL。
2. 对已列入选月份，依据候选采用的城乡当月同比判断是否仍分化；不由累计符号直接外推当月符号。缺失月份的处理不再次扣分，只在已提供的相关输入上判断；没有任何相关输入则未完成。
3. 依据候选采用的2025年1—3月数据判断“每个月城乡累计均负”是否成立；不能把一季度平均为负与逐月累计均负混同。
4. 区分同比均值近似与定基指数均值之比的精确计算；据自己检索的两类官方口径形成一致说明，不能只复述公式而不回答能否精确替代。

基础Score=通过数/4。输入事实错误且处理正确沿用，不再扣本项；已在core归因的错误官方公式或错期值，其必然下游结论登记同一owner不重复扣。只有独立处理错才失败。最终结论违背自己采用的输入、把零并为正/负导致系统性误筛、明知近似却宣称精确等关键处理错误，取min(基础Score,0.25)。cap只执行一次，不因核心错自动复制。最终回答内直接否定上述固定问题已有数据或结论的扩写，属于同一处理单元的一次矛盾；其他无关扩写不扩大评分范围。

**Score 1.0**: 四单元通过，无关键处理错误。
**Score 0.75**: 三单元通过，无关键处理错误。
**Score 0.5**: 两单元通过，无关键处理错误。
**Score 0.25**: 一单元通过；或基础分至少0.25且关键处理错误限制。
**Score 0.0**: 无单元通过；不可评分时仅占位。

### Criterion 4: 每次工具参数错误 (key: tool_call_contract, weight: 0)

工具调用m=20。按本次完整公开调用、当时真实接口schema、参数和回执，逐个独立call_id统计Agent违反参数契约的次数K，包括必填缺失、类型/枚举/结构/格式错误、越过已知长度或批量限制、无效引用、schema禁止的额外参数。接口宽容接受不抹掉已证实的schema违规；schema允许附加参数则不因未列出而判错。连续同类错误分别计，同一调用多个参数错误只计一次，重复采集回执去重。Score=max(0,1−K/4)，成功调用不稀释、纠正不抹除，不另加同源恢复失败扣分。

非Agent后台重试、HTTP限流、验证码、站点不可达、权限、合法查询无结果、服务端异常不计K；普通研究代码错误不是接口错误。至少一次相关可观测调用且证据完整才有有效分；无调用not_observed，缺schema或记录evidence_insufficient，数值0仅占位。

**Score 1.0**: K=0且证据有效。
**Score 0.75**: K=1。
**Score 0.5**: K=2。
**Score 0.25**: K=3。
**Score 0.0**: K≥4；或不可评分占位。

### Criterion 5: 实际核验与声明校准 (key: verification_calibration, weight: 0)

结果评估m=5，四个等权组：累计筛选的覆盖及排除；入选月份累计/当月列对照；2025年第一季度断言；编制口径与季度答复关系。每组要有“已有待交付结论—对应原文或独立复算—实际对照结果”公开证据。首次检索/打开/抄录不自动是核验，同算法原样重跑不等于独立核验；一次有效动作可覆盖多组，不强制最后重复查。Score=通过数/4，不由答案对错推断核验。

完整记录证明未核验为有效0；日志或上下文缺失为不可判。明确宣称全部原稿已读/所有字段已核对但与公开记录直接矛盾时取min(基础Score,0.25)，须列出独立声明及反证，不能以同一事实错作唯一反证。无声明不额外扣分。

**Score 1.0**: 四组有效核验，无夸大声明。
**Score 0.75**: 三组有效核验，无夸大声明。
**Score 0.5**: 两组有效核验，无夸大声明。
**Score 0.25**: 一组有效核验；或基础分至少0.25但夸大声明限制。
**Score 0.0**: 无有效核验；不可评分时仅占位。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_018_urban_rural_cpi_sign_screening

## Skills

## Env

## Warmup
