# AstronCode v4 SearchAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建固定 AstronCode 0.0.13 且内置 SearchAgent 的 v0.4 Harness 镜像，并确保 Harness 重写模型配置后 Search、Fetch MCP 和 SearchBetter Skill 仍可用。

**Architecture:** v4 Dockerfile 从 Codex 基础镜像自包含安装 AstronCode 与 SearchAgent，并把安装器生成的纯 MCP TOML 保存到 `/opt/astroncode/search-agent.config.toml`。AstronCode Runner 在每次写动态模型配置前从任务容器读取该片段，以 `tomllib` 严格校验后同时追加到容器实际配置和宿主机脱敏配置；片段缺失兼容 v1-v3，片段存在但无效则提前失败。

**Tech Stack:** Docker、Bash、npm、SearchAgent updater、Python 3.11 `tomllib`、`unittest`、WildClawBench AstronCode Runner

---

## 文件职责

- Create: `docker/astroncode/v4/Dockerfile`：安装 AstronCode 0.0.13、SearchAgent、运行 doctor 并固化 MCP 配置片段。
- Create: `tests/test_astroncode_v4_image.py`：锁定 v4 Dockerfile 和当前构建脚本契约。
- Modify: `tests/test_astroncode_v3_image.py`：只保留 v3 Dockerfile 历史契约，将“当前默认构建脚本”测试移到 v4 测试文件。
- Modify: `script/build-astroncode-image.sh`：默认 variant/tag 切换到 v4/v0.4，支持 `SEARCH_UPDATER_VERSION`。
- Modify: `src/agents/astroncode/runner.py`：读取、校验、合并 SearchAgent MCP 配置片段，默认镜像切换到 v0.4。
- Modify: `tests/test_astroncode_config.py`：覆盖片段合并、缺失兼容、非法片段、安全边界和默认镜像。
- Modify: `.env.example`：AstronCode 默认镜像切换到 v0.4，并说明内置 SearchAgent。
- Modify (ignored local docs): `docs/local/deploy/export.astroncode.sh`：默认导出镜像切换到 v0.4。
- Modify (ignored local docs): `docs/local/guide/linux-评测命令速查.md`：所有 AstronCode v0.3 命令和离线包说明切换到 v0.4，补充 SearchAgent 验证说明。
- Modify (ignored local docs): `docs/local/guide/macos-本地调试指南.md`：所有 AstronCode v0.3 命令切换到 v0.4，补充 SearchAgent 验证说明。
- Modify (ignored local docs): `docs/local/guide/astroncode/astroncode-评测产物与trace结构说明.md`：更新示例镜像版本，避免产物说明继续引用 v0.3。

`docs/local/**` 被 `.gitignore` 的 `local` 规则忽略。本计划修改并验证这些工作区文档，但不使用 `git add -f` 改变仓库的本地文档管理边界。

### Task 1: 增加 v4 自包含镜像和构建入口

**Files:**
- Create: `tests/test_astroncode_v4_image.py`
- Modify: `tests/test_astroncode_v3_image.py`
- Create: `docker/astroncode/v4/Dockerfile`
- Modify: `script/build-astroncode-image.sh`

- [ ] **Step 1: 写 v4 Dockerfile 和构建脚本失败测试**

在 `tests/test_astroncode_v4_image.py` 中建立与 v3 测试相同的 Docker 指令归一化 helper，并增加以下明确断言：

