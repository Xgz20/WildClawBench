# AstronCode 评测适配设计（镜像 + Agent 后端）

日期：2026-07-15
状态：已确认（用户批准）

## 背景

AstronCode 是基于 OpenAI Codex CLI 二次开发的项目（当前仅改了命令名 `codex` → `astron-code`，其余行为与 Codex 0.121 基本一致），通过 iflytek 内网 npm registry 分发：

```bash
npm install -g @iflytek/astron-code@0.0.5-benchmark-adapt.10 \
  --registry=https://depend.iflytek.com/artifactory/api/npm/npm-repo/
```

目标：让 WildClawBench 可以用 AstronCode 作为被评测 agent，同时**完整保留**现有 Codex 评测能力（不是二选一）。

## 决策记录

| 决策点 | 结论 | 理由 |
| --- | --- | --- |
| 代码改造方式 | 独立复制 `src/agents/astroncode/`（另起炉灶） | 完全不碰已验证的 codex 链路，零回归风险；AstronCode 后续演进自由 |
| 包获取方式 | docker build 时直连内网 registry | 构建机可达内网；离线分发靠 `docker save` 出 tar |
| 镜像基底 | `FROM wildclawbench-codex-ubuntu:v0.0` | 复用 conda/playwright/node20 全套评测环境，只叠加一层 npm 安装 |

## 1. 镜像构建

- 新增 `docker/astroncode/Dockerfile`：
  - `FROM wildclawbench-codex-ubuntu:v0.0`
  - `npm install -g @iflytek/astron-code@0.0.5-benchmark-adapt.10 --registry=<内网源>`
  - 末尾 `astron-code --version` 自校验
  - 保留镜像内原有 codex CLI（互不干扰）
- 新增 `script/build-astroncode-image.sh`：
  - 构建 `wildclawbench-astroncode-ubuntu:v0.0`
  - `docker save` 导出到 `Images/wildclawbench-astroncode-ubuntu_v0.0.tar`（与现有 tar 分发模式一致）
- 构建成功后进容器实测：`astron-code exec` 用法、配置目录（`~/.codex` 还是 `~/.astron-code`）、sessions 落盘路径，以实测结果修正代码侧常量。

## 2. 代码适配

- 新增 `src/agents/astroncode/`（`__init__.py` / `runner.py` / `backend.py`），从 `src/agents/codex/` 复制后改造：
  - 类名 `AstronCodeAgent`；CLI 调用 `astron-code exec ...`
  - 路径常量（HOME / sessions / config.toml）按容器实测调整
  - 默认镜像 `wildclawbench-astroncode-ubuntu:v0.0`，镜像环境变量 `DOCKER_IMAGE_ASTRONCODE`
  - 调参环境变量改名：`ASTRONCODE_REASONING_EFFORT`、`ASTRONCODE_WIRE_API`、`ASTRONCODE_*_PRICE_PER_MTOK` 等
  - OpenClaw transcript shim、usage 统计、image helper 逻辑原样保留
- 接入点：
  - `src/utils/cli_args.py`：`--agent-backend` choices 增加 `astroncode`
  - `eval/run_batch.py`：import `AstronCodeAgent` + 实例化分支；`grade_on_error` / `include_workspace_changes` 的 isinstance 判断加入 `AstronCodeAgent`
- 新增 `docs/local/deploy/export.astroncode.sh`（参照 `export.codex.sh`，镜像变量换为 `DOCKER_IMAGE_ASTRONCODE`）

## 3. 验证

1. 镜像：容器内 `astron-code --version` 输出 `0.0.5-benchmark-adapt.10`
2. 链路：`--agent-backend astroncode` 跑最小任务冒烟，确认 `agent.log`、`chat.jsonl`、usage、openclaw shim 正常产出
3. 回归：`git diff` 不含 `src/agents/codex/`，codex 路径零改动

## 风险与备注

- 若 astron-code 的配置目录/会话目录与 codex 不同（如 `~/.astron-code`），只需改 astroncode runner 顶部常量，不影响其他逻辑。
- 构建机到内网 registry 的连通性是构建前提；主机 shell 当前直连失败（Connection reset），docker build 时如同样失败，需要用户接入 VPN/内网后重试。
