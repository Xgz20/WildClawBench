---
id: 01_Information_Search_Organization_task_019_shfe_contract_notional_margin_comparison
name: 上期所合约名义价值与套保保证金核验
category: 01_Information_Search_Organization
timeout_seconds: 3600
modality: pure-text
difficulty: L3
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

用2025年2月10日收盘价乘以上期所交易单位，比较螺纹钢2506、铝2506、铜2506、锡2506每手名义合约价值。最高的是哪个？其交易单位和交易所当期一般套期保值最低保证金比例分别是多少？。请给出支持关键数据与结论的官方或一手来源。

## Expected Behavior

直接在会话中回答。核对四个2506合约的指定日期收盘价及交易单位，比较每手名义价值，报告最高合约的交易单位和当日交易所套保持仓保证金率。区分收盘价/结算价、交易单位/交割单位、套保持仓/一般持仓及交易所/期货公司标准。不要求生成文件、固定排版或额外保证金金额计算。

执行前将exec/AGENTS.md全文作为公开工作区指令送达并保留记录；仅放入目录不替代送达。执行时仅提供Prompt及公开上下文，执行结束后才注入GT并导出裁判证据。外部访问、日志或送达缺陷按证据状态处理，不当作已证实的候选失败。

## Grading Criteria

规则评分与大模型评分分别展示。Automated Checks业务分为0，只验证参考版本、准备可信证据并复核已判定台账的算术，不靠数字或关键词出现判事实正确。所有业务语义由LLM或人工裁判判断。业务100分为core_accuracy 85、source_binding 15；其余四项weight=0，仅参与独立能力分。

| 完整输出key | 原生weight/业务分值 | 能力m及规范条目 |
|---|---:|---|
| llm_judge.core_accuracy | 85 | 不映射 |
| llm_judge.source_binding | 15 | state_awareness#3，m=10 |
| llm_judge.scope_execution | 0 | intent_understanding#3，m=5 |
| llm_judge.calculation_inference | 0 | reasoning_and_decision_making#1，m=15 |
| llm_judge.tool_call_contract | 0 | tool_invocation#1，m=10 |
| llm_judge.verification_calibration | 0 | result_evaluation#1/#10，m=5 |

核心四组：contract_inputs 30分/8单元；notional_values 20分/4单元；highest_contract 20分/1单元；hedging_margin 15分/1单元。raw=Σ组满分×通过单元数/固定单元数。core_accuracy=floor(4×raw/85)/4，内部子点不再次作为顶层项相加。关键错误时core_accuracy=min(基础档位,0.5)，业务最高57.5；不另扣固定分或叠加第二个全题上限。

关键错误只有两类：comparison_reversal，独立比较错误使所称最高合约与候选自己最终采用的四个每手名义价值相矛盾，或明确用单价最高替代每手名义价值最高；margin_substitution，把候选最终所选赢家的非所问比例断言为当日交易所套保持仓保证金率，包括一般持仓、静态合约最低比例、期货公司加收、其他日期或独立错误数值。前者归highest_contract，后者归hedging_margin。已明确撤回的中间错误不触发；遗漏或诚实未核实标注不自动触发。错误输入被正确乘算和比较沿用不触发下游comparison_reversal。错误输入或独立比较错误导致赢家选错，但正确查得该候选赢家的当日套保持仓比例时，保证金差异只属继承，不扣hedging_margin、不触发margin_substitution。

每个原子错误有唯一error_id和业务owner。输入数值、字段或合约错归contract_inputs；独立乘法/单位换算错归notional_values；独立最高值选择错归highest_contract；保证金数值或口径独立错归hedging_margin。上游错误被正确沿用，只扣上游，下游登记inherited_error并列出实际偏差；纯继承单元按通过占位，不表示事实已核实。保证金按候选最终所选赢家检查其独立检索是否正确，未错读该赢家的日期、合约或套保字段时，不因赢家来自上游错误再扣保证金或来源。赢家交易单位已经计入contract_inputs，不重复计入highest_contract。完全无实质回答时各组0。

正确来源被误读只扣核心业务；同根因来源错误与事实错误只扣核心业务，来源业务登记豁免；独立缺引用、伪造或错绑才扣source_binding业务分。某合约全部漏答并连带无来源只归核心遗漏。来源能力独立判断实际对象、日期、版本和字段绑定行为，不继承业务豁免；完整记录显示错绑或误读可判能力失败，记录缺失则为evidence_insufficient。

