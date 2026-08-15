# AstronClaw 镜像更新日志

本文记录 WildClawBench AstronClaw Harness 评测镜像的版本、完整镜像 tag、构建输入和验证边界。该镜像保留 AstronClaw 产品底座，再叠加统一 WildClawBench 评测运行环境。

## 版本总览

| 日期 | 完整镜像 tag | AstronClaw/OpenClaw | 产品底座 | 评测底座 | 主要变更 |
| --- | --- | --- | --- | --- | --- |
| 2026-07-30 | `wildclawbench-astronclaw-ubuntu:v0.2.9-eval.1` | OpenClaw `2026.5.7`（本机检查） | `astronclaw-core-cicd:v0.2.9` | `wildclawbench-codex-ubuntu:v0.0` | 首次提供统一评测镜像，补齐浏览器、媒体和 SAM3 依赖 |

当前仓库只定义上述一个评测 tag。产品底座的完整 registry 地址见 Dockerfile；本日志不把产品底座 tag 当作 WildClawBench 评测镜像 tag。

## v0.2.9-eval.1

### 版本信息

- 完整镜像 tag：`wildclawbench-astronclaw-ubuntu:v0.2.9-eval.1`
- Dockerfile：`docker/astronclaw/Dockerfile`
- 版本提交：`daa9871`（2026-07-30）
- 产品底座：`artifacts.iflytek.com/docker-private/hy-spark-agent-builder/astronclaw-core-cicd:v0.2.9`
- 评测底座：`wildclawbench-codex-ubuntu:v0.0`
- 默认运行环境：root，Python 3.11

### 更新内容

- 从评测底座复制统一 `eval` Conda 环境和 `agent-browser`，并链接到 `/usr/local/bin`。
- 固定安装 `numpy==1.26.4`、`opencv-python==4.9.0.80` 和 `ortools==9.10.4067`。
- 安装 Playwright Chromium，设置 `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`。
- 安装 `ffmpeg`，满足媒体处理和任务 Warmup 依赖。
- 构建阶段检查 Python 图像依赖、Playwright 浏览器可执行文件、`agent-browser --version`、`ffmpeg --version` 和 `openclaw --version`。
- 运行时仍由 WildClawBench 注入模型、endpoint 和凭证，镜像不预置密钥。

### 本机验证

2026-08-14 在本机正式 tag 中检查：

```text
OpenClaw 2026.5.7 (9f68ba9)
Python 3.11.15
agent-browser 0.26.0
ffmpeg 8.0.1-3ubuntu2
numpy 1.26.4
opencv-python 4.9.0.80
```

验证命令：

```bash
docker run --rm --entrypoint bash \
  wildclawbench-astronclaw-ubuntu:v0.2.9-eval.1 \
  -lc 'set -e; openclaw --version; python3 --version; agent-browser --version; ffmpeg -version | head -n 1; python3 -c "import numpy, cv2, playwright; print(numpy.__version__, cv2.__version__)"'
```

本次检查覆盖镜像能力和关键依赖，不等价于全量 AstronClaw 评测或所有 SAM3 任务验证。

## 构建与发布约定

构建前需要本机已有评测底座，并能访问产品底座 registry：

```bash
docker build \
  -t wildclawbench-astronclaw-ubuntu:v0.2.9-eval.1 \
  docker/astronclaw
```

可通过 `EVAL_BASE_IMAGE`、`ASTRONCLAW_BASE_IMAGE` 和 `PIP_INDEX_URL` build arg 指定兼容的镜像或 Python 源。发布离线包时使用完整 tag 导出，并在分发前完成 `gzip -t` 与 `docker load` 验证。

## 相关实现

- `docker/astronclaw/Dockerfile`
- `src/agents/astronclaw/runner.py`
- `tests/test_astronclaw_eval_image.py`
- `tests/test_openclaw_backends.py`
