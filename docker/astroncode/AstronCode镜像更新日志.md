# AstronCode 镜像更新日志

本文记录 WildClawBench AstronCode 评测镜像的版本演进、完整镜像 tag、主要能力和验证边界。镜像统一使用 `wildclawbench-astroncode-ubuntu` 作为名称，基于 `wildclawbench-codex-ubuntu:v0.0` 构建。正式 tag 与 Dockerfile 的映射维护在 `docker/astroncode/versions.json`。

## 版本总览

| 日期 | 完整镜像 tag | Docker variant | AstronCode 版本 | 主要变更 | 当前定位 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-24 | `wildclawbench-astroncode-ubuntu:v0.5` | `v5` | `0.0.34` | 升级 CLI 和模型目录，继承 SearchAgent 与 PPT 渲染能力 | 当前默认版本 |
| 2026-08-13 | `wildclawbench-astroncode-ubuntu:v0.4-ppt` | `v4` | `0.0.13` | 在 v0.4 基础上增加 LibreOffice 和 PPT 渲染门禁 | PPT 评测推荐版本 |
| 2026-08-04 | `wildclawbench-astroncode-ubuntu:v0.4` | `v4` | `0.0.13` | 内置 SearchAgent 配置片段及构建期验证 | 通用评测历史版本 |
| 2026-07-31 | `wildclawbench-astroncode-ubuntu:v0.3` | `v3` | `0.0.13` | 固定 AstronCode 0.0.13，配置和凭证改为运行时注入 | 0.0.13 基线版本 |
| 2026-07-18 | `wildclawbench-astroncode-ubuntu:v0.2` | `v2` | `0.0.6` | 适配 CLI 内置模型默认配置，正式发布映射固定为 0.0.6 | 旧版兼容 |
| 2026-07-16 | `wildclawbench-astroncode-ubuntu:v0.1-test.8` | `v1` | `0.0.5-test.8` | 烘焙 astron-spark provider、model catalog 和 profile | 旧配置架构 |
| 2026-07-15 | `wildclawbench-astroncode-ubuntu:v0.0` | 历史默认 Dockerfile | `0.0.5-benchmark-adapt.10` | 首次在 Codex 评测镜像上安装 AstronCode CLI | 初始版本 |

> `v0.4` 和 `v0.4-ppt` 的镜像 tag 不能互换使用。早于 2026-08-13 构建的 `v0.4` 镜像不包含 LibreOffice，且历史 `v0.4` 不再注册为可构建版本。新评测默认使用 `v0.5`；需要复现 0.0.13 环境时再显式选择 `v0.4-ppt`。

## v0.5

### 版本信息

- 完整镜像 tag：`wildclawbench-astroncode-ubuntu:v0.5`
- 版本 Dockerfile：`docker/astroncode/v5/Dockerfile`
- AstronCode：`0.0.34`
- Node.js：`22.23.2`（AstronCode 0.0.34 要求 Node.js 22 或更高版本）
- SearchAgent：`@iflytek/install-search-updater@0.1.17`
- PPT 渲染：LibreOffice Impress + PyMuPDF (`fitz`)
- 默认模型目录：`https://astronstudio-api-volces-prod.xf-yun.com/api/v1/astroncode_webserver/config-v4`
- 默认离线包名：`Images/wildclawbench-astroncode-ubuntu_v0.5.tar.gz`

### 更新内容

- 将 `@iflytek/astron-code` 从 `0.0.13` 升级并固定为 `0.0.34`，构建阶段继续执行 `astron-code --version`。
- 将基础镜像的 NodeSource 源从 Node.js 20 切换到 22，固定安装 `22.23.2` 并在构建阶段校验主版本不低于 22。
- 新增独立 `v5` 构建上下文，继承 v4 的 Search、Fetch、SearchBetter、Scrapling Playwright 路径修正、LibreOffice 和 PyMuPDF 构建门禁。
- Harness 默认模型目录从 `config-v1` 切换为 `config-v4`，并继续允许通过 `ASTRON_MODELS_BASE_URL` 覆盖。
- 默认评测镜像和 E2E 评分镜像切换为 `wildclawbench-astroncode-ubuntu:v0.5`。
- 镜像只保存通过构建期验证的 SearchAgent MCP 配置片段，不包含 API Key、运行时模型选择或模型目录地址；模型和凭据仍由 Harness 启动容器时写入。

### 验证记录

2026-08-24 在本机完成 `wildclawbench-astroncode-ubuntu:v0.5` 真实构建和容器内能力检查，实际输出为：

