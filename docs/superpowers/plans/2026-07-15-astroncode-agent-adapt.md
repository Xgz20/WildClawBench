# AstronCode 评测适配实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 AstronCode 评测镜像（支持离线分发），并为 WildClawBench 新增独立的 `astroncode` agent 后端，同时保持 codex 后端零改动。

**Architecture:** 镜像层在 `wildclawbench-codex-ubuntu:v0.0` 之上叠加一层 npm 全局安装 `@iflytek/astron-code`；代码层将 `src/agents/codex/` 整体复制为 `src/agents/astroncode/` 后做命名/常量/CLI 改造（另起炉灶，不共享代码），再接入 `cli_args.py` 与 `run_batch.py`。

**Tech Stack:** Docker、npm（iflytek 内网 registry）、Python 3.10+（现有 WildClawBench 框架）

## Global Constraints

- codex 链路零改动：`src/agents/codex/` 目录不得出现在 git diff 中
- 镜像命名：`wildclawbench-astroncode-ubuntu:v0.0`，离线 tar 输出到 `Images/wildclawbench-astroncode-ubuntu_v0.0.tar`
- AstronCode 包版本固定：`@iflytek/astron-code@0.0.5-benchmark-adapt.10`
- 内网 registry：`https://depend.iflytek.com/artifactory/api/npm/npm-repo/`
- 环境变量前缀：镜像用 `DOCKER_IMAGE_ASTRONCODE`，调参用 `ASTRONCODE_*`（与 `CODEX_*` 并行，互不影响）
- 本仓库无单测框架，验证以命令级冒烟为准（import 检查、`--help`、容器内命令、最小任务运行）

---

### Task 1: AstronCode 镜像构建与容器实测

**Files:**
- Create: `docker/astroncode/Dockerfile`
- Create: `script/build-astroncode-image.sh`

**Interfaces:**
- Produces: 本地镜像 `wildclawbench-astroncode-ubuntu:v0.0`、离线包 `Images/wildclawbench-astroncode-ubuntu_v0.0.tar`；并产出容器实测结论（`astron-code` 的配置 home 目录、sessions 路径、`exec` 子命令参数兼容性），供 Task 2 确定常量。

- [ ] **Step 1: 写 Dockerfile**

```dockerfile
# docker/astroncode/Dockerfile
# AstronCode 评测镜像：在 codex 评测镜像之上叠加 @iflytek/astron-code CLI。
# 构建需要访问 iflytek 内网 npm registry；离线分发通过 docker save 出 tar。
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.5-benchmark-adapt.10
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version
```

- [ ] **Step 2: 写构建脚本**

```bash
#!/usr/bin/env bash
# script/build-astroncode-image.sh
# 构建 AstronCode 评测镜像并导出离线 tar 到 Images/。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="wildclawbench-astroncode-ubuntu"
IMAGE_TAG="${IMAGE_TAG:-v0.0}"
TAR_PATH="${REPO_ROOT}/Images/${IMAGE_NAME}_${IMAGE_TAG}.tar"

docker build \
  -f "${REPO_ROOT}/docker/astroncode/Dockerfile" \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  "${REPO_ROOT}/docker/astroncode"

mkdir -p "${REPO_ROOT}/Images"
docker save -o "${TAR_PATH}" "${IMAGE_NAME}:${IMAGE_TAG}"
echo "OK: ${IMAGE_NAME}:${IMAGE_TAG} -> ${TAR_PATH}"
```

然后 `chmod +x script/build-astroncode-image.sh`。

- [ ] **Step 3: 构建镜像**

Run: `bash script/build-astroncode-image.sh`
Expected: 构建成功，末行输出 `OK: wildclawbench-astroncode-ubuntu:v0.0 -> .../Images/wildclawbench-astroncode-ubuntu_v0.0.tar`。
若 npm install 因网络失败（Connection reset），停下来请用户接入内网/VPN 后重试。

