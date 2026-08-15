# Codex 镜像更新日志

本文记录 WildClawBench Codex Harness 评测镜像的版本演进、完整镜像 tag、构建输入和验证边界。正式 tag 与 Dockerfile 的映射维护在 `docker/codex/versions.json`；底座镜像本身由 WildClawBench 官方镜像分发。

## 版本总览

| 日期 | 完整镜像 tag | Codex CLI | 基础镜像 | 主要变更 | 当前定位 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-04 | `wildclawbench-codex-ubuntu:v0.1` | `0.146.0` | `wildclawbench-codex-ubuntu:v0.0` | 升级 Codex CLI，清理底座旧版配置 | 当前 Codex 评测推荐版本 |
| 2026-04-19 | `wildclawbench-codex-ubuntu:v0.0` | `0.121.0` | 官方 WildClawBench 底座 | 原始评测环境 | 兼容旧评测 |

`v0.0` 的构建历史和 Dockerfile 不在本仓库；本仓库只把它作为基础镜像使用。`v0.1` 是当前仓库 `docker/codex/v1/Dockerfile` 构建的升级镜像。

## v0.1

### 版本信息

- 完整镜像 tag：`wildclawbench-codex-ubuntu:v0.1`
- 版本 Dockerfile：`docker/codex/v1/Dockerfile`
- 构建脚本：`docker/codex/build.sh`
- Codex CLI：`0.146.0`
- 基础镜像：`wildclawbench-codex-ubuntu:v0.0`
- 默认离线包：`Images/wildclawbench-codex-ubuntu_v0.1.tar.gz`
- 版本提交：`4d3ef0c`（2026-08-04）

### 更新内容

- 先卸载底座中的 `@openai/codex`，再锁定安装 `@openai/codex@0.146.0`。
- 使用 `@openai/codex-linux-x64` 平台包，避免新版 vendor 布局不匹配导致 CLI 启动失败。
- 通过 `NPM_REGISTRY` 构建参数选择 npm registry，默认使用 `https://registry.npmmirror.com`。
- 删除底座遗留的 `/root/.codex` 配置和旧版 shim；运行时由 runner 注入模型、provider、base URL、sandbox 等配置。
- 构建阶段执行 `codex --version`，构建脚本随后记录实际安装版本。

### 本机验证

2026-08-14 在本机 Docker daemon 中检查：

```text
wildclawbench-codex-ubuntu:v0.0 -> codex-cli 0.121.0
wildclawbench-codex-ubuntu:v0.1 -> codex-cli 0.146.0
```

验证命令：

```bash
docker run --rm --entrypoint codex \
  wildclawbench-codex-ubuntu:v0.1 --version
```

该检查只证明本机 tag 可启动并报告 CLI 版本，不等价于全量任务评测验证。

## v0.0

### 版本信息

- 完整镜像 tag：`wildclawbench-codex-ubuntu:v0.0`
- Codex CLI：`0.121.0`（本机 tag 检查结果）
- 镜像创建时间：2026-04-19（本机 image metadata）
- 来源：WildClawBench 官方分发镜像；本仓库不包含其 Dockerfile
- README 离线包：`Images/wildclawbench-codex-ubuntu_v0.0.tar`

### 使用边界

该 tag 仍被 AstronCode、OpenCode、AstronClaw 和 DeepSeek Harness Dockerfile 作为评测基础镜像引用。升级 Codex CLI 时应使用新的 tag，不要覆盖 `v0.0`，以免破坏其它镜像的可复现构建。

## 构建与发布约定

默认构建 `v0.1`：

```bash
bash docker/codex/build.sh
```

旧的 `script/build-codex-image.sh` 仍保留为兼容入口；正式版本参数由 `versions.json` 固定，不能再用 `IMAGE_TAG` 或不同的 `CODEX_VERSION` 组合出未登记镜像。

调试时可以覆盖 npm registry：

```bash
NPM_REGISTRY=https://registry.npmjs.org/ \
  bash docker/codex/build.sh --version v0.1
```

只构建不导出离线包：

```bash
SKIP_SAVE=1 bash docker/codex/build.sh --version v0.1
```

离线包发布前应同时执行 `gzip -t` 和 `docker load`，不能只根据文件扩展名判断其可用性。

## 相关实现

- `docker/codex/versions.json`
- `docker/codex/v1/Dockerfile`
- `docker/codex/build.sh`
- `script/build-codex-image.sh`（兼容包装）
- `src/agents/codex/runner.py`
- `README.md` 的 Download Images 章节
