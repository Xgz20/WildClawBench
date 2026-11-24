# OpenCode 镜像更新日志

本文记录 WildClawBench OpenCode Harness 评测镜像的版本、完整镜像 tag、构建输入和验证边界。

## 版本总览

| 日期 | 完整镜像 tag | OpenCode | 基础镜像 | 主要变更 | 当前定位 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-23 | `wildclawbench-opencode-ubuntu:v0.1` | `1.19.6` | `wildclawbench-codex-ubuntu:v0.0` | 升级到 npm latest 版本，使用 v2 构建上下文 | 当前 OpenCode 评测镜像 |
| 2026-07-21 | `wildclawbench-opencode-ubuntu:v0.0` | `1.18.4` | `wildclawbench-codex-ubuntu:v0.0` | 首次增加 OpenCode CLI 评测镜像 | 历史版本 |

当前正式镜像使用 `v0.1` tag；历史 `v0.0` 保留用于复现。版本目录 `v1` 保存
1.18.4，`v2` 保存 1.19.6。

## v0.1

### 版本信息

- 完整镜像 tag：`wildclawbench-opencode-ubuntu:v0.1`
- Dockerfile：`docker/opencode/v2/Dockerfile`
- OpenCode npm 包：`opencode-ai@1.19.6`
- 基础镜像：`wildclawbench-codex-ubuntu:v0.0`
- 版本目录：`docker/opencode/v2`

### 更新内容

- 在 Codex 评测底座上全局安装 `opencode-ai@1.19.6`，生成 `/usr/bin/opencode`。
- 构建时执行 `opencode --version`，缺少 CLI 或版本命令失败时终止构建。
- 创建 `/root/.config/opencode` 和 `/root/.local/share/opencode`，运行时配置通过 `OPENCODE_CONFIG_CONTENT` 等环境变量注入。
- 保留底座提供的 Python、浏览器、媒体和文档工具链；镜像自身不预置评测凭证。

### 验证边界

构建后在目标 Docker daemon 检查正式 tag：

```text
wildclawbench-opencode-ubuntu:v0.1 -> 1.19.6
```

验证命令：

```bash
docker run --rm --entrypoint opencode \
  wildclawbench-opencode-ubuntu:v0.1 --version
```

该检查只覆盖 CLI 启动和版本，不等价于全量 OpenCode 评测验证。随后还需补做
一条 Spark-X2.6 Chat 冒烟，确认 runner 的配置注入、SQLite 轨迹转换和 usage
产物；OpenCode 的思考强度由 runner 按当前 CLI 的 `--variant` 语义传入，不能
据此推断其它版本的参数兼容性。

## 构建与发布约定

通过统一构建脚本构建 v0.1：

```bash
bash docker/opencode/build.sh --version v0.1 --skip-save
```

省略 `--skip-save` 会导出 `Images/wildclawbench-opencode-ubuntu_v0.1.tar.gz`。
构建脚本从 `versions.json` 解析版本目录、镜像 tag、CLI 版本和基础镜像，
并在 Docker 构建后执行 `opencode --version` 校验。

指定 npm registry 或代理时使用环境变量：

```bash
NPM_REGISTRY=https://registry.npmmirror.com \
  bash docker/opencode/build.sh --version v0.1 --skip-save
```

历史 v0.0 镜像可使用 `bash docker/opencode/build.sh --version v0.0` 重建，
不会覆盖当前 v0.1。

发布离线包时使用完整 tag 导出，并在分发前验证 `gzip -t` 与 `docker load`。

## 相关实现

- `docker/opencode/v2/Dockerfile`
- `docker/opencode/v1/Dockerfile`（历史版本）
- `docker/opencode/versions.json`
- `docker/opencode/build.sh`
- `src/agents/opencode/runner.py`
- `src/agents/opencode/backend.py`
- `docs/superpowers/specs/2026-07-31-opencode-thinking-variant-design.md`
