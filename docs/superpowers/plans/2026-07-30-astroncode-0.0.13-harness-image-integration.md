# AstronCode 0.0.13 Harness Image Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建可复现的 AstronCode 0.0.13 v3 Harness 镜像，使 MaaS/Astron、GPT/one-iflytek 和 OpenRouter 模型获得正确且兼容旧命令的运行时配置。

**Architecture:** 镜像层只安装固定版本 CLI，所有 provider 与凭证配置继续由 `AstronCodeAgent` 按任务运行时生成。runner 先归一化模型名，再按显式覆盖、GPT、Astron、OpenRouter 的顺序选择 provider，并分别解析凭证；容器使用真实 token，宿主机评测产物只写脱敏 TOML。

**Tech Stack:** Docker、Bash、Python 3、`unittest`、`tomllib`、AstronCode CLI 0.0.13、WildClawBench batch runner

---

## File Map

- Create: `tests/test_astroncode_config.py` — provider 识别、凭证回退、TOML 结构、脱敏和默认镜像测试。
- Create: `tests/test_astroncode_v3_image.py` — v3 Dockerfile 与构建脚本默认值的静态契约测试。
- Create: `docker/astroncode/v3/Dockerfile` — 固定安装 AstronCode 0.0.13。
- Modify: `src/agents/astroncode/runner.py` — 三路 provider、one-iflytek 配置、凭证解析、错误信息和默认镜像。
- Modify: `script/build-astroncode-image.sh` — 默认 variant/tag 切换到 v3/v0.3。
- Modify: `docs/local/deploy/export.astroncode.sh` — 默认镜像与 0.0.13 环境变量说明。
- Modify: `.env.example` — 增加 AstronCode 镜像和可选 provider 空值示例。
- Modify: `docs/local/guide/linux-评测命令速查.md` — 更新 AstronCode 0.0.13 运行说明和示例。
- Modify: `docs/local/guide/macos-本地调试指南.md` — 更新 §2、§4.2 和三模型冒烟命令。
- Include: `docker/astroncode/v3/AstronCode-0.0.13版本集成.md` — 用户提供的版本配置依据，不改写模型目录快照。
- Include: `docs/superpowers/specs/2026-07-30-astroncode-0.0.13-harness-image-integration-design.md` — 已批准设计。

> Commit 步骤是计划检查点。执行时只有在用户明确授权 Git commit 后才运行；提交信息必须使用中文 Conventional Commits。

### Task 1: Add AstronCode 0.0.13 Config Tests

**Files:**
- Create: `tests/test_astroncode_config.py`
- Modify: `src/agents/astroncode/runner.py:25`
- Modify: `src/agents/astroncode/runner.py:133`
- Modify: `src/agents/astroncode/runner.py:517`

- [ ] **Step 1: Write failing provider and config tests**

Create `tests/test_astroncode_config.py`:

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.astroncode.runner import AstronCodeAgent


