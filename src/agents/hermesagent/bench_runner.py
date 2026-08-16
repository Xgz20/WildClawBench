from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BENCH_CONFIG_PATH = "/tmp/hermes_bench_config.json"
BENCH_RESULT_PATH = "/tmp/hermes_bench_result.json"
HERMES_INSTALL_DIR = "/opt/hermes"


def main() -> int:
    sys.path.insert(0, HERMES_INSTALL_DIR)
    os.chdir(HERMES_INSTALL_DIR)

    from run_agent import AIAgent  # imported after install dir is added to sys.path

    data = json.loads(Path(BENCH_CONFIG_PATH).read_text(encoding="utf-8"))
    cfg = data["config"]
    prompt = data["prompt"]

    agent = AIAgent(
        model=cfg["model"],
        api_key=cfg.get("api_key") or None,
        base_url=cfg.get("base_url", ""),
        max_iterations=cfg.get("max_iterations", 90),
        max_tokens=cfg.get("max_tokens"),
        save_trajectories=True,
        verbose_logging=True,
        reasoning_config=cfg.get("reasoning_config"),
    )
    result = agent.run_conversation(prompt)
    bench_result = {
        "completed": bool(result.get("completed")),
        "partial": bool(result.get("partial")),
        "error": str(result["error"]) if result.get("error") is not None else None,
        "api_calls": int(result.get("api_calls") or 0),
    }
    Path(BENCH_RESULT_PATH).write_text(
        json.dumps(bench_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Completed:", result.get("completed"))
    print("API calls:", result.get("api_calls"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
