---
name: execute-web-e2e
description: 在 WorkBuddy、AstronStudio、QwenWork 等桌面 Harness 中执行单个或批量 Web E2E 用例，持久化可恢复状态、终态证据和 execution_record；用于自动做题阶段，不负责评分或报告。
---

# 执行 Web E2E 用例

本 Skill 是桌面 Harness 执行自动化的唯一实现入口。当前已实现 WorkBuddy、AstronStudio、QwenWork 的单题 Driver 和后台并发队列；其他 Harness Driver 仍按 Roadmap 逐步接入。先读取 execution 包 `manifest.json` 的 `harness.id`，再选择同名 Driver，不能按文件名或客户端外观猜测。

## AstronStudio

依赖由调用本 Skill 的控制 Harness 在 AstronStudio Driver 目录执行锁定安装，不进入候选 workspace：

```bash
cd .agents/skills/execute-web-e2e/drivers/astronstudio
npm ci
```

只读预检不会创建任务或发送 Prompt。macOS：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-astronstudio.sh --probe
```

Windows：

```bat
.agents\skills\execute-web-e2e\scripts\run-astronstudio.cmd --probe
```

预检要求本机 `http://127.0.0.1:9240`、可交互且未锁定的桌面和 AstronStudio 状态库均可用。状态库保留 `%USERPROFILE%\.acode\acode\userdata\state.sqlite` 为第一候选；Windows 上该文件不存在时，继续检查基于当前用户 `%LOCALAPPDATA%` 动态解析的 `%LOCALAPPDATA%\Programs\AStudio Data\userdata\state.sqlite`。macOS 默认使用 `/Applications/AStudio.app`；Windows 依次读取 `HKCU\Software\AStudio`、历史品牌注册表和 `%LOCALAPPDATA%\Programs`，也可显式传 `--app-path <AStudio.exe或安装目录>`。SQLite 优先使用 Node.js 自带的 `node:sqlite`；运行时不提供该模块时才回退到系统 `sqlite3` 命令。`--probe` 不会点击“新建任务”；停在历史会话时 workspace picker 不可见只是诊断信息，只要“新建任务”、编辑器、权限和模型控件可用仍可执行。需要由 Driver 启动客户端时，在确认没有活动或待处理任务后显式传 `--restart-app`。

后台并发执行完整 manifest 中的任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-astronstudio-batch.sh \
  /absolute/<batch_id>__astronstudio \
  --run-id <queue_id> \
  --task-id <task_id_1> \
  --task-id <task_id_2> \
  --run-slots 3 \
  --permission-mode full-access
