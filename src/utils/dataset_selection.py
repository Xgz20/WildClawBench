"""Explicit CLI dataset selection; legacy category discovery is unchanged."""
from pathlib import Path
import json


def require_dataset_output_scope(output_root: Path, manifest):
    """Reject cross-version reuse before any model prompt is dispatched."""
    scope=output_root/'evaluation_scope.json'
    if not scope.exists():return
    data=json.loads(scope.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('CLI_DATASET_OUTPUT_SCOPE_CONFLICT: scope必须是JSON对象')
    identity={'id':manifest['dataset_id'],'digest':manifest['dataset_digest']}
    def normalized(row):
        value = row.get('dataset') or {}
        return {'id': value.get('id', value.get('release_id')),
                'digest': value.get('digest', value.get('dataset_digest'))}
    rows = data.get('planned_tasks') if 'planned_tasks' in data else data.get('tasks')
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or 'planned_tasks' in data and 'planned_task_count' in data and data['planned_task_count'] != len(rows)
            or any(not isinstance(row.get('dataset'), dict) or normalized(row) != identity for row in rows)):
        raise ValueError('CLI_DATASET_OUTPUT_SCOPE_CONFLICT: 请使用独立输出目录，不能覆盖或混用历史评测结果')


def dataset_task_paths(repo: Path, dataset_id: str, *, materialize_root: Path | None = None):
    from eval_general_e2e.datasets.bundle import (DATASETS, compile_dataset,
        dataset_manifest_path, load_manifest_lock)
    from eval_general_e2e.datasets.source_history import dataset_task_path
    from eval_general_e2e.datasets.layout import load_layout
    if dataset_id not in {'general-custom60-v1', 'general-custom70-v2', 'general-custom70-v3',
                          'general-custom70-v4', 'general-custom70-v5', 'general-custom70-v6'}:
        raise ValueError("UNSUPPORTED_CLI_DATASET")
    definition = DATASETS[dataset_id]
    manifest, members = compile_dataset(repo, definition=definition)
    if manifest != load_manifest_lock(dataset_manifest_path(dataset_id)):
        raise ValueError("CLI_DATASET_SOURCE_DRIFT: rebuild a reviewed dataset version before dispatch")
    historical = dataset_id in load_layout(repo).get("historical_releases", ())
    source_root = None
    if materialize_root is not None or historical:
        from eval_general_e2e.datasets.workspaces import materialize_verified_workspaces
        source_root = materialize_verified_workspaces(
            manifest, members, materialize_root or repo / "report-workspace/general-e2e/frozen-cli-sources",
            include_task_files=historical,
        )
    grouped = {}
    for task in manifest['tasks']:
        file_path = (source_root / task["task_id"] / "task.md" if historical else dataset_task_path(
            repo, task["source"]["task_path"], definition.frozen_source_index, definition.current_source_paths))
        grouped.setdefault(task["category"], []).append(file_path)
    return manifest, grouped