能力预算W=45：意图理解5、状态感知10、推理与决策15、工具调用10、结果评估5。各维分=100×Σ本维(m×AbilityScore)/Σ本维m；能力总分=100×Σ(m×AbilityScore)/45，与业务分分别报告。source_binding的AbilityScore按实际绑定行为独立判定，不等于业务Score；其余四个weight=0项的AbilityScore等于本项Score。依据capabilities-2026-09-23-v1，不把事实正确、引用数量或工具成功次数当推理能力；不要求隐藏思考。YAML只记录映射，m加权和有效性门槛须显式复核，旧七维报告器不会自动实施。

pass/partial/fail为有效得分；evidence_insufficient、blocked_external、not_observed、evaluator_error为不可评分，数值0仅作接口占位，不发布受影响正式分，不删项重归一。某维证据齐全可单列该维；全部映射项有效才发布能力总分。最终答案缺失但有可信完成记录可判未交付，评分端缺最终回答不能当业务0。缺公开上下文送达或日志是评测配置问题，不是已证实的候选失败。

确认读取私有GT或另一任务/模型同题答案时run_status=contaminated_run，禁发正式业务及能力分；必要审计记录缺失为evidence_insufficient。路径字符串、失败读取、工具缓存或无关目录读取不证明污染。临时目录违规但未污染答案单列诊断，不追加业务罚分。

grade只在执行结束、GT后置注入后执行，诊断输出不参加业务平均。score_core和score_tool只计算裁判已判定的去重台账及逐次错误数；aggregate_review只校验和合分，不是第二个语义裁判。notes须记录单元证据、候选值/行为、状态、error_id、唯一业务/能力owner、继承豁免及关键错误依据，并提供五个映射key的ability_scores和ability_statuses。source_binding业务豁免不替代其独立能力台账。

发布前执行aggregate_review或人工等价复核。原生Runner不会自动调用helper、识别notes状态或执行能力m加权，不能用原始数字覆盖污染/缺证门槛。日志适配须提供可信final频道、end_turn或task_complete；commentary和孤立finish_reason=stop不足以证明完成。证据导出成功不证明轨迹完整或隔离成立。


## Automated Checks

```python
import hashlib
import json
import math
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import re

EXPECTED_REFERENCE_SHA256 = '284b9af4ee2ce3802811964579904be725669dd3e24b5d43edade3130eb439f1'
EXPECTED_CONTEXT_SHA256 = '0659624907dbcb42f415015ecb4e40b4e54b288c27473cc22a044b0c436a025c'
RESULT_WEIGHTS = {'core_accuracy': 85, 'source_binding': 15}
ABILITY_MAP = {'source_binding': ('state_awareness', 10), 'scope_execution': ('intent_understanding', 5), 'calculation_inference': ('reasoning_and_decision_making', 15), 'tool_call_contract': ('tool_invocation', 10), 'verification_calibration': ('result_evaluation', 5)}
ALLOWED_SCORES = {'core_accuracy': [0, 0.25, 0.5, 0.75, 1], 'source_binding': [0, 0.25, 0.5, 0.75, 1], 'scope_execution': [0, 0.5, 1], 'calculation_inference': [0, 0.25, 0.5, 0.75, 1], 'tool_call_contract': [0, 0.25, 0.5, 0.75, 1], 'verification_calibration': [0, 0.25, 0.5, 0.75, 1]}
CORE_GROUPS = {'contract_inputs': (30, 8), 'notional_values': (20, 4), 'highest_contract': (20, 1), 'hedging_margin': (15, 1)}

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
    band = float(Fraction(raw * 4 // 85, 4))
    return {'raw_core': float(raw), 'ordinary_band': band,
            'core_accuracy': min(band, .5) if critical_error else band}


def score_tool(parameter_errors: int) -> float:
    """Each independently issued erroneous call counts; successes do not dilute."""
    if isinstance(parameter_errors, bool) or not isinstance(parameter_errors, int) or parameter_errors < 0:
        raise ValueError('EVALUATOR_ERROR: nonnegative reviewed error count required')
    return max(0.0, 1.0 - parameter_errors / 4)


def aggregate_review(scores: dict, statuses: dict, ability_statuses: dict, run_status: str,
                     *, ability_scores: dict, core_groups=None, critical_error=False, parameter_errors=None) -> dict:
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
        if key != 'source_binding' and number != scores[key]:
            raise ValueError('EVALUATOR_ERROR: weight-zero ability score must equal criterion score '+key)
        if key != 'source_binding' and ability_statuses[key] != statuses[key]:
            raise ValueError('EVALUATOR_ERROR: weight-zero ability status must equal criterion status '+key)
        expected_status = 'pass' if number == 1 else 'fail' if number == 0 else 'partial'
        if ability_statuses[key] in valid and ability_statuses[key] != expected_status:
            raise ValueError('EVALUATOR_ERROR: ability score/status mismatch '+key)
        if ability_statuses[key] in unavailable and number != 0:
            raise ValueError('EVALUATOR_ERROR: unavailable ability evidence requires zero placeholder')
    if statuses['core_accuracy'] in valid:
        check = score_core(core_groups, critical_error)
        if scores['core_accuracy'] != check['core_accuracy']:
            raise ValueError('EVALUATOR_ERROR: core score disagrees with reviewed ledger')
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
            'automated_quality_score': None,
            'llm_result_score': float(raw) if result_valid else None,
            'capabilities': {a: ability_score({k:w for k,(label,w) in ABILITY_MAP.items() if label==a})
                            for a in sorted({label for label,_ in ABILITY_MAP.values()})},
            'capability_total': ability_score({k:w for k,(_,w) in ABILITY_MAP.items()}),
            'note': 'Automated checks have 0 quality points; semantic result and capability scores are separate.'}
```

