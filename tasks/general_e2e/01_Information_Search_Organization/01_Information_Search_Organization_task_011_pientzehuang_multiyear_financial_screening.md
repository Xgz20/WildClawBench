---
id: 01_Information_Search_Organization_task_011_pientzehuang_multiyear_financial_screening
name: 四家公司跨年度财务筛选与完整排除核验
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

根据截至2025年4月30日已公开的资料，核验片仔癀、恒瑞医药、云南白药、迈瑞医疗是否属于当日沪深300成分股、A股上市超过10年，且2020—2024年每年均满足：营业总收入和归母净利润同比增长为正、加权ROE>15%、自由现金流（经营现金流净额－购建长期资产支付现金）>0、年末资产负债率<20%。逐年列出数值、判定及官方或一手依据，汇总符合条件的公司和全部不达标项。

## Expected Behavior

读取已送达的公开AGENTS.md，自行检索四家公司历史指数身份、A股上市时间及20个公司年度的五项财务指标。识别各报告的当期列和可比上年列，核验100项财务条件；即使已发现某家公司不满足，也继续核验全部条件。以分组文字或表格给出数值、判定、全部不达标项和可定位来源，不要求生成文件或编程。

执行前将exec/AGENTS.md全文作为工作区指令或公开上下文送达Agent并保存送达记录；标准运行路径为/tmp_workspace/AGENTS.md。仅把文件放进目录不替代送达证据。执行时不提供GT；执行结束后才注入GT和导出裁判证据。联网/上下文送达/日志采集缺陷属于运行或评分配置问题，不能当作模型失败。

## Grading Criteria

业务100分：历史身份10、五项财务事实30、时点与版本5、计算与逻辑10、指标定义5、筛选结论10、全部不达标项10、来源15、覆盖5。18项业务检查直接采用原生weight，合计100；Score为各点0—1得分。另有工具参数契约、完成声明校准、最终集合推导3项，业务weight=0，仅参与能力分。不设全题严重错误封顶。最终筛选结论以完整入选集合作为一个业务单元，不用多数公司的正确排除抵消漏选或误选；其他项目保留各自原子单元。

规则与大模型评分分别展示：

- Automated Checks业务分为0。grade()核对参考/上下文版本、送达记录、最终回答边界及证据导出；输出状态和诊断，不把文件存在或数字命中称为财务事实正确。
- 大模型/人工按18项业务标准判语义、按2项过程标准判行为，另按最终集合推导标准判断回答中的前提与最终选择是否一致，共21项。每项附原子单元台账、来源/调用位置、扣分原因和证据状态。判分后aggregate_review只核合法档位与确定性合分；语义判断不会因使用该函数变成“规则判分”。
- 题目分R=Σ(weight×Score)，保留两位小数；原生框架归一化结果为R/100。三个业务weight=0的能力项不与业务100分相加。规则成功不折算为额外奖励分。

| key（输出统一加llm_judge.前缀） | 检查点 | 原生weight/业务分值 | 固定单元数 |
|---|---|---:|---:|
| facts_identity | 主体、历史身份与上市年限 | 10 | 12 |
| facts_revenue | 20个公司年度收入同比 | 6 | 20 |
| facts_profit | 20个公司年度归母净利润同比 | 6 | 20 |
| facts_roe | 20个公司年度加权ROE | 6 | 20 |
| facts_cashflow | 20个公司年度自由现金流 | 8 | 20 |
| facts_balance | 20个公司年度资产负债率 | 4 | 20 |
| scope_and_version | 历史时点与报告版本 | 5 | 8 |
| calc_growth | 40个同比分母与运算 | 2 | 40 |
| calc_fcf | 20个自由现金流运算 | 2 | 20 |
| calc_leverage | 20个负债率运算 | 2 | 20 |
| calc_thresholds | 100个严格阈值判定 | 2 | 100 |
| calc_all_years | 年度五项条件组合 | 2 | 20 |
| metric_definitions | 五项指标口径 | 5 | 5 |
| conclusion | 完整真实入选集合 | 10 | 1 |
| disqualifications | 全部不达标项与误报 | 10 | 26 |
| source_authority | 官方或一手依据 | 5 | 28 |
| source_binding | 公司、年度、指标与来源关联 | 10 | 108 |
| completeness | 完整回应所有公司和年度 | 5 | 112 |
| tool_call_contract | 每次工具参数错误 | 0 | 按独立调用计数 |
| completion_calibration | 完成声明与证据一致 | 0 | 4 |
| decision_consistency | 最终集合推导 | 0 | 1 |

能力映射沿用W=35，数值独立于业务weight：scope_and_version→intent_understanding#3，m=5；source_binding→state_awareness#3，m=5；calc_thresholds、calc_all_years、decision_consistency→reasoning_and_decision_making#1，m依次为2、2、6；tool_call_contract→tool_invocation#1，m=10；completion_calibration→result_evaluation#10，m=5。推理与决策内部预算固定为阈值20%、年度组合20%、最终集合推导60%，不随原子单元数量扩张。依据capabilities-2026-09-23-v1。只映射实际观察的具体能力；同比、FCF和负债率运算项混有无法核算的证据缺口，不将其业务低分直接等同于已证实的推理错误。工具维度仅覆盖参数契约。

错误归因沿推导层级分开：事实项检查真实数值；calc_thresholds按候选采用数值检查单项比较；calc_all_years按候选已列单项判定检查年度组合；decision_consistency按候选已列年度判定和身份/年限检查最终集合。下游正确沿用上游错误不重复扣下游逻辑分。conclusion按真实集合检查业务结果，不再映射能力；业务分与能力分分别报告，不相加。仅最终集合矛盾不再扣年度组合、完整覆盖或完成声明；完成声明必须另有不实完成/核验声明的独立证据。三个正确排除、最终表格出现正确词语或末尾重复正确结论，均不能抵消未撤回的相反最终结论。

各维分=100×Σ本维(m×Score)/Σ本维m；能力总分=100×Σ(m×Score)/35。五维贡献上限依次14.29/14.29/28.57/28.57/14.29。报告分别展示业务得分、规则诊断和五维能力。YAML登记映射关系；旧七维报告器不自动执行m加权，原生Runner也不会自动调用aggregate_review，评分调度须显式复核。

