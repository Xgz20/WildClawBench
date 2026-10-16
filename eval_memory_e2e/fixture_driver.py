"""Protocol fixture, explicitly incapable of evaluating any real Harness.

It produces deliberately non-answering synthetic responses and never connects
to a desktop client. Rubrics and gold answers are not passed to this process.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .io import decode, digest, encoded, publish, read_json


def respond(request):
    if request.get("mode") != "fixture":
        raise ValueError("Fixture Driver refuses native experiments")
    root = Path(request["workspace"]).parents[1] / ".fixture-driver"
    root.mkdir(parents=True, exist_ok=True)
    result_file = root / (request["operation_id"] + ".json")
    if request["transport_action"] == "observe":
        if not result_file.exists():
            raise ValueError("Dispatch outcome unknown; fixture will not redispatch")
        return read_json(result_file)
    if result_file.exists():
        raise ValueError("Duplicate dispatch rejected")
    base = {key: request[key] for key in ("contract", "mode", "experiment_id", "execution_attempt_id", "operation_id", "episode_id",
                                          "profile_id", "namespace", "step_id", "prompt_sha256")}
    token = digest(request)[:16]
    raw = root / (token + ".binding.json")
    publish(raw, {"fixture_only": True, "request": request})
    base.update(status="completed", actual_config={"app_version": "fixture-v1", "model_display": "fixture-no-model",
                                                    "permissions": "fixture-only", "underlying_model": None,
                                                    "account_fingerprint": "fixture-only-account"},
                binding_evidence=str(raw), background_settled=True)
    if request["action"] == "prepare_namespace":
        base["admission"] = {"test_scope_only": True, "precondition_verified": True,
                             "account_policy": "current_signed_in_account", "isolation": "shared_account_cold_first",
                             "capabilities": request["required_capabilities"]}
    else:
        previous = request["previous_native"]
        session_id = previous["session_id"] if previous and request["session_action"] == "continue" else "fixture-session-" + token
        base["native"] = {"session_id": session_id, "turn_id": "fixture-turn-" + token, "cwd": request["workspace"]}
        response, trace = root / (token + ".response.txt"), root / (token + ".trace.jsonl")
        publish(response, "离线协议模拟响应；未调用任何 Harness 或模型，不能作为能力成绩。\n".encode())
        publish(trace, {"fixture_only": True, "prompt_sha256": request["prompt_sha256"], "native": base["native"]})
        base.update(final_response=str(response), trace=str(trace))
        if request["session_action"] == "restart_new":
            restart = root / (token + ".restart.json")
            publish(restart, {"fixture_only": True, "before": "fixture-1", "after": "fixture-2"})
            base["restart_evidence"] = str(restart)
    publish(result_file, base)
    return base


def main():
    request = decode(sys.stdin.buffer.read())
    sys.stdout.buffer.write(encoded(respond(request)))


if __name__ == "__main__":
    main()