- [ ] **Step 4: 容器实测，确定 Task 2 所需常量**

Run:
```bash
docker run --rm wildclawbench-astroncode-ubuntu:v0.0 /bin/bash -c '
  astron-code --version
  command -v astron-code
  astron-code exec --help 2>&1 | head -30
'
```
再跑一次最小 exec（可不配 key，看它把 session/config 写到哪里）：
```bash
docker run --rm wildclawbench-astroncode-ubuntu:v0.0 /bin/bash -c '
  echo hi | timeout 30 astron-code exec --skip-git-repo-check - >/dev/null 2>&1 || true
  ls -la /root/.codex 2>/dev/null; ls -la /root/.astron-code 2>/dev/null
'
```
Expected 记录三件事：
1. 版本 = `0.0.5-benchmark-adapt.10`
2. HOME 目录是 `/root/.codex` 还是 `/root/.astron-code`（决定 Task 2 的 `ASTRONCODE_HOME`）
3. `exec` 子命令是否兼容 `--skip-git-repo-check` / `--cd` / stdin 传 prompt

- [ ] **Step 5: Commit**

```bash
git add docker/astroncode/Dockerfile script/build-astroncode-image.sh
git commit -m "feat: AstronCode 评测镜像构建（Dockerfile + 离线导出脚本）"
```

---

### Task 2: 新增 src/agents/astroncode/ 后端（复制改造）

**Files:**
- Create: `src/agents/astroncode/__init__.py`（复制自 `src/agents/codex/__init__.py`）
- Create: `src/agents/astroncode/runner.py`（复制自 `src/agents/codex/runner.py`）
- Create: `src/agents/astroncode/backend.py`（复制自 `src/agents/codex/backend.py`）

**Interfaces:**
- Consumes: Task 1 实测出的 HOME 目录常量（下文以 `/root/.codex` 为默认假设；若实测为 `/root/.astron-code`，替换 `ASTRONCODE_HOME` 的值即可）
- Produces: `AstronCodeAgent` 类（构造签名与 `CodexAgent` 相同），供 Task 3 在 `run_batch.py` 中实例化；`from src.agents.astroncode import AstronCodeAgent` 可用

- [ ] **Step 1: 复制目录**

```bash
cp -r src/agents/codex src/agents/astroncode
rm -rf src/agents/astroncode/__pycache__
```

- [ ] **Step 2: 改造 runner.py**

对 `src/agents/astroncode/runner.py` 做以下精确替换（Edit 逐条执行）：

1. import 行：
   - `from src.agents.codex.backend import (` → `from src.agents.astroncode.backend import (`
   - `CODEX_PROMPT_PATH,` / `prepare_codex_prompt,` 保持名字不变（backend 内部同名导出）
2. 顶部常量块整体替换：

```python
ASTRONCODE_HOME = "/root/.codex"  # Task 1 实测：astron-code 沿用 codex 的配置目录（若实测不同则改这里）
ASTRONCODE_SESSIONS_DIR = f"{ASTRONCODE_HOME}/sessions"
ASTRONCODE_CONFIG_PATH = f"{ASTRONCODE_HOME}/config.toml"
ASTRONCODE_SKILLS_DIR = f"{ASTRONCODE_HOME}/skills"
```

   并全文将 `CODEX_HOME` → `ASTRONCODE_HOME`、`CODEX_SESSIONS_DIR` → `ASTRONCODE_SESSIONS_DIR`、`CODEX_CONFIG_PATH` → `ASTRONCODE_CONFIG_PATH`、`CODEX_SKILLS_DIR` → `ASTRONCODE_SKILLS_DIR`。
3. 类与镜像：
   - `class CodexAgent(BaseAgent):` → `class AstronCodeAgent(BaseAgent):`
   - `os.environ.get("DOCKER_IMAGE_CODEX") or "wildclawbench-codex-ubuntu:v0.0"` → `os.environ.get("DOCKER_IMAGE_ASTRONCODE") or "wildclawbench-astroncode-ubuntu:v0.0"`
