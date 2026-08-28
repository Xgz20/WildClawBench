# Claude Code 评测镜像

Claude Code 镜像采用版本目录、`versions.json` 和统一构建脚本维护。

## 当前正式版本

- 镜像：`wildclawbench-claudecode-ubuntu:v0.3`
- Claude Code：`2.1.250`
- 构建目录：`docker/claudecode/v3`
- 评测底座：`wildclawbench-codex-ubuntu:v0.0`
- Node.js：`node:24-bookworm-slim` 提供的 Node 24

旧的 `v0.2-patched` 仍记录在 `versions.json` 的 `legacy_versions` 中，但仓库没有其构建源，因此不能通过当前脚本重建。

## 构建

```bash
bash docker/claudecode/build.sh --version v0.3 --skip-save
```

省略 `--skip-save` 时，构建完成后会导出：

```text
Images/wildclawbench-claudecode-ubuntu_v0.3.tar.gz
```

服务器只有 `uv`、没有系统 `python3` 时，构建脚本会自动使用 `uv run python` 读取版本清单。

## 运行时约定

- Claude Code 通过全局命令 `claude` 启动。
- API key、base URL 和模型名只在容器启动时注入。
- 无头模式使用 `stream-json` 输出并写入 `/claude_code/log/chat.json`。
- 镜像保留评测底座中的 Chrome、Agent Browser、Playwright、Python 和文档处理工具。
