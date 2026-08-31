"""评测报告与跨单元分析的工作区路径约定。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROUND_DIR_RE = re.compile(r"^round\d+(?:[-_].*)?$", re.IGNORECASE)


def safe_component(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._@-]+", "_", value.strip())
    return normalized.strip("._-") or "comparison"


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def round_root_from_unit_dir(unit_dir: str | Path) -> Path:
    path = Path(unit_dir).expanduser().resolve()
    if path.parent.parent.name == path.name:
        return path.parents[2]
    return path.parents[1]


def build_cross_eval_comparison_id(
    *,
    axis: str,
    fixed_model: str | None,
    fixed_harness: str | None,
    models: Iterable[str] | None,
    harnesses: Iterable[str] | None,
    target_model: str | None,
    target_harness: str | None,
    timestamp: str | None = None,
) -> str:
    if axis == "model":
        candidates = list(models or [])
        target = target_model or (candidates[0] if candidates else "target-model")
        references = [item for item in candidates if item != target]
        fixed = fixed_harness or "fixed-harness"
    else:
        candidates = list(harnesses or [])
        target = target_harness or (candidates[0] if candidates else "target-harness")
        references = [item for item in candidates if item != target]
        fixed = fixed_model or "fixed-model"
    reference_label = "_".join(references) if references else "references"
    return safe_component(
        f"{axis}_{target}_vs_{reference_label}_on_{fixed}_{timestamp or timestamp_now()}"
    )


def find_source_map(result_root: Path, explicit: str | Path | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"SOURCE_MAP 不存在：{path}")
        return path
    for candidate in (result_root / "SOURCE_MAP.tsv", result_root.parent / "SOURCE_MAP.tsv"):
        if candidate.is_file():
            return candidate.resolve()
    return None


def source_map_round_roots(source_map: Path) -> list[Path]:
    roots: set[Path] = set()
    for raw_line in source_map.read_text(encoding="utf-8").splitlines():
        source = raw_line.split("\t", 1)[0].strip()
        if not source:
            continue
        path = Path(source).expanduser().resolve()
        for candidate in (path, *path.parents):
            if ROUND_DIR_RE.match(candidate.name):
                roots.add(candidate)
                break
    return sorted(roots)


def infer_cross_round_reports_root(source_map: Path) -> Path:
    round_roots = source_map_round_roots(source_map)
    if len(round_roots) < 2:
        raise ValueError(
            "SOURCE_MAP 未包含至少两个 round，无法推断跨 round 报告目录；"
            "请检查来源映射或显式传 --reports-root"
        )
    parents = {root.parent for root in round_roots}
    if len(parents) != 1:
        raise ValueError("SOURCE_MAP 中的 round 不在同一父目录，请显式传 --reports-root")
    return next(iter(parents)) / "reports"


def resolve_cross_eval_workspace(
    *,
    result_root: str | Path,
    comparison_scope: str,
    comparison_id: str,
    workspace_dir: str | Path | None = None,
    reports_root: str | Path | None = None,
    source_map: str | Path | None = None,
) -> tuple[Path, Path | None]:
    root = Path(result_root).expanduser().resolve()
    detected_source_map = find_source_map(root, source_map)
    if comparison_scope == "same-round":
        if detected_source_map and len(source_map_round_roots(detected_source_map)) >= 2:
            raise ValueError(
                "结果目录包含跨 round SOURCE_MAP；请使用 --comparison-scope cross-round"
            )
        base = root / "report-workspace" / "cross-eval"
    elif comparison_scope == "cross-round":
        if detected_source_map is None:
            raise ValueError("跨 round 对比必须提供可审计的 SOURCE_MAP.tsv")
        report_root = (
            Path(reports_root).expanduser().resolve()
            if reports_root else infer_cross_round_reports_root(detected_source_map)
        )
        base = report_root / "cross-round" / "cross-eval"
    else:
        raise ValueError(f"未知 comparison_scope：{comparison_scope}")
    workspace = (
        Path(workspace_dir).expanduser().resolve()
        if workspace_dir else base / safe_component(comparison_id)
    )
    return workspace, detected_source_map


def resolve_cross_round_trend_build_dir(
    round_roots: Iterable[Path],
    *,
    unit: str,
    report_id: str | None = None,
    timestamp: str | None = None,
) -> Path:
    roots = [Path(root).expanduser().resolve() for root in round_roots]
    parents = {root.parent for root in roots}
    if len(parents) != 1:
        raise ValueError("跨轮目录不在同一父目录，请显式传 --output-dir")
    round_scope = "_".join(root.name for root in roots)
    identifier = safe_component(report_id or f"{unit}__{round_scope}")
    return (
        next(iter(parents))
        / "reports"
        / "cross-round"
        / "trend"
        / identifier
        / "builds"
        / (timestamp or timestamp_now())
    )
