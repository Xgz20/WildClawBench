from pathlib import Path
import json
from unittest.mock import patch
from src.e2e import DEFAULT_AGENTCUBE_TEMPLATE, DEFAULT_CHATGPT_DESKTOP_TEMPLATE
from src.e2e.controller_catalog import builtin_catalog, chatgpt_desktop_profile, default_profiles
from src.e2e.environment import runtime_status
from src.e2e.preparation import normalize_plan


def test_builtin_catalog_covers_controller_defaults_and_never_publishes_connections():
    catalog = builtin_catalog()
    profiles = default_profiles()
    assert {p["harness"] for p in profiles} == {"astronstudio", "workbuddy", "chatgpt-desktop"}
    assert {p["template"] for p in profiles if p["harness"] != "chatgpt-desktop"} == {DEFAULT_AGENTCUBE_TEMPLATE}
    desktop = next(p for p in profiles if p["harness"] == "chatgpt-desktop")
    assert desktop["template"] == DEFAULT_CHATGPT_DESKTOP_TEMPLATE
    assert desktop["template_namespace"] == "agentcube-windows"
    assert desktop["controller_revision"] == "37fa332a3a2c360406e7b830c5b0036582346ed7"
    assert desktop["scenarios"] == desktop["desktop_scoring_scenarios"] == ["general", "web"]
    assert desktop["chatgpt_scoring_auth"] == "subscription"
    assert desktop["default_permission"] == "full access"
    assert desktop["reasoning_efforts"] == ["low", "high"]
    assert "gpt-6.2-sol" in {row["id"] for row in desktop["models"]}
    assert {"auto", "spark-x2.6", "spark-x2.6-preview", "spark-x2.6-lite", "glm-5.3",
            "glm-5.3-flash", "glm-5.2", "deepseek-v4.1-flash", "deepseek-v4-pro",
            "deepseek-v4-flash"} <= {row["id"] for row in catalog["products"]["astronstudio"]["models"]}
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


def test_default_chatgpt_profile_is_independent_of_the_shared_template():
    profiles = default_profiles(template="another-astudio-template")
    assert {row["template"] for row in profiles if row["harness"] != "chatgpt-desktop"} == {"another-astudio-template"}
    desktop = next(row for row in profiles if row["harness"] == "chatgpt-desktop")
    assert desktop["template"] == DEFAULT_CHATGPT_DESKTOP_TEMPLATE
    desktop["models"].clear()
    assert next(row for row in default_profiles() if row["harness"] == "chatgpt-desktop")["models"]


def test_describe_publishes_default_chatgpt_and_preserves_explicit_file_replacement(tmp_path, monkeypatch):
    from src.e2e.protocol import describe

    monkeypatch.setenv("WCB_E2E_CAPABILITIES_FILE", "")
    repo = Path(__file__).resolve().parents[2]
    description = describe(repo)
    assert {row["harness"] for row in description["profiles"] if row["enabled"]} == {
        "astronstudio", "workbuddy", "chatgpt-desktop"
    }
    desktop = next(row for row in description["profiles"] if row["harness"] == "chatgpt-desktop")
    external = tmp_path / "capabilities.json"
    external.write_text(json.dumps({"schema": "wildclawbench.e2e-capabilities/v1", "profiles": [desktop]}))
    monkeypatch.setenv("WCB_E2E_CAPABILITIES_FILE", str(external))
    assert describe(repo)["profiles"] == [desktop]