```python
DOCKERFILE = REPO_ROOT / "docker" / "astroncode" / "v4" / "Dockerfile"
BUILD_SCRIPT = REPO_ROOT / "script" / "build-astroncode-image.sh"

def test_defaults_to_astron_code_0_0_13(self):
    self.assertIn("ARG ASTRON_CODE_VERSION=0.0.13", self.instruction_content)

def test_installs_search_agent_and_runs_full_doctor(self):
    self.assertIn("ARG SEARCH_UPDATER_VERSION=latest", self.instruction_content)
    self.assertIn(
        'npm install -g "@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}"',
        self.instruction_content,
    )
    self.assertIn("--foreground-scripts", self.instruction_content)
    self.assertIn("install-search", self.instruction_content)
    self.assertIn("install-search doctor --full", self.instruction_content)

def test_persists_validated_mcp_fragment(self):
    self.assertIn("/root/.acode/config.toml", self.instruction_content)
    self.assertIn("/opt/astroncode/search-agent.config.toml", self.instruction_content)
    self.assertIn("tomllib", self.instruction_content)
    self.assertIn("mcp_servers", self.instruction_content)

def test_build_script_defaults_to_v4(self):
    self.assertIn('IMAGE_TAG="${IMAGE_TAG:-v0.4}"', self.build_script)
    self.assertIn(
        'ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v4}"',
        self.build_script,
    )
    self.assertRegex(self.compact_build_script, r"v1\|v2\|v3\|v4")
    self.assertIn('SEARCH_UPDATER_VERSION', self.build_script)
```

把 `AstronCodeBuildScriptTest` 从 `tests/test_astroncode_v3_image.py` 移至新文件，并把默认值断言更新为 v4/v0.4；v3 文件只校验旧 Dockerfile 未被修改。

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
uv run python -m unittest tests.test_astroncode_v3_image tests.test_astroncode_v4_image -v
```

Expected: FAIL，原因包括缺少 `docker/astroncode/v4/Dockerfile`，且构建脚本仍默认 v3/v0.3。

- [ ] **Step 3: 实现 v4 Dockerfile**

创建以下自包含安装流程；Python 校验必须发生在复制片段之前：

```dockerfile
# AstronCode 0.0.13 evaluation image with SearchAgent.
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.13
ARG SEARCH_UPDATER_VERSION=latest
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true \
    && npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version \
    && rm -rf /root/.acode \
    && install -d -m 700 /root/.acode \
    && npm install -g \
      "@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}" \
      --foreground-scripts \
      --registry="${NPM_REGISTRY}" \
    && install-search \
    && install-search doctor --full \
    && python3 -c 'import pathlib,tomllib; p=pathlib.Path("/root/.acode/config.toml"); d=tomllib.loads(p.read_text(encoding="utf-8")); assert set(d) == {"mcp_servers"} and isinstance(d["mcp_servers"], dict) and d["mcp_servers"], "SearchAgent config must contain only non-empty mcp_servers"' \
    && install -d -m 755 /opt/astroncode \
    && install -m 444 /root/.acode/config.toml \
      /opt/astroncode/search-agent.config.toml
```

- [ ] **Step 4: 更新构建脚本**

将默认值和白名单改为：

```bash
IMAGE_TAG="${IMAGE_TAG:-v0.4}"
ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v4}"

case "${ASTRONCODE_DOCKER_VARIANT}" in
  v1|v2|v3|v4) ;;
```

在现有 `ASTRON_CODE_VERSION` build arg 后追加：

```bash
if [[ -n "${SEARCH_UPDATER_VERSION:-}" ]]; then
  BUILD_ARGS+=(--build-arg "SEARCH_UPDATER_VERSION=${SEARCH_UPDATER_VERSION}")
fi
```

更新脚本头部注释，声明默认 v4，并保留 v1-v3 覆盖示例。

- [ ] **Step 5: 运行镜像静态测试确认 GREEN**

Run:

```bash
uv run python -m unittest tests.test_astroncode_v3_image tests.test_astroncode_v4_image -v
bash -n script/build-astroncode-image.sh
git diff --check
```

Expected: 两个测试模块全部 PASS；Bash 语法和 diff 检查返回 0。

- [ ] **Step 6: 提交镜像与构建入口**

```bash
git add docker/astroncode/v4/Dockerfile \
  script/build-astroncode-image.sh \
  tests/test_astroncode_v3_image.py \
  tests/test_astroncode_v4_image.py
