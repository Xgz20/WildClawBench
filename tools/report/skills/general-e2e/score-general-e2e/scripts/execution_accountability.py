"""Separate absent candidate evidence from an evaluator's inability to observe it.

This policy never assigns scores. Native admission validates provenance; the
original grader and independent Judge still determine every numeric result.
Old manifests without the marker retain their frozen protocol.
"""
from copy import deepcopy

PROFILE = "evidence-accountability/v1"
FAILED_ADMISSION = "verified-harness-failure-evidence/v1"
INTERRUPTED_ADMISSION = "verified-harness-interruption-evidence/v1"
NATIVE_ADMISSIONS = {FAILED_ADMISSION, INTERRUPTED_ADMISSION}
POLICY = {
    "profile": PROFILE,
    "candidate_evidence_not_demonstrated": "score_by_original_criterion_anchors",
    "harness_failure_is_not_automatic_whole_task_zero": True,
    "native_failure_does_not_require_complete_sdk_terminal": True,
    "missing_candidate_trace_is_not_automatically_evaluator_evidence_loss": True,
    "evaluator_or_task_source_fault": "repair_before_grading",
    "execution_affecting_framework_repair": "new_execution_attempt",
    "scoring_only_repair_with_recoverable_original_answer": "independent_rescore_original_execution",
    "retain_original_rubric_weights_and_anchors": True,
    "interpret_missing_evidence_clauses_by_evidence_origin": True,
    "decision_request_fields": ["criterion_key", "origin", "problem", "missing_evidence", "evidence_checked",
                                "why_rules_cannot_decide", "repair_execution_impact", "proposed_actions", "decision_question"],
    "unresolved_origins": ["evaluator", "task_source", "unresolved_origin"],
    "judge_instruction": (
        "先区分缺的是被测端交付/行为证明，还是评测端采集、解析、题源参考或身份绑定。"
        "已受理回合的原生报错、中断、未生成轨迹或未提供交付属于被测结果；"
        "按原检查点和锚点评分，没有满足证据的该项不得分，有已证实工作则保留部分分。"
        "原Rubric中缺证不可判定条款按证据归属解释，不能仅因被测端未提供证明而整题留空。"
        "不得丢弃已保留的前段轨迹或产物以凑零分，也不得推断无返回的调用已经成功。"
        "对未满足证明要求的判定，不声称未观察的行为绝对未发生。"
        "评测侧或题源故障不计被测能力0；现有规则仍不能决定时，列明检查点、原件位置、"
        "缺口、已核查内容、可能原因、修复影响和具体待决问题，交用户决策。"
    ),
}


def policy(manifest):
    marker = manifest.get("runtime", {}).get("evidence_accountability_profile")
    if marker is None:
        return None
    if marker != PROFILE:
        raise ValueError("EVIDENCE_ACCOUNTABILITY_PROFILE_INVALID")
    return deepcopy(POLICY)


def validate_response(request, response):
    """Unresolved scores require an actionable evaluator/source/unknown issue."""
    if request.get("evidence_accountability_policy") is None:
        return
    if request["evidence_accountability_policy"] != POLICY:
        raise ValueError("EVIDENCE_ACCOUNTABILITY_POLICY_DRIFT")
    issues = response.get("decision_requests", [])
    if not isinstance(issues, list):
        raise ValueError("EVIDENCE_DECISION_REQUEST_INVALID")
    rows = response.get('criteria')
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get('key'), str) for row in rows):
        raise ValueError('EVIDENCE_DECISION_RESPONSE_INVALID')
    unresolved = {row["key"] for row in rows if row.get("status") == "unresolved"}
    unavailable = {'evidence_insufficient', 'blocked_external', 'not_observed', 'evaluator_error'}
    for field in ('criterion_evidence_statuses', 'capability_evidence_statuses'):
        values = response.get(field, {})
        if not isinstance(values, dict):
            raise ValueError('EVIDENCE_DECISION_RESPONSE_INVALID: ' + field)
        unresolved.update(key for key, value in values.items()
                          if isinstance(value, dict) and value.get('status') in unavailable)
    if isinstance(response.get('run_validity'), dict) and response['run_validity'].get('status') == 'evidence_insufficient':
        unresolved.add('run_validity')
    keys = [item.get("criterion_key") for item in issues if isinstance(item, dict)]
    if len(keys) != len(issues) or len(set(keys)) != len(keys) or set(keys) != unresolved:
        raise ValueError("EVIDENCE_DECISION_REQUEST_SCOPE_MISMATCH: " + repr(sorted(unresolved)))
    for issue in issues:
        if issue.get("origin") not in {"evaluator", "task_source", "unresolved_origin"}:
            raise ValueError("CANDIDATE_EVIDENCE_ABSENCE_IS_NOT_UNRESOLVED: " + issue["criterion_key"])
        for key in ("problem", "missing_evidence", "evidence_checked", "why_rules_cannot_decide",
                    "repair_execution_impact", "decision_question"):
            if not isinstance(issue.get(key), str) or not issue[key].strip():
                raise ValueError("EVIDENCE_DECISION_REQUEST_INCOMPLETE: " + issue["criterion_key"] + "/" + key)
        actions = issue.get("proposed_actions")
        if not isinstance(actions, list) or not actions or not all(isinstance(x, str) and x.strip() for x in actions):
            raise ValueError("EVIDENCE_DECISION_REQUEST_INCOMPLETE: proposed_actions")


def decision_request(execution, failure):
    """Diagnostics for a failed pre-grading gate; never infer native acceptance."""
    return {
        "profile": PROFILE,
        "task_id": execution.get("identity", {}).get("task_id"),
        "execution_attempt_id": execution.get("identity", {}).get("attempt_id"),
        "prompt_send_status": execution.get("prompt", {}).get("send_status"),
        "native_session": deepcopy(execution.get("session", {})),
        "execution_error": deepcopy(execution.get("execution", {}).get("error")),
        "candidate_status": execution.get("candidate", {}).get("drift_status"),
        "missing_evidence": deepcopy(execution.get("evidence", {}).get("missing", [])),
        "blocking_check": deepcopy(failure),
        "origin": "unresolved_origin",
        "score_assigned": False,
        "required_review": [
            "核对原Prompt是否被原生端受理；未知发送只观察，禁止重发。",
            "核对题源、公开输入、评分参考与采集器是否完整可用。",
            "区分被测端未提供证据与评测侧丢失/损坏证据，附原件路径和行号。",
            "已证实执行前框架故障须修复后新执行；已受理原生失败应交原Rubric评分。",
        ],
        "decision_question": "现有证明仍不足以区分评测框架/题源问题与已受理后的Harness问题，需补充哪项证明或采用哪种处理？",
    }
