# MiMoCode 镜像更新日志

## v0.1 · CLI 0.1.15（2026-09-24）

新增 `wildclawbench-mimocode-ubuntu:v0.1`，使用 `v2/` 构建上下文，通过 npm
固定安装 `@mimo-ai/cli@0.1.15`。基础镜像继续为 `wildclawbench-codex-ubuntu:v0.0`，
三协议配置、非交互执行、JSONL/SQLite 采集和 usage 口径不变。
默认版本、runner 默认镜像及 Linux/macOS 本地命令同步切换到 `v0.1`。

升级原因：2026-09-24 实际查询官方 npm 与 npmmirror，版本列表只含 `0.1.15`；
官方 `@mimo-ai/cli/0.1.14` 返回 404，`0.1.15` 返回 200。此事实表示旧版本当前
不能通过 npm 重新安装，不推断其撤下原因。升级不使用 `latest` 浮动版本。

旧 `v0.0` 条目和 `v1/` 文件保留，明确 `buildable=false`。显式请求旧版构建时，
脚本提前失败并提示使用已有离线镜像或构建 `v0.1`，不会静默把旧 tag 替换为新 CLI。

构建与验证命令：

```bash
NPM_REGISTRY=https://registry.npmmirror.com \
bash docker/mimocode/build.sh --version v0.1 --skip-save
docker run --rm --entrypoint mimo wildclawbench-mimocode-ubuntu:v0.1 --version
WCB_MIMOCODE_DOCKER_TESTS=1 uv run python -m unittest tests.test_mimocode_wire -v
```

验收结果（macOS Docker Desktop，Linux amd64 容器）：

- npm 安装与 CLI 版本检查成功；镜像 ID 为
  `sha256:a05a088c31894bc7d3b0e397e358f9b8153c40980d7b7324e1bdd16cbd681e75`。
- Dockerfile build check 无告警；102 项相关回归测试通过。
- 真实 CLI + 本地模拟服务的 Responses、Chat Completions、Anthropic Messages
  三协议工具闭环均通过；此结果不是远端模型全量评测。
- GLM5.2 / MaaS `/v2` / Chat 冒烟 run `xopglm52_20260924_1457_2943ce`：
  `finished`、退出码 0、CLI 0.1.15，用时 168.70 秒，分数 0.9613；20 次 Slack get，0 次 send。
- 裁判审计为 5 次成功请求，requested/returned 均为 `claude-opus-5`，Anthropic Messages；
  `anomalies.json` 为 PASS，未报告异常。
- 原生 JSONL 40 行，转换会话 32 行；SQLite quick_check=ok，2 个会话、22 条消息、99 个 part。
  usage 汇总主会话及后代会话 19 个已完成步骤：input 71470、output 8560、cache read 485888，
  total/provider total 均为 565918。统计范围内 `usage_complete=true`，费用仍由报告定价层计算。

产物位于本地 `eval_out_debug/smoke/mimocode-v0.1/xopglm52-chat/mimocode/` 下的上述 run；
使用独立版本目录，不覆盖旧 run。旧 `v0.0` 镜像仍保持原 ID
`sha256:b1f249f2694fb3a0166fdee997e53dab28fd86ef57e38337536ddc1a35f11485`。
本次未重跑 GLM5.2 的远端 Responses 组合，也未运行真实 Anthropic 模型完整评测。

## v0.0 · CLI 0.1.14（历史版本）

首次集成版本，构建上下文为 `v1/`。已完成的历史 GLM5.2 Chat 冒烟及三协议模拟测试
仅适用于该版本；历史证据保留在 `docs/design/harness-integration/mimocode/`。
保留现有镜像与历史结果，不自动重新构建或迁移这些产物。
