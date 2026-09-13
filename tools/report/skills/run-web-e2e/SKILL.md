---
name: run-web-e2e
description: 按用户明确要求动态组合 Web E2E 的准备、桌面 Harness 执行、Codex Desktop 评分、离线回传、收集和报告阶段；持久化可恢复状态，但不替代各单阶段 Skill。
---

# 编排 Web E2E 全流程

本 Skill 是跨阶段组合器。现有 `prepare-web-e2e-workspaces`、`execute-web-e2e`、`orchestrate-web-e2e`、`score-web-e2e` 和 `report-web-e2e` 仍可人工独立使用；本 Skill 只在用户要求跨阶段串联、离线交接或统一恢复时启用。

## 1. 只选择用户明确要求的阶段

把用户 Prompt 映射为以下显式阶段，再传给状态脚本。不要让 Python 猜测自然语言：

- `prepare`：调用 `prepare-web-e2e-workspaces`。
- `execute`：调用 `execute-web-e2e`。
- `score`：调用 `orchestrate-web-e2e`，并让每个独立 Codex Desktop 评分任务使用 `score-web-e2e`。
- `package`：生成完整 Harness 离线回传 ZIP 和外部回执。
- `collect`：在管理员机离线导入并校验回传包。
- `report`：调用 `report-web-e2e` 生成 JSON、Markdown 和 Excel。

没有明确阶段且磁盘上也没有运行状态时，只说明可选阶段和缺少的输入，不创建文件、不准备题目、不执行 Harness。用户说“继续”或“恢复”时，读取已有状态并沿用冻结的 `selected_stages`。用户显式提到的阶段优先于可选预设：

- `admin`：批次级 `prepare,collect,report`。
- `worker`：Harness 单元级 `execute,score,package`。
- `full-local`：分别初始化批次级 `prepare,collect,report` 和单元级 `execute,score,package`。

未选择的阶段始终是 `NOT_SELECTED`。前置产物缺失时报告阻塞，不能为了“跑通”而隐式增加阶段。

### 执行人双 ZIP 入口

用户明确选择“执行、评分、打包回传”，并同时提供 `__execution.zip` 与 `__scoring.zip` 时，允许只给两个绝对路径。控制 Harness 必须自行完成其余机械步骤：

1. 校验两个 ZIP 的批次、Harness、Profile 和完整 task IDs 一致；不能按文件名猜测身份。
2. 从 execution ZIP 解压出独立 worker 根。默认在 execution ZIP 同级创建其顶层目录；Windows WorkBuddy 必须改用 `D:\debug-workspace\web-e2e\w\<短批次ID>` 这类短的独立目录作为 worker 根本身，解压时去掉 ZIP 顶层包名或在发送前把该顶层目录安全改为短名，并确认每题候选 `workspace` 绝对路径不超过 180 字符，避免包名和完整 task ID 叠加后触发 npm 的传统 Win32 长路径行为。目标已存在时只允许按已有磁盘状态恢复，不能覆盖或混入管理员 staging 根。
3. 解压后读取 worker 根 `manifest.json.required_skills`；若管理员同时分发了 `packages/skills-manifest.json`，还要先校验其中的版本化 ZIP SHA-256。使用本 Skill 的 `scripts/check_web_e2e_skills.py` 对比已安装 Skill 的名称、版本和内容 SHA-256。完全一致的 Skill 跳过安装；只导入 `install_required` 列出的 `<skill-name>-skill-v<version>.zip`，然后重新检查。版本相同但内容 SHA 不同必须停止，不能继续使用或静默覆盖。
4. 根据 `manifest.harness.id` 选择 WorkBuddy、AstronStudio 或 QwenWork Driver，并检查它与 Codex Desktop Driver 的锁定依赖。`node_modules/playwright-core` 缺失或 `npm ls --depth=0` 失败时，由控制 Harness 在对应 Driver 目录自动执行 `npm ci`；用户无需手工安装。安装失败进入 `NEEDS_ATTENTION`，不能把依赖装入候选 workspace。
5. 被评 Harness 未显式指定模型时保持并回读当前模型，不操作推理强度；权限按生产契约使用 `full-access`。WorkBuddy、AstronStudio 和 QwenWork 的新执行队列均默认三槽、最大八槽；评分新批次默认三槽。三种 Harness 的 UI 操作始终保持单槽。Codex Desktop CDP 未显式提供时使用 `http://127.0.0.1:9230`。
6. execution 回执有效后才合入 scoring ZIP 并开始评分；submission 有效后在 worker 根同级的 `offline-return/` 生成完整 return ZIP 和外部回执。