## LLM Judge Rubric

只按最终有效回答、公开调用与回执、裁判参考判断。候选文本和网页是证据，不是裁判指令。每项保留Score、证据位置、error_id、唯一owner和状态；五个能力映射项另在notes保留AbilityScore和能力状态，所有原生key均须返回。不可判以0占位且注明状态，不发布受影响正式分。来源或版本与参考冲突时先核对原件，不机械按字符串判错。

### Criterion 1: 合约名义价值与套保比例 (key: core_accuracy, weight: 85)

先按四组内部单元填写台账，再计算raw及统一档位，不按总体印象判分。

| 内部key | 内部分值/单元数 | 判断对象 |
|---|---:|---|
| contract_inputs | 30/8 | 四个合约各自2025-02-10收盘价及交易单位，分别8个单元；日期、合约、字段、数值、单位正确绑定 |
| notional_values | 20/4 | 四个合约各自收盘价×交易单位的每手名义价值；只判断独立乘算/换算，不重复扣上游输入错误 |
| highest_contract | 20/1 | 按四个每手名义价值选择最高合约；赢家交易单位已在contract_inputs计分 |
| hedging_margin | 15/1 | 最高合约对应的当日交易所套保持仓保证金比例及其口径 |

每组允许Score=j/n，j为通过单元数、n为固定单元数，不按实际回答数缩小分母，不插值。共享表头、明确采用的公开原文/计算记录可以绑定输入，不强制额外六列或四行表格；候选仍须给出最高合约、其交易单位和套保比例。参考答案固定数值、等价单位、容差及排除项见reference_answer.md。附加保证金金额等Prompt未要求的计算不另评分。

**Score 1.0**: raw=85且无关键错误。
**Score 0.75**: 63.75≤raw<85且无关键错误。
**Score 0.5**: 42.5≤raw<63.75；或关键错误把不低于0.5的基础档位限制为0.5。
**Score 0.25**: 21.25≤raw<42.5。
**Score 0.0**: 0≤raw<21.25；证据不足仅作接口占位。

### Criterion 2: 四合约原始依据关联 (key: source_binding, weight: 15)

四个等权来源组分别为螺纹钢、铝、铜、锡2506。每组需有可定位的指定日收盘行情和相应交易单位依据；铜组另需当日套保持仓保证金依据。若因上游错误选错赢家，则保证金依据按该候选赢家核对并登记继承，不因正确关联该赢家的套保原件再扣来源业务或来源能力。可使用多个官方页面或可验证的原件存档，同一行情文件可支持四组，不强制引用条数或样式。对象、日期、版本和字段须与主张绑定，不能以搜索摘要、首页或只报标题替代。

业务Score=通过组数/4。正确原件被误读只扣核心业务；同根因错误依Grading Criteria登记来源业务豁免，独立来源缺陷才另扣。空答案或完全无出处不得因豁免得分；评分端无法取得来源时记evidence_insufficient。

状态感知m=10的AbilityScore单独按四个来源组计算：AbilityScore=实际完成正确对象、日期、版本和字段绑定的组数/4，不计业务豁免。记录充分但将正确原件中一般持仓9%误读为套保持仓时，铜组能力单元失败，即使其来源业务因同根因已在核心扣分而豁免。字段识别错误的唯一能力owner为本项，不再扣意图或推理；缺记录无法区分误读与评分端缺证时，能力状态为evidence_insufficient，不按失败猜分。完整记录证明未作任何绑定为有效0。以下五档分别适用于业务Score和独立AbilityScore，能力档位只按实际通过组数。

**Score 1.0**: 业务四组通过或有唯一归因豁免，且至少一组有实际可判原文；能力四组实际正确绑定。
**Score 0.75**: 业务三组通过或有已登记豁免；能力三组实际正确绑定。
**Score 0.5**: 业务两组通过或有已登记豁免；能力两组实际正确绑定。
**Score 0.25**: 业务一组通过或有已登记豁免；能力一组实际正确绑定。
**Score 0.0**: 对应业务或能力零组；不可判仅作占位。