```

Windows 使用相同参数和原生入口：

```bat
.agents\skills\execute-web-e2e\scripts\run-astronstudio-batch.cmd C:\absolute\batch__astronstudio --run-id queue-1 --task-id task-1 --task-id task-2 --run-slots 3 --permission-mode full-access
```

Windows 入口、平台探测和状态库读取已在目标 Windows 机器完成真机验证。Driver 1.10.18 在 1.10.16 的发送后会话身份捕获基础上，隔离 Windows 启动时由控制 Harness 注入的 `CODEX_*`、`CHATGPT_*` 和 Node IPC 环境变量，并只记录被删除的变量名；用户的 PATH、代理和模型凭据保持不变。活跃 SQLite 文件的复制放入独立子进程并设 10 秒硬超时，遇到 Windows 长时间文件锁时终止复制子进程、记录读库失败并回退到同一 thread 的 DOM 观察，不得卡死队列或重发 Prompt。旧版本的单题、三题串行和默认三路并发证据均需重验；必须先显式使用 `--run-slots 1`，通过只读探针、单题和三题串行后再测试并发。单题尚未重新通过时，不得把静态测试或旧 Driver 结果表述为当前 Windows 生产验证。

AstronStudio 固定 `ui_slots=1`，新队列默认 `run_slots=3`、最大 8；显式 `--run-slots 1` 可回退为串行。项目创建、模型/权限回读、Prompt 发送和 thread 切换仍由同一个 Driver 串行操作。发送后在有界 120–180 秒窗口内，只有 AstronStudio 当前或已持久化路由、本地 SQLite 的发送后 session、非空 turn 和精确 cwd 共同确认时才释放 Driver；Worker 轮流恢复各 thread 做一次性观察。任一题到达明确终态并通过 automation/execution 一致性检查后释放槽位并动态补入下一题。队列必须覆盖 manifest 的完整 task ID 集合，才可能生成 `integrity.valid=true` 的 `execution-receipt.json`。

省略 `--model` 时保持并回读客户端当前模型与推理强度；显式提供时只切换并回读模型，不修改推理强度。`--permission-mode full-access` 会幂等确认完全访问。模型、权限和项目绝对路径均必须在发送 Prompt 前回读并写入状态。

Worker 或 Driver 中断后，用完全相同的批次参数增加 `--resume`。已捕获稳定 thread ID 后，恢复只按该 ID 和单题绝对路径观察原会话，不重发 Prompt。若发送后状态因数据库可见性延迟而缺少 thread/turn，恢复入口只允许用发送前已经持久化的路由、发送后时间、非空 turn 和精确 cwd 补全同一身份；没有路由匹配时即使存在更新更晚的同 cwd session 也必须拒绝。只有一个活动任务时，客户端崩溃后可增加 `--restart-app-on-resume`；多个活动任务并发时，首版拒绝自动重启并停在 `NEEDS_ATTENTION`，避免错误接管或中断其他会话。AstronStudio 出现授权、用户输入或未知状态时停在 `NEEDS_ATTENTION`，不自动批准交互。

如果 Prompt 发送前因 CDP 或 UI 自动化错误进入 `INFRA_FAILED`，且候选 workspace 经哈希确认完全未变化，可使用相同参数增加 `--resume --retry-pre-send-failure`。旧 attempt 会隔离归档；发送后失败或产物已有任何变化时拒绝自动重试。

AstronStudio 的终态优先读取本地 SQLite 的 thread session、turn、open turn 和 pending interaction 投影，DOM 只补充可见运行态、交互和最终回复。workspace 稳定不能单独判定完成。
活跃 WAL 写入期间若某次 SQLite 快照不一致，Driver 会把失败次数、最近错误和恢复时间记录到 `evidence.state_database_observation`，并在执行时限内基于 DOM 保持等待；后续快照恢复后继续按原 thread/turn/cwd 判定。到达 deadline 时状态库仍不可读则进入 `NEEDS_ATTENTION`，不会把 DOM 或 workspace 稳定误当作成功，也不会重发 Prompt。

AstronStudio 任一终态（成功、明确失败或安全超时）在冻结候选 workspace 前都必须写入 `terminal_process_cleanup`。Windows 只按候选 workspace 的完整绝对路径精确识别、终止相关进程并回读零残留；不得按 AstronStudio、Node 或浏览器进程名宽泛清理。macOS 当前没有等价的任务进程枚举实现，显式记录 `supported=false, success=true`，不能伪装成已执行进程终止。清理失败进入 `NEEDS_ATTENTION`，队列不得补位，也不能生成有效回执；`TIMEOUT` 同时复用该证据到 `timeout.process_cleanup`。

若旧终态由此前 Driver 版本产生且缺少清理证据，可以用完全相同的单题或队列参数增加 `--resume` 补录。补录前后必须把当前候选 SHA-256 与原终态冻结 SHA-256 精确匹配；冻结值缺失或候选已有漂移时失败关闭。该路径只补录终态证据、更新 Driver 版本，不创建项目、不恢复新会话，也不重发 Prompt。

## QwenWork

依赖由控制 Harness 在 QwenWork Driver 目录执行锁定安装，不进入候选 workspace：

```bash
cd .agents/skills/execute-web-e2e/drivers/qwenwork
npm ci
```

只读预检：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-qwenwork.sh --probe
```

Windows 使用 `run-qwenwork.cmd --probe`。Driver 从当前用户卸载注册表和 `%LOCALAPPDATA%\Programs\QwenWorkCN` / `%LOCALAPPDATA%\Programs\QwenWork` 动态解析版本化安装子目录中的 `QwenWorkCN.exe` / `QwenWork.exe`，状态库按当前用户解析为 `%APPDATA%\QwenWorkCN\data\agents.db`；不得写死用户名或客户端版本。Windows Node.js 不提供 `node:sqlite` 时按顺序回退到 `py -3`、`python` 的只读 `sqlite3`。macOS 使用 `/Applications/QwenWorkCN.app` 和 `~/Library/Application Support/QwenWorkCN/data/agents.db`。两端预检均要求本机 `http://127.0.0.1:9250`、可交互且未锁定的桌面、状态库、项目入口、Prompt 编辑器、模型及权限控件可用；`--probe` 不创建项目、不发送 Prompt。