git commit -m "feat(astroncode): 增加 v4 SearchAgent 评测镜像"
```

### Task 2: 合并 SearchAgent MCP 配置片段

**Files:**
- Modify: `tests/test_astroncode_config.py`
- Modify: `src/agents/astroncode/runner.py`

- [ ] **Step 1: 写 Runner 配置片段失败测试**

增加固定片段和以下测试组：

```python
SEARCH_AGENT_CONFIG = """[mcp_servers.web-search]
command = "python3"
args = ["/root/.acode/mcp/web-search-mcp/server.py"]

[mcp_servers.scrapling]
command = "scrapling"
"""

@patch("src.agents.astroncode.runner.subprocess.run")
def test_config_write_merges_search_agent_fragment(self, run_mock) -> None:
    run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
    with tempfile.TemporaryDirectory() as tmp:
        agent = self.make_agent()
        with patch.object(
            agent, "_load_search_agent_config", return_value=SEARCH_AGENT_CONFIG
        ):
            agent._write_codex_config(
                "search-agent", "openrouter/claude-4", None, None, Path(tmp)
            )
        host_config = (Path(tmp) / "config.toml").read_text(encoding="utf-8")

    self.assertEqual(
        set(tomllib.loads(host_config)["mcp_servers"]),
        {"web-search", "scrapling"},
    )
    self.assertIn(SEARCH_AGENT_CONFIG.strip(), run_mock.call_args.kwargs["input"])
```

直接测试 `_load_search_agent_config()` 的矩阵：

- rc=44：返回空字符串，代表旧镜像中片段不存在。
- rc=0 且为合法的两个 MCP table：返回规范化为单个末尾换行的原文。
- rc=0 且 stdout 为空：抛出 `RuntimeError`。
- rc=0 且 TOML 语法非法：抛出 `RuntimeError`。
- rc=0 且顶层为 `model = "x"`：抛出 `RuntimeError`。
- rc=0 且 `mcp_servers = {}`：抛出 `RuntimeError`。
- rc=5 且 stderr 含测试 secret：错误消息包含路径和 rc，不包含 stderr 或 secret。

扩展现有 bearer token 测试，令 `_load_search_agent_config()` 返回合法片段，并确认 secret 不出现在宿主机配置、Docker 命令参数、日志和异常中。

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
uv run python -m unittest tests.test_astroncode_config -v
```

Expected: FAIL，原因是 `_load_search_agent_config` 和固定片段路径尚未实现。

- [ ] **Step 3: 实现片段读取与校验**

在 `runner.py` 导入 `tomllib`，增加：

```python
ASTRONCODE_SEARCH_AGENT_CONFIG_PATH = (
    "/opt/astroncode/search-agent.config.toml"
)

def _load_search_agent_config(self, task_id: str) -> str:
    path = shlex.quote(ASTRONCODE_SEARCH_AGENT_CONFIG_PATH)
    result = subprocess.run(
        [
            "docker", "exec", task_id, "/bin/sh", "-c",
            f"if [ ! -e {path} ]; then exit 44; fi; test -f {path} && cat {path}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 44:
        return ""
    if result.returncode != 0:
        raise RuntimeError(
            "AstronCode SearchAgent config read failed "
            f"at {ASTRONCODE_SEARCH_AGENT_CONFIG_PATH} (rc={result.returncode})"
        )
    try:
        parsed = tomllib.loads(result.stdout)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError("AstronCode SearchAgent config is invalid TOML") from exc
    if (
        set(parsed) != {"mcp_servers"}
        or not isinstance(parsed["mcp_servers"], dict)
        or not parsed["mcp_servers"]
    ):
        raise RuntimeError(
            "AstronCode SearchAgent config must contain only non-empty mcp_servers"
        )
    return result.stdout.rstrip() + "\n"
```

异常消息不得拼接 `stdout` 或 `stderr`。

- [ ] **Step 4: 在写配置流程中合并片段**

在 `_write_codex_config()` 中先读取一次片段，再复用于实际配置和脱敏配置：

```python
search_agent_config = self._load_search_agent_config(task_id)

def append_fragment(config: str) -> str:
    if not search_agent_config:
        return config
    return config.rstrip() + "\n\n" + search_agent_config

config_toml = append_fragment(
    self._render_codex_config(
        model=model,
        reasoning_effort=reasoning_effort,
        wire_api=wire_api,
        provider_api_key=provider_api_key,
        redact_secrets=False,
    )
)
debug_config_toml = append_fragment(
    self._render_codex_config(
        model=model,
        reasoning_effort=reasoning_effort,
        wire_api=wire_api,
        provider_api_key=provider_api_key,
        redact_secrets=True,
    )
)
```

