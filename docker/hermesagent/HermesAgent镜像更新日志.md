# Hermes Agent 镜像更新日志

本文记录 WildClawBench Hermes Agent Harness 使用的外部评测镜像 tag、分发文件和验证边界。

## 当前镜像

| 记录日期 | 完整镜像 tag | Hermes Agent 版本 | 离线包 | 来源 |
| --- | --- | --- | --- | --- |
| 2026-08-14 仓库配置 | `wildclawbench-hermes-agent:v0.5` | 当前仓库未复核 | `wildclawbench-hermes-agent-v0.5.tar.gz` | WildClawBench Hugging Face 数据集 Images 目录 |

### 版本信息

- 完整镜像 tag：`wildclawbench-hermes-agent:v0.5`
- Dockerfile：当前仓库不包含
- 分发文件：`Images/wildclawbench-hermes-agent-v0.5.tar.gz`
- 来源说明：`README.md` 的 Download Images 章节指定该文件加载为上述 tag。

### 运行时验证边界

本仓库的 `HermesAgentAgent` 使用该 tag 启动任务容器，运行时负责：

- 注入 `/root/.hermes` 配置、模型 endpoint 和凭证；
- 安装任务技能并执行 Warmup；
- 通过 benchmark runner 执行任务；
- 采集 session/usage 并生成 OpenClaw 兼容 transcript 供评分器使用。

这些行为来自当前 runner，不能反推镜像内 Hermes Agent 的精确版本或依赖清单。当前环境没有加载该离线包，因此版本输出和镜像级能力仍待复核。

## 使用约定

```bash
docker load -i Images/wildclawbench-hermes-agent-v0.5.tar.gz
export HERMES_DOCKER_IMAGE=wildclawbench-hermes-agent:v0.5
```

密钥仅通过运行时环境变量注入，不写入镜像或跟踪文件。

## 证据边界

当前仓库没有该镜像的 Dockerfile、构建脚本或版本提交；本日志只记录可从 README、runner 默认值和分发文件确认的 tag。获得可追溯构建源后，再补充具体版本历史，不将 `v0.5` 直接解释为 Hermes Agent CLI 版本。

## 相关实现

- `src/agents/hermesagent/runner.py`
- `src/agents/hermesagent/bench_runner.py`
- `src/agents/hermesagent/compat_transcript.py`
- `README.md` 的 Download Images 章节