class AstronCodeConfigTests(unittest.TestCase):
    def make_agent(
        self,
        api_key: str = "openrouter-fallback-key",
        base_url: str = "https://openrouter.example/api/v1",
    ) -> AstronCodeAgent:
        return AstronCodeAgent(
            openrouter_api_key=api_key,
            openrouter_base_url=base_url,
        )

    def parse_config(
        self,
        agent: AstronCodeAgent,
        model: str,
        *,
        redact_secrets: bool = False,
    ) -> dict:
        provider = agent._provider_for_model(model)
        rendered = agent._render_codex_config(
            model=model,
            reasoning_effort=None,
            wire_api=None,
            provider_api_key=agent._resolve_provider_api_key(provider),
            redact_secrets=redact_secrets,
        )
        return tomllib.loads(rendered)

    def test_provider_auto_detection_uses_three_routes(self) -> None:
        with patch.dict(os.environ, {"ASTRONCODE_MODEL_PROVIDER": ""}, clear=False):
            agent = self.make_agent()
            for model in (
                "openrouter/xminimaxm25",
                "openrouter/xopglm52",
                "openrouter/xsparkx2agent",
                "openrouter/astronclaw-auto",
            ):
                self.assertEqual(agent._provider_for_model(model), "astron-spark")
            self.assertEqual(agent._provider_for_model("openrouter/gpt-5.5"), "one-iflytek")
            self.assertEqual(agent._provider_for_model("openrouter/claude-4"), "openrouter")

    def test_provider_override_accepts_only_supported_values(self) -> None:
        agent = self.make_agent()
        for provider in ("astron-spark", "one-iflytek", "openrouter"):
            with self.subTest(provider=provider), patch.dict(
                os.environ,
                {"ASTRONCODE_MODEL_PROVIDER": provider},
                clear=False,
            ):
                self.assertEqual(agent._provider_for_model("openrouter/unknown"), provider)

        with patch.dict(
            os.environ,
            {"ASTRONCODE_MODEL_PROVIDER": "unsupported"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "astron-spark.*one-iflytek.*openrouter"):
                agent._provider_for_model("openrouter/gpt-5.5")

    def test_provider_keys_preserve_legacy_fallbacks(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "astron-primary",
                "ASTRON_SPARK_API_KEY": "astron-legacy",
                "ONE_IFLYTEK_API_KEY": "one-primary",
            },
            clear=False,
        ):
            agent = self.make_agent(api_key="openrouter-fallback")
            self.assertEqual(agent._resolve_provider_api_key("astron-spark"), "astron-primary")
            self.assertEqual(agent._resolve_provider_api_key("one-iflytek"), "one-primary")
            self.assertEqual(agent._resolve_provider_api_key("openrouter"), "openrouter-fallback")

        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "",
                "ASTRON_SPARK_API_KEY": "astron-legacy",
                "ONE_IFLYTEK_API_KEY": "",
            },
            clear=False,
        ):
            agent = self.make_agent(api_key="openrouter-fallback")
            self.assertEqual(agent._resolve_provider_api_key("astron-spark"), "astron-legacy")
            self.assertEqual(agent._resolve_provider_api_key("one-iflytek"), "openrouter-fallback")

    def test_one_iflytek_base_url_prefers_dedicated_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ONE_IFLYTEK_BASE_URL": "https://one.example/v1",
                "OPENROUTER_BASE_URL": "https://fallback.example/v1",
            },
            clear=False,
        ):
            agent = self.make_agent(base_url="")
            self.assertEqual(agent._resolve_one_iflytek_base_url(), "https://one.example/v1")

        with patch.dict(
            os.environ,
            {
                "ONE_IFLYTEK_BASE_URL": "",
                "OPENROUTER_BASE_URL": "https://fallback.example/v1",
            },
            clear=False,
        ):
            agent = self.make_agent(base_url="")
            self.assertEqual(agent._resolve_one_iflytek_base_url(), "https://fallback.example/v1")

    def test_astron_spark_config_matches_0_0_13(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRON_API_KEY": "astron-secret", "ASTRONCODE_MODEL_PROVIDER": ""},
            clear=False,
        ):
            config = self.parse_config(self.make_agent(), "openrouter/xopglm52")

        self.assertEqual(config["model"], "xopglm52")
        self.assertEqual(config["model_provider"], "astron-spark")
        provider = config["model_providers"]["astron-spark"]
        self.assertEqual(provider["experimental_bearer_token"], "astron-secret")
        self.assertNotIn("models_base_url", provider)

    def test_one_iflytek_config_uses_responses_contract(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ONE_IFLYTEK_API_KEY": "one-secret",
                "ONE_IFLYTEK_BASE_URL": "https://one.example/v1",
                "ASTRONCODE_MODEL_PROVIDER": "",
            },
            clear=False,
        ):
            config = self.parse_config(self.make_agent(), "openrouter/gpt-5.5")

        self.assertEqual(config["model"], "gpt-5.5")
        self.assertEqual(config["model_provider"], "one-iflytek")
        provider = config["model_providers"]["one-iflytek"]
        self.assertEqual(provider["base_url"], "https://one.example/v1")
        self.assertEqual(provider["experimental_bearer_token"], "one-secret")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertIs(provider["requires_openai_auth"], False)
        self.assertEqual(provider["stream_idle_timeout_ms"], 300000)

    def test_openrouter_config_keeps_env_reference(self) -> None:
        with patch.dict(os.environ, {"ASTRONCODE_MODEL_PROVIDER": ""}, clear=False):
            config = self.parse_config(self.make_agent(), "openrouter/claude-4")

        self.assertEqual(config["model_provider"], "openrouter")
        provider = config["model_providers"]["openrouter"]
        self.assertEqual(provider["env_key"], "OPENROUTER_API_KEY")
        self.assertNotIn("experimental_bearer_token", provider)

    def test_redacted_configs_never_contain_provider_secrets(self) -> None:
        cases = (
            ("openrouter/xopglm52", "ASTRON_API_KEY", "astron-secret-never-write"),
            ("openrouter/gpt-5.5", "ONE_IFLYTEK_API_KEY", "one-secret-never-write"),
        )
        for model, env_key, secret in cases:
            with self.subTest(model=model), patch.dict(
                os.environ,
                {env_key: secret, "ASTRONCODE_MODEL_PROVIDER": ""},
                clear=False,
            ):
                agent = self.make_agent()
                provider = agent._provider_for_model(model)
                rendered = agent._render_codex_config(
                    model=model,
                    reasoning_effort="high",
                    wire_api=None,
                    provider_api_key=agent._resolve_provider_api_key(provider),
                    redact_secrets=True,
                )
                config = tomllib.loads(rendered)

            self.assertNotIn(secret, rendered)
            self.assertEqual(
                config["model_providers"][provider]["experimental_bearer_token"],
                "***",
            )

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_host_config_artifact_is_redacted(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
        cases = (
            ("openrouter/xopglm52", "ASTRON_API_KEY", "host-astron-secret"),
            ("openrouter/gpt-5.5", "ONE_IFLYTEK_API_KEY", "host-one-secret"),
        )
        for model, env_key, secret in cases:
            with self.subTest(model=model), patch.dict(
                os.environ,
                {env_key: secret, "ASTRONCODE_MODEL_PROVIDER": ""},
                clear=False,
            ), tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                self.make_agent()._write_codex_config(
                    task_id="redaction-test",
                    model=model,
                    reasoning_effort=None,
                    wire_api=None,
                    output_dir=output_dir,
                )
                config_text = (output_dir / "config.toml").read_text(encoding="utf-8")

            self.assertNotIn(secret, config_text)
            self.assertIn('experimental_bearer_token = "***"', config_text)

    def test_missing_provider_key_fails_without_leaking_other_keys(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "",
                "ASTRON_SPARK_API_KEY": "",
                "OPENROUTER_API_KEY": "",
                "ONE_IFLYTEK_API_KEY": "unrelated-secret",
            },
            clear=False,
        ), tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(api_key="")
            with self.assertRaisesRegex(RuntimeError, "ASTRON_API_KEY") as raised:
                agent._write_codex_config(
                    task_id="missing-key",
                    model="openrouter/xopglm52",
                    reasoning_effort=None,
                    wire_api=None,
                    output_dir=Path(tmp),
                )

        self.assertNotIn("unrelated-secret", str(raised.exception))

    def test_default_image_is_v0_3(self) -> None:
        with patch.dict(os.environ, {"DOCKER_IMAGE_ASTRONCODE": ""}, clear=False):
            self.assertEqual(
                self.make_agent().image,
                "wildclawbench-astroncode-ubuntu:v0.3",
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run python -m unittest tests.test_astroncode_config -v
```

Expected: FAIL because `_resolve_provider_api_key`, `_resolve_one_iflytek_base_url`, `provider_api_key` and one-iflytek routing do not exist, and the default image is still `v0.2`.

- [ ] **Step 3: Add provider constants and constructor state**

Replace `DEFAULT_ASTRON_MODELS_BASE_URL` with:

```python
DEFAULT_ONE_IFLYTEK_BASE_URL = "https://one.iflytek.com/api/llm/console/chat/v1"
VALID_ASTRONCODE_PROVIDERS = ("astron-spark", "one-iflytek", "openrouter")
ASTRON_MODEL_PREFIXES = ("xminimax", "xop", "xspark", "astronclaw-")
```

In `AstronCodeAgent.__init__`, use:

```python
resolved_image = (
    image
    or os.environ.get("DOCKER_IMAGE_ASTRONCODE")
    or "wildclawbench-astroncode-ubuntu:v0.3"
)
self.image = resolved_image
self.openrouter_api_key = (
    openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
).strip()
configured_openrouter_base_url = (
    openrouter_base_url or os.environ.get("OPENROUTER_BASE_URL", "")
).strip()
self.openrouter_base_url = normalize_openrouter_base_url_for_openclaw(
    configured_openrouter_base_url
)
self.one_iflytek_api_key = (
    os.environ.get("ONE_IFLYTEK_API_KEY", "").strip()
    or self.openrouter_api_key
)
self.one_iflytek_base_url = (
    os.environ.get("ONE_IFLYTEK_BASE_URL", "").strip()
    or configured_openrouter_base_url
    or DEFAULT_ONE_IFLYTEK_BASE_URL
)
self.reasoning_effort_default = reasoning_effort_default
```

- [ ] **Step 4: Implement provider routing and credential resolution**

Replace `_provider_for_model`, `_resolve_astron_api_key` and `_resolve_astron_models_base_url` with:

```python
def _resolve_provider_api_key(self, provider: str) -> str:
    if provider == "astron-spark":
        return (
            os.environ.get("ASTRON_API_KEY", "").strip()
            or os.environ.get("ASTRON_SPARK_API_KEY", "").strip()
            or self.openrouter_api_key
        )
    if provider == "one-iflytek":
        return self.one_iflytek_api_key
    if provider == "openrouter":
        return self.openrouter_api_key
    raise ValueError(f"Unsupported AstronCode provider: {provider}")

def _resolve_one_iflytek_base_url(self) -> str:
    return self.one_iflytek_base_url

@staticmethod
def _provider_for_model(model: str) -> str:
    override = os.environ.get("ASTRONCODE_MODEL_PROVIDER", "").strip().lower()
    if override:
        if override not in VALID_ASTRONCODE_PROVIDERS:
            allowed = ", ".join(VALID_ASTRONCODE_PROVIDERS)
            raise ValueError("ASTRONCODE_MODEL_PROVIDER must be one of: " + allowed)
        return override

    bare_model = model.split("/", 1)[1] if model.startswith("openrouter/") else model
    normalized_model = bare_model.lower()
    if normalized_model.startswith("gpt-"):
        return "one-iflytek"
    if normalized_model.startswith(ASTRON_MODEL_PREFIXES):
        return "astron-spark"
    return "openrouter"
```

- [ ] **Step 5: Render three provider-specific TOML blocks**

Rename `_render_codex_config(..., astron_api_key: str, ...)` to `_render_codex_config(..., provider_api_key: str, ...)`. Keep the common settings and use:

```python
token = "***" if redact_secrets else provider_api_key
if provider == "openrouter":
    return common_config + (
        "\n"
        "[model_providers.openrouter]\n"
        'name = "openrouter"\n'
        f"base_url = {toml_basic_string(self.openrouter_base_url)}\n"
        'env_key = "OPENROUTER_API_KEY"\n'
    )
if provider == "one-iflytek":
    return common_config + (
        "\n"
        "[model_providers.one-iflytek]\n"
        'name = "Codex via iFlytek One"\n'
        f"base_url = {toml_basic_string(self._resolve_one_iflytek_base_url())}\n"
        f"experimental_bearer_token = {toml_basic_string(token)}\n"
        'wire_api = "responses"\n'
        "requires_openai_auth = false\n"
        "stream_idle_timeout_ms = 300000\n"
    )
return common_config + (
    "\n"
    "[model_providers.astron-spark]\n"
    'name = "Astron Spark"\n'
    f"experimental_bearer_token = {toml_basic_string(token)}\n"
)
```

Keep `wire_api` as a compatibility argument but do not let it override the one-iflytek `responses` contract.

- [ ] **Step 6: Validate provider-specific keys before writing config**

In `_write_codex_config`, resolve and validate the active provider only:

```python
provider = self._provider_for_model(model)
provider_api_key = self._resolve_provider_api_key(provider)
if not provider_api_key:
    key_hints = {
        "astron-spark": "ASTRON_API_KEY, ASTRON_SPARK_API_KEY, or OPENROUTER_API_KEY",
        "one-iflytek": "ONE_IFLYTEK_API_KEY or OPENROUTER_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    raise RuntimeError(
        f"AstronCode provider {provider} requires {key_hints[provider]}."
    )
```

Pass `provider_api_key` to both render calls, with `redact_secrets=False` for the container and `True` for the host artifact. Update the docstring from `0.0.6+` to `0.0.13` and remove stale `models_base_url` comments.

- [ ] **Step 7: Run focused tests and verify GREEN**

```bash
uv run python -m unittest tests.test_astroncode_config -v
```

Expected: all tests in `AstronCodeConfigTests` pass.

- [ ] **Step 8: Commit runner behavior when authorized**

```bash
git add tests/test_astroncode_config.py src/agents/astroncode/runner.py
git commit -m "feat(astroncode): 支持0.0.13三路模型配置"
```

### Task 2: Add the v3 Image and Build Defaults

**Files:**
- Create: `tests/test_astroncode_v3_image.py`
- Create: `docker/astroncode/v3/Dockerfile`
- Modify: `script/build-astroncode-image.sh:1`

- [ ] **Step 1: Write failing image contract tests**

Create `tests/test_astroncode_v3_image.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker/astroncode/v3/Dockerfile"
BUILD_SCRIPT = REPO_ROOT / "script/build-astroncode-image.sh"


class AstronCodeV3ImageTests(unittest.TestCase):
    def test_v3_image_pins_astroncode_0_0_13(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("FROM wildclawbench-codex-ubuntu:v0.0", text)
        self.assertIn("ARG ASTRON_CODE_VERSION=0.0.13", text)
        self.assertIn('"@iflytek/astron-code@${ASTRON_CODE_VERSION}"', text)
        self.assertIn("astron-code --version", text)
        self.assertIn("mkdir -p /root/.acode", text)

    def test_build_script_defaults_to_v3_and_v0_3(self) -> None:
        text = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('IMAGE_TAG="${IMAGE_TAG:-v0.3}"', text)
        self.assertIn(
            'ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v3}"',
            text,
        )
        self.assertIn("ASTRON_CODE_VERSION=0.0.13", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run image tests and verify RED**

```bash
uv run python -m unittest tests.test_astroncode_v3_image -v
```

Expected: ERROR because the v3 Dockerfile does not exist, then FAIL until script defaults change.

- [ ] **Step 3: Create the pinned v3 Dockerfile**

Create `docker/astroncode/v3/Dockerfile`:

```dockerfile
# AstronCode 0.0.13 evaluation image. Provider credentials are written at runtime.
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.13
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true \
    && npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version

RUN mkdir -p /root/.acode && chmod 700 /root/.acode
```

- [ ] **Step 4: Switch build script defaults**

Use these defaults and examples, keeping all existing build args, variant validation, Docker build, and gzip export logic:

```bash
# 默认构建 v3（AstronCode 0.0.13，运行时生成 provider 配置）。
# 可选：ASTRON_CODE_VERSION=0.0.13 IMAGE_TAG=v0.3 bash script/build-astroncode-image.sh
# 可选：ASTRONCODE_DOCKER_VARIANT=v2 IMAGE_TAG=v0.2 bash script/build-astroncode-image.sh
IMAGE_TAG="${IMAGE_TAG:-v0.3}"
ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v3}"
```

- [ ] **Step 5: Verify image contracts and shell syntax**

```bash
uv run python -m unittest tests.test_astroncode_v3_image -v
bash -n script/build-astroncode-image.sh
```

Expected: tests pass and `bash -n` exits 0 with no output.

- [ ] **Step 6: Commit image changes when authorized**

```bash
git add docker/astroncode/v3/Dockerfile docker/astroncode/v3/AstronCode-0.0.13版本集成.md tests/test_astroncode_v3_image.py script/build-astroncode-image.sh
git commit -m "feat(astroncode): 增加0.0.13评测镜像"
```

### Task 3: Update Deployment and Evaluation Guides

**Files:**
- Modify: `.env.example`
- Modify: `docs/local/deploy/export.astroncode.sh`
- Modify: `docs/local/guide/linux-评测命令速查.md`
- Modify: `docs/local/guide/macos-本地调试指南.md`
- Include: `docs/superpowers/specs/2026-07-30-astroncode-0.0.13-harness-image-integration-design.md`

- [ ] **Step 1: Update environment examples without adding secrets**

Add after `DOCKER_IMAGE_ASTRONCLAW` in `.env.example`:

```dotenv
DOCKER_IMAGE_ASTRONCODE=wildclawbench-astroncode-ubuntu:v0.3

# Optional AstronCode provider overrides. Existing OPENROUTER_* fallbacks remain valid.
ASTRON_API_KEY=
ASTRON_SPARK_API_KEY=
ONE_IFLYTEK_API_KEY=
ONE_IFLYTEK_BASE_URL=
ASTRONCODE_MODEL_PROVIDER=
```

Do not copy values from local guides or `back.env-bak` into `.env.example`.

- [ ] **Step 2: Update `export.astroncode.sh` for 0.0.13**

Replace the v0.2 block with:

```bash
# v0.3 = astron-code 0.0.13 + runtime astron-spark/one-iflytek/OpenRouter config.
# 老版本镜像仍可通过 ASTRONCODE_DOCKER_VARIANT=v1/v2 构建。
export DOCKER_IMAGE_ASTRONCODE='wildclawbench-astroncode-ubuntu:v0.3'

# 兼容现有命令：MaaS 仍可复用 OPENROUTER_API_KEY。
export ASTRON_API_KEY="${ASTRON_API_KEY:-${OPENROUTER_API_KEY}}"
export ASTRON_SPARK_API_KEY="${ASTRON_SPARK_API_KEY:-${ASTRON_API_KEY}}"

# GPT/one-iflytek 可单独覆盖；留空时 runner 回退到 OPENROUTER_*。
export ONE_IFLYTEK_API_KEY="${ONE_IFLYTEK_API_KEY:-}"
export ONE_IFLYTEK_BASE_URL="${ONE_IFLYTEK_BASE_URL:-}"
```

Remove `ASTRON_MODELS_BASE_URL`.

- [ ] **Step 3: Update Linux AstronCode sections**

In `docs/local/guide/linux-评测命令速查.md`:

- Replace AstronCode-specific `0.0.6`/`v0.2` instructions with `0.0.13`/`v0.3`.
- Explain `gpt-* -> one-iflytek`, Astron prefixes -> `astron-spark`, other models -> OpenRouter.
- Explain optional `ONE_IFLYTEK_*` and legacy `OPENROUTER_*` fallback.
- Remove `ASTRON_MODELS_BASE_URL` from AstronCode commands.
- Keep other Harness sections unchanged.
- Keep `xsparkx2agent`, `xopglm52`, `gpt-5.5` as the supported AstronCode smoke matrix; remove the obsolete AstronCode `xsparkx2flash` smoke command.

Include this compatibility statement:

```markdown
AstronCode 0.0.13 仍接受框架侧的 `openrouter/<modelId>` 参数；该前缀只用于兼容现有评测命令，不决定 AstronCode provider。`gpt-*` 使用 `one-iflytek`，Astron 内置模型使用 `astron-spark`，其他模型使用 OpenRouter。
```

- [ ] **Step 4: Update macOS §2 and §4.2**

Apply the same version, image, provider and `ASTRON_MODELS_BASE_URL` changes in `docs/local/guide/macos-本地调试指南.md`. Keep §4.2 as three required single-run commands: `xsparkx2agent`, `xopglm52`, `gpt-5.5`. Preserve optional GLM debug examples outside the required smoke matrix. For GPT, intentionally omit `ONE_IFLYTEK_API_KEY` and keep `OPENROUTER_API_KEY` to verify compatibility fallback. Preserve the VPN warning and judge endpoint.

- [ ] **Step 5: Verify documentation consistency**

```bash
rg -n "wildclawbench-astroncode-ubuntu:v0\.2|AstronCode 0\.0\.6|ASTRON_MODELS_BASE_URL" \
  docs/local/deploy/export.astroncode.sh \
  docs/local/guide/linux-评测命令速查.md \
  docs/local/guide/macos-本地调试指南.md
```

Expected: no matches in active AstronCode v3 instructions. Review intentional historical comparisons manually.

- [ ] **Step 6: Commit documentation when authorized**

```bash
git add .env.example docs/local/deploy/export.astroncode.sh docs/local/guide/linux-评测命令速查.md docs/local/guide/macos-本地调试指南.md docs/superpowers/specs/2026-07-30-astroncode-0.0.13-harness-image-integration-design.md docs/superpowers/plans/2026-07-30-astroncode-0.0.13-harness-image-integration.md
git commit -m "docs(astroncode): 更新0.0.13评测指引"
```

### Task 4: Run the Complete Unit Test Gates

**Files:**
- Test: `tests/test_astroncode_config.py`
- Test: `tests/test_astroncode_v3_image.py`
- Test: `tests/test_*.py`
- Test: `tools/report/tests/test_*.py`

- [ ] **Step 1: Run all core tests**

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
```

Expected: exit 0 and all discovered tests pass.

- [ ] **Step 2: Run all report tests**

```bash
uv run python -m unittest discover -s tools/report/tests -p 'test_*.py'
```

Expected: exit 0 and all discovered tests pass.

- [ ] **Step 3: Check formatting and repository diff**

```bash
git diff --check
git status --short
```

Expected: `git diff --check` exits 0. `git status --short` contains only this task's files plus the user's pre-existing `back.env-bak`.

### Task 5: Build and Verify the v3 Image

**Files:**
- Verify: `docker/astroncode/v3/Dockerfile`
- Verify: `script/build-astroncode-image.sh`

- [ ] **Step 1: Confirm Docker and the base image are available**

```bash
docker info >/dev/null
docker image inspect wildclawbench-codex-ubuntu:v0.0 >/dev/null
```

Expected: both commands exit 0. If the base image is missing, load or build it before continuing; do not substitute a different base image.

- [ ] **Step 2: Build the v3 image without exporting the large tar**

```bash
docker build \
  -f docker/astroncode/v3/Dockerfile \
  -t wildclawbench-astroncode-ubuntu:v0.3 \
  docker/astroncode/v3
```

Expected: build succeeds and the install layer prints AstronCode 0.0.13.

- [ ] **Step 3: Verify the installed CLI version**

```bash
docker run --rm wildclawbench-astroncode-ubuntu:v0.3 astron-code --version
```

Expected: output contains `0.0.13`.

- [ ] **Step 4: Inspect image metadata**

```bash
docker image inspect wildclawbench-astroncode-ubuntu:v0.3 \
  --format '{{.Id}} {{.Architecture}} {{.Os}}'
```

Expected: one image ID followed by the Docker platform. On Apple Silicon, record amd64 emulation in the validation result.

### Task 6: Run Three AstronCode End-to-End Smoke Cases

**Files:**
- Follow: `docs/local/guide/macos-本地调试指南.md:143`
- Verify outputs under: `../eval_out_debug/smoke/astroncode-0.0.13/`

Before running, export real credentials into the current shell without writing them to tracked files:

```bash
: "${WCB_MAAS_API_KEY:?export WCB_MAAS_API_KEY for Astron MaaS}"
: "${WCB_ONE_IFLYTEK_API_KEY:?export WCB_ONE_IFLYTEK_API_KEY for gpt-5.5}"
: "${ANTHROPIC_API_KEY:?export ANTHROPIC_API_KEY for the judge}"
: "${ANTHROPIC_BASE_URL:?export ANTHROPIC_BASE_URL for the judge}"
: "${JUDGE_MODEL:?export JUDGE_MODEL for the judge}"
```

- [ ] **Step 1: Run `xsparkx2agent` single-case smoke**

```bash
D="../eval_out_debug/smoke/astroncode-0.0.13/xsparkx2agent"; mkdir -p "$D/astroncode"
OUTPUT_SUBDIR="$D" \
DOCKER_IMAGE_ASTRONCODE='wildclawbench-astroncode-ubuntu:v0.3' \
OPENROUTER_BASE_URL='https://maas-api.cn-huabei-1.xf-yun.com/v1' \
OPENROUTER_API_KEY="$WCB_MAAS_API_KEY" \
ASTRON_API_KEY="$WCB_MAAS_API_KEY" \
ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
JUDGE_MODEL="$JUDGE_MODEL" \
uv run eval/run_batch.py --agent-backend astroncode \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xsparkx2agent
```

Expected: exit 0 and one AstronCode run under `$D/astroncode`.

- [ ] **Step 2: Run `xopglm52` single-case smoke**

```bash
D="../eval_out_debug/smoke/astroncode-0.0.13/xopglm52"; mkdir -p "$D/astroncode"
OUTPUT_SUBDIR="$D" \
DOCKER_IMAGE_ASTRONCODE='wildclawbench-astroncode-ubuntu:v0.3' \
OPENROUTER_BASE_URL='https://maas-api.cn-huabei-1.xf-yun.com/v1' \
OPENROUTER_API_KEY="$WCB_MAAS_API_KEY" \
ASTRON_API_KEY="$WCB_MAAS_API_KEY" \
ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
JUDGE_MODEL="$JUDGE_MODEL" \
uv run eval/run_batch.py --agent-backend astroncode \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xopglm52
```

Expected: exit 0 and one AstronCode run under `$D/astroncode`.

- [ ] **Step 3: Run `gpt-5.5` through the legacy fallback**

Do not set `ONE_IFLYTEK_API_KEY` in this command. Passing the GPT key through `OPENROUTER_API_KEY` verifies the approved backward compatibility path.

```bash
D="../eval_out_debug/smoke/astroncode-0.0.13/gpt-5.5"; mkdir -p "$D/astroncode"
env -u ONE_IFLYTEK_API_KEY \
OUTPUT_SUBDIR="$D" \
DOCKER_IMAGE_ASTRONCODE='wildclawbench-astroncode-ubuntu:v0.3' \
OPENROUTER_BASE_URL='https://one.iflytek.com/api/llm/console/chat/v1' \
OPENROUTER_API_KEY="$WCB_ONE_IFLYTEK_API_KEY" \
ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
JUDGE_MODEL="$JUDGE_MODEL" \
uv run eval/run_batch.py --agent-backend astroncode \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/gpt-5.5
```

Expected: exit 0 and generated config selects `one-iflytek`.

- [ ] **Step 4: Validate status, usage, score, version, provider and redaction**

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

root = Path("../eval_out_debug/smoke/astroncode-0.0.13")
expected_providers = {
    "xsparkx2agent": "astron-spark",
    "xopglm52": "astron-spark",
    "gpt-5.5": "one-iflytek",
}
secrets = {
    os.environ["WCB_MAAS_API_KEY"],
    os.environ["WCB_ONE_IFLYTEK_API_KEY"],
    os.environ["ANTHROPIC_API_KEY"],
}

for model, expected_provider in expected_providers.items():
    status_paths = sorted((root / model / "astroncode").glob("**/execution_status.json"))
    assert status_paths, f"missing execution_status.json for {model}"
    run_dir = status_paths[-1].parent
    status = json.loads((run_dir / "execution_status.json").read_text(encoding="utf-8"))
    usage = json.loads((run_dir / "usage.json").read_text(encoding="utf-8"))
    score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
    config_text = (run_dir / "config.toml").read_text(encoding="utf-8")
    config = tomllib.loads(config_text)

    assert status["status"] == "finished", (model, status)
    assert status["exit_code"] == 0, (model, status)
    assert status["harness_version"] == "0.0.13", (model, status)
    assert usage.get("total_tokens", 0) > 0, (model, usage)
    assert isinstance(score.get("overall_score"), (int, float)), (model, score)
    assert config["model_provider"] == expected_provider, (model, config)
    for secret in secrets:
        assert secret not in config_text, f"secret leaked in {model}/config.toml"
    provider = config["model_providers"][expected_provider]
    assert provider["experimental_bearer_token"] == "***", (model, provider)

print("PASS: AstronCode 0.0.13 smoke matrix")
PY
```

Expected: `PASS: AstronCode 0.0.13 smoke matrix`.

- [ ] **Step 5: Record external validation outcome**

If a run fails, preserve its output directory and report `failure_stage` from `execution_status.json`. Do not mark integration complete until all three pass; MaaS success cannot substitute for one-iflytek GPT success.

### Task 7: Final Diff and Optional Integration Commit

**Files:**
- Review all files listed in the File Map.

- [ ] **Step 1: Review the scoped diff**

```bash
git diff -- \
  .env.example \
  docker/astroncode/v3 \
  docs/local/deploy/export.astroncode.sh \
  docs/local/guide/linux-评测命令速查.md \
  docs/local/guide/macos-本地调试指南.md \
  docs/superpowers/plans/2026-07-30-astroncode-0.0.13-harness-image-integration.md \
  docs/superpowers/specs/2026-07-30-astroncode-0.0.13-harness-image-integration-design.md \
  script/build-astroncode-image.sh \
  src/agents/astroncode/runner.py \
  tests/test_astroncode_config.py \
  tests/test_astroncode_v3_image.py
```

Expected: no unrelated refactors, no secrets, and no changes to v1/v2 Dockerfiles.

- [ ] **Step 2: Scan the diff for credential-like values**

```bash
git diff --no-ext-diff -U0 \
  | rg '^\+[^+]' \
  | rg -n '(^|[^A-Za-z0-9])(sk-[A-Za-z0-9_-]{16,}|[A-Fa-f0-9]{24,}:[A-Za-z0-9+/=]{16,})'
```

Expected: no matches from newly added lines. Existing guide credentials must not be copied into new files or examples.

- [ ] **Step 3: Create a consolidated commit only when authorized**

If Tasks 1-3 were not committed separately and the user explicitly authorizes one commit:

```bash
git add \
  .env.example \
  docker/astroncode/v3 \
  docs/local/deploy/export.astroncode.sh \
  docs/local/guide/linux-评测命令速查.md \
  docs/local/guide/macos-本地调试指南.md \
  docs/superpowers/plans/2026-07-30-astroncode-0.0.13-harness-image-integration.md \
  docs/superpowers/specs/2026-07-30-astroncode-0.0.13-harness-image-integration-design.md \
  script/build-astroncode-image.sh \
  src/agents/astroncode/runner.py \
  tests/test_astroncode_config.py \
  tests/test_astroncode_v3_image.py
git commit -m "feat(astroncode): 集成0.0.13 Harness镜像"
```

Expected: commit succeeds with a Chinese Conventional Commits message and does not stage `back.env-bak`.
