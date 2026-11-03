#!/usr/bin/env python3
"""Execute one trusted General E2E rule inside a managed worker process."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any
import math


REQUEST_SCHEMA = "wildclawbench.general-e2e-rule-worker-request/v1"
RESULT_SCHEMA = "wildclawbench.general-e2e-rule-worker-result/v1"


def adapt_rule_result(raw: dict[str, Any], policy: object) -> dict[str, Any]:
    """Adapt an explicitly frozen imported contract; keep the original in raw_result."""
    if policy is None:
        return raw
    if not isinstance(policy, dict) or policy.get("schema_version") != "wildclawbench.general-e2e-numeric-diagnostics/v1":
        raise ValueError("unsupported rule result adapter")
    diagnostic_keys = policy.get("diagnostic_keys")
    if not isinstance(diagnostic_keys, list) or any(key not in {"diagnostics", "诊断"} for key in diagnostic_keys):
        raise ValueError("invalid diagnostic key policy")
    result = dict(raw)
    for key in diagnostic_keys:
        if key in result:
            if not isinstance(result[key], dict):
                raise ValueError(f"diagnostics must be an object: {key}")
            del result[key]
    text_keys = policy.get("diagnostic_text_keys", [])
    if not isinstance(text_keys, list) or len(text_keys) != len(set(text_keys)) or any(key != "evidence_status" for key in text_keys):
        raise ValueError("invalid diagnostic text key policy")
    for key in text_keys:
        if key in result:
            if not isinstance(result[key], str):
                raise ValueError(f"diagnostic text must be a string: {key}")
            del result[key]
    list_keys=policy.get('diagnostic_list_keys',[])
    if not isinstance(list_keys,list) or len(list_keys)!=len(set(list_keys)) or any(k!='errors' for k in list_keys):
        raise ValueError('invalid diagnostic list key policy')
    for key in list_keys:
        if key in result:
            value=result[key]
            if not isinstance(value,list) or any(not isinstance(item,str) for item in value):
                raise ValueError('diagnostic errors must be a string list')
            if any(item.startswith('证据提取预算超限:') for item in value):
                raise ValueError('EVALUATOR_EVIDENCE_LIMIT: complete original evidence is required before scoring')
            del result[key]
    nullable_text_keys=policy.get('diagnostic_nullable_text_keys',[])
    if (not isinstance(nullable_text_keys,list) or len(nullable_text_keys)!=len(set(nullable_text_keys))
            or any(k!='candidate_read_error' for k in nullable_text_keys)):
        raise ValueError('invalid nullable diagnostic text policy')
    for key in nullable_text_keys:
        if key in result:
            if result[key] is not None and not isinstance(result[key],str):raise ValueError('nullable diagnostic must be text or null')
            del result[key]
    policy_key=policy.get('final_total_policy_object_key')
    if policy_key is not None:
        if policy_key!='_score_policy' or policy_key not in result:raise ValueError('invalid final-total policy object key')
        import importlib.util
        spec=importlib.util.spec_from_file_location('_managed_work_order_final_policy',Path(__file__).with_name('work_order_final_policy.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.validate_policy(result[policy_key])
        del result[policy_key]
    details_key=policy.get('domain_details_object_key')
    if details_key is not None:
        if details_key!='details' or details_key not in result:raise ValueError('invalid domain details object key')
        import importlib.util
        spec=importlib.util.spec_from_file_location('_managed_domain_details',Path(__file__).with_name('domain_details_diagnostics.py'))
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module);module.validate_details(result[details_key])
        del result[details_key]
    if "overall_score" not in result:
        if policy.get("evidence_only") is True and not result:
            # Neutral transport placeholder with a frozen zero scoring weight.
            result["overall_score"] = 0.0
        elif policy.get("default_overall") == "mean" and result:
            values = list(result.values())
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
                raise ValueError("mean aggregation requires numeric checkpoints in [0,1]")
            result["overall_score"] = sum(values) / len(values)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("worker request must be a JSON object")
    return value


def _validate_transcript(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("transcript must be an array")
    events: list[dict[str, Any]] = []
    for index, event in enumerate(value):
        if not isinstance(event, dict):
            raise ValueError(f"transcript event {index} must be a JSON object")
        events.append(event)
    return events


def _write_result(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(data)


def execute(request_path: Path, result_path: Path) -> int:
    try:
        request = _read_json(request_path)
        if request.get("schema_version") != REQUEST_SCHEMA:
            raise ValueError("worker request schema mismatch")
        source = request.get("automated_checks")
        workspace_text = request.get("workspace_path")
        transcript_value = request.get("transcript")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("automated_checks must be a non-empty string")
        if not isinstance(workspace_text, str) or not workspace_text:
            raise ValueError("workspace_path must be a non-empty string")

        workspace = Path(workspace_text).resolve(strict=True)
        if not workspace.is_dir() or workspace.is_symlink():
            raise ValueError("workspace_path must be a regular directory")
        transcript = _validate_transcript(transcript_value)

        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
            "__name__": "__general_e2e_rule__",
        }
        review=request.get('rule_review')
        if review is not None:
            if (not isinstance(review,dict) or review.get('schema_version')!='wildclawbench.general-e2e-rule-review-worker/v1'
                    or review.get('profile') not in {'hr-fields-and-sources-semantic-review/v1',
                        'office001-numeric-extraction-semantic-review/v1','escrow-status-equivalence-review/v1','escrow-status-equivalence-review/v2','escrow-status-equivalence-review/v3','warranty-recovery-reason-semantic-review/v1'}
                    or review.get('mode') not in {'discover','apply'}
                    or not isinstance(review.get('decisions'),dict)
                    or any(not isinstance(k,str) or not isinstance(v,bool) for k,v in review['decisions'].items())):
                raise ValueError('Invalid rule review configuration')
            namespace['_GENERAL_E2E_RULE_REVIEW']=dict(review)
        exec(compile(source, "<general-e2e-automated-checks>", "exec"), namespace)
        grade = namespace.get("grade")
        if not callable(grade):
            raise ValueError("automated_checks did not define callable grade()")
        raw = grade(transcript=transcript, workspace_path=str(workspace))
        if not isinstance(raw, dict):
            raise ValueError("grade() must return a JSON object")
        json.dumps(raw, ensure_ascii=False, allow_nan=False)
        discovery=review is not None and review['mode']=='discover'
        adapted = {} if discovery else adapt_rule_result(raw, request.get("rule_result_adapter"))
        observed=namespace.get('_GENERAL_E2E_RULE_REVIEW',{})
        _write_result(
            result_path,
            {
                "schema_version": RESULT_SCHEMA,
                "ok": True,
                "result": {} if discovery else adapted,
                **({"raw_result": raw} if request.get("rule_result_adapter") is not None and not discovery else {}),
                **({'rule_review':{'profile':review['profile'],'mode':review['mode'],
                    'contexts':observed.get('observations',{}),'applied':observed.get('applied',[]),
                    'provisional_scores_suppressed':discovery}} if review is not None else {}),
                "error": None,
                "worker": {
                    "pid": os.getpid(),
                    "python": sys.version.split()[0],
                },
            },
        )
        return 0
    except BaseException as exc:  # Worker must serialize rule failures.
        try:
            _write_result(
                result_path,
                {
                    "schema_version": RESULT_SCHEMA,
                    "ok": False,
                    "result": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc) or type(exc).__name__,
                        "traceback": traceback.format_exc(limit=20),
                    },
                    "worker": {
                        "pid": os.getpid(),
                        "python": sys.version.split()[0],
                    },
                },
            )
        except BaseException:
            traceback.print_exc(file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args(argv)
    return execute(args.request, args.result)


if __name__ == "__main__":
    raise SystemExit(main())
