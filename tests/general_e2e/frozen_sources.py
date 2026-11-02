"""Historical correction tests exercise archived v1 source, never new v2 code."""
from eval_general_e2e.datasets.bundle import _parse_task_source
from eval_general_e2e.datasets.source_history import frozen_task_path


def parse_frozen_task_source(path):
    return _parse_task_source(frozen_task_path(path))