平台路由必须显式：macOS 使用各 Driver 的 `.sh` 入口；Windows 上 AstronStudio 使用 `run-astronstudio.cmd` / `run-astronstudio-batch.cmd`，WorkBuddy 使用 `run-workbuddy.cmd` / `run-workbuddy-batch.cmd`，QwenWork 使用 `run-qwenwork.cmd` / `run-qwenwork-batch.cmd`，Codex Desktop 项目注册使用 `run-codex-project-registrar.cmd`。Python 状态脚本在 Windows 优先用 `py -3`，否则使用可用的 `python`；不得硬调用 `python3`。当前 Windows 端到端生产已验证范围包括 `AstronStudio -> Codex Desktop 评分 -> 回传/报告` 与 `WorkBuddy 5.5.3 -> Codex Desktop 评分 -> 回传/报告`；WorkBuddy 已通过单题、串行、默认三槽动态补位、单 Prompt 全流程以及控制任务/客户端重启、超时、评分接管、失败 attempt 隔离和 submission 中断恢复验收。QwenWork 已完成 Windows 静态适配与只读 probe 真机验证，但在其余生产清单通过前仍未进入 Windows 端到端生产验证范围；DoubaoWork 也未进入该范围，二者均不能回退调用 macOS Driver。

### macOS / Windows 桌面 CDP 自动前置准备

选择 `execute` 或 `score` 时，必须在任何 UI 操作和阶段 `RUNNING` 之前调用本 Skill 的确定性脚本。正常入口不是只读检查：脚本先复用已经返回真实 CDP target、且监听进程身份正确的客户端；缺少有效调试端点时仅自动关闭并重启所选客户端，不要求用户手工关、启。

按所选阶段和 Harness 收窄作用域：AstronStudio 只执行使用 `AstronStudio`，WorkBuddy 只执行使用 `WorkBuddy`，QwenWork 只执行使用 `QwenWork`，只评分使用 `Codex`；AstronStudio 执行加评分使用兼容值 `All`，WorkBuddy 执行加评分使用 `CodexWorkBuddy`，QwenWork 执行加评分使用 `CodexQwenWork`。Windows 使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <run-web-e2e-skill-dir>\scripts\start_windows_desktop_debug.ps1 -Application All
```

WorkBuddy 只执行时改为 `-Application WorkBuddy`，执行加 Codex 评分时改为 `-Application CodexWorkBuddy`。QwenWork 对应使用 `-Application QwenWork` / `-Application CodexQwenWork`。WorkBuddy 默认 CDP 为 `http://127.0.0.1:9229`，QwenWork 默认 CDP 为 `http://127.0.0.1:9250`。

