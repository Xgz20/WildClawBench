# 无头评分运行时

基础镜像按冻结 Score Skill 创建独立 Python 3.11 环境，再使用**同一解释器**
安装其对应的 Chromium。仅安装 Playwright Python 包或 install-deps 不包含浏览器。
构建会运行公开合成 HTML 的离线浏览器预检：点击、键盘、窄窗口、减少动画、
页面网络阻断和截图均须通过，不读取候选或调用模型。

既有运行镜像缺浏览器时，使用独立标签追加修复层：

    docker build --build-arg SCORER_BASE_IMAGE=已冻结的评分镜像 \
      -f browser-runtime.Dockerfile -t 新评分镜像标签 .

保留旧标签及镜像。新评分操作按镜像 ID 冻结配置；已有操作继续使用原配置。
新镜像的 /opt/scoring-browser-preflight/observations.json 保留实际预检记录。
Office 能力由 native-office.Dockerfile 单独提供；正式评分仍执行任务对应的
原生 Office/浏览器预检，环境失败保留为评测异常，不计能力零分。

## 一键构建（含 Office）

从仓库根目录运行，默认 Codex 0.171.0、DSH 0.1.2-rc.1：

```bash
bash docker/e2e-scorer/build.sh
```

最终标签 `wildclawbench-e2e-scorer:codex-0.171.0-office-v1`；中间标签追加
`-runtime`。原执行镜像不变。`--tag` 可指定新发行标签，CLI 版本可用
`--codex-version` / `--dsh-version` 显式指定，标签记录真实构建版本。
底座支持 `--eval-base-image` / `--node-runtime-image`；跨机器时按目标架构构建，
不要把 Mac 的 ARM64 镜像用作 Linux AMD64 镜像。

仅有 Docker 的远程主机可接收独立构建上下文（无仓库及凭据）：

```bash
bash docker/e2e-scorer/build.sh --prepare-only --context /tmp/scorer-context \
  --eval-base-image python:3.11-slim-bookworm \
  --node-runtime-image node:24.13.1-bookworm-slim
# 将整个 scorer-context 目录传至服务器后：
bash /absolute/scorer-context/build-prepared.sh
```

代理通过执行时的 `HTTP_PROXY_INNER` / `HTTPS_PROXY_INNER` 传入，不写入上下文。
新上下文默认写入 `.cache/headless-scorer-build`。底层 Python 入口保持兼容：
省略 `--with-office` 时只构建基础评分镜像。

最终镜像含 LibreOffice Writer/Calc/Impress、中文字体和 PDF 工具。
构建会实际生成 DOCX/XLSX/PPTX，使用受管 `soffice` 转换为 PDF，检查文本、
表格公式重算为 42、中文字体以及输入文件未被改写，再在无网络容器里复验。
`build-manifest.json`、`runtime-validation.json`、`image-receipt.txt` 分别保留
Skill 来源及 SHA、运行时实测和镜像 ID/架构/标签。此为公共合成探针，
不调用模型；正式题目的特殊 Office 预检仍按冻结 Skill 执行。

平台后端 `.env` 绑定（已有其他 Harness 的映射需保留）：

```dotenv
WCB_E2E_SCORING_IMAGES={"codex":"wildclawbench-e2e-scorer:codex-0.171.0-office-v1"}
WCB_E2E_SCORING_DOCKER_CONTEXT=default
```

需在后端使用的 Docker daemon 上构建。修改 `.env` 后，经现有 CICD 重建后端
容器生效；不覆盖框架执行源码或冻结的批次。镜像构建与后端部署分开进行。