4. CLI 命令：
   - `_build_exec_command` 中 `codex exec --skip-git-repo-check --cd /tmp_workspace -` → `astron-code exec --skip-git-repo-check --cd /tmp_workspace -`
   - `_terminate_codex_processes` 中两处 `pkill ... -f 'codex exec'` → `pkill ... -f 'astron-code exec'`
5. 环境变量旋钮：
   - `CODEX_REASONING_EFFORT` → `ASTRONCODE_REASONING_EFFORT`
   - `CODEX_WIRE_API` → `ASTRONCODE_WIRE_API`
   - `_estimate_cost` 中 4 个 `CODEX_*_PRICE_PER_MTOK` → `ASTRONCODE_*_PRICE_PER_MTOK`
6. 日志/报错文案：字符串中的 `Codex` → `AstronCode`（如 "Codex timed out"、"Codex container startup failed" 等），保持结构不变。
7. `CODEX_LOG_NOISE_MARKERS` 重命名为 `ASTRONCODE_LOG_NOISE_MARKERS`（内容不变）。

- [ ] **Step 3: 改造 backend.py**

对 `src/agents/astroncode/backend.py`：
1. `DEFAULT_CODEX_NPM_PACKAGE` 默认值 `@openai/codex` → `@iflytek/astron-code`；env 名 `CODEX_NPM_PACKAGE` → `ASTRONCODE_NPM_PACKAGE`
2. `DEFAULT_CODEX_NPM_VERSION` 默认值 `0.117.0` → `0.0.5-benchmark-adapt.10`；env 名 `CODEX_NPM_VERSION` → `ASTRONCODE_NPM_VERSION`
3. `build_codex_bootstrap_command` 与 `build_codex_exec_command` 中的 `codex` 可执行名 → `astron-code`（`command -v codex` → `command -v astron-code`）
4. 其余函数名（`prepare_codex_prompt`、`CODEX_PROMPT_PATH` 等）保持不变——runner 按原名 import，避免无谓的接口扩散

- [ ] **Step 4: 改造 __init__.py**

```python
from src.agents.astroncode.runner import AstronCodeAgent

__all__ = ["AstronCodeAgent"]
```

- [ ] **Step 5: 验证 import 与残留检查**

Run:
```bash
python3 -c "from src.agents.astroncode import AstronCodeAgent; a=AstronCodeAgent(); print(a.image)"
grep -n "CodexAgent\|DOCKER_IMAGE_CODEX\|'codex exec'\|\"codex exec\"" src/agents/astroncode/*.py
```
Expected: 第一条输出 `wildclawbench-astroncode-ubuntu:v0.0`；第二条 grep 无输出（无 codex 残留标识符）。

- [ ] **Step 6: Commit**

```bash
git add src/agents/astroncode
git commit -m "feat: 新增 astroncode agent 后端（独立于 codex）"
```

---

### Task 3: 接入 cli_args 与 run_batch

**Files:**
- Modify: `src/utils/cli_args.py:23`（`--agent-backend` choices）
- Modify: `eval/run_batch.py:19`（import）、`eval/run_batch.py:243`、`eval/run_batch.py:280`（isinstance 判断）、`eval/run_batch.py:316-317`（实例化分支）
- Modify: `script/run.sh`（usage 文案 + case 分支）

**Interfaces:**
- Consumes: `from src.agents.astroncode import AstronCodeAgent`（Task 2）
- Produces: `--agent-backend astroncode` 全链路可用

- [ ] **Step 1: cli_args.py 增加 choice**

```python
choices=["openclaw", "claudecode", "codex", "hermesagent", "astroncode"],
```

- [ ] **Step 2: run_batch.py 接入**

```python
from src.agents.astroncode import AstronCodeAgent
```

isinstance 两处（保持原语义，仅扩元组）：