保留已有 `umask 077`、截断写入和 `chmod 600`。片段读取失败必须发生在宿主机 `config.toml` 写入前。

- [ ] **Step 5: 运行 Runner 测试确认 GREEN**

Run:

```bash
uv run python -m unittest tests.test_astroncode_config -v
git diff --check
```

Expected: 全部 PASS，且无 whitespace error。

- [ ] **Step 6: 提交 Runner 改造**

```bash
git add src/agents/astroncode/runner.py tests/test_astroncode_config.py
git commit -m "feat(astroncode): 保留 SearchAgent MCP 配置"
```

### Task 3: 切换默认镜像和评测文档

**Files:**
- Modify: `tests/test_astroncode_config.py`
- Modify: `src/agents/astroncode/runner.py`
- Modify: `.env.example`
- Modify (ignored): `docs/local/deploy/export.astroncode.sh`
- Modify (ignored): `docs/local/guide/linux-评测命令速查.md`
- Modify (ignored): `docs/local/guide/macos-本地调试指南.md`
- Modify (ignored): `docs/local/guide/astroncode/astroncode-评测产物与trace结构说明.md`

- [ ] **Step 1: 将默认镜像测试改为 v0.4 并确认 RED**

```python
def test_default_image_is_v0_4(self) -> None:
    with patch.dict(os.environ, {"DOCKER_IMAGE_ASTRONCODE": ""}, clear=False):
        self.assertEqual(
            self.make_agent().image,
            "wildclawbench-astroncode-ubuntu:v0.4",
        )
```

Run:

```bash
uv run python -m unittest \
  tests.test_astroncode_config.AstronCodeConfigTests.test_default_image_is_v0_4 -v
```

Expected: FAIL，实际值仍为 v0.3。

- [ ] **Step 2: 切换代码和环境示例默认值**

将 `runner.py` 的回退镜像和 `.env.example` 改为：

```text
wildclawbench-astroncode-ubuntu:v0.4
```

在 `.env.example` 镜像行附近增加注释，说明 v0.4 固定 AstronCode 0.0.13 并内置 SearchAgent。

- [ ] **Step 3: 更新被忽略的本地部署和评测文档**

对四个 `docs/local/**` 文件只在 AstronCode 上下文中执行以下机械替换：

```text
wildclawbench-astroncode-ubuntu:v0.3
  -> wildclawbench-astroncode-ubuntu:v0.4
wildclawbench-astroncode-ubuntu_v0.3.tar.gz
  -> wildclawbench-astroncode-ubuntu_v0.4.tar.gz
AstronCode 0.0.13 / v0.3
  -> AstronCode 0.0.13 / v0.4
```

在 Linux §2 和 macOS §4.2 的 AstronCode 说明中各加入同一事实：v0.4 内置 Search、Fetch MCP 和 SearchBetter Skill，现有命令无需增加 SearchAgent 开关；结果目录的脱敏 `config.toml` 可核对 `[mcp_servers.*]`。

更新 `export.astroncode.sh` 头部注释，说明 v0.4 内置 SearchAgent，并保留 v3 回退示例。

- [ ] **Step 4: 验证默认值和文档一致**

Run:

```bash
uv run python -m unittest tests.test_astroncode_config -v
rg -n "wildclawbench-astroncode-ubuntu:v0\.3|wildclawbench-astroncode-ubuntu_v0\.3" \
  src/agents/astroncode/runner.py \
  .env.example \
  script/build-astroncode-image.sh \
  docs/local/deploy/export.astroncode.sh \
  docs/local/guide/linux-评测命令速查.md \
  docs/local/guide/macos-本地调试指南.md \
  docs/local/guide/astroncode/astroncode-评测产物与trace结构说明.md
```