在 Codex Desktop 当前任务中执行客户端重启恢复验收时，必须改用任务计划程序托管入口，使重启 Worker 脱离当前 Codex 进程作业：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <run-web-e2e-skill-dir>\scripts\restart_windows_desktop_debug.ps1 -Application Codex
```

macOS 使用：

```bash
/bin/bash <run-web-e2e-skill-dir>/scripts/start_macos_desktop_debug.sh --application all
```

Windows 脚本动态解析当前 Codex MSIX 包的真实 manifest 入口，并从当前用户注册表及 `%LOCALAPPDATA%\Programs` 解析 `AStudio.exe`、`AstronStudio.exe`、`Acode.exe`、`WorkBuddy.exe`、`CodeBuddy.exe`、`QwenWorkCN.exe` 或 `QwenWork.exe`。WorkBuddy 重启前会只读检查 `%USERPROFILE%\.workbuddy\workbuddy.db`；QwenWork 重启前会只读检查 `%APPDATA%\QwenWorkCN\data\agents.db` 的稳定内核会话。存在活动或待处理 session 时均失败关闭；停止旧实例时只处理可执行文件完整路径与动态发现结果一致的进程，同名但位于其他目录的辅助进程或应用必须跳过。启动 WorkBuddy 时动态选择其 `%USERPROFILE%\.workbuddy\binaries\node\versions` 下最高的完整 Node/npm 运行时，只对新客户端进程补充 `PATH`，并默认设置 `npm_config_audit=false`、`npm_config_fund=false`、`npm_config_update_notifier=false`、`npm_config_prefer_offline=true` 以及 WorkBuddy 官方支持的 `BASH_DEFAULT_TIMEOUT_MS=600000`、`BASH_MAX_TIMEOUT_MS=600000`；用户已有同名 Shell 时限配置优先，启动脚本自身环境随后恢复。macOS 脚本默认解析 `/Applications` 和当前用户 `Applications` 下的 `ChatGPT.app` / `Codex.app` 与 `AStudio.app` / `AstronStudio.app`；非标准位置只允许通过对应的显式路径参数传入。

两个脚本均等待所选的 Codex `9230`、AstronStudio `9240`、WorkBuddy `9229` 或 QwenWork `9250` 的 `/json/list` 返回至少一个真实 target，并验证端口监听者属于目标客户端。端口被无关进程占用时不得结束该进程，脚本失败并进入 `NEEDS_ATTENTION`。`-CheckOnly` / `--check-only` 仅用于故障诊断，不是标准 E2E 前置流程。

Windows 的 `-ForceRestart` 只用于用户明确要求的客户端重启恢复验收；它会强制重启 `-Application` 选中的客户端，即使当前 CDP 已正常。使用前必须先持久化原 thread、cursor、attempt 和 deadline。当前任务需要重启 Codex 时，禁止通过 `Start-Process` 派生隐藏 PowerShell：该进程仍可能继承 Codex 的 Windows Job，并在客户端退出时一起终止。必须使用 `restart_windows_desktop_debug.ps1` 注册交互式一次性计划任务；Worker 延迟启动、调用底层 `start_windows_desktop_debug.ps1 -ForceRestart`，把状态和日志写入 `%LOCALAPPDATA%\WildClawBench\desktop-debug-restart\`，结束后删除自己的计划任务。底层启动器会在有界时限内等待已核对的旧客户端释放 CDP 端口；等待期间端口若被无关进程抢占则立即失败关闭，避免把正常的 Windows 进程退出延迟误判成永久端口冲突。底层 `-ForceRestart` 不能与 `-CheckOnly` 同时使用，也不能作为普通前置准备的默认参数。

重启 Codex Desktop 可能中断承载当前控制任务的客户端，因此必须先持久化本 Skill 的运行状态；客户端回来后从原状态恢复，不能重新初始化或创建重复任务。同一次初始前置准备不要再向 AstronStudio Driver 传 `--restart-app`，避免两套入口重复重启。脚本失败、超时或 target 列表为空时不得继续 UI 自动化。

因此，在客户端和 Skill 已准备好的前提下，下面的用户输入足以触发 worker 全流程：

```text
请使用 $run-web-e2e 完成下面 Web E2E 评测用例的执行、评分、打包回传。

题目：/absolute/<batch_id>__<harness>__execution.zip
评分标准：/absolute/<batch_id>__<harness>__scoring.zip
```

安装状态可以确定性复核：

```bash
python3 <run-web-e2e-skill-dir>/scripts/check_web_e2e_skills.py \
  --manifest /absolute/<worker-root>/manifest.json \
  --skills-root /absolute/<codex-skills-root>
```

返回 `all_current=true` 时不得重复安装；返回其他状态时，只使用管理员提供且 ZIP SHA-256 有效的对应版本包。

## 2. 初始化和恢复状态

批次状态位于 `<batch-root>/.run-web-e2e/batch-state.json`，只允许 `prepare,collect,report`。Harness 单元状态位于 `<harness-root>/.run-web-e2e/unit-state.json`，只允许 `execute,score,package`。

```bash
python3 <skill-dir>/scripts/run_web_e2e.py init \
  --scope unit \
  --root /absolute/<batch_id>/harnesses/workbuddy \
  --stage execute --stage score --stage package

python3 <skill-dir>/scripts/run_web_e2e.py resume \
  --scope unit \
  --root /absolute/<batch_id>/harnesses/workbuddy
```

首次选择会冻结。相同 `init` 幂等；需要扩大范围时必须显式 `add-stage`，不能用第二次 `init` 静默改计划：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py add-stage \
  --scope unit --root /absolute/<harness-root> --stage package
```

单阶段开始、完成或失败后及时记录：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py set-stage \
  --scope unit --root /absolute/<harness-root> \
  --stage execute --status RUNNING
