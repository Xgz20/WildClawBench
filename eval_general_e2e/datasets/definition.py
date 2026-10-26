"""Source-side dataset definitions; published bundles keep the v1 protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class DatasetDefinition:
    dataset_id: str
    created_at: str
    include_tags: tuple[str, ...]
    exclude_tags: tuple[str, ...]
    expected_task_count: int
    expected_category_counts: Mapping[str, int]
    expected_grading_type_counts: Mapping[str, int]
    expected_difficulty_counts: Mapping[str, int]
    expected_timeout_counts: Mapping[str, int]
    task_root: str = "tasks/extension"
    workspace_root: str = "workspace/extension"
    registry_path: str = "tasks/extension/task_sources.yaml"
    capability_map_path: str = "tools/report/data/checkpoint_capability_map7.yaml"
    manifest_path: str = "eval_general_e2e/datasets/manifests/general-custom60-v1.json"
    revision_scope: tuple[str, ...] = ("tasks/extension", "workspace/extension")
    task_ids: tuple[str, ...] = ()
    task_id_prefix: str = ""
    category_labels: Mapping[str, str] = field(default_factory=dict)
    constraints: Mapping[str, Any] = field(default_factory=dict)


DEFAULT_DEFINITION = DatasetDefinition(
    dataset_id="general-custom60-v1",
    created_at="2026-09-17T00:00:00+08:00",
    include_tags=("custom",),
    exclude_tags=("ppt", "web-site", "web-site-gen", "invalid"),
    expected_task_count=60,
    expected_category_counts={
        "01_Productivity_Flow": 10,
        "02_Code_Intelligence": 10,
        "03_Social_Interaction": 10,
        "04_Search_Retrieval": 10,
        "05_Creative_Synthesis": 10,
        "06_Safety_Alignment": 10,
    },
    expected_grading_type_counts={"automated": 19, "hybrid": 35, "llm_judge": 6},
    expected_difficulty_counts={"L1": 15, "L2": 17, "L3": 18, "L4": 10},
    expected_timeout_counts={"300": 32, "600": 19, "900": 9},
)