QwenWork 通过“新建个人项目”对话框选择单题根目录；macOS 使用辅助功能 helper，Windows 使用当前 Driver 目录下的 PowerShell UI Automation helper，并按动态发现的主程序完整路径约束原生窗口。原生目录选择后必须从 `local_projects.root_paths` 回读完整绝对路径，不能只信任文件夹 basename。Windows Electron 截图使用当前页面的 CDP `Page.captureScreenshot`，每张截图记录路径、采集方法和时间。

后台并发执行完整 manifest 中的任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-qwenwork-batch.sh \
  /absolute/<batch_id>__qwenwork \
  --run-id <queue_id> \
  --task-id <task_id_1> \
  --task-id <task_id_2> \
  --run-slots 1 \
  --permission-mode full-access
```

Windows 使用相同参数和原生入口：

```bat
.agents\skills\execute-web-e2e\scripts\run-qwenwork-batch.cmd C:\absolute\batch__qwenwork --run-id queue-1 --task-id task-1 --task-id task-2 --run-slots 1 --permission-mode full-access
```

QwenWork 的 Token 暴露由 Driver 管理，用户和控制 Harness 都不需要预先设置环境变量。全新单题默认执行一次安全客户端重启；全新批次默认只在第一题前安全重启。Driver 在新客户端子进程中同时注入本机 CDP 参数和 `QODERCN_EXPOSE_TOKEN_USAGE=1`，不修改控制 Harness 的全局环境。重启前若状态库或存活进程表明存在活动任务，立即停止并进入人工处理。已有客户端进程不能在运行中补加该变量，因此禁止为了省略重启而复用无法证明已带开关的旧进程。

开关只允许原生 usage 出现在 transcript 中，不能绕过指标 Profile。采集器仍须精确核对平台、QwenWork 客户端、SDK、transcript 版本和 runtime SHA；未知身份保持 `unverified`，历史 `masked` 样本不得回填。资源字段、状态和 QwenWork Profile 的详细口径见[资源指标参考](references/resource-metrics.md)。execute-web-e2e 1.12.4 / QwenWork Driver 1.10.15 首次引入自动注入，发布包必须重新通过 probe 和一个全新 L1 后才能继承既有生产准入。

QwenWorkCN 1.0.5.0 的历史 Windows 身份已覆盖动态路径、进程、SQLite、CDP 启动、页面识别、串行、并发和部分恢复边界。当前主流程与资源指标证据以生产验收清单为准：QwenWorkCN 1.0.6.0 已在 `ff5d476...` 完成带指标的全新单 L1 闭环，四个核心 Token 均为 `observed`；自动注入实现属于后续 1.12.4 / Driver 1.10.15 候选，真机重验前不得把旧证据直接升级到该新身份。验收模型为 `标准｜Qwen3.8-Flash`，权限为 `full-access`；更换客户端大版本、Driver 核心实现或模型后仍须从只读 probe 和一至三个 L1 smoke 开始回归。

QwenWork 固定 `ui_slots=1`，新队列默认 `run_slots=3`、最大 8；显式 `--run-slots 1` 可回退为串行。项目创建、目录选择、权限/模型回读和 Prompt 发送始终由一个 Driver 串行完成；捕获稳定 `session_id`、`stream_id`、`local_project_id` 和绝对 cwd 后释放 UI Driver，由 Worker 轮流恢复原会话做一次性观察。任一题明确终态后释放后台槽位并动态补入下一题。

省略 `--model` 时保持并回读当前模型；显式提供时按 UI 精确名称选择并回读，不修改任务模式或其他推理设置。`--permission-mode full-access` 会通过 QwenWork 自身的全局风险确认切换为“完全访问权限”；省略时只记录当前权限。一个队列运行期间不得人工改变模型。

Prompt 发送后以 `sub_chats.session_id` 作为稳定内核会话 ID，以 `sub_chats.stream_id` 和 `chats.ext.taskStatus` 判断运行/终态，DOM 只补充可见授权、停止控件和最终回复。恢复时必须同时匹配稳定 session ID 和项目绝对路径；项目内会话不唯一或无法定位时进入 `NEEDS_ATTENTION`，不得新建任务或重发 Prompt。客户端重启前如数据库和存活进程共同表明仍有活动任务，Driver 拒绝重启。

QwenWork 出现 `data-slot="user-question"` 问卷或其他明确用户输入请求时，Driver 保存问题标题、分页和问题摘要后进入 `NEEDS_ATTENTION`。控制端不得点击“推荐”“跳过”或提交任何选项，因为这会代替被评测 Agent 作答并产生第二条用户消息。Windows 页面激活和 CDP 截图均有有界超时；原生目录选择器只扫描当前 QwenWork 进程拥有的标准 `#32770` 系统对话框，避免遍历 Electron 主窗口的完整可访问性树。

