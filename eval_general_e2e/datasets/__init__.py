"""Versioned General E2E dataset bundle support.

Exports are loaded lazily so ``python -m eval_general_e2e.datasets.bundle``
does not import the executable module twice.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "DEFAULT_DEFINITION",
    "DatasetDefinition",
    "build_default_bundle",
    "compile_dataset",
    "load_manifest_lock",
    "verify_dataset_bundle",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    return getattr(import_module(".bundle", __name__), name)