```python
grade_on_error = isinstance(backend, (CodexAgent, ClaudeCodeAgent, AstronCodeAgent))
```

```python
include_workspace_changes=isinstance(backend, (CodexAgent, ClaudeCodeAgent, AstronCodeAgent)),
```

实例化分支（加在 `elif args.agent_backend == "codex":` 之后）：

```python
elif args.agent_backend == "astroncode":
    backend = AstronCodeAgent()
```

- [ ] **Step 3: script/run.sh 增加分支**

usage 段增加一行 `bash script/run.sh astroncode  [run_batch args...]`，case 中 `hermesagent)` 分支后新增：

```bash
  astroncode)
    exec python3 eval/run_batch.py --agent-backend astroncode "$@"
    ;;
```

并把 `Expected one of: ...` 文案补上 `astroncode`。

- [ ] **Step 4: 验证**

Run:
```bash
python3 -c "import ast,sys; ast.parse(open('eval/run_batch.py').read()); ast.parse(open('src/utils/cli_args.py').read()); print('syntax ok')"
python3 eval/run_batch.py --help 2>&1 | grep -o "astroncode" | head -1
bash script/run.sh 2>&1 | grep astroncode
```
Expected: `syntax ok`；`astroncode` 出现在 run_batch help 与 run.sh usage 中。

- [ ] **Step 5: Commit**

```bash
git add src/utils/cli_args.py eval/run_batch.py script/run.sh
git commit -m "feat: run_batch/cli_args/run.sh 接入 astroncode 后端"
```

---

### Task 4: 部署环境脚本 export.astroncode.sh

**Files:**
- Create: `docs/local/deploy/export.astroncode.sh`（参照 `docs/local/deploy/export.codex.sh`）

**Interfaces:**
- Produces: `source docs/local/deploy/export.astroncode.sh` 后可直接跑 astroncode 评测

- [ ] **Step 1: 写脚本**

以 `docs/local/deploy/export.codex.sh` 为模板复制生成（保留其中已有的模型/裁判变量原值，不在本计划文档中重复粘贴密钥）：

```bash
cp docs/local/deploy/export.codex.sh docs/local/deploy/export.astroncode.sh
```

然后做两处修改：
1. 头部注释 `Codex Harness` → `AstronCode Harness`，用法行改为 `source docs/local/deploy/export.astroncode.sh`
2. `export DOCKER_IMAGE_CODEX='wildclawbench-codex-ubuntu:v0.0'` → `export DOCKER_IMAGE_ASTRONCODE='wildclawbench-astroncode-ubuntu:v0.0'`

- [ ] **Step 2: Commit**

```bash
git add docs/local/deploy/export.astroncode.sh
git commit -m "feat: astroncode 部署环境变量脚本"
```

---

### Task 5: 冒烟验证与回归检查

**Files:**
- 无新增文件（运行验证）

**Interfaces:**
- Consumes: Task 1 镜像、Task 2-4 代码

- [ ] **Step 1: codex 零改动回归**

Run: `git diff main -- src/agents/codex/ | head -5` 与 `git log --oneline main..HEAD -- src/agents/codex/`
Expected: 均无输出（codex 目录零改动）。

- [ ] **Step 2: 最小任务冒烟**

```bash
source docs/local/deploy/export.astroncode.sh
bash script/run.sh astroncode \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xsparkx2flash
```
（与 `docs/local/guide/wildclawbench-codex-评测指南.md` §2.1 的 codex 冒烟同参数。）
Expected: 任务 output 目录产出 `agent.log`、`execution_status.json`（status=finished）、`chat.jsonl`、`codex_sessions/`（usage 非零）、`chat_openclaw.jsonl`。
若模型 API 不可达，降级验证：容器能启动、config.toml 正确写入、`astron-code exec` 进程被正确拉起并在 agent.log 留痕。

- [ ] **Step 3: Commit（如冒烟过程中有修正）**

```bash
git add -A && git commit -m "fix: astroncode 冒烟修正"
```