def test_default_chatgpt_execution_preflight_and_subscription_scoring_use_the_published_binding(monkeypatch):
    from src.case_catalog import current_cases
    from src.e2e.desktop_scoring import _config, _verify_subscription_profile
    from src.e2e.protocol import preflight, profiles

    monkeypatch.setenv("WCB_E2E_CAPABILITIES_FILE", "")
    repo = Path(__file__).resolve().parents[2]
    desktop = next(row for row in profiles() if row["harness"] == "chatgpt-desktop")
    for scenario, library in (("general", "general-regression"), ("web", "web-custom")):
        task = current_cases(repo, library)[0]
        plan = {
            "selection": {"scenario": scenario, "library_dataset": library, "task_ids": [task["task_id"]]},
            "units": [{"harness": "chatgpt-desktop", "model": "gpt-6.2-sol", "reasoning_effort": "high"}],
        }
        result = preflight(repo, plan)
        assert result["valid"], result["issues"]
        unit = result["plan"]["units"][0]
        assert unit["template"] == desktop["template"]
        assert unit["chatgpt_permission"] == "full access"

    binding = {
        "id": 1, "namespace": desktop["template_namespace"],
        "image_digest": "sha256:" + "a" * 64, "waa_revision": desktop["controller_revision"],
        "profile_id": desktop["id"],
    }
    scoring = _config({
        "harness": "chatgpt-desktop", "model": "gpt-6.2-sol", "reasoning_effort": "high",
        "template": desktop["template"], "template_binding": binding,
        "chatgpt_scoring_auth": "subscription", "concurrency": 1, "timeout_seconds": 120,
    })
    _verify_subscription_profile(scoring)


def test_explicit_chatgpt_template_and_permission_remain_frozen():
    plan = normalize_plan({
        "selection": {"scenario": "web"},
        "units": [{"harness": "chatgpt-desktop", "model": "gpt-6.2-sol", "template": "legacy-chatgpt",
                   "chatgpt_permission": "ask for approval"}],
    })
    unit = plan["units"][0]
    assert unit["template"] == "legacy-chatgpt"
    assert unit["chatgpt_permission"] == "ask for approval"


def test_runtime_status_never_allocates_or_claims_authentication():
    with patch("src.e2e.agentcube.AgentCubeClient.create_session") as create:
        status = runtime_status()
    assert status["cloud_capacity"]["value"] is None
    assert status["credentials"]["authenticated"] is None
    create.assert_not_called()


def test_chatgpt_template_capabilities_follow_the_controller_sources(tmp_path):
    source = tmp_path / "src/win-arena-container/wgui/guest/products/chatgpt_desktop/ui_driver.py"
    source.parent.mkdir(parents=True)
    legacy = 'PILOT_MODEL = "gpt-6.2-sol"\nPILOT_EFFORT = "low"\nPRODUCT_VERSION = "26.1117.3838.0"\n'
    source.write_text(legacy)
    profile = chatgpt_desktop_profile(tmp_path, "legacy", "old")
    assert profile["scenarios"] == ["general"]
    assert profile["models"][0]["reasoning_efforts"] == ["low"]
    assert profile["default_permission"] == "ask for approval"
    source.write_text(legacy + 'PILOT_EFFORTS = ("low", "high")\nPILOT_SCENARIOS = ("general", "web")\nPILOT_PERMISSION = "full access"\n')
    profile = chatgpt_desktop_profile(tmp_path, "web-high", "new")
    assert profile["scenarios"] == ["general", "web"]
    assert profile["models"][0]["reasoning_efforts"] == ["low", "high"]
    assert profile["default_permission"] == "full access"
    with source.open("a") as stream:
        stream.write('MODEL_NAMES = {"gpt-6.2-sol": "GPT-6.2 Sol", "gpt-6.2-astra": "GPT-6.2 Astra"}\n')
    extended = chatgpt_desktop_profile(tmp_path, "multi-model", "new")
    assert [row["id"] for row in extended["models"]] == ["gpt-6.2-sol", "gpt-6.2-astra"]

    plan = normalize_plan({
        "selection": {"scenario": "web"},
        "units": [{"harness": "chatgpt-desktop", "model": "gpt-6.2-sol", "reasoning_effort": "high",
                   "chatgpt_permission": "full access"}],
    })
    assert plan["units"][0]["reasoning_effort"] == "high"
    assert plan["units"][0]["chatgpt_permission"] == "full access"


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