Expected: 单测 PASS；`rg` 无输出。历史 `docker/astroncode/v3/Dockerfile` 和历史设计/计划文档不参与该检查。

- [ ] **Step 5: 提交可跟踪的默认值改动**

```bash
git add .env.example src/agents/astroncode/runner.py tests/test_astroncode_config.py
git commit -m "chore(astroncode): 默认使用 v0.4 Harness 镜像"
```

本步骤不强制暂存被忽略的 `docs/local/**`。最终交付说明应明确这些文档已在当前工作区更新但未进入 Git。

### Task 4: 完整验证和真实镜像验收

**Files:**
- Verify only: all files changed in Tasks 1-3
- Generated (ignored): `Images/wildclawbench-astroncode-ubuntu_v0.4.tar.gz`

- [ ] **Step 1: 运行聚焦测试和完整单测**

```bash
uv run python -m unittest \
  tests.test_astroncode_config \
  tests.test_astroncode_v3_image \
  tests.test_astroncode_v4_image -v
uv run python -m unittest discover -s tests -p 'test_*.py'
bash -n script/build-astroncode-image.sh
git diff --check
```

Expected: 所有测试 PASS，Bash 和 diff 检查返回 0。

- [ ] **Step 2: 构建并导出 v0.4 镜像**

```bash
bash script/build-astroncode-image.sh
```

Expected: Docker build 成功，最后输出镜像标签 `wildclawbench-astroncode-ubuntu:v0.4` 和离线包 `Images/wildclawbench-astroncode-ubuntu_v0.4.tar.gz`。

- [ ] **Step 3: 验证容器内版本、doctor、Skill 和片段结构**

```bash
docker run --rm wildclawbench-astroncode-ubuntu:v0.4 astron-code --version
docker run --rm wildclawbench-astroncode-ubuntu:v0.4 install-search doctor --full
docker run --rm wildclawbench-astroncode-ubuntu:v0.4 \
  python3 -c 'import pathlib,tomllib; d=tomllib.loads(pathlib.Path("/opt/astroncode/search-agent.config.toml").read_text()); assert set(d) == {"mcp_servers"} and d["mcp_servers"]; assert pathlib.Path("/root/.acode/skills/search-better").is_dir(); print(sorted(d["mcp_servers"]))'
```

Expected: 版本包含 `0.0.13`；doctor 全部通过；最后一条输出非空 MCP server 名称列表。

- [ ] **Step 4: 验证离线包可读**

```bash
gzip -t Images/wildclawbench-astroncode-ubuntu_v0.4.tar.gz
docker image inspect wildclawbench-astroncode-ubuntu:v0.4 \
  --format '{{.RepoTags}} {{.Architecture}}'
```

Expected: gzip 校验返回 0，镜像 inspect 输出 v0.4 标签和当前架构。

- [ ] **Step 5: 在已有评测凭证环境下运行搜索冒烟**

```bash
D=/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out_debug/smoke/round1/xopglm52-searchagent
mkdir -p "$D/astroncode"
OUTPUT_SUBDIR="$D" \
DOCKER_IMAGE_ASTRONCODE='wildclawbench-astroncode-ubuntu:v0.4' \
uv run eval/run_batch.py --agent-backend astroncode --thinking high \
  --task tasks/04_Search_Retrieval/04_Search_Retrieval_task_1_google_scholar_search.md \
  --model openrouter/xopglm52
```

前提是当前 shell 已导出模型和裁判所需凭证。Expected: run 产生 `score.json`、`execution_status.json`、`usage.json`、trace/session 产物；脱敏 `config.toml` 包含 `mcp_servers`；日志没有 MCP 初始化失败或 Search/Fetch 工具不可用错误。外部模型、裁判或搜索服务不可达时记录具体环境阻塞，不把该结果表述为代码验收通过。

- [ ] **Step 6: 最终范围检查**

```bash
git status --short
git log --oneline -5
git diff --check
```

Expected: `back.env-bak`、离线镜像和其他既有无关文件未进入提交；提交信息均为中文 Conventional Commits；没有遗漏的可跟踪代码改动。