- `v22.23.2`
- `astron-code 0.0.34`
- `LibreOffice 7.3.7.2 30(Build:2)`
- `fitz 1.27.2.2`
- `install-search` 可执行，MCP 配置包含 `scrapling` 和 `web-search`

能力检查命令：

```bash
docker run --rm --entrypoint bash \
  wildclawbench-astroncode-ubuntu:v0.5 \
  -lc 'set -e; astron-code --version; soffice --version; python3 -c "import fitz; print(fitz.__version__)"; command -v install-search; test -s /opt/astroncode/search-agent.config.toml'
```

镜像配置环境中未发现 API Key、Token、Secret 或 `ASTRON_MODELS_BASE_URL`。对新模型目录发起无凭据请求返回 HTTP 401，说明地址可达且需要鉴权；实际模型目录读取和推理仍以带凭据的评测冒烟结果为准。

## v0.4-ppt

### 版本信息

- 完整镜像 tag：`wildclawbench-astroncode-ubuntu:v0.4-ppt`
- 版本 Dockerfile：`docker/astroncode/v4/Dockerfile`
- AstronCode：`0.0.13`
- SearchAgent：`@iflytek/install-search-updater@0.1.17`，保留 v0.4 的 Search、Fetch 及配置片段
- PPT 渲染：LibreOffice Impress + PyMuPDF (`fitz`)
- 默认离线包名：`Images/wildclawbench-astroncode-ubuntu_v0.4-ppt.tar.gz`

### 更新内容

- 安装 `libreoffice-impress`，为评分容器提供 `soffice`/`libreoffice`。
- 构建时执行 `command -v soffice` 和 `soffice --version`，缺少 LibreOffice 时直接终止构建。
- 构建时执行 `import fitz`，确认基础评测镜像中的 PyMuPDF 可用。
- 配合 `ppt` metric profile，评分阶段会将 `results/` 下的 PPTX 转换为 PDF 和逐页 PNG，再将渲染图像作为多模态 Judge 证据。
- 构建脚本默认 tag 由 `v0.4` 切换为 `v0.4-ppt`，并继续使用 gzip 格式导出离线镜像。

### 验证记录

2026-08-14 在本机对正式 tag 运行检查，实际输出为：

- `astron-code 0.0.13`
- `LibreOffice 7.3.7.2 30(Build:2)`
- `fitz 1.27.2.2`
- `install-search` 可执行，`/opt/astroncode/search-agent.config.toml` 存在且非空

能力检查命令：

```bash
docker run --rm --entrypoint bash \
  wildclawbench-astroncode-ubuntu:v0.4-ppt \
  -lc 'set -e; astron-code --version; soffice --version; python3 -c "import fitz; print(fitz.__version__)"; command -v install-search; test -s /opt/astroncode/search-agent.config.toml'
```

### 离线包状态

2026-08-14 检查发现，本机现有的 `Images/wildclawbench-astroncode-ubuntu_v0.4-ppt.tar.gz` 只有 20 字节，不包含可供 `docker load` 的镜像 tar 数据，不能作为已发布的离线包。需重新执行导出，并在分发前完成 `gzip -t` 和 `docker load` 验证。

## v0.4

### 版本信息

- 完整镜像 tag：`wildclawbench-astroncode-ubuntu:v0.4`
- Dockerfile：历史 `docker/astroncode/v4/Dockerfile`；当前不作为 `v0.4` 的可构建映射
- AstronCode：`0.0.13`
- 首次提交日期：2026-08-04

### 更新内容

- 在 v0.3 的 AstronCode 0.0.13 基础上安装 `@iflytek/install-search-updater`。
- 构建阶段执行 SearchAgent 工具列表和 Fetch 冒烟检查，并执行 `install-search doctor --full`。
- 将通过验证的 MCP 配置片段保存为 `/opt/astroncode/search-agent.config.toml`，供 Harness 运行时合并模型与凭证配置。
- 修正 SearchAgent 的 `uv` 执行路径、MCP 配置结构检查和 Scrapling Playwright 浏览器路径。

### 兼容说明

该 tag 在 PPT 依赖加入之前已经生成过镜像。历史 `v0.4` 不一定包含 `soffice`，不能仅因为当前 v4 Dockerfile 已更新就视为支持 PPT 渲染。

## v0.3

### 版本信息

- 完整镜像 tag：`wildclawbench-astroncode-ubuntu:v0.3`
- 版本 Dockerfile：`docker/astroncode/v3/Dockerfile`
- AstronCode：`0.0.13`
- 发布日期：2026-07-31

### 更新内容