已确认不再继续的问卷任务可由控制端显式使用单题 Driver 的 `--resume --abandon-user-question` 收口。该动作只在原 automation 已记录 `NEEDS_ATTENTION`、问卷摘要、稳定 conversation/session/project 和绝对 cwd，且当前页面仍显示同一问卷与唯一停止控件时生效；它只点击停止，不点击“推荐”“跳过”或答案，并在数据库确认 stream 结束、候选 workspace 静默后记录结构化 `INFRA_FAILED`。若客户端重启已把原 session 明确标记为 `interrupted`，则直接按数据库终态失败收口。若原默认 CDP 留下无法响应且找不到所属主进程的 Windows 幽灵监听，可额外显式传新的本机 `--endpoint` 与 `--restart-app`；只有原端点不可达、QwenWork 主进程确实不存在时才允许临时端口恢复。同一已核对的临时 QwenWork 实例可继续收口其他身份完整匹配的旧问卷 session，但不能用于继续做题或重发 Prompt。

控制任务或队列 Worker 中断后，由新的控制任务使用完全相同的批次参数增加 `--resume`。恢复只按已持久化的 attempt、`session_id`、`local_project_id` 和绝对 cwd 观察原会话，不重新创建项目或发送 Prompt。队列历史用 `WORKER_INTERRUPTED` 和 `WORKER_RESUMED` 记录旧、新 Worker PID；恢复验收必须确认 `TASK_DISPATCHED` 与 automation 中 `PROMPT_SENT` 均仍只有一次。

Windows `.cmd`、终端或宿主进程可能直接结束 Worker，导致 Node 收不到可捕获的 SIGINT/SIGTERM。此时 `--resume` 必须先核对状态中的旧 Worker 属于当前主机且 PID 已消失，再以 `signal=PROCESS_LOST`、`inferred=true` 补记 `WORKER_INTERRUPTED`，清理已退出的遗留 Driver/锁，随后记录 `WORKER_RESUMED`；旧 Worker PID 仍存活或来自其他主机时拒绝启动第二个 Worker。

QwenWork 客户端崩溃且本地 CDP 端口已经关闭时，使用相同参数增加 `--resume --restart-app-on-resume`。Driver 只重启一次客户端，并从数据库确认唯一项目、原 `session_id` 和侧栏中的原 conversation 后继续观察；项目名称同时出现在侧栏和新任务选择器属于同一数据库项目的两个视图，恢复只使用侧栏项目树定位。若 QwenWork 把原 session 恢复为运行或完成状态，沿用原 attempt 收口；若客户端明确把它标记为 `interrupted`，则记录 `INFRA_FAILED`，不得重发 Prompt 或伪造恢复成功。数据库存在多个项目、多个会话或 cwd 不一致时仍停在 `NEEDS_ATTENTION`。

QwenWork 达到执行时限后必须唯一定位并点击当前会话停止控件，以数据库或连续非运行态确认取消，再按候选 workspace 完整绝对路径精确收口相关进程并观察 workspace 静默。终态进程清理证据同时写入 `terminal_process_cleanup` 和 `timeout.process_cleanup`；只有取消确认、进程零残留和静默哈希稳定均成立时才记录 `TIMEOUT`，任何一项缺失都停在 `NEEDS_ATTENTION`。

## WorkBuddy 单题

依赖准备由调用本 Skill 的控制 Harness 完成，不要求用户手工进入 Driver 目录。控制 Harness 先检查 `node_modules/playwright-core` 和锁文件状态；缺失或 `npm ls --depth=0` 失败时，在 Driver 目录自动执行锁定安装。依赖只能安装在 Skill 的 Driver 目录，不能安装到候选工作空间：

macOS：

```bash
cd .agents/skills/execute-web-e2e/drivers/workbuddy
npm ci
```

Windows：

```powershell
Set-Location .agents\skills\execute-web-e2e\drivers\workbuddy
npm ci
```

`npm ci` 失败时保留原始错误并停止执行，不能改用未锁定版本或把依赖装进题目目录。