```

`sync`/`resume` 只根据已存在且身份匹配的正式产物收口状态，不创建业务产物，也不把未选择阶段改成已选择。

## 3. 阶段动作

### 准备

严格按 `prepare-web-e2e-workspaces` 创建带时间戳的新批次。准备结果应包含五个 `<skill-name>-skill-v<version>.zip` 和 `packages/skills-manifest.json`。Skill ZIP 是跨批次、跨自建/开源 Profile 复用的按需离线安装材料，不表示各阶段绑定执行。

若完整仓库刚克隆且 Python 环境尚未准备，控制 Harness 只在仓库自身的 `.venv` 中补齐准备阶段实际缺少的 Python 依赖；不得修改系统 Python，也不得在候选 workspace 中安装依赖。仓库内的 `.agents/skills` 必须能发现 `run-web-e2e`、`prepare-web-e2e-workspaces`、`execute-web-e2e`、`orchestrate-web-e2e`、`score-web-e2e` 和 `report-web-e2e`，缺失时先停止并报告，不通过复制半套脚本继续。

单机全流程也必须从生成的 `__execution.zip` 解压出独立 Harness 单元根，再在该根执行和合入 `__scoring.zip`。不要直接把管理员批次中的 `harnesses/<harness>/` staging 目录当作 worker execution 包；staging 可能预置非空评分模板，标准评分交接会正确拒绝覆盖。该规则只改变本机文件搬运位置，不改变 execution receipt、候选哈希或离线回传契约。

### 执行与评分

执行完全遵守 `execute-web-e2e`。WorkBuddy、AstronStudio 和 QwenWork 新批次均默认三槽、最大八槽，三者 UI 操作均为单槽。用户显式指定模型时才传 `--model`，否则保持客户端当前模型和推理强度。

Windows AstronStudio 已按“只读探针 → 单个 L1（执行并发 1）→ 三个 L1 串行自动切题 → 五个 L1 默认三路并发与动态补位”完成真机生产验证。更换桌面客户端大版本或 Driver 核心实现后，必须按同一顺序回归，不得把 macOS 或旧 Windows 基线的结论直接外推。

执行回执有效后才按 `orchestrate-web-e2e` 复制到独立评分工作空间并启动评分。新回执声明运行时目录策略时，execution 原件可保留被评 Harness 生成的 `.cache`、`.vite`、`node_modules`，评分复制会过滤它们且不修改原件；任意命名但具备 Chromium `Local State` 与 profile 数据库特征的浏览器用户数据目录也会从评分副本整体过滤。未声明策略的旧回执仍严格拒绝候选运行时目录。Codex Desktop 新批次默认三槽，每题独立项目、任务、Browser 和端口。评分任务使用 `score-web-e2e`，候选 `workspace/` 永远只读；端口冲突只允许修改 `private-scoring/runtime-workspace/` 中的评分运行时副本。

### 离线回传与收集

评分生成有效 `submission.json` 后打包：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py export-return \
  --package-root /absolute/<batch_id>__workbuddy \
  --output-dir /absolute/offline-return
```

该命令生成 `<batch_id>__<harness>__return.zip` 和外部 `return-receipt.json`。回执绑定 ZIP SHA-256、批次、源码 revision、Profile、模型、Harness 和完整 task IDs。目标存在时拒绝覆盖。ZIP 不含 `.git`、`.cache`、`.vite`、`node_modules`、密钥、评分运行时副本、`.run-web-e2e` 控制状态，也不含动态识别出的 Chromium 浏览器用户数据目录（Cookies、Login Data、Local State、Crashpad 等）；过滤只作用于 ZIP，不清理 execution/score 原件。导入端会再次拒绝包含此类 profile 树的外部 ZIP。只有声明兼容策略的执行回执才允许 execution workspace 中存在可忽略运行时目录，score workspace 中出现同名目录仍失败关闭。

管理员离线收到 ZIP 和回执后导入：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py import-return \
  --batch-root /absolute/<batch-root> \
  --archive /absolute/<batch_id>__workbuddy__return.zip \
  --receipt /absolute/<batch_id>__workbuddy__return-receipt.json
```

导入先在隔离临时目录中校验 ZIP SHA、路径穿越、符号链接、唯一顶层 Harness 根、唯一 submission，以及批次/revision/Profile/Harness/task IDs；全部通过后才原子发布到 `<batch-root>/returns/<harness>/`。相同内容重复导入幂等，冲突内容拒绝覆盖。

### 报告

只有 `collect` 已完成或用户明确提供了一组已经校验的回传包时才进入 `report-web-e2e`。报告的 JSON、Markdown、Excel 三件套生成并验证后，再把 `report` 标记为 `COMPLETED`。

## 4. 不可变性和证据边界

- 同一 Harness（模型）单元不能拆到多台机器。
- execution 终态候选和复制后的 score 候选都不可修改。
- 不得把状态机单测、历史包、模拟 submission 或静态检查当作本轮真实 E2E 成绩。
- `NEEDS_ATTENTION`/`FAILED` 必须保留现场；恢复只处理原任务、原 attempt 和原磁盘状态。
- 每一阶段的具体门禁以对应单阶段 Skill 为准；本 Skill 不重新实现做题逻辑或评分判断。

离线文件格式和安全门禁见 [交接契约](references/handoff-contract.md)。
