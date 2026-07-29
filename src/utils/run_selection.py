"""评测任务多 run 的统一选择规则。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable


RUN_METADATA_SCHEMA_VERSION = 1


def load_run_metadata(run_dir: Path) -> dict:
    try:
        value = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_rerun_metadata(
    run_dir: Path,
    *,
    supersedes_run: str,
    trigger: str,
    task_id: str,
    model: str,
) -> None:
    value = {
        "schema_version": RUN_METADATA_SCHEMA_VERSION,
        "purpose": "reliability_rerun",
        "supersedes_run": Path(supersedes_run).name,
        "trigger": trigger,
        "task_id": task_id,
        "model": model,
    }
    (run_dir / "run_metadata.json").write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _has_material_validity_issue(anomaly: dict) -> bool:
    return any(
        item.get("validity_impact") in {"fail", "review"}
        for item in anomaly.get("items", [])
    )


def select_effective_run_dirs(
    run_dirs: Iterable[Path],
    anomaly_loader: Callable[[Path], dict] | None = None,
) -> list[Path]:
    """返回参与当前结果统计的 run。

    显式被可靠性重跑替换的 run 永久排除。对尚无 run_metadata.json 的旧结果，
    若较早 run 存在 fail/review 且后面已有 run，则把它视作历史异常重跑。
    模型/Harness 能力结果的 validity_impact=none，不会被该兼容规则剔除。
    """
    ordered = sorted(Path(path) for path in run_dirs if Path(path).is_dir())
    if not ordered:
        return []

    superseded_names = {
        Path(str(metadata.get("supersedes_run"))).name
        for run_dir in ordered
        if (metadata := load_run_metadata(run_dir)).get("supersedes_run")
    }
    selected: list[Path] = []
    for index, run_dir in enumerate(ordered):
        if run_dir.name in superseded_names:
            continue
        if anomaly_loader is not None and index < len(ordered) - 1:
            try:
                if _has_material_validity_issue(anomaly_loader(run_dir)):
                    continue
            except (OSError, ValueError, TypeError):
                pass
        selected.append(run_dir)

    # 元数据异常时仍保证任务有一个权威 run，避免整题静默消失。
    return selected or [ordered[-1]]