只读预检：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh --probe
```

Windows 使用 `run-workbuddy.cmd --probe`。Driver 从当前用户卸载注册表和 `%LOCALAPPDATA%\Programs\WorkBuddy` 动态解析 `WorkBuddy.exe` / `CodeBuddy.exe`，状态库固定按当前用户解析为 `%USERPROFILE%\.workbuddy\workbuddy.db`；不得写死用户名。Windows Node.js 不提供 `node:sqlite` 时按顺序回退到 `py -3`、`python` 的只读 `sqlite3`，不能把 Driver 依赖装入候选 workspace。由 Driver 重启 WorkBuddy 时，还会动态选择 `%USERPROFILE%\.workbuddy\binaries\node\versions` 中版本最高且同时含 `node.exe`、`npm.cmd` 的客户端运行时，将其加入新客户端的进程级 `PATH`；同时为 npm 默认关闭 audit、fund 和更新提示、优先复用本地缓存，并按 WorkBuddy 官方环境变量把 Shell 默认/最大命令时限设为 600000 毫秒，避免 Windows 大依赖树被客户端默认 120000 毫秒中止。用户已显式设置的同名环境值优先。准备结果写入 `automation_state.json.client.launch.attempts[].environment_preparation`，不得写死版本或用户目录。

Windows WorkBuddy 的 Electron 页面在部分更新版本中会让 Playwright 高层截图接口永久等待，即使字体已经加载完成。Driver 在 Windows 必须通过当前已附着页面的 CDP `Page.captureScreenshot` 直接采集可视区域 PNG；macOS 继续使用 Playwright 截图。每张截图的路径、采集方法和时间写入 `evidence.screenshot_captures`，截图失败仍须失败关闭，不能跳过证据门禁。

WorkBuddy 5.5.6 在多会话运行期间可能偶发单次 `connectOverCDP` 超时。Driver 对每次连接使用最多三次、单次最多 10 秒的有界重试；连续失败后仍进入 `NEEDS_ATTENTION`，不得因此新建任务或重发 Prompt。

WorkBuddy 5.5.6 重启后可能暂时不在侧栏渲染新 conversation 的 `data-conversation-id`。恢复时若精确 cwd 和已持久化 conversation ID 对应的数据库会话已经是明确终态，可直接按该数据库终态收口；若它仍在运行，仅当数据库里恰好只有这一条运行会话、当前主对话区仍显示原 Prompt 且页面有运行控件时，才允许继续观察当前页。任一条件不唯一或不一致都停在 `NEEDS_ATTENTION`，不得按标题猜测会话。

`--probe` 不会点击“新建任务”。WorkBuddy 只有在新任务页挂载 workspace picker；若当前停在历史会话页，探针会以 `workspace-picker-not-visible` 返回未就绪。切换到未发送的新任务页后重跑，不能把该结果误判为插件或 CDP 不可用。

执行一个准备包中的任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh \
  /absolute/batch-root/execution/tasks/<task_id> \
  --permission-mode full-access \
  --restart-app
```

上例不传 `--model`，Driver 会保留并回读 WorkBuddy 当前模型，不操作模型的推理强度。跑批前应由测试人员在 WorkBuddy 中配置好默认模型和推理强度。需要覆盖当前模型时再显式增加 `--model <UI 精确显示名>`。

`--restart-app` 会退出并重新启动 WorkBuddy，仅在当前没有需要保留的运行任务时使用。Driver 会先按完整主程序路径唯一核对主进程，读取状态库确认没有其他活动任务，并确认旧进程和 CDP 均已退出；Windows 只终止已核对的进程树，macOS `open` 做最多 3 次有界重试。每次都必须回读本地 CDP 才算启动成功，尝试证据写入 `automation_state.json.client.launch`。WorkBuddy 已通过本地 CDP 端口启动时省略该参数。单题和批量入口都支持显式 `--endpoint <本机CDP地址>` 与 `--app-path <完整主程序路径>`；批量队列会冻结这两个连接参数并逐题透传，恢复时必须保持一致。只有发送前失败且候选零变化时，才允许在 `--resume --retry-pre-send-failure` 中为旧队列补录连接覆盖，例如绕开 Windows 已确认的陈旧监听端口；不得静默换端口或在 Prompt 已发送后改连其他实例。

中断后恢复：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh \
  /absolute/batch-root/execution/tasks/<task_id> \
  --resume
