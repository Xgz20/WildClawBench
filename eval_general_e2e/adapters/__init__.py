"""Harness-specific General E2E adapter namespace.

Shared component bindings are introduced by G1-03. Runtime task execution is
still delivered by later milestones. Keeping this as a separate package
prevents the legacy ``eval_e2e`` modules or Web-specific adapters from becoming
implicit General E2E dependencies.
"""

from .components import EXPECTED_COMPONENTS, inspect_shared_component_layout

__all__ = ["EXPECTED_COMPONENTS", "inspect_shared_component_layout"]
