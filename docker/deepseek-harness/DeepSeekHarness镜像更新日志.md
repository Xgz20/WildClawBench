# DeepSeek Harness 镜像更新日志

本文记录 WildClawBench DeepSeek Harness 评测镜像的版本、完整镜像 tag、构建输入和验证边界。该镜像把 DeepSeek Harness CLI（DSH）安装到统一 Codex 评测底座中，并保留正式 backend 所需的入口包装脚本。

## 版本总览

| 日期 | 完整镜像 tag | DSH | Node | 基础镜像 | 主要变更 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-14 | `wildclawbench-deepseek-harness-ubuntu:v0.0` | `0.1.0-rc.6` | `24.19.0` | `wildclawbench-codex-ubuntu:v0.0` | 首次正式评测镜像，增加协议选择、技能规范化和轨迹入口 |
| 2026-08-14 | `wildclawbench-deepseek-harness-poc:0.1.0-rc.6` | `0.1.0-rc.6` | `24.19.0` | 同上 | 与正式镜像内容相同的 PoC 兼容 tag（本机 metadata） |

`wildclawbench-deepseek-harness-poc:0.1.0-rc.6` 是本机同一 image ID 的别名，不应作为新的独立构建版本对外宣传。正式评测统一使用 `wildclawbench-deepseek-harness-ubuntu:v0.0`。

## v0.0

### 版本信息

- 完整镜像 tag：`wildclawbench-deepseek-harness-ubuntu:v0.0`
- Dockerfile：`docker/deepseek-harness/Dockerfile`
- 入口脚本：`docker/deepseek-harness/wcb-dsh`
- DSH：`@deepseek-ai/dsh@0.1.0-rc.6`
- Node：`24.19.0`，来自 `node:24-bookworm-slim`
- 基础镜像：`wildclawbench-codex-ubuntu:v0.0`
- 版本提交：`b2a0b13` 至 `39f34dd`（2026-08-14）
- 默认离线包：`Images/wildclawbench-deepseek-harness-ubuntu_v0.0.tar.gz`

### 更新内容

- 将 Node 24 runtime 复制到评测底座，满足 DSH 对 Node `^22.19` 或 `>=24` 的要求。
- 安装 `@deepseek-ai/dsh@0.1.0-rc.6`，构建时执行 `dsh --version`。
- 设置 `DSH_HOME=/root/.dsh`、`DSH_PERMISSION_MODE=danger-full-access` 和 `DSH_TELEMETRY_DISABLED=1`。
- 通过 `wcb-dsh` 作为容器入口，正式 backend 可在容器中保留任务进程并采集原始 session。
- 保留评测底座提供的 Python、浏览器、媒体和文档工具链；模型 endpoint、API key 和任务技能由运行时注入。

### 本机验证

2026-08-14 对正式 tag 的镜像级检查：

```text
DSH 0.1.0-rc.6
Node v24.19.0
Python 3.11.15
```

正式 `run_batch.py` 单任务闭环也已记录在 `docker/deepseek-harness/README.md`：任务容器启动、模型调用、结果评分、usage、session 转换和有效性检查均完成。该证据只覆盖单个文本/工具任务，不等价于全量评测、DeepSeek Search 或原生多模态评测。

### 离线包状态

2026-08-14 检查发现，本机 `Images/wildclawbench-deepseek-harness-ubuntu_v0.0.tar.gz` 只有 20 字节，不包含可供 `docker load` 的镜像 tar 数据，不能作为已发布的离线包。需要重新导出正式 tag，并在分发前执行 `gzip -t` 和 `docker load` 验证。

## 构建与发布约定

```bash
docker build \
  -t wildclawbench-deepseek-harness-ubuntu:v0.0 \
  docker/deepseek-harness

docker run --rm --entrypoint dsh \
  wildclawbench-deepseek-harness-ubuntu:v0.0 --version
```

可通过 `EVAL_BASE_IMAGE`、`NODE_RUNTIME_IMAGE` 和 `NPM_REGISTRY` build arg 指定兼容源。发布离线包时应使用完整 tag 导出并验证 `gzip -t`、`docker load` 和 `docker image inspect`。

## 相关实现

- `docker/deepseek-harness/Dockerfile`
- `docker/deepseek-harness/wcb-dsh`
- `docker/deepseek-harness/README.md`
- `src/agents/deepseek_harness/runner.py`
