# General E2E 本地受管规则运行时

## 能力与边界

该运行时在本机独立 Python Worker 中执行冻结、可信的 General E2E 自动规则，不使用 Docker。它生成规则组件和运行审计，不调用语义裁判、不合成标准 `score.json`，也不把规则分当作完整评测分。

专用虚拟环境、独立进程和环境白名单用于依赖复现、故障收口和凭据隔离，不是针对恶意 grader 的安全沙箱。只允许执行版本化数据集中的冻结规则；不要把任意第三方 Python 代码传给 Worker。

## 固定运行时

- Python `3.11`
- PyYAML `6.0.3`
- Playwright `1.55.0`
- Chromium revision `1187`，browser version `140.0.7339.16`

完整 Python 依赖和制品哈希由 `scoring-runtime-requirements.txt` 与 `scoring-runtime-lock.json` 固定。macOS x86-64 已完成依赖安装、Chromium 启动、Playwright 规则 Worker、真实 S1 冻结用例和超时子进程清理 smoke；Windows 当前只有代码路径和 PowerShell 进程树实现，必须在 Windows 真机完成安装、浏览器启动、超时和残留进程验证后才能标记通过。

## 一次性初始化

在 Skill 根目录运行：

```bash
python scripts/score_general_e2e.py bootstrap-runtime \
  --venv-root /absolute/path/to/general-e2e-rule-runtime
```

该命令使用 `uv` 创建专用虚拟环境、按哈希安装锁定依赖、把 Chromium 安装到虚拟环境内的 `playwright-browsers/`，然后执行版本与浏览器启动 smoke。代理和证书只在 bootstrap 阶段按白名单继承；评分 Worker 不继承这些变量。

`--offline` 只使用已有 `uv` 缓存。`--skip-browser` 可准备不含浏览器的环境，但 Playwright 规则会在运行前失败关闭，不能据此宣称完整运行时就绪。

## 准备私有 attempt

```bash
python scripts/score_general_e2e.py prepare \
  --unit-root /absolute/path/to/execution-unit \
  --execution-record /absolute/path/to/execution-record.json \
  --scoring-package /absolute/path/to/unit-scoring.zip \
  --task-id TASK_ID \
  --scoring-attempt-id ATTEMPT_ID \
  --output-root /absolute/path/to/private-scoring-root
```

`prepare` 只接受已完成且 evidence complete、候选状态 stable 的执行记录。它复核 batch/unit/task/dataset/release 锁、候选树和 scoring ZIP 的路径、类型与 SHA-256，然后创建不可覆盖的私有 attempt：

- `candidate-original/`：候选只读原件；
- `runtime/workspace/`：一次性可写副本，GT 在执行阶段之后注入 `gt/`；
- `private/`：冻结 contract、task、GT、transcript、execution record 与 runtime lock；
- `attempt-manifest.json`：身份、来源 SHA、路径和初始 runtime 哈希。

候选本身已有 `gt`、ZIP 路径穿越或重复成员、越界 symlink、候选漂移、私有材料不一致以及 attempt 已存在都会失败关闭。

## 复核与运行规则

```bash
python scripts/score_general_e2e.py verify \
  --attempt-root /absolute/path/to/private-attempt

python scripts/score_general_e2e.py run-rules \
  --attempt-root /absolute/path/to/private-attempt \
  --runtime-python /absolute/path/to/general-e2e-rule-runtime/bin/python \
  --timeout-seconds 120
```

Windows 的 Python 路径使用 `Scripts/python.exe`。bootstrap 生成的 marker 会让 `run-rules` 自动定位同一虚拟环境中的 Chromium；手工管理浏览器缓存时可显式传入 `--playwright-browsers-path`。

`run-rules` 在启动前复核候选原件、私有材料、transcript 数量和 runtime 初始哈希；然后按规则实际 import 只探测所需依赖。Worker 只接收结构化 JSON，请求中的 workspace 是本机真实绝对路径；`/tmp_workspace` 仅保留为任务协议中的逻辑名称。

终态产物采用不覆盖写入：

- `rule-component.json`：通过 grading core 契约校验的规则分；
- `rule-audit.json`：运行时探测、PID、耗时、环境变量键、日志 SHA、timeout、进程树清理以及 runtime 前后哈希；
- `worker/{request,result,stdout,stderr}`：本次 Worker 的私有 IPC 和原始日志。

超时、日志或结果过大、依赖/浏览器版本不符、Worker 异常、残留进程树以及评分材料漂移都产生失败审计，不补零，也不生成有效规则组件。失败 attempt 不可原地重跑；应使用新的 `scoring_attempt_id`。
