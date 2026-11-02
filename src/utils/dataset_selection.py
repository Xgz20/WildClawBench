"""Explicit CLI dataset selection; legacy category discovery is unchanged."""
from pathlib import Path
import json


def require_dataset_output_scope(output_root: Path, manifest):
    """Reject cross-version reuse before any model prompt is dispatched."""
    scope=output_root/'evaluation_scope.json'
    if not scope.exists():return
    data=json.loads(scope.read_text(encoding='utf-8'))
    identity={'id':manifest['dataset_id'],'digest':manifest['dataset_digest']}
    if any(row.get('dataset')!=identity for row in data.get('tasks',[])):
        raise ValueError('CLI_DATASET_OUTPUT_SCOPE_CONFLICT: 请使用独立输出目录，不能覆盖或混用历史评测结果')


def dataset_task_paths(repo: Path, dataset_id: str):
    from eval_general_e2e.datasets.bundle import (GENERAL70_V2_DEFINITION, compile_dataset,
        dataset_manifest_path, load_manifest_lock)
    if dataset_id != GENERAL70_V2_DEFINITION.dataset_id:
        raise ValueError("UNSUPPORTED_CLI_DATASET")
    manifest, _ = compile_dataset(repo, definition=GENERAL70_V2_DEFINITION)
    if manifest != load_manifest_lock(dataset_manifest_path(dataset_id)):
        raise ValueError("CLI_DATASET_SOURCE_DRIFT: rebuild a reviewed dataset version before dispatch")
    grouped = {}
    for task in manifest['tasks']:
        grouped.setdefault(task['category'], []).append(repo/task['source']['task_path'])
    return manifest, grouped
