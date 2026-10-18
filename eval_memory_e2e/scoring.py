"""Private checkpoint review admission, evidence binding and reproducible scores."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from . import CONTRACT, METRICS
from .batch import episode, load_batch, operation_id
from .io import MemoryEvaluationError, append, archive, digest, events, lock, read_json, require, verify_artifact
from .runner import _receipts, next_action


def review_template(root, episode_id):
    manifest = load_batch(root)
    item = episode(manifest, episode_id)
    if manifest["mode"] == "native":
        policy = manifest["profiles"][item["harness"]].get("memory_protocol", {})
        require(policy.get("formal_scoring_allowed") is True, "MEMORY_CONDITION_NOT_ADMITTED",
                "This batch validates immediate automation only; memory-formation conditions are not admitted for capability scoring")
    require(next_action(root, episode_id)["status"] == "COMPLETED", "EXECUTION_INCOMPLETE", episode_id)
    receipts = _receipts(root, episode_id)
    case = read_json(Path(root) / "private/scenarios.json")[item["private_key"]]
    checks = []
    planned_steps = {s['id'] for s in read_json(Path(root) / item['plan_path'])['steps']}
    for check in case["checkpoints"]:
        if check['step_id'] not in planned_steps:
            continue
        receipt = receipts[operation_id(manifest, episode_id, check["step_id"])]
        checks.append({**check, "direction": METRICS[check["metric"]], "value": None,
                       "reason": "", "evidence": [],
                       "available_evidence": receipt["artifacts"]})
    return {"contract": CONTRACT, "mode": manifest["mode"], "episode_id": episode_id,
            "manifest_sha256": digest(manifest), "judge": manifest["judge"],
            "judge_context_id": None, "checkpoints": checks}


def validate_review(root, review):
    manifest = load_batch(root)
    require(isinstance(review, dict) and review.get("contract") == CONTRACT
            and review.get("mode") == manifest["mode"] and review.get("manifest_sha256") == digest(manifest),
            "REVIEW_BINDING", "Review must bind to the exact batch, mode and manifest")
    item = episode(manifest, review.get("episode_id"))
    require(review.get("judge") == manifest["judge"] and isinstance(manifest["judge"].get("model"), str)
            and manifest["judge"]["model"].strip(), "JUDGE_NOT_FROZEN", "Freeze the same explicit judge for all units")
    require(isinstance(review.get("judge_context_id"), str) and review["judge_context_id"].strip(),
            "JUDGE_IDENTITY", "Independent scoring context ID is required")
    template = review_template(root, item["id"])
    expected = {check["id"]: check for check in template["checkpoints"]}
    checks = review.get("checkpoints", [])
    require(isinstance(checks, list) and len(checks) == len(expected)
            and {check.get("id") for check in checks} == set(expected), "CHECKPOINT_SCOPE", "Missing or duplicate checkpoints")
    normalized = []
    receipts = _receipts(root, item["id"])
    native_ids = {value for receipt in receipts.values()
                  for value in receipt.get("native", {}).values() if isinstance(value, str)}
    require(review["judge_context_id"] not in native_ids, "JUDGE_CONTEXT_OVERLAP", "Judge must not be the candidate session")
    for check in checks:
        spec = expected[check["id"]]
        require(type(check.get("value")) in {int, float} and check["value"] in (0, 1),
                "CHECKPOINT_VALUE", "Binary observed event/criterion value required")
        require(isinstance(check.get("reason"), str) and check["reason"].strip(), "CHECKPOINT_REASON", check["id"])
        citations = check.get("evidence")
        require(isinstance(citations, list) and citations, "CHECKPOINT_EVIDENCE", check["id"])
        receipt = receipts[operation_id(manifest, item["id"], spec["step_id"])]
        for citation in citations:
            require(citation.get("step_id") == spec["step_id"]
                    and citation.get("artifact") in {"final_response", "trace", "binding_evidence"},
                    "CITATION_SCOPE", check["id"])
            reference = receipt["artifacts"][citation["artifact"]]
            require(citation.get("sha256") == reference["sha256"], "CITATION_HASH", check["id"])
            text = verify_artifact(root, reference).decode("utf-8")
            quote = citation.get("quote")
            require(isinstance(quote, str) and quote.strip() and quote in text,
                    "CITATION_NOT_FOUND", check["id"])
        value = float(check["value"])
        normalized.append({"id": spec["id"], "step_id": spec["step_id"], "metric": spec["metric"],
                           "value": value, "quality": value if METRICS[spec["metric"]] == "higher" else 1 - value,
                           "required": spec["required"], "reason": check["reason"], "evidence": citations})
    return {"contract": CONTRACT, "mode": manifest["mode"], "episode_id": item["id"],
            "result": "valid", "score": sum(check["quality"] for check in normalized) / len(normalized),
            "success": all(check["quality"] == 1 for check in normalized if check["required"]),
            "judge": manifest["judge"], "judge_context_id": review["judge_context_id"], "checkpoints": normalized}


def import_review(root, review_path):
    with lock(root):
        manifest = load_batch(root)
        reference = archive(root, review_path)
        attempt = "score-" + uuid4().hex
        review = None
        try:
            review = read_json(review_path)
            score = validate_review(root, review)
            require(not any(event["kind"] == "SCORE" and event["episode_id"] == score["episode_id"]
                            for event in events(root)), "SCORE_EXISTS", "Keep the original score; do not choose the best retry")
        except MemoryEvaluationError as exc:
            episode_id = review.get("episode_id") if isinstance(review, dict) else None
            if episode_id not in {item["id"] for item in manifest["episodes"]}:
                episode_id = None
            append(root, "SCORING_ERROR", episode_id, {"scoring_attempt_id": attempt,
                                                       "review_artifact": reference, "error_code": exc.code})
            raise
        score["review_artifact"] = reference
        score["scoring_attempt_id"] = attempt
        append(root, "SCORE", score["episode_id"], score)
        return score