- 将 `@iflytek/astron-code` 固定为 `0.0.13`，构建阶段执行 `astron-code --version`。
- 镜像不再预置运行时凭证和完整模型配置，由 Harness 启动容器时写入 `/root/.acode/config.toml`。
- 构建时删除并重建 `/root/.acode`，避免基础镜像遗留配置影响评测。
- 增加 Astron、one-iflytek 和 OpenRouter 的运行时 provider 选择与配置注入支持。

## v0.2

### 版本信息

- 完整镜像 tag：`wildclawbench-astroncode-ubuntu:v0.2`
- 版本 Dockerfile：`docker/astroncode/v2/Dockerfile`
- AstronCode：`0.0.6`
- 发布日期：2026-07-18

### 更新内容

- 适配 AstronCode 0.0.6 开始内置默认模型配置的行为，运行时不再需要烘焙 v1 的完整 provider/catalog/profile 配置包。
- 历史 v2 Dockerfile 允许 `ASTRON_CODE_VERSION` 为空时安装 registry 当时的最新版本；当前 `versions.json` 和标准构建入口已固定为 `0.0.6`，不再接受独立覆盖。
- 继续使用 `/root/.acode` 作为 AstronCode home，并保证目录权限为 `700`。

## v0.1-test.8

### 版本信息

- 完整镜像 tag：`wildclawbench-astroncode-ubuntu:v0.1-test.8`
- 版本 Dockerfile：`docker/astroncode/v1/Dockerfile`
- AstronCode：`0.0.5-test.8`
- 发布日期：2026-07-16

### 更新内容

- 替换基础镜像中可能存在的 AstronCode，安装 `@iflytek/astron-code@0.0.5-test.8`。
- 将 astron-spark provider、model catalog 和默认 profile 安装到 `/root/.acode`。
- 运行时使用 `ASTRON_SPARK_API_KEY`，配置包中不包含密钥。

## v0.0

### 版本信息

- 完整镜像 tag：`wildclawbench-astroncode-ubuntu:v0.0`
- Dockerfile：初始版 `docker/astroncode/Dockerfile`，后续已由 `v1`/`v2` 目录取代
- AstronCode：`0.0.5-benchmark-adapt.10`
- 发布日期：2026-07-15

### 更新内容

- 首次在 `wildclawbench-codex-ubuntu:v0.0` 上全局安装 `@iflytek/astron-code`。
- 构建时执行 `astron-code --version`，确认 CLI 入口可用。
- 增加镜像构建和 `docker save | gzip` 离线导出脚本。

## 构建与发布约定

当前默认构建 `v0.5`：

```bash
bash docker/astroncode/build.sh
```

构建指定版本时只选择清单中的完整版本，不再分别指定 Docker variant 和镜像 tag：

```bash
# v0.5
bash docker/astroncode/build.sh --version v0.5

# v0.4-ppt，复现 AstronCode 0.0.13 + Search/PPT 环境
bash docker/astroncode/build.sh --version v0.4-ppt

# v0.3
bash docker/astroncode/build.sh --version v0.3

# v0.2，显式固定 AstronCode 0.0.6
bash docker/astroncode/build.sh --version v0.2

# v0.1-test.8
bash docker/astroncode/build.sh --version v0.1-test.8
```

旧的 `script/build-astroncode-image.sh` 仍保留为兼容入口。它只接受清单中已有的 variant/tag 映射：`v1`、`v2`、`v3`、`v4`、`v5` 分别对应 `v0.1-test.8`、`v0.2`、`v0.3`、`v0.4-ppt`、`v0.5`；variant 与 tag 不匹配时会直接失败。

离线包发布前至少执行：

```bash
gzip -t Images/wildclawbench-astroncode-ubuntu_v0.5.tar.gz

# 建议在没有目标 tag 的独立 Docker 环境中验证
docker load -i Images/wildclawbench-astroncode-ubuntu_v0.5.tar.gz
docker image inspect wildclawbench-astroncode-ubuntu:v0.5 >/dev/null
```

`gzip -t` 只能验证 gzip 容器完整性，不能证明其中包含可加载的 Docker 镜像；离线包必须再通过 `docker load` 验证。

## 相关实现

- `docker/astroncode/versions.json`
- `docker/astroncode/build.sh`
- `docker/astroncode/v1/Dockerfile`
- `docker/astroncode/v2/Dockerfile`
- `docker/astroncode/v3/Dockerfile`
- `docker/astroncode/v4/Dockerfile`
- `docker/astroncode/v5/Dockerfile`
- `script/build-astroncode-image.sh`（兼容包装）
- `src/utils/ppt_evidence.py`
- `tests/test_astroncode_ppt_image.py`
