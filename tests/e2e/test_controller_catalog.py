from pathlib import Path
from unittest.mock import patch
from src.e2e.controller_catalog import builtin_catalog, default_profiles
from src.e2e.environment import runtime_status
from src.e2e.preparation import normalize_plan


def test_builtin_catalog_covers_controller_defaults_and_never_publishes_connections():
    catalog = builtin_catalog()
    profiles = default_profiles()
    assert {p["harness"] for p in profiles} == {"astronstudio", "workbuddy"}
    assert {p["template"] for p in profiles} == {"winarena-pc-20261118-a"}
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


def test_workbuddy_permission_is_frozen_into_distinct_unit_identity():
    import pytest
    from src.e2e.common import E2EError

    def normalized(harness, value):
        return normalize_plan({
            "selection": {"scenario": "general", "dataset": "general-custom70-v6"},
            "units": [{"harness": harness, "model": "GLM-5.3", "workbuddy_full_access": value}],
        })["units"][0]

    off = normalized("workbuddy", False)
    on = normalized("workbuddy", True)
    implicit = normalize_plan({
        "selection": {"scenario": "general", "dataset": "general-custom70-v6"},
        "units": [{"harness": "workbuddy", "model": "GLM-5.3"}],
    })["units"][0]
    assert implicit == on
    assert off["template"] == on["template"] == "winarena-pc-20261118-a"
    assert off["workbuddy_full_access"] is False
    assert on["workbuddy_full_access"] is True
    assert off["unit_id"] != on["unit_id"]
    with pytest.raises(E2EError, match="WORKBUDDY_FULL_ACCESS_MUST_BE_BOOLEAN"):
        normalized("workbuddy", "false")
    with pytest.raises(E2EError, match="FULL_ACCESS_OPTION_REQUIRES_WORKBUDDY"):
        normalized("astronstudio", False)
