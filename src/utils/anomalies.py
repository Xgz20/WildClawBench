"""WildClawBench run 级异常检测与有效性归因。

检测器只读取 run 目录中的结构化产物，不修改评分。异常信号、责任归因、
有效性影响和重跑动作彼此独立；模型/Harness 的失败可以是有效能力结果。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 2
RULESET_VERSION = "2026-08-12.1"

ERROR = "error"
WARNING = "warning"

_TOOL_REJECT_KEYWORDS = ("unsupported call", "unknown tool")
_RATE_LIMIT_RE = re.compile(r"rate.?limit|too many requests|\b429\b", re.I)
_SERVER_ERROR_RE = re.compile(
    r"bad gateway|service unavailable|internal server error|\b50[0234]\b", re.I
)
_CONTENT_POLICY_RE = re.compile(
    r"(?:code\s*[:=]\s*10013\b|根据相关法律法规|content policy)", re.I
)
_GRADING_TIMEOUT_RE = re.compile(
    r"\btimed out after\s+\d+(?:\.\d+)?\s+seconds?\b", re.I
)
_JUDGE_OUTPUT_ERROR_RE = re.compile(
    r"judge failed:|judge_call_failed:|judge returned no valid json|"
    r"json parse failed|no valid json in (?:stdout|response)|"
    r"judge (?:output|response) (?:was )?truncated",
    re.I,
)
_HTTP_STATUS_RE = re.compile(r"(?<!\d)([45]\d\d)(?!\d)")
_ENVIRONMENT_ERROR_RE = re.compile(
    r"cannot connect to the docker daemon|docker daemon|no space left on device|"
    r"read-only file system|container .*not found|host network|dns resolution",
    re.I,
)
_HARNESS_RUN_FAILED_RE = re.compile(
    r"^(?:AstronCode|AstronClaw|OpenCode|Codex|OpenClaw|HermesAgent|ClaudeCode)\s+run failed\s*\(rc=\d+\)",
    re.I,
)
# Auth / quota exhaustion on the evaluation's own LLM endpoint is an infrastructure
# failure of the eval account, NOT a model capability outcome. It typically surfaces as
# a harness "run failed (rc=1)" wrapping a 401/403 + quota message, so it must be checked
# BEFORE _HARNESS_RUN_FAILED_RE — otherwise a zero-output crash is recorded as a real 0.0.
_AUTH_QUOTA_ERROR_RE = re.compile(
    r"401\s+unauthorized|403\s+forbidden|invalid\s+api\s*key|invalid\s+access\s+token|"
    r"authentication\s+fail|insufficient[_\s]*quota|exceeded\s+your\s+quota|"
    r"额度已用尽|余额不足|令牌.*额度|remainquota\s*=\s*-?\d",
    re.I,
)
_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{8,}", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}", re.I),
    re.compile(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|password|passwd|secret)\b\s*[:=]\s*[\"']?)"
        r"[^\s\"']+"
    ),
)
_FRAMEWORK_STAGES = {
    "created",
    "starting_container",
    "container_started",
    "preparing_workspace",
    "collecting_artifacts",
    "grading",
    "parsing_metrics",
    "preparing_harness_input",
    "launching_harness",
    "harness_launch_failed",
}
_HARNESS_STAGES = {
    "astroncode_running",
    "codex_running",
    "opencode_running",
    "openclaw_running",
    "astronclaw_running",
    "hermesagent_running",
    "claudecode_running",
    "harness_running",
    "model_execution",
}


def _load_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_text(path: Path, max_bytes: int = 4_000_000) -> str:
    try:
        with path.open("rb") as stream:
            return stream.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _iter_jsonl(path: Path):
    """流式读取完整 JSONL；超长非结构化行跳过，避免只扫描到大文件开头。"""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line_no, line in enumerate(stream, 1):
                if len(line) > 2_000_000:
                    continue
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield line_no, value
    except OSError:
        return


def _transcript_events(run_dir: Path) -> tuple[list[dict[str, Any]], Path | None]:
    """优先使用非空且可解析的轨迹，避免空 chat.jsonl 遮蔽兼容轨迹。"""
    existing: Path | None = None
    for name in ("chat.jsonl", "chat_openclaw.jsonl"):
        path = run_dir / name
        if not path.is_file():
            continue
        existing = existing or path
        events = _read_jsonl(path)
        if events:
            return events, path
    return [], existing


def _raw_session_files(run_dir: Path) -> list[Path]:
    result: list[Path] = []
    for dirname in ("astroncode_sessions", "codex_sessions"):
        root = run_dir / dirname
        if root.is_dir():
            result.extend(sorted(root.rglob("*.jsonl")))
    return result


def _tool_result_texts(events: Iterable[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for event in events:
        payload = event.get("payload") or event.get("message") or event
        if not isinstance(payload, dict):
            continue
        payload_type = str(payload.get("type") or "").lower()
        if payload_type in {"function_call_output", "tool_result"}:
            texts.append(str(payload.get("output") or payload.get("content") or ""))
        content = payload.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    texts.append(str(block.get("content") or ""))
    return texts


def _interaction_counts(events: Iterable[dict[str, Any]], usage: dict) -> tuple[int, int]:
    model_turns = 0
    tool_attempts = 0
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else None
        if payload is None and isinstance(event.get("message"), dict):
            payload = event["message"]
        if payload is None:
            payload = event
        event_type = str(event.get("type") or "").lower()
        payload_type = str(payload.get("type") or "").lower()
        role = str(payload.get("role") or "").lower()
        if role == "assistant" or payload_type in {
            "agent_message", "assistant_message", "agent_reasoning", "reasoning"
        }:
            model_turns += 1
        if event_type == "event_msg" and payload_type == "token_count":
            model_turns += 1
        if payload_type in {"function_call", "tool_call", "mcp_tool_call", "tool_use"}:
            tool_attempts += 1
        content = payload.get("content")
        if isinstance(content, list):
            tool_attempts += sum(
                1 for block in content
                if isinstance(block, dict)
                and block.get("type") in {"tool_use", "tool_call", "toolCall"}
            )
    request_count = usage.get("request_count")
    if isinstance(request_count, (int, float)) and request_count > model_turns:
        model_turns = int(request_count)
    return model_turns, tool_attempts


def _referenced_model_tail(error_text: str) -> str:
    """从图像/PDF 工具错误文本中提取被引用的模型名尾段（路径最后一节）。

    "Model does not support images: anthropic/claude-3-5-sonnet-20241022"
    → "claude-3-5-sonnet-20241022"

    "Unknown model: wildclaw/gpt-4o" → "gpt-4o"
    """
    import re
    # 两种典型格式："Model does not support images: X" 或 "Unknown model: X"
    m = re.search(r"(?:does not support images|Unknown model):\s*([^\s,;]+)", error_text)
    if not m:
        return ""
    ref = m.group(1).strip()
    # 取路径最后一段（如 anthropic/claude-xxx → claude-xxx）
    return ref.rsplit("/", 1)[-1].lower()


def _structured_tool_configuration_items(
    events: Iterable[dict[str, Any]], transcript_path: Path | None,
    subject_model: str = "",
) -> list[dict[str, Any]]:
    """结构化工具配置异常。

    `subject_model` 为被测模型（execution_status.model）。图片/PDF 工具报
    "Model does not support images: X" / "Unknown model: X" 时，若 X 就是被测
    模型自身，说明该模型本身不具备多模态能力（MaaS 纯文本模型的固有边界），
    属模型能力结果而非评测框架配错，不计入有效性失败——否则仅"显式暴露了
    图片工具"的 Harness 会被误判 FAIL，与其它 Harness 口径不一致。
    只有 X 是另一个被错配的辅助模型时，才是真正的框架配置问题。
    """
    service_hits: list[dict[str, Any]] = []
    model_hits: list[dict[str, Any]] = []
    capability_hits: list[dict[str, Any]] = []
    subject_tail = str(subject_model).rsplit("/", 1)[-1].strip().lower()
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "toolResult":
            continue
        details = message.get("details")
        if not isinstance(details, dict) or str(details.get("status") or "").lower() != "error":
            continue
        error = str(details.get("error") or "")
        evidence = {
            "file": transcript_path.name if transcript_path else "chat.jsonl",
            "tool": message.get("toolName"),
            "tool_call_id": message.get("toolCallId"),
            "error": error[:300],
        }
        if "SearXNG base URL is not configured" in error:
            service_hits.append(evidence)
        elif (
            "Model does not support images:" in error
            or ("Unknown model: wildclaw/" in error and message.get("toolName") in {"image", "pdf"})
        ):
            referenced = _referenced_model_tail(error)
            if subject_tail and referenced and referenced == subject_tail:
                # 图片/PDF 工具用的就是被测模型本身 → 模型无多模态能力，非框架配错
                capability_hits.append(evidence)
            else:
                model_hits.append(evidence)

    items: list[dict[str, Any]] = []
    if service_hits:
        items.append(_item(
            "TOOL_SERVICE_NOT_CONFIGURED",
            f"搜索工具服务未配置（{len(service_hits)} 次结构化失败）",
            stage="tool_execution", attribution="evaluation_environment",
            confidence="high", validity_impact="fail", score_reliability="unreliable",
            rerun_action="required_after_fix", evidence=service_hits[:5],
        ))
    if model_hits:
        items.append(_item(
            "TOOL_MODEL_CONFIGURATION_ERROR",
            f"图片/PDF 工具模型配置不可用（{len(model_hits)} 次结构化失败）",
            stage="tool_execution", attribution="evaluation_framework",
            confidence="high", validity_impact="fail", score_reliability="unreliable",
            rerun_action="required_after_fix", evidence=model_hits[:5],
        ))
    return items


def _item(
    rule_id: str,
    description: str,
    *,
    stage: str,
    attribution: str,
    confidence: str,
    validity_impact: str,
    score_reliability: str,
    rerun_action: str,
    evidence: list[dict[str, Any]] | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    if severity is None:
        severity = ERROR if validity_impact == "fail" else WARNING
    description = _redact(description)
    return {
        "id": rule_id,
        "severity": severity,
        "stage": stage,
        "attribution": attribution,
        "confidence": confidence,
        "validity_impact": validity_impact,
        "score_reliability": score_reliability,
        "rerun_action": rerun_action,
        "description": description,
        "evidence": _redact(evidence or []),
    }


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub(
                lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]",
                result,
            )
        return result
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _finalize(items: list[dict[str, Any]]) -> dict[str, Any]:
    has_failure = any(item.get("validity_impact") == "fail" for item in items)
    needs_review = any(item.get("validity_impact") == "review" for item in items)
    verdict = "FAIL" if has_failure else ("REVIEW" if needs_review else "PASS")
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "validity_verdict": verdict,
        "is_anomalous": bool(items),
        "has_error": has_failure,
        "has_validity_failure": has_failure,
        "has_model_or_harness_issue": any(
            item.get("attribution") in {"model", "harness"} for item in items
        ),
        "needs_review": needs_review,
        "needs_rerun": any(item.get("rerun_action") == "required_after_fix" for item in items),
        "items": items,
    }


def classify_execution_error(status: dict) -> dict[str, Any]:
    """按结构化阶段归因非超时执行错误，供异常、报告和审核共享。"""
    error = str(status.get("error") or "execution_status=error")
    stage = str(status.get("failure_stage") or status.get("stage") or "unknown")
    evidence = [{"file": "execution_status.json", "field": "failure_stage", "value": stage}]
    # Auth/quota exhaustion on the eval endpoint is an environment failure regardless of
    # stage or harness wrapping — must win over the harness "run failed (rc=N)" rule below,
    # so a zero-output 401 crash is excluded from scoring instead of counting as a real 0.0.
    if _AUTH_QUOTA_ERROR_RE.search(error):
        return _item(
            "EXECUTION_ERROR",
            f"评测端点鉴权/额度失败（基础设施），非模型能力结果：{error[:180]}",
            stage=stage, attribution="evaluation_environment", confidence="high",
            validity_impact="fail", score_reliability="unreliable",
            rerun_action="required_after_fix", evidence=evidence,
        )
    if stage in _FRAMEWORK_STAGES:
        if _ENVIRONMENT_ERROR_RE.search(error):
            return _item(
                "EXECUTION_ERROR", f"评测运行环境在 {stage} 阶段失败：{error[:180]}",
                stage=stage, attribution="evaluation_environment", confidence="high",
                validity_impact="fail", score_reliability="unreliable",
                rerun_action="required_after_fix", evidence=evidence,
            )
        return _item(
            "EXECUTION_ERROR", f"评测框架在 {stage} 阶段失败：{error[:180]}",
            stage=stage, attribution="evaluation_framework", confidence="high",
            validity_impact="fail", score_reliability="unreliable",
            rerun_action="required_after_fix", evidence=evidence,
        )
    if stage in _HARNESS_STAGES:
        return _item(
            "EXECUTION_ERROR", f"Harness 在 {stage} 阶段退出：{error[:180]}",
            stage=stage, attribution="harness", confidence="high",
            validity_impact="none", score_reliability="valid_capability_outcome",
            rerun_action="do_not_rerun", evidence=evidence,
        )
    if _HARNESS_RUN_FAILED_RE.search(error):
        return _item(
            "EXECUTION_ERROR", f"Harness 进程非零退出：{error[:180]}",
            stage="harness_process", attribution="harness", confidence="medium",
            validity_impact="none", score_reliability="valid_capability_outcome",
            rerun_action="do_not_rerun",
            evidence=[{"file": "execution_status.json", "field": "error",
                       "match": "<Harness> run failed (rc=N)"}],
        )
    return _item(
        "EXECUTION_ERROR", f"运行异常尚无法定责：{error[:180]}",
        stage=stage, attribution="undetermined", confidence="low",
        validity_impact="review", score_reliability="requires_review",
        rerun_action="review_first", evidence=evidence,
    )


def classify_report_outcome(
    status: dict,
    grading_error: str = "",
    anomaly_items: Iterable[dict[str, Any]] | None = None,
) -> str:
    """返回报告互斥状态：finished/execution_error/timeout/evaluation_anomaly。"""
    if grading_error:
        return "evaluation_anomaly"
    if any(
        item.get("validity_impact") in {"fail", "review"}
        for item in (anomaly_items or [])
    ):
        return "evaluation_anomaly"
    if bool(status.get("timed_out")):
        return "timeout"
    if status.get("error") or str(status.get("status") or "") == "error":
        item = classify_execution_error(status)
        if item.get("attribution") in {"model", "harness"}:
            return "execution_error"
        return "evaluation_anomaly"
    return "finished"


def _structured_model_errors(run_dir: Path, status: dict) -> list[dict[str, Any]]:
    """只读取模型请求的结构化失败事件，不扫描 agent.log 或工具输出。"""
    errors: list[dict[str, Any]] = []
    current_model = str(status.get("model") or "")

    runtime_path = run_dir / "runtime_events.jsonl"
    for line_no, event in _iter_jsonl(runtime_path):
        if event.get("stage") != "model_inference":
            continue
        event_model = str(event.get("model") or "")
        if not event_model:
            continue
        if (
            current_model and event_model
            and event_model.rsplit("/", 1)[-1] != current_model.rsplit("/", 1)[-1]
        ):
            continue
        event_type = str(event.get("event_type") or "").lower()
        if event_type not in {"request_failed", "request_error", "error"}:
            continue
        status_code = event.get("http_status")
        message = str(event.get("message") or event.get("error_type") or "")
        errors.append({
            "message": message,
            "http_status": status_code,
            "recovered": bool(event.get("recovered")),
            "evidence": {
                "file": "runtime_events.jsonl", "line": line_no,
                "source": event.get("source"), "provider": event.get("provider"),
                "model": event_model, "endpoint_host": event.get("endpoint_host"),
                "http_status": status_code, "recovered": bool(event.get("recovered")),
            },
        })

    for session_file in _raw_session_files(run_dir):
        for line_no, event in _iter_jsonl(session_file):
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            event_type = str(event.get("type") or "").lower()
            payload_type = str(payload.get("type") or "").lower()
            is_error_event = (
                (event_type == "event_msg" and payload_type == "error")
                or (event_type == "response_item" and payload_type == "error")
                or event_type == "error"
            )
            if not is_error_event:
                continue
            message = str(
                payload.get("message") or payload.get("error") or payload.get("text")
                or event.get("message") or event.get("error") or ""
            )
            errors.append({
                "message": message,
                "http_status": payload.get("http_status") or payload.get("status_code"),
                "recovered": False,
                "evidence": {
                    "file": str(session_file.relative_to(run_dir)),
                    "line": line_no,
                    "event_type": f"{event_type}/{payload_type}".strip("/"),
                },
            })

    db_candidates = sorted((run_dir / "opencode_data").rglob("opencode*.db")) \
        if (run_dir / "opencode_data").is_dir() else []
    if db_candidates:
        try:
            connection = sqlite3.connect(f"file:{db_candidates[0]}?mode=ro", uri=True)
            try:
                rows = connection.execute("SELECT id, data FROM message").fetchall()
            finally:
                connection.close()
            for message_id, raw_data in rows:
                try:
                    data = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    continue
                error = data.get("error")
                if not error or str(data.get("role") or "").lower() != "assistant":
                    continue
                data_model = str(data.get("modelID") or data.get("model") or "")
                if (
                    current_model and data_model
                    and data_model.rsplit("/", 1)[-1] != current_model.rsplit("/", 1)[-1]
                ):
                    continue
                message = json.dumps(error, ensure_ascii=False) if isinstance(error, dict) else str(error)
                errors.append({
                    "message": message,
                    "http_status": error.get("statusCode") if isinstance(error, dict) else None,
                    "recovered": False,
                    "evidence": {"file": str(db_candidates[0].relative_to(run_dir)),
                                 "message_id": message_id, "field": "message.data.error"},
                })
        except sqlite3.Error:
            pass

    # OpenClaw/AstronClaw emit one machine-shaped completion line for each
    # embedded model run. Parse only that exact event instead of searching
    # arbitrary gateway/tool log text for error keywords.
    gateway_path = run_dir / "gateway.log"
    try:
        gateway_lines = gateway_path.open(encoding="utf-8", errors="replace")
    except OSError:
        gateway_lines = None
    if gateway_lines is not None:
        with gateway_lines:
            for line_no, line in enumerate(gateway_lines, 1):
                marker = "[agent/embedded] embedded run agent end:"
                if marker not in line or " isError=true " not in line:
                    continue
                suffix = line.split(marker, 1)[1].strip()
                model_match = re.search(r"(?:^|\s)model=([^\s]+)", suffix)
                provider_match = re.search(r"(?:^|\s)provider=([^\s]+)", suffix)
                error_match = re.search(
                    r"(?:^|\s)error=(.*?)(?:\s+rawError=|$)", suffix
                )
                event_model = model_match.group(1) if model_match else ""
                if (
                    current_model and event_model
                    and event_model.rsplit("/", 1)[-1] != current_model.rsplit("/", 1)[-1]
                ):
                    continue
                message = (
                    error_match.group(1).strip()
                    if error_match else "model request failed"
                )
                status_match = _HTTP_STATUS_RE.search(message)
                errors.append({
                    "message": message,
                    "http_status": int(status_match.group(1)) if status_match else None,
                    "recovered": False,
                    "evidence": {
                        "file": "gateway.log",
                        "line": line_no,
                        "event_type": "embedded_run_end",
                        "provider": provider_match.group(1) if provider_match else "",
                        "model": event_model,
                        "is_error": True,
                    },
                })
    return errors


def _api_items(errors: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "policy": [], "rate": [], "server": [], "other": [],
    }
    for error in errors:
        message = str(error.get("message") or "")
        raw_code = error.get("http_status")
        try:
            code = int(raw_code) if raw_code is not None else None
        except (TypeError, ValueError):
            code = None
        if _CONTENT_POLICY_RE.search(message):
            grouped["policy"].append(error)
        elif code == 429 or _RATE_LIMIT_RE.search(message):
            grouped["rate"].append(error)
        elif (isinstance(code, int) and 500 <= code < 600) or _SERVER_ERROR_RE.search(message):
            grouped["server"].append(error)
        else:
            grouped["other"].append(error)
    result: list[dict[str, Any]] = []
    policy_hits = grouped["policy"]
    if policy_hits:
        result.append(_item(
            "MODEL_CONTENT_POLICY_REJECTION",
            f"模型内容安全策略拒答（{len(policy_hits)} 个结构化事件）",
            stage="model_inference", attribution="model", confidence="high",
            validity_impact="none", score_reliability="valid_capability_outcome",
            rerun_action="do_not_rerun",
            evidence=[hit["evidence"] for hit in policy_hits[:5]],
        ))
    for kind, rule_id, description in (
        ("rate", "MODEL_API_RATE_LIMIT", "当前被测模型推理请求出现限流"),
        ("server", "MODEL_API_SERVER_ERROR", "当前被测模型推理请求出现服务端错误"),
    ):
        hits = grouped[kind]
        if not hits:
            continue
        recovered = all(bool(hit.get("recovered")) for hit in hits)
        result.append(_item(
            rule_id,
            f"{description}（{len(hits)} 个结构化事件，recovered={str(recovered).lower()}）",
            stage="model_inference", attribution="external_service", confidence="high",
            validity_impact="review", score_reliability="requires_review",
            rerun_action="review_first",
            evidence=[hit["evidence"] for hit in hits[:5]],
        ))
    other_hits = grouped["other"]
    if other_hits:
        result.append(_item(
            "MODEL_API_ERROR",
            f"当前被测模型推理请求出现结构化错误（{len(other_hits)} 个事件）",
            stage="model_inference", attribution="external_service", confidence="high",
            validity_impact="review", score_reliability="requires_review",
            rerun_action="review_first",
            evidence=[hit["evidence"] for hit in other_hits[:5]],
        ))
    return result


def scan_run_dir(run_dir: Path) -> dict[str, Any]:
    """检测单个 run 目录，返回 anomalies v2 dict（不落盘）。"""
    run_dir = Path(run_dir)
    status = _load_json(run_dir / "execution_status.json") or {}
    usage = _load_json(run_dir / "usage.json") or {}
    score = _load_json(run_dir / "score.json")
    events, transcript_path = _transcript_events(run_dir)
    raw_sessions = [path for path in _raw_session_files(run_dir) if path.stat().st_size > 0]
    model_turns, tool_attempts = _interaction_counts(events, usage)
    items: list[dict[str, Any]] = []
    structured_model_errors = _structured_model_errors(run_dir, status)
    api_items = _api_items(structured_model_errors)

    execution_item: dict[str, Any] | None = None
    if str(status.get("status") or "") == "error":
        execution_item = classify_execution_error(status)
        items.append(execution_item)
    failure_stage = str(status.get("failure_stage") or "")
    pre_grading_failure = bool(
        execution_item
        and execution_item["attribution"] == "evaluation_framework"
        and failure_stage in {
            "created", "starting_container", "container_started", "preparing_workspace",
            "preparing_harness_input", "launching_harness", "harness_launch_failed",
        }
    )

    timed_out = bool(status.get("timed_out"))
    if timed_out:
        evidence = [
            {"file": "execution_status.json", "field": "timed_out", "value": True},
            {"file": transcript_path.name if transcript_path else "usage.json",
             "summary": f"{model_turns} model turns, {tool_attempts} tool attempts"},
        ]
        if model_turns > 0 or tool_attempts > 0:
            items.append(_item(
                "TASK_TIMED_OUT", f"{status.get('timeout_seconds')}s 内任务未完成，"
                f"已发生 {model_turns} 次模型交互和 {tool_attempts} 次工具尝试",
                stage="model_execution", attribution="model", confidence="high",
                validity_impact="none", score_reliability="valid_capability_outcome",
                rerun_action="do_not_rerun", evidence=evidence,
            ))
        else:
            items.append(_item(
                "TASK_TIMED_OUT", f"{status.get('timeout_seconds')}s 后超时且无可确认模型交互",
                stage=str(status.get("failure_stage") or "model_execution"),
                attribution="undetermined", confidence="low", validity_impact="review",
                score_reliability="requires_review", rerun_action="review_first", evidence=evidence,
            ))

    if status.get("exit_code") == 137:
        items.append(_item(
            "EXIT_CODE_OOM", "进程收到 SIGKILL（exit_code=137），仅凭退出码无法区分资源环境与被测进程失控",
            stage=str(status.get("failure_stage") or "model_execution"),
            attribution="undetermined", confidence="low", validity_impact="review",
            score_reliability="requires_review", rerun_action="review_first",
            evidence=[{"file": "execution_status.json", "field": "exit_code", "value": 137}],
        ))

    if not events and not timed_out and not pre_grading_failure:
        if raw_sessions:
            attribution, impact, reliability, action, confidence = (
                "evaluation_framework", "fail", "unreliable", "required_after_fix", "high"
            )
            description = "Harness 原始 session 存在，但标准轨迹缺失或为空"
        elif execution_item and execution_item["attribution"] == "harness":
            attribution, impact, reliability, action, confidence = (
                "harness", "none", "valid_capability_outcome", "do_not_rerun", "medium"
            )
            description = "Harness 退出且未产生可用轨迹"
        else:
            attribution, impact, reliability, action, confidence = (
                "undetermined", "review", "requires_review", "review_first", "low"
            )
            description = "未发现可用轨迹，当前无法区分 Harness 未执行与轨迹采集失败"
        items.append(_item(
            "EMPTY_TRANSCRIPT", description, stage="transcript_collection",
            attribution=attribution, confidence=confidence, validity_impact=impact,
            score_reliability=reliability, rerun_action=action,
            evidence=[{"file": transcript_path.name if transcript_path else "chat.jsonl",
                       "state": "missing_or_empty"}],
        ))
    elif 0 < len(events) < 5:
        items.append(_item(
            "SHORT_TRANSCRIPT", f"轨迹仅包含 {len(events)} 个事件",
            stage="model_execution", attribution="model", confidence="medium",
            validity_impact="none", score_reliability="valid_capability_outcome",
            rerun_action="do_not_rerun",
            evidence=[{"file": transcript_path.name if transcript_path else "chat.jsonl",
                       "event_count": len(events)}],
        ))

    elapsed = status.get("elapsed_time")
    if isinstance(elapsed, (int, float)) and elapsed < 10 and status.get("status") == "finished":
        items.append(_item(
            "QUICK_EXIT_SUSPICIOUS", f"任务在 {elapsed:.1f}s 内结束",
            stage="model_execution", attribution="model", confidence="medium",
            validity_impact="none", score_reliability="valid_capability_outcome",
            rerun_action="do_not_rerun",
            evidence=[{"file": "execution_status.json", "field": "elapsed_time", "value": elapsed}],
        ))

    request_count = usage.get("request_count", 0)
    total_tokens = usage.get("total_tokens", 0)
    if events and (request_count == 0 or total_tokens == 0) and not structured_model_errors:
        has_model_response = model_turns > 0
        items.append(_item(
            "ZERO_TOKEN_RUN", "存在模型轨迹但 usage 请求数或 token 为 0",
            stage="usage_collection",
            attribution="evaluation_framework" if has_model_response else "undetermined",
            confidence="high" if has_model_response else "low",
            validity_impact="fail" if has_model_response else "review",
            score_reliability="unreliable" if has_model_response else "requires_review",
            rerun_action="required_after_fix" if has_model_response else "review_first",
            evidence=[{"file": "usage.json", "request_count": request_count,
                       "total_tokens": total_tokens, "observed_model_turns": model_turns}],
        ))

    if score is None and not pre_grading_failure:
        if execution_item and execution_item["attribution"] in {"model", "harness"}:
            attribution, impact, reliability, action = (
                execution_item["attribution"], "none", "valid_capability_outcome", "do_not_rerun"
            )
        elif timed_out and (model_turns > 0 or tool_attempts > 0):
            attribution, impact, reliability, action = (
                "model", "none", "valid_capability_outcome", "do_not_rerun"
            )
        elif api_items:
            attribution, impact, reliability, action = (
                "external_service", "review", "requires_review", "review_first"
            )
        else:
            attribution, impact, reliability, action = (
                "evaluation_framework", "fail", "unreliable", "required_after_fix"
            )
        items.append(_item(
            "SCORE_MISSING", "score.json 缺失或不可解析",
            stage="grading", attribution=attribution, confidence="medium",
            validity_impact=impact, score_reliability=reliability, rerun_action=action,
            evidence=[{"file": "score.json", "state": "missing_or_invalid"}],
        ))
    else:
        grading_error_field = ""
        grading_error = ""
        if score.get("error"):
            grading_error_field = "error"
            grading_error = str(score["error"])
        elif score.get("llm_error"):
            grading_error_field = "llm_error"
            grading_error = str(score["llm_error"])
        else:
            grading_metadata = score.get("_grading")
            judge_notes = (
                grading_metadata.get("llm_notes")
                if isinstance(grading_metadata, dict)
                else ""
            )
            if isinstance(judge_notes, str) and _JUDGE_OUTPUT_ERROR_RE.search(judge_notes):
                grading_error_field = "_grading.llm_notes"
                grading_error = judge_notes
        grading_timed_out = bool(_GRADING_TIMEOUT_RE.search(grading_error))
        if not pre_grading_failure and (
            grading_error_field in {"llm_error", "_grading.llm_notes"}
            or grading_timed_out
            or "Grading failed" in grading_error
            or "Traceback" in grading_error
        ):
            description = (
                f"判分进程超时：{grading_error[:180]}"
                if grading_timed_out
                else f"判分失败：{grading_error[:180]}"
            )
            items.append(_item(
                "GRADING_SCRIPT_ERROR", description,
                stage="grading", attribution="evaluation_framework", confidence="high",
                validity_impact="fail", score_reliability="unreliable",
                rerun_action="required_after_fix",
                evidence=[{"file": "score.json", "field": grading_error_field}],
            ))

    tool_results = _tool_result_texts(events)
    rejected = [text for text in tool_results
                if any(keyword in text.lower() for keyword in _TOOL_REJECT_KEYWORDS)]
    if len(tool_results) >= 3 and len(rejected) / len(tool_results) >= 0.8:
        items.append(_item(
            "TOOL_CALLS_ALL_REJECTED",
            f"{len(rejected)}/{len(tool_results)} 次工具调用因 unsupported/unknown tool 被拒绝",
            stage="tool_execution", attribution="model", confidence="medium",
            validity_impact="none", score_reliability="valid_capability_outcome",
            rerun_action="do_not_rerun",
            evidence=[{"file": transcript_path.name if transcript_path else "chat.jsonl",
                       "rejected": len(rejected), "total": len(tool_results)}],
        ))

    items.extend(_structured_tool_configuration_items(
        events, transcript_path, subject_model=status.get("model", "")
    ))
    items.extend(api_items)
    return _finalize(items)


def iter_run_dirs(output_root: Path):
    """遍历 output_root 下所有含 execution_status.json 的 run 目录。"""
    for status_file in Path(output_root).glob("*/*/*/execution_status.json"):
        yield status_file.parent


def scan_batch(output_root: Path) -> dict[str, Any]:
    """整批扫描：逐 run 规则 + 跨 run 轨迹重复规则。"""
    output_root = Path(output_root)
    runs: dict[str, dict[str, Any]] = {}
    digests: dict[str, list[str]] = {}
    for run_dir in iter_run_dirs(output_root):
        rel = str(run_dir.relative_to(output_root))
        runs[rel] = scan_run_dir(run_dir)
        for name in ("chat_openclaw.jsonl", "chat.jsonl"):
            path = run_dir / name
            if path.exists() and path.stat().st_size > 0:
                digest = hashlib.md5(path.read_bytes()).hexdigest()
                digests.setdefault(digest, []).append(rel)
                break
    for digest, rels in digests.items():
        tasks = {rel.split("/")[1] for rel in rels}
        if len(tasks) <= 1:
            continue
        for rel in rels:
            duplicate = _item(
                "DUPLICATE_TRANSCRIPT",
                f"轨迹 md5 {digest[:8]} 被不同任务共享：{sorted(tasks)}",
                stage="artifact_collection", attribution="evaluation_framework",
                confidence="high", validity_impact="fail", score_reliability="unreliable",
                rerun_action="required_after_fix",
                evidence=[{"file": "chat*.jsonl", "md5": digest,
                           "tasks": sorted(tasks)}],
            )
            runs[rel] = _finalize([*runs[rel]["items"], duplicate])
    anomalous = {key: value for key, value in runs.items() if value["is_anomalous"]}
    validity_failures = sum(1 for value in runs.values() if value["has_validity_failure"])
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "output_root": str(output_root),
        "total_runs": len(runs),
        "anomalous_runs": len(anomalous),
        "error_runs": validity_failures,
        "validity_failure_runs": validity_failures,
        "review_runs": sum(1 for value in runs.values() if value["needs_review"]),
        "model_or_harness_issue_runs": sum(
            1 for value in runs.values() if value["has_model_or_harness_issue"]
        ),
        "rerun_runs": sum(1 for value in runs.values() if value["needs_rerun"]),
        "runs": anomalous,
    }