```

恢复时必须沿用相同的 `automation_state.json`。Prompt 已进入发送临界区后，Driver 只检查已有 WorkBuddy conversation，不能盲目重发。侧栏 ID 暂时缺失时只允许使用上一段定义的精确数据库终态或“唯一运行会话 + 当前主区原 Prompt”回退；状态不明时停在 `NEEDS_ATTENTION`。

运行中 Worker 收到 `SIGINT`/`SIGTERM` 时会记录 Worker 和 Driver PID、终止观察 Driver、释放 UI 锁，但不会停止 WorkBuddy 内的任务；使用同一参数加 `--resume` 后按已捕获的 `data-conversation-id` 恢复原会话。Worker 被 `SIGKILL` 或 Windows 宿主直接结束时，恢复入口会在确认旧 PID 已消失后补记推断型 `WORKER_INTERRUPTED(signal=PROCESS_LOST)`，再通过 stale-lock 和遗留 Driver 检查恢复；旧 Worker/Driver 仍存活或旧 Worker 属于其他主机时拒绝启动第二个进程。

## WorkBuddy 后台并发队列

用同一 `run-id` 按声明顺序执行多个任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy-batch.sh \
  /absolute/<batch_id>__workbuddy \
  --run-id <queue_id> \
  --task-id <task_id_1> \
  --task-id <task_id_2> \
  --run-slots 3 \
  --permission-mode full-access
```

Windows 使用同名参数的 `run-workbuddy-batch.cmd`。为避免 npm 依赖树触发传统 Win32 长路径问题，worker 必须直接解压到 `D:\debug-workspace\web-e2e\w\<短批次ID>` 这类短目录，不能再嵌套 `workers\<完整批次名>\<完整包名>`；解压后还要在发送前确认每题候选 `workspace` 绝对路径长度不超过 180。该限制只约束 worker 的本机搬运位置，不改变包内 task ID、execution receipt 或候选哈希。WorkBuddy 5.5.6 与 `xopglm52` 曾在 Windows 三路后台会话中出现第三条会话 `session/load` 或 `session/set_mode` 初始化超时，双路五题动态补位则已 5/5 通过。当前产品契约重新统一为三路默认，因此目标客户端、模型和机器必须重新完成五题三槽动态补位验证，旧双路证据不能证明新默认值生产可用；验证前可显式回退到 `--run-slots 1` 或 `2`。

新队列默认 `run_slots=3`，最大 8；显式 `--run-slots 1` 可回退为串行。已有队列冻结首次记录的并发值，恢复时省略该参数会沿用冻结值，显式提供不同值则失败关闭。没有 `run_slots` 字段的旧队列迁移为 1，不自动升级为 3。

`--model` 是可选覆盖项，接收 WorkBuddy 模型下拉框中的精确显示名，例如 `--model xopglm52`。显式传入时，Driver 选择并回读该模型；省略时，Driver 只回读当前模型，不展开下拉框，也不再自动选择“均衡”。两种模式都不操作推理强度。一个队列运行期间不得人工改变模型；所有题的实际回读模型必须一致。同一个 `run-id` 恢复时模型模式和显式请求值不可变；可选 `execution_record.json` 已预声明模型时，实际回读值也必须与其一致。

`--permission-mode full-access` 是评测运行的显式授权：Driver 会在发送 Prompt 前回读权限状态，已开启时不重复点击；未开启时通过 WorkBuddy 自身的风险确认界面开启。WorkBuddy 5.5.3 将该设置作用于当前客户端的全部任务，而不是单个项目。省略该参数时默认 `current`，只记录当前权限，不修改客户端设置。

Worker 从 Harness 根目录的 `manifest.json` 按精确 task ID 解析工作空间，使用文件锁保证同一 execution 包只有一个 WorkBuddy UI 队列，并把状态写到 `execution/.execute-web-e2e/queues/<queue_id>/queue_state.json`。`ui_slots` 始终为 1：新建项目、设置权限/模型、发送 Prompt、切换会话和处理授权都由同一个 Driver 串行完成。Prompt 发送并捕获稳定 conversation ID 后，Driver 退出观察，让 WorkBuddy 最多保留 `run_slots` 个后台 Agent 任务；Worker 轮流按原 conversation ID 做一次性观察。任一题明确终态并通过自动化状态与 `execution_record.json` 一致性校验后释放槽位，立即补入下一题。

模型下拉框完成唯一回读后，Driver 必须在发送 Prompt 前把实际模型写入 `execution_record.json.model`。显式模式记录 `mode=explicit` 及请求/实际模型；保持当前配置时记录 `mode=current`、`requested_model=null` 和实际模型。若执行记录预先声明了不同模型则失败关闭。最终回执的顶层 `model`、逐题 `model_selection` 和 execution record 必须一致，不能等到报告阶段再补模型身份。

