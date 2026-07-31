# AstronCode models_base_url Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 AstronCode 0.0.13 的 MaaS、GPT 和 OpenRouter provider 统一生成可由环境变量覆盖的 `models_base_url`。

**Architecture:** `AstronCodeAgent` 构造时读取并快照 `ASTRON_MODELS_BASE_URL`，空值回退生产环境默认地址。配置渲染器将该快照值写入当前激活的任一 provider 表，保持 provider 路由和鉴权逻辑不变。

**Tech Stack:** Python 3、`unittest`、TOML、Docker Harness 运行配置

---

## File Structure

- Modify: `tests/test_astroncode_config.py` - 定义默认值、覆盖值、快照语义和三类 provider 输出的回归测试。
- Modify: `src/agents/astroncode/runner.py` - 解析模型目录地址并写入 AstronCode TOML。
- Modify: `.env.example` - 记录 `ASTRON_MODELS_BASE_URL` 配置入口及生产默认值。

### Task 1: 测试并实现公共模型目录地址

**Files:**
- Modify: `tests/test_astroncode_config.py`
- Modify: `src/agents/astroncode/runner.py`

- [ ] **Step 1: Write the failing tests**

在 `AstronCodeConfigTests` 中更新现有三类 provider 断言，并增加覆盖值测试：

```python
DEFAULT_MODELS_BASE_URL = (
    "https://astroncode-api-prod.xf-yun.com/"
    "api/v1/astroncode_webserver/config-v1"
)

def test_models_base_url_override_applies_to_all_providers(self) -> None:
    cases = (
        "openrouter/xopglm52",
        "openrouter/gpt-5.5",
        "openrouter/claude-4",
    )
    with patch.dict(
        os.environ,
        {
            "ASTRON_MODELS_BASE_URL": "https://catalog.example/config-v1",
            "ASTRONCODE_MODEL_PROVIDER": "",
        },
        clear=False,
    ):
        agent = self.make_agent()
        for model in cases:
            with self.subTest(model=model):
                config = self.parse_config(agent, model)
                provider = config["model_provider"]
                self.assertEqual(
                    config["model_providers"][provider]["models_base_url"],
                    "https://catalog.example/config-v1",
                )
```

在 `test_runtime_configuration_is_snapshotted_at_construction` 的初始环境中加入：

```python
"ASTRON_MODELS_BASE_URL": "https://initial.catalog/config-v1",
```

在构造后的变更环境中加入不同值，并断言：

```python
self.assertEqual(
    agent.models_base_url,
    "https://initial.catalog/config-v1",
)
```

将三个现有 provider 配置测试都断言：

```python
self.assertEqual(provider["models_base_url"], DEFAULT_MODELS_BASE_URL)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_astroncode_config -v
```

Expected: FAIL，缺少 `AstronCodeAgent.models_base_url`，且三个 provider TOML 均未完整提供 `models_base_url`。

- [ ] **Step 3: Write the minimal implementation**

在 `src/agents/astroncode/runner.py` 的 URL 常量区增加：

```python
DEFAULT_ASTRON_MODELS_BASE_URL = (
    "https://astroncode-api-prod.xf-yun.com/"
    "api/v1/astroncode_webserver/config-v1"
)
```

在 `AstronCodeAgent.__init__` 中快照配置：

```python
self.models_base_url = (
    os.environ.get("ASTRON_MODELS_BASE_URL", "").strip()
    or DEFAULT_ASTRON_MODELS_BASE_URL
)
```

在 `_render_codex_config` 的 `openrouter`、`one-iflytek` 和 `astron-spark` 三个 provider 表中分别加入：

```python
f"models_base_url = {toml_basic_string(self.models_base_url)}\n"
```

- [ ] **Step 4: Run focused tests to verify they pass**

Run:

```bash
uv run python -m unittest tests.test_astroncode_config -v
```

Expected: all tests PASS。

- [ ] **Step 5: Commit runtime behavior**

```bash
git add src/agents/astroncode/runner.py tests/test_astroncode_config.py
git commit -m "fix(astroncode): 补充统一模型目录地址配置"
```

### Task 2: 补充环境变量示例并执行回归验证

**Files:**
- Modify: `.env.example`
- Test: `tests/test_astroncode_config.py`
- Test: `tests/test_astroncode_v3_image.py`

- [ ] **Step 1: Document the environment variable**

在 `.env.example` 的 AstronCode provider 配置区增加：

```dotenv
# Optional override; defaults to the AstronCode production model catalog endpoint.
ASTRON_MODELS_BASE_URL=https://astroncode-api-prod.xf-yun.com/api/v1/astroncode_webserver/config-v1
```

- [ ] **Step 2: Run formatting and regression checks**

Run:

```bash
git diff --check
uv run python -m unittest tests.test_astroncode_config tests.test_astroncode_v3_image -v
uv run python -m compileall -q src/agents/astroncode tests/test_astroncode_config.py
```

Expected: `git diff --check` 无输出，所有测试 PASS，`compileall` 返回 0。

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git diff -- .env.example src/agents/astroncode/runner.py tests/test_astroncode_config.py
git status --short
```

Expected: 仅目标文件包含本功能改动；工作区原有的其他未提交文件保持不变。

- [ ] **Step 4: Commit environment documentation**

```bash
git add .env.example
git commit -m "docs(astroncode): 补充模型目录地址环境变量"
```
