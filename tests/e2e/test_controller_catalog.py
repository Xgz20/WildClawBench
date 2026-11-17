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


def test_quota_rejection_is_a_platform_failure_before_model_dispatch():
    from src.e2e.agentcube import AgentCubeClient,AgentCubeConfig,PlatformError
    from unittest.mock import Mock
    import pytest
    response=Mock(status_code=200)
    response.json.return_value={'code':30043,'msg':'QUOTA_REJECTED:USER_QUOTA_NOT_ACTIVE User has no active quota rule','data':None}
    client=AgentCubeClient(AgentCubeConfig(user_id='synthetic',auth_token='synthetic'))
    with pytest.raises(PlatformError) as caught:client._json(response,'CREATE_SESSION')
    assert caught.value.platform_code=='USER_QUOTA_NOT_ACTIVE' and not caught.value.uncertain
    assert '配额未生效' in str(caught.value)
