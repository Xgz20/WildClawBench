"""General end-to-end evaluation integration package."""

from .stages import (
    BUNDLE_PROTOCOL,
    CONTRACT_VERSION,
    GENERAL_E2E_SKILLS,
    SKILL_METADATA_SCHEMA,
    GeneralE2ESkillSpec,
    get_skill_spec,
)

__all__ = [
    "BUNDLE_PROTOCOL",
    "CONTRACT_VERSION",
    "GENERAL_E2E_SKILLS",
    "SKILL_METADATA_SCHEMA",
    "GeneralE2ESkillSpec",
    "contracts",
    "datasets",
    "get_skill_spec",
]