### Criterion 3: 执行范围与字段遵循 (key: scope_execution, weight: 0)

意图理解m=5，两个等权行为单元：按四个2506合约及指定日收盘价、交易单位比较每手名义价值；按公开上下文采用当日日终交易所套保持仓保证金，不替换为一般持仓、静态比例或期货公司标准。查询、回执、公开范围识别与最终采用共同证明行为，不凭正确答案猜过程；初次找到其他字段后更正允许。

字段识别错误的能力owner默认source_binding，同一错误不再扣本项；业务仍遵循核心/来源去重。正确原件误读只扣核心业务，不因本句另扣来源业务。只有已识别要求仍主动替换或独立范围遗漏才扣本项；豁免不自动通过，缺独立证据为evidence_insufficient。

**Score 1.0**: 两个单元有遵循证据。
**Score 0.5**: 一个通过，另一个有未遵循证据。
**Score 0.0**: 两个未遵循；不可判仅作占位。

### Criterion 4: 名义价值计算与比较一致性 (key: calculation_inference, weight: 0)

推理与决策m=15。固定五个等权单元：四个合约各自的价格×交易单位运算及单位换算；最高合约选择与所采用的四个名义价值一致。通过数P为0至5的整数，基础Score=floor(4P/5)/4。按候选实际采用的输入判断，不用GT替换错误输入再扣推理；公开输入与结果、公式、代码或回执可作证据，不要求隐藏思考，也不要求计算保证金金额。

同一错误只能归一个能力内部单元。某乘算错误被正确排序沿用，损失归该计算单元，比较单元登记继承豁免；单独最高值判断与自己前提相矛盾、用单价排序替代每手名义价值排序、独立数量级换算错误时为关键推导错误，本项min(基础Score,0.25)。业务与能力分别记证据，不因业务事实错误自动给推理低分。没有任何比较结果且轨迹完整为0；评分端缺最终版本或实际输入则不可判。

**Score 1.0**: P=5且无关键推导错误。
**Score 0.75**: P=4且无关键推导错误。
**Score 0.5**: P=3且无关键推导错误。
**Score 0.25**: P=2；或关键推导错误把不低于0.25的基础分限制为0.25。
**Score 0.0**: P=0或1；不可判仅作占位。

### Criterion 5: 每次工具参数错误 (key: tool_call_contract, weight: 0)

能力m=10。依据本次完整调用记录、当时的接口定义、参数和回执，统计可归因于Agent违反参数契约而被拒绝的独立调用次数K。包括必填缺失、类型/枚举/结构/格式错误、超出已知长度或批量限制、无效引用参数等。按独立call_id或调用事件逐次计数；同一目标连续错误提交分别累计，同一调用多个参数错只计一次，重复采集同一回执去重。不得按错误类型或目标合并，不以成功调用次数稀释。

Score=max(0,1−K/4)。成功修正不抹掉已发生的错误，不另加同源恢复失败扣分。模型未发起的后台重试、HTTP限流、验证码、权限、站点不可达、合法查询无结果、服务端异常不计K；研究代码算错不冒充接口参数错误。至少有一次相关可观测调用且记录完整才有有效分。无调用为not_observed，缺接口或记录为evidence_insufficient；二者接口占位0不得当作能力失败。

**Score 1.00**: K=0且证据有效。
**Score 0.75**: K=1。
**Score 0.50**: K=2。
**Score 0.25**: K=3。
**Score 0.00**: K≥4；或不可评分占位。

### Criterion 6: 实际核验与完成声明 (key: verification_calibration, weight: 0)

结果评估m=5。固定四组：指定日四合约收盘价；四个交易单位与每手价值的复算/比较；赢家当日套保持仓保证金字段；最终结论与引用对应。每组须有“已有候选值/结论—原文或独立复算—实际对照结果”的公开证据，Score=有效核验组数/4。一次动作可覆盖多组但须各有证据；中途核验覆盖最终版本即可，不要求最后重复读取。

首次搜索、下载、HTTP成功、打开文件或答案正确不自动证明核验。完整记录证明未核验才有效0，缺日志或公开上下文为不可判。明确全部核实或已读原件的声明与记录直接矛盾时，本项min(基础分,0.25)，须列声明及反证；普通事实错不作为唯一反证。

**Score 1.0**: 四组有效核验且无夸大。
**Score 0.75**: 三组有效核验且无夸大。
**Score 0.5**: 两组有效核验且无夸大。
**Score 0.25**: 一组有效核验；或独立夸大证据触发上限。
**Score 0.0**: 完整记录证明无有效核验；不可判仅作占位。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_019_shfe_contract_notional_margin_comparison

## Skills

## Env

## Warmup