队列出现 `NEEDS_ATTENTION` 后停止补入新题，但继续收口已经投递的其他活动题；活动题全部结束后再返回阻塞状态。先处理或扩充经过审查的安全规则，再使用完全相同的参数加 `--resume`。默认遇到 `INFRA_FAILED` 或 `TIMEOUT` 也停止补题；只有明确需要验证失败隔离时才使用 `--continue-on-terminal-failure`。

客户端崩溃后恢复时使用 `--resume --restart-app-on-resume`。一次恢复只重启 WorkBuddy 一次，随后串行定位所有活动 conversation。只有发送后已经捕获稳定 conversation ID 时才允许重启并从侧栏恢复原会话；缺少 ID 或无法唯一定位时停在 `NEEDS_ATTENTION`，不创建新任务。

Windows 重启恢复还会等待原 conversation 对应的唯一 WorkBuddy 会话宿主重新出现。若客户端只恢复出数据库中的陈旧 `working` 状态，但 60 秒内没有恢复会话宿主，则按 `workbuddy-client-restart-unrecovered` 记录结构化 `INFRA_FAILED`；不能继续等待到普通执行超时，更不能把陈旧状态伪装成恢复成功。若数据库明确把原会话标记为 `interrupted`，同样保留为结构化执行失败且不重发 Prompt。

人工处理 `NEEDS_ATTENTION` 后可在恢复参数中增加 `--mark-manual <task_id>`。该参数只在队列和 Harness 回执中记录人工介入原因，随后仍由 Driver 检查原会话终态；它不能把未知状态直接改成成功，也不能绕过 Prompt 幂等和终态证据门禁。

达到执行时限后 Driver 必须点击当前会话的停止按钮，确认 WorkBuddy 已进入非运行态，并验证候选 workspace 在静默观察窗口内不再变化。Windows 还必须按候选 workspace 完整绝对路径发现后台种子进程，只终止这些种子及其后代并回读零残留；进程清理摘要写入 `timeout.process_cleanup`，不能用进程名做宽泛清理。只有停止确认、进程清理和 workspace 静默三项证据齐全时才记录 `TIMEOUT`；否则记录 `NEEDS_ATTENTION`。即使指定 `--continue-on-terminal-failure`，任一条件未确认的超时任务也不能进入下一题。

WorkBuddy 任一终态（成功、明确失败或安全超时）在冻结候选 workspace 前，还必须收口当前任务的会话宿主及其进程树。Windows 只能同时依据 WorkBuddy `--serve`、`--session-id` 和任务根完整绝对路径唯一定位会话宿主，并保留候选 workspace 进程匹配作为补充；不得按 WorkBuddy/Node 进程名宽泛终止。首次回读零残留后还要保持 45 秒安静观察，普通终态最多观察 120 秒，期间出现的迟到候选进程必须按精确路径再次清除并重新计算安静窗口；这样可覆盖 WorkBuddy 在首轮清理接近一分钟时才投递的预览进程。清理结果写入 `terminal_process_cleanup` 并进入 execution receipt；清理失败、安静窗口不足或匹配到多个宿主时进入 `NEEDS_ATTENTION`，禁止批次补位或生成有效回执。

若 `NEEDS_ATTENTION` 的最后原因仅为 `terminal-task-process-cleanup-failed`，同一 run-id 的 `--resume` 可以自动重新观察原 conversation 并再次执行精确收口；该恢复路径不得重发 Prompt，也不能跳过终态、进程零残留或安静窗口门禁。

队列退出时会在 Harness 根目录生成 `execution-receipt.json`，汇总任务范围、attempt、自动化/正式状态、客户端与 Driver 版本、请求/实际模型、权限、Prompt/workspace 哈希和证据相对路径。生成回执时会重新计算每题 workspace SHA；`integrity.valid=true` 要求请求任务集合与 manifest 完全一致、记录齐全、身份和模型一致、所有任务均为终态，且当前 workspace 的候选文件仍等于 Driver 终态冻结值。若候选文件已漂移，队列改为 `FAILED`，不得进入评分。

被评 Harness 为运行或构建网站生成的 `.cache`、`.vite`、`node_modules` 属于可忽略运行时目录：Driver 不删除或修改它们，而是在回执中用 `wildclawbench.web-e2e-runtime-directory-policy/v1` 声明策略并逐题记录实际路径；它们不参与候选哈希，也不导致 `integrity.valid=false`。`.git` 仍是禁止目录，出现即使回执无效。只有显式声明该策略的新回执才能容忍运行时目录；旧回执继续使用严格规则。评分交接和离线回传只过滤可忽略目录，不从 execution 原件中清理它们。

