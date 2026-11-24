# OpenCode 评测镜像

OpenCode 镜像使用版本目录、`versions.json` 和统一 `build.sh` 构建入口维护。
当前正式版本为 `wildclawbench-opencode-ubuntu:v0.1`，内置
`opencode-ai@1.19.6`，构建上下文为 `v2`；`v1` 和 `v0.0` 保留用于历史结果复现。

## 构建

前置条件：本机 Docker daemon 已加载 `wildclawbench-codex-ubuntu:v0.0`。
读取版本清单时优先使用仓库 `.venv/bin/python3` 或 `.venv/bin/python`，
无需激活环境；没有仓库虚拟环境时回退到系统 `python3` 或 `uv run python`。

```bash
NPM_REGISTRY=https://registry.npmmirror.com \
  bash docker/opencode/build.sh --version v0.1 --skip-save

docker run --rm --entrypoint opencode \
  wildclawbench-opencode-ubuntu:v0.1 --version
```

省略 `--skip-save` 会导出：

```text
Images/wildclawbench-opencode-ubuntu_v0.1.tar.gz
```

省略 `--version` 会使用 `versions.json` 中的默认版本。历史镜像可显式构建：

```bash
bash docker/opencode/build.sh --version v0.0 --skip-save
```

构建脚本会校验版本、基础镜像、Dockerfile 所属版本目录，并在构建后执行
`opencode --version`；不会把运行时 API key 写入镜像。