证据状态：pass/partial/fail为有效得分；evidence_insufficient、blocked_external、not_observed、evaluator_error为不可评分状态，0仅接口占位，不发布受影响正式分，不删项重归一。完整记录确认未履行公开义务可判0；评分端缺记录不可如此判定。ability_statuses单独记录行为证据有效性，业务可由回答判定时不得推断过程日志也齐全。

运行隔离是有效性前提：确认读取本题私有GT或另一模型同题答案时run_status=contaminated_run，正式题目分及能力分不发布；必要隔离记录缺失为evidence_insufficient。仅路径名称、无关跨目录读取、工具内部缓存不足以认定污染。临时目录/隔离义务已公开；违反目录但没有答案污染，记录违规，不凭空追加业务扣分或把参数合法性扣分替代隔离判定。

## Automated Checks

```python
import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re

EXPECTED_REFERENCE_SHA256 = '6ec0ee5def1c9e2f23b02b675ed6fdc8f8e8260d099f0a9ce0cca4fa1607db9f'
EXPECTED_CONTEXT_SHA256 = '5003471585296c307d4f87de8e924764d2500a66cd7e9d0c820c11eaadd5ef41'
RESULT_WEIGHTS = {'facts_identity': 10, 'facts_revenue': 6, 'facts_profit': 6, 'facts_roe': 6, 'facts_cashflow': 8, 'facts_balance': 4, 'scope_and_version': 5, 'calc_growth': 2, 'calc_fcf': 2, 'calc_leverage': 2, 'calc_thresholds': 2, 'calc_all_years': 2, 'metric_definitions': 5, 'conclusion': 10, 'disqualifications': 10, 'source_authority': 5, 'source_binding': 10, 'completeness': 5}
ABILITY_MAP = {'scope_and_version': ('intent_understanding', 5), 'source_binding': ('state_awareness', 5), 'calc_thresholds': ('reasoning_and_decision_making', 2), 'calc_all_years': ('reasoning_and_decision_making', 2), 'tool_call_contract': ('tool_invocation', 10), 'completion_calibration': ('result_evaluation', 5), 'decision_consistency': ('reasoning_and_decision_making', 6)}
ALLOWED_SCORES = {'facts_identity': [0.0, 0.08, 0.17, 0.25, 0.33, 0.42, 0.5, 0.58, 0.67, 0.75, 0.83, 0.92, 1.0], 'facts_revenue': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'facts_profit': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'facts_roe': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'facts_cashflow': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'facts_balance': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'scope_and_version': [0.0, 0.13, 0.25, 0.38, 0.5, 0.63, 0.75, 0.88, 1.0], 'calc_growth': [0.0, 0.03, 0.05, 0.08, 0.1, 0.13, 0.15, 0.18, 0.2, 0.23, 0.25, 0.28, 0.3, 0.33, 0.35, 0.38, 0.4, 0.43, 0.45, 0.48, 0.5, 0.53, 0.55, 0.58, 0.6, 0.63, 0.65, 0.68, 0.7, 0.73, 0.75, 0.78, 0.8, 0.83, 0.85, 0.88, 0.9, 0.93, 0.95, 0.98, 1.0], 'calc_fcf': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'calc_leverage': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'calc_thresholds': [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.2, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28, 0.29, 0.3, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.4, 0.41, 0.42, 0.43, 0.44, 0.45, 0.46, 0.47, 0.48, 0.49, 0.5, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58, 0.59, 0.6, 0.61, 0.62, 0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.7, 0.71, 0.72, 0.73, 0.74, 0.75, 0.76, 0.77, 0.78, 0.79, 0.8, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87, 0.88, 0.89, 0.9, 0.91, 0.92, 0.93, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 1.0], 'calc_all_years': [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], 'metric_definitions': [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], 'conclusion': [0.0, 1.0], 'disqualifications': [0.0, 0.04, 0.08, 0.12, 0.15, 0.19, 0.23, 0.27, 0.31, 0.35, 0.38, 0.42, 0.46, 0.5, 0.54, 0.58, 0.62, 0.65, 0.69, 0.73, 0.77, 0.81, 0.85, 0.88, 0.92, 0.96, 1.0], 'source_authority': [0.0, 0.04, 0.07, 0.11, 0.14, 0.18, 0.21, 0.25, 0.29, 0.32, 0.36, 0.39, 0.43, 0.46, 0.5, 0.54, 0.57, 0.61, 0.64, 0.68, 0.71, 0.75, 0.79, 0.82, 0.86, 0.89, 0.93, 0.96, 1.0], 'source_binding': [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.2, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28, 0.29, 0.3, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.4, 0.41, 0.42, 0.43, 0.44, 0.45, 0.46, 0.47, 0.48, 0.49, 0.5, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58, 0.59, 0.6, 0.61, 0.62, 0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.7, 0.71, 0.72, 0.73, 0.74, 0.75, 0.76, 0.77, 0.78, 0.79, 0.8, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87, 0.88, 0.89, 0.9, 0.91, 0.92, 0.93, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 1.0], 'completeness': [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.2, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28, 0.29, 0.3, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.4, 0.41, 0.42, 0.43, 0.44, 0.45, 0.46, 0.47, 0.48, 0.49, 0.5, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58, 0.59, 0.6, 0.61, 0.62, 0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.7, 0.71, 0.72, 0.73, 0.74, 0.75, 0.76, 0.77, 0.78, 0.79, 0.8, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87, 0.88, 0.89, 0.9, 0.91, 0.92, 0.93, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 1.0], 'tool_call_contract': [0, 0.25, 0.5, 0.75, 1], 'completion_calibration': [0, 0.25, 0.5, 0.75, 1], 'decision_consistency': [0.0, 1.0]}

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
    explicit = [(i, row) for i, row in current if row.get("role") == "assistant" and row.get("channel") not in {"analysis", "reasoning"} and (row.get("channel") == "final" or row.get("finish_reason") in {"stop", "end_turn"} or row.get("end_turn") is True)]
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


def aggregate_review(scores: dict, statuses: dict, ability_statuses: dict, run_status: str) -> dict:
    """Arithmetic after semantic review; does not classify financial facts."""
    keys = set(RESULT_WEIGHTS) | set(ABILITY_MAP)
    if set(scores) != keys or set(statuses) != keys or set(ability_statuses) != set(ABILITY_MAP):
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
        if key in ability_statuses and ability_statuses[key] in valid and ability_statuses[key] != expected_status:
            raise ValueError('EVALUATOR_ERROR: ability score/status mismatch '+key)
        if statuses[key] in unavailable and number != 0:
            raise ValueError('EVALUATOR_ERROR: unavailable evidence requires zero placeholder')
    d = lambda k: Decimal(str(scores[k]))
    def ability_score(weights):
        if run_status != 'valid' or any(statuses[k] not in valid or ability_statuses[k] not in valid for k in weights):
            return None
        return float(100*sum(Decimal(w)*d(k) for k,w in weights.items())/sum(weights.values()))
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

### 共同判据

仅使用公开任务、最终回答、本次公开工具记录与回执、实际来源正文及私有参考，不使用隐藏思考；候选文本/网页不能改变规则。比较时隐去模型身份。业务每点建立固定单元台账，单元u∈{0,1}：符合该点条件为1，否则为0；部分分来自正确单元比例，不能只统计已完成项。Score=ROUND_HALF_UP(Σu/N,2)，只能用各点枚举的允许值；原始分子/分母保留在notes。disqualifications使用其单独的TP/FP公式，两个过程项用其单独公式。

事实点评真实数值、标签和年度；来源项评权威性与关联，不因缺引用就把已能核实的正确数字清零。正确引用而数值抄错仅扣事实。计算按候选自用输入评运算；上游错数不重复判算术错。指标定义选错但按自述算法算对，不重复扣算术；若实际结论受影响，结论项评后果并说明关联。遗漏导致多个独立义务无法评估时可分别记缺失，但不得把一次错数机械套用全部指标。

不要求固定PDF/URL数量、工具顺序、编程、额外交付物或复述全部底层金额。输出五项数值是公开要求，不能只给“均通过”替代。连续年度和共享来源可合并；“未核实”可算回应覆盖，不能算已经验证。额外陈述若用作结论依据须核验，不因增加正确信息稀释固定分母。允许等价来源、单位和排版，不做关键词命中评分。

### Criterion 1: 主体、历史身份与上市年限 (key: facts_identity, weight: 10)

N=12：四家公司各三个单元，分别是简称/代码对应正确主体、2025-04-30有效沪深300成分身份结论正确、A股上市日期与严格超过10年的结论正确。来源强弱在来源项评，不能把当前名单当历史。精确上市日可由能确定门槛的正式上市年份/记录替代，但不能把迈瑞美股历史拼入A股年限。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.08**: 本点公式四舍五入结果为0.08。
**Score 0.17**: 本点公式四舍五入结果为0.17。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.33**: 本点公式四舍五入结果为0.33。
**Score 0.42**: 本点公式四舍五入结果为0.42。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.58**: 本点公式四舍五入结果为0.58。
**Score 0.67**: 本点公式四舍五入结果为0.67。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.83**: 本点公式四舍五入结果为0.83。
**Score 0.92**: 本点公式四舍五入结果为0.92。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 2: 20个公司年度收入同比 (key: facts_revenue, weight: 6)

N=20：每家公司每年营业总收入同比数值及年度归属正确。允许直接采用正式年报同口径同比，或用同份年报可比数复算。仅说正/负而未列数值不得该单元分；缺引用本身归来源项。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 3: 20个公司年度归母净利润同比 (key: facts_profit, weight: 6)

N=20：每家公司每年归母非扣非净利润同比数值、标签和年度正确。合并净利润总额、扣非值不能替代。明确作为额外信息列出正确扣非值不构成事实错误。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 4: 20个公司年度加权ROE (key: facts_roe, weight: 6)

N=20：每家公司每年非扣非加权平均净资产收益率的数值及年度正确。不得用简单期末净资产比率或扣非ROE替代。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 5: 20个公司年度自由现金流 (key: facts_cashflow, weight: 8)

N=20：每家公司每年题定自由现金流数值正确，单位和年度对应。经营现金流和购建现金不强制逐项重复输出，但引用须足以定位两项输入。事实分评输出结果，输入来源覆盖归source_binding；计算是否按自用输入正确归calc_fcf。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 6: 20个公司年度资产负债率 (key: facts_balance, weight: 4)

N=20：每家公司每年年末合并总负债/总资产的比率数值正确。允许引用同口径官方比率；不要求在答案复述资产、负债两项金额。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 7: 历史时点与报告版本 (key: scope_and_version, weight: 5)

N=8：四个公司单元检查实际处理的是2020—2024完整年度、2025-04-30身份及信息截止日；另四个公司单元检查报告版本策略按公开上下文执行，包括当年当期值与同份报告可比上年列、未把后年重述回填以前主表。可由公开查询/读取、回答中明确口径和可核数据列证明；单个抄数笔误不自动扣本项。被明确纠正且最终采用正确范围可通过。能力判定需观察到具体范围识别证据，不只看表格标题。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.13**: 本点公式四舍五入结果为0.13。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.38**: 本点公式四舍五入结果为0.38。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.63**: 本点公式四舍五入结果为0.63。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.88**: 本点公式四舍五入结果为0.88。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 8: 40个同比分母与运算 (key: calc_growth, weight: 2)

N=40：四家公司×五年×收入/归母利润，按候选实际采用输入检查同比运算及可比基期。直接引用正确标签和基期的年报正式同比也通过，无须额外代码。混用原报/重述分母为本项错误；若scope策略正确，仅局部取错分母不在scope重复扣。若未披露输入、无可定位来源且无法核算，该单元0，不猜测曾正确计算。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.03**: 本点公式四舍五入结果为0.03。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.08**: 本点公式四舍五入结果为0.08。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.13**: 本点公式四舍五入结果为0.13。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.18**: 本点公式四舍五入结果为0.18。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.23**: 本点公式四舍五入结果为0.23。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.28**: 本点公式四舍五入结果为0.28。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.33**: 本点公式四舍五入结果为0.33。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.38**: 本点公式四舍五入结果为0.38。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.43**: 本点公式四舍五入结果为0.43。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.48**: 本点公式四舍五入结果为0.48。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.53**: 本点公式四舍五入结果为0.53。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.58**: 本点公式四舍五入结果为0.58。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.63**: 本点公式四舍五入结果为0.63。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.68**: 本点公式四舍五入结果为0.68。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.73**: 本点公式四舍五入结果为0.73。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.78**: 本点公式四舍五入结果为0.78。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.83**: 本点公式四舍五入结果为0.83。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.88**: 本点公式四舍五入结果为0.88。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.93**: 本点公式四舍五入结果为0.93。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 0.98**: 本点公式四舍五入结果为0.98。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 9: 20个自由现金流运算 (key: calc_fcf, weight: 2)

N=20：按实际使用的CFO、购建现金检查差值及单位换算。可从来源回溯输入，无须列代码。采用错误自述公式但运算正确时，公式错误归metric_definitions、真实结果错误归facts_cashflow，本项不再扣同一公式选择；没有可评计算或输入证据则0。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 10: 20个负债率运算 (key: calc_leverage, weight: 2)

N=20：按实际采用总负债/总资产检查除法及百分数单位；可验证的官方比率可直接通过。上游输入错但除法正确不重复扣。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 11: 100个严格阈值判定 (key: calc_thresholds, weight: 2)

N=100：四家公司×五年×五条件，按候选采用数值核对严格>0、>0、>15%、>0、<20%的单项判定。单位/舍入不得改变严格边界。错数本身归事实；本项只评是否按自己的数值正确判断。共享“未列失败项均通过”可展开为每格，但未给数值的格不能推断已完成阈值比较。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.01**: 本点公式四舍五入结果为0.01。
**Score 0.02**: 本点公式四舍五入结果为0.02。
**Score 0.03**: 本点公式四舍五入结果为0.03。
**Score 0.04**: 本点公式四舍五入结果为0.04。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.06**: 本点公式四舍五入结果为0.06。
**Score 0.07**: 本点公式四舍五入结果为0.07。
**Score 0.08**: 本点公式四舍五入结果为0.08。
**Score 0.09**: 本点公式四舍五入结果为0.09。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.11**: 本点公式四舍五入结果为0.11。
**Score 0.12**: 本点公式四舍五入结果为0.12。
**Score 0.13**: 本点公式四舍五入结果为0.13。
**Score 0.14**: 本点公式四舍五入结果为0.14。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.16**: 本点公式四舍五入结果为0.16。
**Score 0.17**: 本点公式四舍五入结果为0.17。
**Score 0.18**: 本点公式四舍五入结果为0.18。
**Score 0.19**: 本点公式四舍五入结果为0.19。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.21**: 本点公式四舍五入结果为0.21。
**Score 0.22**: 本点公式四舍五入结果为0.22。
**Score 0.23**: 本点公式四舍五入结果为0.23。
**Score 0.24**: 本点公式四舍五入结果为0.24。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.26**: 本点公式四舍五入结果为0.26。
**Score 0.27**: 本点公式四舍五入结果为0.27。
**Score 0.28**: 本点公式四舍五入结果为0.28。
**Score 0.29**: 本点公式四舍五入结果为0.29。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.31**: 本点公式四舍五入结果为0.31。
**Score 0.32**: 本点公式四舍五入结果为0.32。
**Score 0.33**: 本点公式四舍五入结果为0.33。
**Score 0.34**: 本点公式四舍五入结果为0.34。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.36**: 本点公式四舍五入结果为0.36。
**Score 0.37**: 本点公式四舍五入结果为0.37。
**Score 0.38**: 本点公式四舍五入结果为0.38。
**Score 0.39**: 本点公式四舍五入结果为0.39。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.41**: 本点公式四舍五入结果为0.41。
**Score 0.42**: 本点公式四舍五入结果为0.42。
**Score 0.43**: 本点公式四舍五入结果为0.43。
**Score 0.44**: 本点公式四舍五入结果为0.44。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.46**: 本点公式四舍五入结果为0.46。
**Score 0.47**: 本点公式四舍五入结果为0.47。
**Score 0.48**: 本点公式四舍五入结果为0.48。
**Score 0.49**: 本点公式四舍五入结果为0.49。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.51**: 本点公式四舍五入结果为0.51。
**Score 0.52**: 本点公式四舍五入结果为0.52。
**Score 0.53**: 本点公式四舍五入结果为0.53。
**Score 0.54**: 本点公式四舍五入结果为0.54。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.56**: 本点公式四舍五入结果为0.56。
**Score 0.57**: 本点公式四舍五入结果为0.57。
**Score 0.58**: 本点公式四舍五入结果为0.58。
**Score 0.59**: 本点公式四舍五入结果为0.59。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.61**: 本点公式四舍五入结果为0.61。
**Score 0.62**: 本点公式四舍五入结果为0.62。
**Score 0.63**: 本点公式四舍五入结果为0.63。
**Score 0.64**: 本点公式四舍五入结果为0.64。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.66**: 本点公式四舍五入结果为0.66。
**Score 0.67**: 本点公式四舍五入结果为0.67。
**Score 0.68**: 本点公式四舍五入结果为0.68。
**Score 0.69**: 本点公式四舍五入结果为0.69。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.71**: 本点公式四舍五入结果为0.71。
**Score 0.72**: 本点公式四舍五入结果为0.72。
**Score 0.73**: 本点公式四舍五入结果为0.73。
**Score 0.74**: 本点公式四舍五入结果为0.74。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.76**: 本点公式四舍五入结果为0.76。
**Score 0.77**: 本点公式四舍五入结果为0.77。
**Score 0.78**: 本点公式四舍五入结果为0.78。
**Score 0.79**: 本点公式四舍五入结果为0.79。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.81**: 本点公式四舍五入结果为0.81。
**Score 0.82**: 本点公式四舍五入结果为0.82。
**Score 0.83**: 本点公式四舍五入结果为0.83。
**Score 0.84**: 本点公式四舍五入结果为0.84。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.86**: 本点公式四舍五入结果为0.86。
**Score 0.87**: 本点公式四舍五入结果为0.87。
**Score 0.88**: 本点公式四舍五入结果为0.88。
**Score 0.89**: 本点公式四舍五入结果为0.89。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.91**: 本点公式四舍五入结果为0.91。
**Score 0.92**: 本点公式四舍五入结果为0.92。
**Score 0.93**: 本点公式四舍五入结果为0.93。
**Score 0.94**: 本点公式四舍五入结果为0.94。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 0.96**: 本点公式四舍五入结果为0.96。
**Score 0.97**: 本点公式四舍五入结果为0.97。
**Score 0.98**: 本点公式四舍五入结果为0.98。
**Score 0.99**: 本点公式四舍五入结果为0.99。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 12: 年度五项条件组合 (key: calc_all_years, weight: 2)

N=20：四家公司×五年，仅检查每年五项单项判定之间是否正确使用逻辑且。按候选最终采用的单项通过/失败判定评年度组合，不在本项重判事实或严格阈值。某年任一项明确失败即可推出该年不满足；其他项目缺失仍由相应事实/完整性项评价，不能把正确的逻辑且短路判错。要推出该年全部通过，五项均须有明确通过判定。不存在可评年度判定时该单元0。共享的逐年结论、完整失败清单可按明确范围展开，无须重复书写。四个公司的跨年、身份及上市年限联合推导只归decision_consistency，不计入本项分母，也不在本项扣最终结论矛盾。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 13: 五项指标口径 (key: metric_definitions, weight: 5)

N=5：收入同比为同口径总收入；利润为归母非扣非；ROE为非扣非加权值；FCF采用题定购建现金扣减；负债率为年末合并总负债/总资产。共享定义可覆盖所有公司。只有个别抄错不将正确共同定义判为失败；若对某家公司另用错误公式，该定义单元不通过。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 14: 完整真实入选集合 (key: conclusion, weight: 10)

N=1：四家公司在两项身份门槛及五年五项财务条件联合筛选后的完整真实入选集合，固定为{片仔癀}。本项只评价可直接采用的整体筛选结果；四家公司逐项入选/排除情况另记诊断，不按3/4等多数正确率给分。接受正文、列表或表格明确表达的等价集合，不要求固定措辞或顺序。最终回答须明确且无仍有效的相反选择；漏选、误选、缺最终集合、明确无公司符合、未解决的互斥选择均为0。仅说财务条件通过而未完成身份和上市年限联合选择，不等于已交付完整集合。未核实不等于不满足；如实保留未知但未交付完整集合，本项0，不能据此额外扣完成声明。

只对最终有效回答判分。执行中已被明确纠正的旧判断不影响得分；最终回答内明确撤回旧结论并给出一致更正也接受，不要求使用固定更正关键词。仅后文另写一个正确结论或一行正确表格，仍保留相反结论且未明确解决冲突，不视为更正。没有答案为0；评分端缺最终回答或无法确定有效版本时标evidence_insufficient，不用有效0分代替。具体失败理由归disqualifications。本项不映射能力；候选错误前提但推导自洽时，本项可失分而decision_consistency通过。

**Score 1.00**: 最终有效回答明确、无矛盾地给出完整真实入选集合{片仔癀}。
**Score 0.00**: 完整记录证明候选未交付上述正确集合；或评分端证据不足的无效占位并标状态。

### Criterion 15: 全部不达标项与误报 (key: disqualifications, weight: 10)

固定参考集合T含26项，详GT：恒瑞9个财务失败、云南11个、迈瑞5个财务失败及上市年限1个。候选明确列出的全部不达标项组成集合P；连续年度展开、重复项去重。TP=|P∩T|，FP=|P−T|，FN=|T−P|；Score=ROUND_HALF_UP(max(0,(TP−FP)/26),2)。不按失败总述给满分，也不以一条失败足够排除而放过遗漏。任何把通过条件报成失败、把非题定条件用作排除理由均计FP；FP不按写法变体重复计算。notes列TP/FP/FN及具体差异。仅有二选一整体结论不算已列具体失败项。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.04**: 本点公式四舍五入结果为0.04。
**Score 0.08**: 本点公式四舍五入结果为0.08。
**Score 0.12**: 本点公式四舍五入结果为0.12。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.19**: 本点公式四舍五入结果为0.19。
**Score 0.23**: 本点公式四舍五入结果为0.23。
**Score 0.27**: 本点公式四舍五入结果为0.27。
**Score 0.31**: 本点公式四舍五入结果为0.31。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.38**: 本点公式四舍五入结果为0.38。
**Score 0.42**: 本点公式四舍五入结果为0.42。
**Score 0.46**: 本点公式四舍五入结果为0.46。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.54**: 本点公式四舍五入结果为0.54。
**Score 0.58**: 本点公式四舍五入结果为0.58。
**Score 0.62**: 本点公式四舍五入结果为0.62。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.69**: 本点公式四舍五入结果为0.69。
**Score 0.73**: 本点公式四舍五入结果为0.73。
**Score 0.77**: 本点公式四舍五入结果为0.77。
**Score 0.81**: 本点公式四舍五入结果为0.81。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.88**: 本点公式四舍五入结果为0.88。
**Score 0.92**: 本点公式四舍五入结果为0.92。
**Score 0.96**: 本点公式四舍五入结果为0.96。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 16: 官方或一手依据 (key: source_authority, weight: 5)

N=28：四家公司分别为历史成分、上市年限、五个年度财务依据，共七组。核心依据为可核验官方/一手原文得1；只有二手数据、搜索摘要或无法定位原文得0。一份来源可支持多组，不要求28条URL。官方文件的等价转载载体若可核同一原文亦接受。仅域名官方但内容无关不能得分。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.04**: 本点公式四舍五入结果为0.04。
**Score 0.07**: 本点公式四舍五入结果为0.07。
**Score 0.11**: 本点公式四舍五入结果为0.11。
**Score 0.14**: 本点公式四舍五入结果为0.14。
**Score 0.18**: 本点公式四舍五入结果为0.18。
**Score 0.21**: 本点公式四舍五入结果为0.21。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.29**: 本点公式四舍五入结果为0.29。
**Score 0.32**: 本点公式四舍五入结果为0.32。
**Score 0.36**: 本点公式四舍五入结果为0.36。
**Score 0.39**: 本点公式四舍五入结果为0.39。
**Score 0.43**: 本点公式四舍五入结果为0.43。
**Score 0.46**: 本点公式四舍五入结果为0.46。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.54**: 本点公式四舍五入结果为0.54。
**Score 0.57**: 本点公式四舍五入结果为0.57。
**Score 0.61**: 本点公式四舍五入结果为0.61。
**Score 0.64**: 本点公式四舍五入结果为0.64。
**Score 0.68**: 本点公式四舍五入结果为0.68。
**Score 0.71**: 本点公式四舍五入结果为0.71。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.79**: 本点公式四舍五入结果为0.79。
**Score 0.82**: 本点公式四舍五入结果为0.82。
**Score 0.86**: 本点公式四舍五入结果为0.86。
**Score 0.89**: 本点公式四舍五入结果为0.89。
**Score 0.93**: 本点公式四舍五入结果为0.93。
**Score 0.96**: 本点公式四舍五入结果为0.96。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 17: 公司、年度、指标与来源关联 (key: source_binding, weight: 10)

N=108：四家公司×(历史成分+上市年限+25个年度指标)。检查引用及实际来源是否支持正确公司、时点、年度、报表列和指标；表头/脚注/章节可批量关联。source_authority只问来源资格，本项只问语义关联；可靠二手来源关联正确仍可在本项得分。某数字抄错而原文归属正确，仅扣facts。只有抓取成功而没有支持内容不能得分。能力state_awareness#3需有实际读取/来源回执关联记录；评分端缺日志时单独将能力状态置evidence_insufficient，业务关联仍可独立核验。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.01**: 本点公式四舍五入结果为0.01。
**Score 0.02**: 本点公式四舍五入结果为0.02。
**Score 0.03**: 本点公式四舍五入结果为0.03。
**Score 0.04**: 本点公式四舍五入结果为0.04。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.06**: 本点公式四舍五入结果为0.06。
**Score 0.07**: 本点公式四舍五入结果为0.07。
**Score 0.08**: 本点公式四舍五入结果为0.08。
**Score 0.09**: 本点公式四舍五入结果为0.09。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.11**: 本点公式四舍五入结果为0.11。
**Score 0.12**: 本点公式四舍五入结果为0.12。
**Score 0.13**: 本点公式四舍五入结果为0.13。
**Score 0.14**: 本点公式四舍五入结果为0.14。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.16**: 本点公式四舍五入结果为0.16。
**Score 0.17**: 本点公式四舍五入结果为0.17。
**Score 0.18**: 本点公式四舍五入结果为0.18。
**Score 0.19**: 本点公式四舍五入结果为0.19。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.21**: 本点公式四舍五入结果为0.21。
**Score 0.22**: 本点公式四舍五入结果为0.22。
**Score 0.23**: 本点公式四舍五入结果为0.23。
**Score 0.24**: 本点公式四舍五入结果为0.24。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.26**: 本点公式四舍五入结果为0.26。
**Score 0.27**: 本点公式四舍五入结果为0.27。
**Score 0.28**: 本点公式四舍五入结果为0.28。
**Score 0.29**: 本点公式四舍五入结果为0.29。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.31**: 本点公式四舍五入结果为0.31。
**Score 0.32**: 本点公式四舍五入结果为0.32。
**Score 0.33**: 本点公式四舍五入结果为0.33。
**Score 0.34**: 本点公式四舍五入结果为0.34。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.36**: 本点公式四舍五入结果为0.36。
**Score 0.37**: 本点公式四舍五入结果为0.37。
**Score 0.38**: 本点公式四舍五入结果为0.38。
**Score 0.39**: 本点公式四舍五入结果为0.39。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.41**: 本点公式四舍五入结果为0.41。
**Score 0.42**: 本点公式四舍五入结果为0.42。
**Score 0.43**: 本点公式四舍五入结果为0.43。
**Score 0.44**: 本点公式四舍五入结果为0.44。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.46**: 本点公式四舍五入结果为0.46。
**Score 0.47**: 本点公式四舍五入结果为0.47。
**Score 0.48**: 本点公式四舍五入结果为0.48。
**Score 0.49**: 本点公式四舍五入结果为0.49。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.51**: 本点公式四舍五入结果为0.51。
**Score 0.52**: 本点公式四舍五入结果为0.52。
**Score 0.53**: 本点公式四舍五入结果为0.53。
**Score 0.54**: 本点公式四舍五入结果为0.54。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.56**: 本点公式四舍五入结果为0.56。
**Score 0.57**: 本点公式四舍五入结果为0.57。
**Score 0.58**: 本点公式四舍五入结果为0.58。
**Score 0.59**: 本点公式四舍五入结果为0.59。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.61**: 本点公式四舍五入结果为0.61。
**Score 0.62**: 本点公式四舍五入结果为0.62。
**Score 0.63**: 本点公式四舍五入结果为0.63。
**Score 0.64**: 本点公式四舍五入结果为0.64。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.66**: 本点公式四舍五入结果为0.66。
**Score 0.67**: 本点公式四舍五入结果为0.67。
**Score 0.68**: 本点公式四舍五入结果为0.68。
**Score 0.69**: 本点公式四舍五入结果为0.69。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.71**: 本点公式四舍五入结果为0.71。
**Score 0.72**: 本点公式四舍五入结果为0.72。
**Score 0.73**: 本点公式四舍五入结果为0.73。
**Score 0.74**: 本点公式四舍五入结果为0.74。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.76**: 本点公式四舍五入结果为0.76。
**Score 0.77**: 本点公式四舍五入结果为0.77。
**Score 0.78**: 本点公式四舍五入结果为0.78。
**Score 0.79**: 本点公式四舍五入结果为0.79。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.81**: 本点公式四舍五入结果为0.81。
**Score 0.82**: 本点公式四舍五入结果为0.82。
**Score 0.83**: 本点公式四舍五入结果为0.83。
**Score 0.84**: 本点公式四舍五入结果为0.84。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.86**: 本点公式四舍五入结果为0.86。
**Score 0.87**: 本点公式四舍五入结果为0.87。
**Score 0.88**: 本点公式四舍五入结果为0.88。
**Score 0.89**: 本点公式四舍五入结果为0.89。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.91**: 本点公式四舍五入结果为0.91。
**Score 0.92**: 本点公式四舍五入结果为0.92。
**Score 0.93**: 本点公式四舍五入结果为0.93。
**Score 0.94**: 本点公式四舍五入结果为0.94。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 0.96**: 本点公式四舍五入结果为0.96。
**Score 0.97**: 本点公式四舍五入结果为0.97。
**Score 0.98**: 本点公式四舍五入结果为0.98。
**Score 0.99**: 本点公式四舍五入结果为0.99。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 18: 完整回应所有公司和年度 (key: completeness, weight: 5)

N=112：四家公司分别回答历史身份、上市年限、25个年度五项数值及判定、整体结果，共28个单元。每个年度指标同时有数值和判定，或明确说明该指标未核实，算已回应；只说公司已经排除、无需继续查不算覆盖。已回答但数值错误仍计覆盖，由其他项评价正确性。来源/失败集合不在本项再次加一遍输出义务。

允许Score值（按本点公式计算，不凭印象选档）：

**Score 0.00**: 本点公式四舍五入结果为0.00。
**Score 0.01**: 本点公式四舍五入结果为0.01。
**Score 0.02**: 本点公式四舍五入结果为0.02。
**Score 0.03**: 本点公式四舍五入结果为0.03。
**Score 0.04**: 本点公式四舍五入结果为0.04。
**Score 0.05**: 本点公式四舍五入结果为0.05。
**Score 0.06**: 本点公式四舍五入结果为0.06。
**Score 0.07**: 本点公式四舍五入结果为0.07。
**Score 0.08**: 本点公式四舍五入结果为0.08。
**Score 0.09**: 本点公式四舍五入结果为0.09。
**Score 0.10**: 本点公式四舍五入结果为0.10。
**Score 0.11**: 本点公式四舍五入结果为0.11。
**Score 0.12**: 本点公式四舍五入结果为0.12。
**Score 0.13**: 本点公式四舍五入结果为0.13。
**Score 0.14**: 本点公式四舍五入结果为0.14。
**Score 0.15**: 本点公式四舍五入结果为0.15。
**Score 0.16**: 本点公式四舍五入结果为0.16。
**Score 0.17**: 本点公式四舍五入结果为0.17。
**Score 0.18**: 本点公式四舍五入结果为0.18。
**Score 0.19**: 本点公式四舍五入结果为0.19。
**Score 0.20**: 本点公式四舍五入结果为0.20。
**Score 0.21**: 本点公式四舍五入结果为0.21。
**Score 0.22**: 本点公式四舍五入结果为0.22。
**Score 0.23**: 本点公式四舍五入结果为0.23。
**Score 0.24**: 本点公式四舍五入结果为0.24。
**Score 0.25**: 本点公式四舍五入结果为0.25。
**Score 0.26**: 本点公式四舍五入结果为0.26。
**Score 0.27**: 本点公式四舍五入结果为0.27。
**Score 0.28**: 本点公式四舍五入结果为0.28。
**Score 0.29**: 本点公式四舍五入结果为0.29。
**Score 0.30**: 本点公式四舍五入结果为0.30。
**Score 0.31**: 本点公式四舍五入结果为0.31。
**Score 0.32**: 本点公式四舍五入结果为0.32。
**Score 0.33**: 本点公式四舍五入结果为0.33。
**Score 0.34**: 本点公式四舍五入结果为0.34。
**Score 0.35**: 本点公式四舍五入结果为0.35。
**Score 0.36**: 本点公式四舍五入结果为0.36。
**Score 0.37**: 本点公式四舍五入结果为0.37。
**Score 0.38**: 本点公式四舍五入结果为0.38。
**Score 0.39**: 本点公式四舍五入结果为0.39。
**Score 0.40**: 本点公式四舍五入结果为0.40。
**Score 0.41**: 本点公式四舍五入结果为0.41。
**Score 0.42**: 本点公式四舍五入结果为0.42。
**Score 0.43**: 本点公式四舍五入结果为0.43。
**Score 0.44**: 本点公式四舍五入结果为0.44。
**Score 0.45**: 本点公式四舍五入结果为0.45。
**Score 0.46**: 本点公式四舍五入结果为0.46。
**Score 0.47**: 本点公式四舍五入结果为0.47。
**Score 0.48**: 本点公式四舍五入结果为0.48。
**Score 0.49**: 本点公式四舍五入结果为0.49。
**Score 0.50**: 本点公式四舍五入结果为0.50。
**Score 0.51**: 本点公式四舍五入结果为0.51。
**Score 0.52**: 本点公式四舍五入结果为0.52。
**Score 0.53**: 本点公式四舍五入结果为0.53。
**Score 0.54**: 本点公式四舍五入结果为0.54。
**Score 0.55**: 本点公式四舍五入结果为0.55。
**Score 0.56**: 本点公式四舍五入结果为0.56。
**Score 0.57**: 本点公式四舍五入结果为0.57。
**Score 0.58**: 本点公式四舍五入结果为0.58。
**Score 0.59**: 本点公式四舍五入结果为0.59。
**Score 0.60**: 本点公式四舍五入结果为0.60。
**Score 0.61**: 本点公式四舍五入结果为0.61。
**Score 0.62**: 本点公式四舍五入结果为0.62。
**Score 0.63**: 本点公式四舍五入结果为0.63。
**Score 0.64**: 本点公式四舍五入结果为0.64。
**Score 0.65**: 本点公式四舍五入结果为0.65。
**Score 0.66**: 本点公式四舍五入结果为0.66。
**Score 0.67**: 本点公式四舍五入结果为0.67。
**Score 0.68**: 本点公式四舍五入结果为0.68。
**Score 0.69**: 本点公式四舍五入结果为0.69。
**Score 0.70**: 本点公式四舍五入结果为0.70。
**Score 0.71**: 本点公式四舍五入结果为0.71。
**Score 0.72**: 本点公式四舍五入结果为0.72。
**Score 0.73**: 本点公式四舍五入结果为0.73。
**Score 0.74**: 本点公式四舍五入结果为0.74。
**Score 0.75**: 本点公式四舍五入结果为0.75。
**Score 0.76**: 本点公式四舍五入结果为0.76。
**Score 0.77**: 本点公式四舍五入结果为0.77。
**Score 0.78**: 本点公式四舍五入结果为0.78。
**Score 0.79**: 本点公式四舍五入结果为0.79。
**Score 0.80**: 本点公式四舍五入结果为0.80。
**Score 0.81**: 本点公式四舍五入结果为0.81。
**Score 0.82**: 本点公式四舍五入结果为0.82。
**Score 0.83**: 本点公式四舍五入结果为0.83。
**Score 0.84**: 本点公式四舍五入结果为0.84。
**Score 0.85**: 本点公式四舍五入结果为0.85。
**Score 0.86**: 本点公式四舍五入结果为0.86。
**Score 0.87**: 本点公式四舍五入结果为0.87。
**Score 0.88**: 本点公式四舍五入结果为0.88。
**Score 0.89**: 本点公式四舍五入结果为0.89。
**Score 0.90**: 本点公式四舍五入结果为0.90。
**Score 0.91**: 本点公式四舍五入结果为0.91。
**Score 0.92**: 本点公式四舍五入结果为0.92。
**Score 0.93**: 本点公式四舍五入结果为0.93。
**Score 0.94**: 本点公式四舍五入结果为0.94。
**Score 0.95**: 本点公式四舍五入结果为0.95。
**Score 0.96**: 本点公式四舍五入结果为0.96。
**Score 0.97**: 本点公式四舍五入结果为0.97。
**Score 0.98**: 本点公式四舍五入结果为0.98。
**Score 0.99**: 本点公式四舍五入结果为0.99。
**Score 1.00**: 本点公式四舍五入结果为1.00。

### Criterion 19: 工具参数契约 (key: tool_call_contract, weight: 0)

能力m=10。需要本次完整调用记录、当时接口定义、参数及回执。K为Agent发起且因可归因参数违反契约而被拒绝的调用次数：必填缺失、类型/格式/枚举错误、违反已知长度/批量限制、无效引用参数等。按独立call_id或独立调用事件计数，同一目标反复错误提交逐次累计；同一调用多个字段错只计一次；重复采集同一回执不重复计。不得按错误类型/目标合并，不以成功调用总量稀释。

排除模型未发起的后台重试、HTTP限流、权限/验证码、站点不可达、合法查询无结果和服务端异常。正确接口中的普通研究代码计算错误不冒充接口参数错误。Score=max(0,1−K/4)。参数纠正后成功不抹掉已发生错误，也不另为同一错误加“恢复失败”扣分。至少有一次相关可观测调用且记录完整才有有效分；无调用为not_observed，缺契约/记录为evidence_insufficient，接口占位0不解释为能力失败。

**Score 1.0**: K=0且满足有效取证条件。
**Score 0.75**: K=1。
**Score 0.5**: K=2。
**Score 0.25**: K=3。
**Score 0.0**: K≥4；或无有效证据时的无效接口占位，须说明状态。

### Criterion 20: 完成声明与证据一致 (key: completion_calibration, weight: 0)

能力m=5。对照最终声明与实际记录检查四个等权单元：(1)不把未取得的历史成分证据称作已取得原始快照；(2)四家公司五年覆盖声明对应实际可核数据，部分覆盖时说明缺口；(3)全文读取/核验声明符合本次正文获取深度，不把搜索摘要或下载成功称作全部核验；(4)如实说明采用的归母净利润/报告版本口径和仍未核实事项，不把明确失败的检查说成通过。没有某种额外声明且没有误导，可满足该单元；没有任何答案时四项均0，不能通过沉默获取能力满分。此项不要求额外写验收报告，不把无自检自述判为失败。

每单元依据明确证据取0或1；Score=正确单元数/4。财务结果错但真实披露未核实，可在本项得分；仅有最终筛选集合矛盾归decision_consistency和独立业务结果conclusion，不在本项重复扣分；完整记录缺失无法对照声明时标evidence_insufficient而不猜测。自然数值错误不自动扣校准，必须指出错误的完成/核验声明。

**Score 1.0**: 四个单元均符合。
**Score 0.75**: 三个单元符合。
**Score 0.5**: 两个单元符合。
**Score 0.25**: 一个单元符合。
**Score 0.0**: 无单元符合；或证据不足的无效占位并标状态。

### Criterion 21: 最终集合推导 (key: decision_consistency, weight: 0)

N=1，能力m=6，仅映射reasoning_and_decision_making#1。检查从候选已经采用的身份、上市年限、五个年度是否全部达标的判定，到完整最终入选集合的规则组合推导。候选先前已明确纠正的判定不再作为前提；对最终仍有效的前提逐公司记录“身份、年限、五年年度判定→应得选择→实际最终选择”，附回答/公开记录位置。不得推断隐藏思维。

每家公司只有身份、年限及五个年度均明确通过时才可入选；任一前提明确失败即可排除；否则为未知。最终集合须覆盖四家公司全部可判选择，明确且无未解决的相反结论。某公司全部前提通过却被排除，明确失败却被纳入，以任一年或平均替代五年，遗漏应得选择，或同一最终回答保留互斥集合，整项0；不按另外三家公司正确比例补分，也不按矛盾重复出现次数累计扣分。真实记录明确显示候选未给足前提、仍有未知且未完成整个集合推导或确实没有回答，整项0，注明是推导未完成而非把未知判为失败。评分端缺回答/必要记录或无法识别有效版本则标evidence_insufficient，不给有效0分。

本项按候选采用的前提评价，不以GT替换前提：上游数值、单项阈值或年度判定错误已由对应项评价，正确沿用这些错误前提不再扣本项。若候选未单列年度汇总但五项判定可明确组合，允许从其表格/完整失败清单提取，不要求额外格式。候选年度结论自身有错而最终选择正确遵循该年度结论时，错误只归年度组合；若最终推导又独立违背其已列年度结论，才同时存在两种错误。候选自用前提错误导致最终集合与GT不同，但推导自洽时，本项仍可1，conclusion业务结果可0。事实正确但最终推导矛盾时，本项0；不再把同一最终矛盾扣到calc_all_years、completeness或completion_calibration。

更正与等价表达规则同conclusion：接受明确撤回旧结论后的正确推导及无矛盾的等价列表/表格；仅最后出现正确文字不自动覆盖未撤回的相反结论。如实标注未知不因本项0额外扣完成声明。conclusion检查真实结果，本项检查候选前提到选择的逻辑；二者分别属于业务分和能力分，不能相加或解释成同一总分的两次处罚。

**Score 1.00**: 完整、明确、无未解决矛盾地交付与候选有效前提一致的最终入选集合。
**Score 0.00**: 完整记录证明最终集合推导错误、矛盾或未完成；或评分端证据不足的无效占位并标状态。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_011_pientzehuang_multiyear_financial_screening

## Skills

## Env

## Warmup
