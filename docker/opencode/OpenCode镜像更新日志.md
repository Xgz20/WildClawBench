# OpenCode 镜像更新日志

本文记录 WildClawBench OpenCode Harness 评测镜像的版本、完整镜像 tag、构建输入和验证边界。

## 版本总览

| 日期 | 完整镜像 tag | OpenCode | 基础镜像 | 主要变更 | 当前定位 |
| --- | --- | --- | --- | --- | --- |
| 2026-07-21 | `wildclawbench-opencode-ubuntu:v0.0` | `1.18.4` | `wildclawbench-codex-ubuntu:v0.0` | 首次增加 OpenCode CLI 评测镜像 | OpenCode 评测基线 |

当前仓库只定义一个 OpenCode 镜像 tag。后续升级应创建新 tag，保留 `v0.0` 供历史结果复现。

## v0.0

### 版本信息

- 完整镜像 tag：`wildclawbench-opencode-ubuntu:v0.0`
- Dockerfile：`docker/opencode/Dockerfile`
- OpenCode npm 包：`opencode-ai@1.18.4`
- 基础镜像：`wildclawbench-codex-ubuntu:v0.0`
- 版本提交：`3d64f5d`（2026-07-21）
- 本机镜像创建时间：2026-07-21

### 更新内容

- 在 Codex 评测底座上全局安装 `opencode-ai@1.18.4`，生成 `/usr/bin/opencode`。
- 构建时执行 `opencode --version`，缺少 CLI 或版本命令失败时终止构建。
- 创建 `/root/.config/opencode` 和 `/root/.local/share/opencode`，运行时配置通过 `OPENCODE_CONFIG_CONTENT` 等环境变量注入。
- 保留底座提供的 Python、浏览器、媒体和文档工具链；镜像自身不预置评测凭证。

### 本机验证

2026-08-14 检查正式 tag：

```text
wildclawbench-opencode-ubuntu:v0.0 -> 1.18.4
```

验证命令：

```bash
docker run --rm --entrypoint opencode \
  wildclawbench-opencode-ubuntu:v0.0 --version
```

该检查只覆盖 CLI 启动和版本，不等价于全量 OpenCode 评测验证。OpenCode 的思考强度由 runner 按当前 CLI 的 `--variant` 语义传入，不能据此推断其它版本的参数兼容性。

## 构建与发布约定

仓库当前没有独立构建脚本，可直接构建：

```bash
docker build \
  -t wildclawbench-opencode-ubuntu:v0.0 \
  docker/opencode
```

指定 npm registry 或升级版本时传入对应 build arg：

```bash
docker build \
  --build-arg OPENCODE_VERSION=1.18.4 \
  --build-arg NPM_REGISTRY=https://registry.npmjs.org/ \
  -t wildclawbench-opencode-ubuntu:v0.0 \
  docker/opencode
```

发布离线包时使用完整 tag 导出，并在分发前验证 `gzip -t` 与 `docker load`。

## 相关实现

- `docker/opencode/Dockerfile`
- `src/agents/opencode/runner.py`
- `src/agents/opencode/backend.py`
- `docs/superpowers/specs/2026-07-31-opencode-thinking-variant-design.md`
