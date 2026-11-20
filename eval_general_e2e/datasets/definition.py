"""Unified source definitions for built-in products and registered families.

Definitions have no dependency on catalog or bundle construction, so both entry
points share the same immutable type without importing each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from typing import Any, Mapping, Optional


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
    task_glob: str = "*/*_task_*.md"
    category_directories: tuple[tuple[str, str], ...] = ()
    source_revision: Optional[str] = None
    frozen_source_index: Optional[str] = None
    task_ids: tuple[str, ...] = ()
    current_source_paths: tuple[str, ...] = ()
    registry_path: str = "tasks/extension/task_sources.yaml"
    capability_map_path: str = "tools/report/data/checkpoint_capability_map7.yaml"
    manifest_path: str = "eval_general_e2e/datasets/manifests/general-custom60-v1.json"
    revision_scope: tuple[str, ...] = ("tasks/extension", "workspace/extension")
    category_directory_task_ids: bool = False
    task_id_prefix: str = ""
    legacy_task_id_prefixes: tuple[str, ...] = ()
    series_id: str = ""
    category_labels: Mapping[str, str] = field(default_factory=dict)
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def category_directory(self, category: str) -> str:
        return next((directory for directory, key in self.category_directories if key == category), category)

    def task_id_stems(self, category: str) -> tuple[str, ...]:
        if self.category_directory_task_ids:
            return (self.category_directory(category),)
        return tuple(prefix + category for prefix in (self.task_id_prefix, *self.legacy_task_id_prefixes))


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
    expected_grading_type_counts={
        "automated": 19,
        "hybrid": 35,
        "llm_judge": 6,
    },
    expected_difficulty_counts={"L1": 15, "L2": 17, "L3": 18, "L4": 10},
    expected_timeout_counts={"300": 32, "600": 19, "900": 9},
)

GENERAL116_DEFINITION = DatasetDefinition(
    dataset_id="general-custom116-v1",
    created_at="2026-10-29T00:00:00+08:00",
    include_tags=(),
    exclude_tags=(),
    expected_task_count=116,
    expected_category_counts={
        "01_Information_Search_Organization": 20, "02_Office": 30, "data-analysis": 66,
    },
    expected_grading_type_counts={"hybrid": 115, "llm_judge": 1},
    expected_difficulty_counts={"L1": 2, "L2": 6, "L3": 42, "L4": 66},
    expected_timeout_counts={"1800": 18, "2400": 3, "3600": 24, "5400": 2, "7200": 69},
    task_root="tasks/general_e2e",
    workspace_root="workspace/general_e2e",
    capability_map_path="tools/report/data/checkpoint_capability_map5.yaml",
    task_glob="**/*_task_*.md",
    source_revision="9bee3a1260676446880ed125f25b1026d1cca9ce",
    frozen_source_index="eval_general_e2e/datasets/source-snapshots/general-custom116-v1/index.json",
    category_directories=(
        ("01_Information_Search_Organization", "01_Information_Search_Organization"),
        ("02_Office", "02_Office"),
        ("03_Data_Analysis_task", "data-analysis"),
    ),
)
_GENERAL70 = json.loads((Path(__file__).parent / "definitions/general-custom70-v2.json").read_text(encoding="utf-8"))
_GENERAL70_STATS = _GENERAL70["expected_statistics"]
GENERAL70_V2_DEFINITION = replace(
    GENERAL116_DEFINITION, dataset_id="general-custom70-v2",
    created_at=_GENERAL70["created_at"], source_revision="c72afc7a892725373010f38519d7340e8cd34c9e",
    frozen_source_index="eval_general_e2e/datasets/source-snapshots/general-custom70-v2/index.json",
    task_ids=tuple(_GENERAL70["task_ids"]), expected_task_count=70,
    expected_category_counts=_GENERAL70_STATS["category_counts"],
    expected_grading_type_counts=_GENERAL70_STATS["grading_type_counts"],
    expected_difficulty_counts=_GENERAL70_STATS["difficulty_counts"],
    expected_timeout_counts=_GENERAL70_STATS["timeout_counts"],
)
_GENERAL70_V3 = json.loads((Path(__file__).parent / "definitions/general-custom70-v3.json").read_text(encoding="utf-8"))
GENERAL70_V3_DEFINITION = replace(
    GENERAL70_V2_DEFINITION, dataset_id="general-custom70-v3",
    created_at=_GENERAL70_V3["created_at"], source_revision=_GENERAL70_V3.get('source_revision'),
    frozen_source_index="eval_general_e2e/datasets/source-snapshots/general-custom70-v3/index.json",
)
_GENERAL70_V4 = json.loads((Path(__file__).parent / "definitions/general-custom70-v4.json").read_text(encoding="utf-8"))
GENERAL70_V4_DEFINITION = replace(
    GENERAL70_V3_DEFINITION, dataset_id="general-custom70-v4",
    created_at=_GENERAL70_V4["created_at"], source_revision=_GENERAL70_V4["source_revision"],
    frozen_source_index="eval_general_e2e/datasets/source-snapshots/general-custom70-v4/index.json",
)
GENERAL70_V5_DEFINITION = replace(
    GENERAL70_V4_DEFINITION, dataset_id="general-custom70-v5",
    created_at="2026-11-09T00:00:00+08:00", source_revision="2d71f7aeef8359127251280960c39ea278b625e1",
    current_source_paths=(
        "tasks/general_e2e/01_Information_Search_Organization/01_Information_Search_Organization_task_002_nonlinear_substructuring_author_bibliography.md",
        "tasks/general_e2e/01_Information_Search_Organization/01_Information_Search_Organization_task_004_luxun_national_character_source_comparison.md",
        "workspace/general_e2e/01_Information_Search_Organization/task_002_nonlinear_substructuring_author_bibliography/gt",
        "workspace/general_e2e/01_Information_Search_Organization/task_004_luxun_national_character_source_comparison/gt",
    ),
)
GENERAL70_V6_DEFINITION = replace(
    GENERAL70_V5_DEFINITION, dataset_id="general-custom70-v6",
    created_at="2026-11-11T00:00:00+08:00", source_revision="5340d1ed09ac0b59b6d67853aca26aec9e21441d",
    current_source_paths=GENERAL70_V5_DEFINITION.current_source_paths + (
        "tasks/general_e2e/01_Information_Search_Organization/01_Information_Search_Organization_task_001_acl2024_long_context_qa.md",
        "workspace/general_e2e/01_Information_Search_Organization/task_001_acl2024_long_context_qa/gt",
    ),
)
INFO004_OPEN_DEFINITION = replace(
    GENERAL70_V3_DEFINITION, dataset_id="general-info004-open-v1", created_at="2026-11-04T00:00:00+08:00",
    source_revision="4bc133fd3b8e710f8bd8e163bac97a5bcb4c06d3",
    frozen_source_index="eval_general_e2e/datasets/source-snapshots/general-info004-open-v1/index.json",
    task_ids=("01_Information_Search_Organization_task_004_luxun_national_character_source_comparison",),
    expected_task_count=1, expected_category_counts={"01_Information_Search_Organization": 1},
    expected_grading_type_counts={"hybrid": 1}, expected_difficulty_counts={"L3": 1},
    expected_timeout_counts={"3600": 1},
)
INFO004_OPEN_V2_DEFINITION = replace(
    INFO004_OPEN_DEFINITION, dataset_id="general-info004-open-v2", created_at="2026-11-05T00:00:00+08:00",
    source_revision="0ba583d42993cf141445ad86a29a50629d26867c",
    frozen_source_index="eval_general_e2e/datasets/source-snapshots/general-info004-open-v2/index.json",
)
INFO004_OPEN_V3_DEFINITION = replace(
    INFO004_OPEN_V2_DEFINITION, dataset_id="general-info004-open-v3", created_at="2026-11-05T00:00:00+08:00",
    source_revision="df8ff3b4530e1d93e65f3ec83d401c2990745a51",
    frozen_source_index="eval_general_e2e/datasets/source-snapshots/general-info004-open-v3/index.json",
)
_BUILTIN_DEFINITIONS = (DEFAULT_DEFINITION, GENERAL116_DEFINITION, GENERAL70_V2_DEFINITION, GENERAL70_V3_DEFINITION, GENERAL70_V4_DEFINITION, GENERAL70_V5_DEFINITION, GENERAL70_V6_DEFINITION, INFO004_OPEN_DEFINITION, INFO004_OPEN_V2_DEFINITION, INFO004_OPEN_V3_DEFINITION)


DATASETS = {
    item.dataset_id: replace(
        item,
        registry_path=f"{item.task_root}/task_sources.yaml",
        manifest_path=f"eval_general_e2e/datasets/manifests/{item.dataset_id}.json",
        revision_scope=(item.task_root, item.workspace_root),
    )
    for item in _BUILTIN_DEFINITIONS
}
# Public constants and the registry refer to the same unified definitions.
DEFAULT_DEFINITION = DATASETS[DEFAULT_DEFINITION.dataset_id]
GENERAL116_DEFINITION = DATASETS[GENERAL116_DEFINITION.dataset_id]
GENERAL70_V2_DEFINITION = DATASETS[GENERAL70_V2_DEFINITION.dataset_id]
GENERAL70_V3_DEFINITION = DATASETS[GENERAL70_V3_DEFINITION.dataset_id]
GENERAL70_V4_DEFINITION = DATASETS[GENERAL70_V4_DEFINITION.dataset_id]
GENERAL70_V5_DEFINITION = DATASETS[GENERAL70_V5_DEFINITION.dataset_id]
GENERAL70_V6_DEFINITION = DATASETS[GENERAL70_V6_DEFINITION.dataset_id]
INFO004_OPEN_DEFINITION = DATASETS[INFO004_OPEN_DEFINITION.dataset_id]
INFO004_OPEN_V2_DEFINITION = DATASETS[INFO004_OPEN_V2_DEFINITION.dataset_id]
INFO004_OPEN_V3_DEFINITION = DATASETS[INFO004_OPEN_V3_DEFINITION.dataset_id]
