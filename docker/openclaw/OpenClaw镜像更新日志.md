# OpenClaw 镜像更新日志

本文记录 WildClawBench OpenClaw Harness 使用的外部评测镜像 tag、分发文件和验证边界。

## 当前镜像

| 记录日期 | 完整镜像 tag | OpenClaw | 离线包 | 来源 |
| --- | --- | --- | --- | --- |
| 2026-08-14 本机检查 | `wildclawbench-ubuntu:v1.3` | `2026.3.11`（本机检查） | `wildclawbench-ubuntu_v1.3.tar` | WildClawBench Hugging Face 数据集 Images 目录 |

### 版本信息

- 完整镜像 tag：`wildclawbench-ubuntu:v1.3`
- Dockerfile：当前仓库不包含
- 分发文件：`Images/wildclawbench-ubuntu_v1.3.tar`
- 来源说明：`README.md` 的 Download Images 章节指定该文件加载为上述 tag。

### 本机验证

2026-08-14 在本机 Docker daemon 中检查正式 tag：

```text
OpenClaw 2026.3.11 (29dc654)
Node v22.22.1
```

验证命令：

```bash
docker run --rm --entrypoint openclaw \
  wildclawbench-ubuntu:v1.3 --version
docker run --rm --entrypoint node \
  wildclawbench-ubuntu:v1.3 --version
```

该检查只覆盖本机 tag 的 CLI 和 Node 运行时。由于构建源不在当前仓库，无法仅凭本日志还原其完整 Dockerfile、依赖锁定或历史变更。

## 使用约定

```bash
docker load -i Images/wildclawbench-ubuntu_v1.3.tar
export DOCKER_IMAGE=wildclawbench-ubuntu:v1.3
```

OpenClaw backend 会在每个任务容器中注入模型、endpoint、技能、Warmup 和工作区；本日志不记录任何 API key。

## 证据边界

当前仓库仅保留运行时默认 tag 和 Hugging Face 分发文件名，没有该镜像的构建提交或 Dockerfile。后续如果补充可追溯构建源，应在此追加版本条目、构建提交、依赖变更和对应验证记录。

## 相关实现

- `src/agents/openclaw/runner.py`
- `src/utils/docker_utils.py`
- `README.md` 的 Download Images 章节
