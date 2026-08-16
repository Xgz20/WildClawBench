# Claude Code 镜像更新日志

本文记录 WildClawBench Claude Code Harness 使用的外部评测镜像 tag、分发文件和验证边界。

## 当前镜像

| 记录日期 | 完整镜像 tag | Claude Code 版本 | 离线包 | 来源 |
| --- | --- | --- | --- | --- |
| 2026-08-16 正式版本 | `wildclawbench-claudecode-ubuntu:v0.2-patched` | `2.1.88` | `wildclawbench-claudecode-ubuntu_v0.2-patched.tar` | WildClawBench Hugging Face 数据集 Images 目录 |

### 版本信息

- 完整镜像 tag：`wildclawbench-claudecode-ubuntu:v0.2-patched`
- Dockerfile：当前仓库不包含
- 分发文件：`Images/wildclawbench-claudecode-ubuntu_v0.2-patched.tar`
- Claude Code 版本：本机通过镜像内 `/claude_code/package.json` 复核为 `2.1.88`。
- 来源说明：`README.md` 的 Download Images 章节指定该文件加载为上述正式 tag。

### 运行时验证边界

本仓库的 `ClaudeCodeAgent` 使用该 tag 启动任务容器，并在运行时完成：

- `/claude_code/log/chat.json` 和 `usage.json` 的采集；
- Claude Code transcript 到 OpenClaw 兼容 `chat.jsonl` 的转换；
- 任务技能、Warmup、工作区和模型 endpoint 的注入。

这些是 Harness 集成行为；镜像内 Claude Code 版本已复核，但仓库仍不包含镜像构建源，无法从源码复核 `patched` 变更内容。

## 使用约定

```bash
docker load -i Images/wildclawbench-claudecode-ubuntu_v0.2-patched.tar
export DOCKER_IMAGE_CLAUDECODE=wildclawbench-claudecode-ubuntu:v0.2-patched
```

API key 和 base URL 只通过运行时环境变量注入，不写入日志或镜像文档。

## 证据边界

当前仓库只保存默认 tag、离线包名称、镜像内版本验证结果和 Claude Code runner 的调用约定，没有镜像 Dockerfile 或构建提交。后续获得构建源后，应按 tag 追加依赖变更和镜像级验证。

## 相关实现

- `src/agents/claudecode/runner.py`
- `src/agents/claudecode/transcript.py`
- `README.md` 的 Download Images 章节
