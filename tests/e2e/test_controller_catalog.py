from pathlib import Path
from unittest.mock import patch
from src.e2e.controller_catalog import builtin_catalog, default_profiles
from src.e2e.environment import runtime_status
from src.e2e.preparation import normalize_plan


def test_builtin_catalog_covers_controller_defaults_and_never_publishes_connections():
    catalog = builtin_catalog()
    profiles = default_profiles()
    assert {p["harness"] for p in profiles} == {"astronstudio", "workbuddy"}
    assert len(catalog["products"]["astronstudio"]["models"]) == 7
    assert len(catalog["products"]["workbuddy"]["models"]) == 20
    assert all(
        model["kind"] == "builtin"
        and not set(model) & {"api_key", "base_url", "model_connection"}
        for p in profiles
        for model in p["models"]
    )
    assert next(p for p in profiles if p["harness"] == "workbuddy")[
        "max_mode_supported"
    ]


def test_runtime_status_never_allocates_or_claims_authentication():
    with patch("src.e2e.agentcube.AgentCubeClient.create_session") as create:
        status = runtime_status()
    assert status["cloud_capacity"]["value"] is None
    assert status["credentials"]["authenticated"] is None
    create.assert_not_called()