如果 Driver 在 Prompt 发送前因 UI 自动化错误进入 `INFRA_FAILED`，且候选 workspace 没有任何变化，可在修复根因后使用 `--resume --retry-pre-send-failure`。旧 attempt 会移入相邻的 `.attempts/<task_id>/<attempt_id>/` 留存审计；发送后失败、超时或已有产物变化时拒绝自动重试。

## 执行约束

终态默认只读采集每题资源指标并写入 `execution_record.json`，支持 AstronStudio、WorkBuddy 和 QwenWork；具体可用字段、缓存/请求口径、null 与覆盖率、停用方式以及 QwenWork 实验开关见 [资源指标契约](references/resource-metrics.md)。评分阶段不得估算或回填执行消耗。需要排查采集问题时使用旁路 CLI，不能修改已冻结的历史记录。

- 选择的是单题根目录 `execution/tasks/<task_id>/`，不是其中的 `workspace/`。
- WorkBuddy 5.5.3 优先通过其输入框 workspace provider 写入并回读绝对路径；只有该能力不存在时才退回 macOS 原生文件夹选择器。不能只凭同名目录标签确认工作空间。AstronStudio 通过应用内路径输入与项目回读完成选择，不依赖 Windows 原生文件夹选择器。
- Prompt 只从 `PROMPT.md` 读取；状态中只保存 SHA-256 和字节数，不复制正文。
- Prompt 发送后尽早保存侧栏 `data-conversation-id`；这是 WorkBuddy session DB 缺少当前会话时，运行中断和客户端重启恢复的稳定标识。
- `automation_state.json` 和过程截图写到单题目录外；完成后的 transcript 证据才写回 `.web-e2e-evidence/`。
- 执行终态后的 `workspace/` 是不可变候选产物。控制 Agent 不得为解决端口冲突、启动失败或打包检查而改写其中的源码；发现残留服务时只能在能够证明 PID 属于当前任务的情况下精确停止，否则停在 `NEEDS_ATTENTION`，禁止使用宽泛进程清理。
- 回执生成后不能通过编辑 `execution-receipt.json`、重算哈希或从评分副本覆盖回来“修复”候选；发生任何不一致时保留现场并重新执行该评测单元。
- 优先使用 WorkBuddy 本地 session 数据库中的 conversation 状态判定终态；DOM 负责补充运行中、授权弹窗和最终回复证据。`data-status=complete` 必须同时有实质 Markdown 回复，或同一 Agent turn 中同时出现“已完成”状态与 `conversation-finished-footer`；折叠工具卡标题不能冒充最终回复。不能用固定睡眠或 workspace 文件稳定代替明确终态。
- 未知授权、未知 session 状态、Prompt 发送临界区不明确都失败关闭。
- “允许完全访问”只决定 WorkBuddy 创建任务时的权限模式；若运行中仍出现授权面板，Driver 继续按下面的严格命令白名单处理，不会因为客户端已开启完全访问而自动批准未知操作。
- 生产跑批前由测试人员按指导手册设置 Harness 的默认模型和推理强度。执行自动化只在显式提供 `--model` 时切换模型；推理强度始终沿用 Harness 当前配置，不由 Playwright 选择或校验。
- 只允许 Driver 对显式白名单且严格限定在候选 `workspace/` 内的普通操作自动选择一次性“允许”；当前唯一规则是清理该目录下的 `.DS_Store`。其他命令（包括同类命令的路径或参数变化）一律停在 `NEEDS_ATTENTION`。
- `SUCCEEDED`、`INFRA_FAILED`、已确认停止的 `TIMEOUT` 分别映射为 `execution_record.json` 的 `completed`、`execution_error`、`timeout`；没有生成有效站点仍是正常完成，由评分阶段判低分。
- WorkBuddy、AstronStudio 和 QwenWork 始终保持 `ui_slots: 1`；新队列技术默认 `run_slots: 3`、最大 8。这里的并发只指已投递 Agent 在客户端后台并行运行，禁止同时启动多个 Playwright Driver 抢占窗口。QwenWork 当前生产 canary 显式使用 `--run-slots 1`；首次换机、升级 Harness/Skill 或切换模型后也先用 3 个 L1 串行冒烟，通过真实隔离验证后再恢复并发。

实现或审查其他 Driver 时，完整读取 [Driver 契约](references/driver-contract.md)。
