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

只读预检不会创建任务或发送 Prompt：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-astronstudio.sh --probe
```

预检要求 `/Applications/AStudio.app`、本机 `http://127.0.0.1:9240`、macOS 可交互桌面和 `~/.acode/acode/userdata/state.sqlite` 均可用。`--probe` 不会点击“新建任务”；停在历史会话时 workspace picker 不可见只是诊断信息，只要“新建任务”、编辑器、权限和模型控件可用仍可执行。需要由 Driver 启动客户端时，在确认没有活动或待处理任务后显式传 `--restart-app`。

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

AstronStudio 固定 `ui_slots=1`，新队列默认 `run_slots=3`、最大 8；显式 `--run-slots 1` 可回退为串行。项目创建、模型/权限回读、Prompt 发送和 thread 切换仍由同一个 Driver 串行操作。发送后只有在 AstronStudio 路由与本地 SQLite 共同确认稳定 thread、turn 和 cwd 时才释放 Driver；Worker 轮流恢复各 thread 做一次性观察。任一题到达明确终态并通过 automation/execution 一致性检查后释放槽位并动态补入下一题。队列必须覆盖 manifest 的完整 task ID 集合，才可能生成 `integrity.valid=true` 的 `execution-receipt.json`。

省略 `--model` 时保持并回读客户端当前模型与推理强度；显式提供时只切换并回读模型，不修改推理强度。`--permission-mode full-access` 会幂等确认完全访问。模型、权限和项目绝对路径均必须在发送 Prompt 前回读并写入状态。

Worker 或 Driver 中断后，用完全相同的批次参数增加 `--resume`。已捕获稳定 thread ID 后，恢复只按该 ID 和单题绝对路径观察原会话，不重发 Prompt。只有一个活动任务时，客户端崩溃后可增加 `--restart-app-on-resume`；多个活动任务并发时，首版拒绝自动重启并停在 `NEEDS_ATTENTION`，避免错误接管或中断其他会话。AstronStudio 出现授权、用户输入或未知状态时停在 `NEEDS_ATTENTION`，不自动批准交互。

如果 Prompt 发送前因 CDP 或 UI 自动化错误进入 `INFRA_FAILED`，且候选 workspace 经哈希确认完全未变化，可使用相同参数增加 `--resume --retry-pre-send-failure`。旧 attempt 会隔离归档；发送后失败或产物已有任何变化时拒绝自动重试。

AstronStudio 的终态优先读取本地 SQLite 的 thread session、turn、open turn 和 pending interaction 投影，DOM 只补充可见运行态、交互和最终回复。workspace 稳定不能单独判定完成。

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

预检要求 `/Applications/QwenWorkCN.app`、本机 `http://127.0.0.1:9250`、macOS 可交互桌面、辅助功能权限和 `~/Library/Application Support/QwenWorkCN/data/agents.db` 可用。QwenWork 通过“新建个人项目”对话框选择单题根目录；原生目录选择后必须从 `local_projects.root_paths` 回读完整绝对路径，不能只信任文件夹 basename。

后台并发执行完整 manifest 中的任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-qwenwork-batch.sh \
  /absolute/<batch_id>__qwenwork \
  --run-id <queue_id> \
  --task-id <task_id_1> \
  --task-id <task_id_2> \
  --run-slots 3 \
  --permission-mode full-access
```

QwenWork 固定 `ui_slots=1`，新队列默认 `run_slots=3`、最大 8；显式 `--run-slots 1` 可回退为串行。项目创建、目录选择、权限/模型回读和 Prompt 发送始终由一个 Driver 串行完成；捕获稳定 `session_id`、`stream_id`、`local_project_id` 和绝对 cwd 后释放 UI Driver，由 Worker 轮流恢复原会话做一次性观察。任一题明确终态后释放后台槽位并动态补入下一题。

省略 `--model` 时保持并回读当前模型；显式提供时按 UI 精确名称选择并回读，不修改任务模式或其他推理设置。`--permission-mode full-access` 会通过 QwenWork 自身的全局风险确认切换为“完全访问权限”；省略时只记录当前权限。一个队列运行期间不得人工改变模型。

Prompt 发送后以 `sub_chats.session_id` 作为稳定内核会话 ID，以 `sub_chats.stream_id` 和 `chats.ext.taskStatus` 判断运行/终态，DOM 只补充可见授权、停止控件和最终回复。恢复时必须同时匹配稳定 session ID 和项目绝对路径；项目内会话不唯一或无法定位时进入 `NEEDS_ATTENTION`，不得新建任务或重发 Prompt。客户端重启前如数据库和存活进程共同表明仍有活动任务，Driver 拒绝重启。

## WorkBuddy 单题

依赖准备由调用本 Skill 的控制 Harness 完成，不要求用户手工进入 Driver 目录。控制 Harness 先检查 `node_modules/playwright-core` 和锁文件状态；缺失或 `npm ls --depth=0` 失败时，在 Driver 目录自动执行锁定安装。依赖只能安装在 Skill 的 Driver 目录，不能安装到候选工作空间：

```bash
cd .agents/skills/execute-web-e2e/drivers/workbuddy
npm ci
```

`npm ci` 失败时保留原始错误并停止执行，不能改用未锁定版本或把依赖装进题目目录。

只读预检：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh --probe
```

`--probe` 不会点击“新建任务”。WorkBuddy 只有在新任务页挂载 workspace picker；若当前停在历史会话页，探针会以 `workspace-picker-not-visible` 返回未就绪。切换到未发送的新任务页后重跑，不能把该结果误判为插件或 CDP 不可用。

执行一个准备包中的任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh \
  /absolute/batch-root/execution/tasks/<task_id> \
  --permission-mode full-access \
  --restart-app
```

上例不传 `--model`，Driver 会保留并回读 WorkBuddy 当前模型，不操作模型的推理强度。跑批前应由测试人员在 WorkBuddy 中配置好默认模型和推理强度。需要覆盖当前模型时再显式增加 `--model <UI 精确显示名>`。

`--restart-app` 会退出并重新启动 WorkBuddy，仅在当前没有需要保留的运行任务时使用。Driver 会先确认旧进程和 CDP 均已退出，再对 macOS `open` 做最多 3 次有界重试；每次都必须回读本地 CDP 才算启动成功，尝试证据写入 `automation_state.json.client.launch`。WorkBuddy 已通过本地 CDP 端口启动时省略该参数。

中断后恢复：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh \
  /absolute/batch-root/execution/tasks/<task_id> \
  --resume
```

恢复时必须沿用相同的 `automation_state.json`。Prompt 已进入发送临界区后，Driver 只检查已有 WorkBuddy conversation，不能盲目重发。状态不明时停在 `NEEDS_ATTENTION`。

运行中 Worker 收到 `SIGINT`/`SIGTERM` 时会记录 Worker 和 Driver PID、终止观察 Driver、释放 UI 锁，但不会停止 WorkBuddy 内的任务；使用同一参数加 `--resume` 后按已捕获的 `data-conversation-id` 恢复原会话。Worker 被 `SIGKILL` 时由 stale-lock 和遗留 Driver 检查恢复；旧 Driver 仍存活时拒绝启动第二个 Driver。

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

新队列默认 `run_slots=3`，最大 8；显式 `--run-slots 1` 可回退为串行。已有队列冻结首次记录的并发值，恢复时省略该参数会沿用冻结值，显式提供不同值则失败关闭。没有 `run_slots` 字段的旧队列迁移为 1，不自动升级为 3。

`--model` 是可选覆盖项，接收 WorkBuddy 模型下拉框中的精确显示名，例如 `--model xopglm52`。显式传入时，Driver 选择并回读该模型；省略时，Driver 只回读当前模型，不展开下拉框，也不再自动选择“均衡”。两种模式都不操作推理强度。一个队列运行期间不得人工改变模型；所有题的实际回读模型必须一致。同一个 `run-id` 恢复时模型模式和显式请求值不可变；可选 `execution_record.json` 已预声明模型时，实际回读值也必须与其一致。

`--permission-mode full-access` 是评测运行的显式授权：Driver 会在发送 Prompt 前回读权限状态，已开启时不重复点击；未开启时通过 WorkBuddy 自身的风险确认界面开启。WorkBuddy 5.5.3 将该设置作用于当前客户端的全部任务，而不是单个项目。省略该参数时默认 `current`，只记录当前权限，不修改客户端设置。

Worker 从 Harness 根目录的 `manifest.json` 按精确 task ID 解析工作空间，使用文件锁保证同一 execution 包只有一个 WorkBuddy UI 队列，并把状态写到 `execution/.execute-web-e2e/queues/<queue_id>/queue_state.json`。`ui_slots` 始终为 1：新建项目、设置权限/模型、发送 Prompt、切换会话和处理授权都由同一个 Driver 串行完成。Prompt 发送并捕获稳定 conversation ID 后，Driver 退出观察，让 WorkBuddy 最多保留 `run_slots` 个后台 Agent 任务；Worker 轮流按原 conversation ID 做一次性观察。任一题明确终态并通过自动化状态与 `execution_record.json` 一致性校验后释放槽位，立即补入下一题。

模型下拉框完成唯一回读后，Driver 必须在发送 Prompt 前把实际模型写入 `execution_record.json.model`。显式模式记录 `mode=explicit` 及请求/实际模型；保持当前配置时记录 `mode=current`、`requested_model=null` 和实际模型。若执行记录预先声明了不同模型则失败关闭。最终回执的顶层 `model`、逐题 `model_selection` 和 execution record 必须一致，不能等到报告阶段再补模型身份。

队列出现 `NEEDS_ATTENTION` 后停止补入新题，但继续收口已经投递的其他活动题；活动题全部结束后再返回阻塞状态。先处理或扩充经过审查的安全规则，再使用完全相同的参数加 `--resume`。默认遇到 `INFRA_FAILED` 或 `TIMEOUT` 也停止补题；只有明确需要验证失败隔离时才使用 `--continue-on-terminal-failure`。

客户端崩溃后恢复时使用 `--resume --restart-app-on-resume`。一次恢复只重启 WorkBuddy 一次，随后串行定位所有活动 conversation。只有发送后已经捕获稳定 conversation ID 时才允许重启并从侧栏恢复原会话；缺少 ID 或无法唯一定位时停在 `NEEDS_ATTENTION`，不创建新任务。

人工处理 `NEEDS_ATTENTION` 后可在恢复参数中增加 `--mark-manual <task_id>`。该参数只在队列和 Harness 回执中记录人工介入原因，随后仍由 Driver 检查原会话终态；它不能把未知状态直接改成成功，也不能绕过 Prompt 幂等和终态证据门禁。

达到执行时限后 Driver 必须点击当前会话的停止按钮，确认 WorkBuddy 已进入非运行态，并验证候选 workspace 在静默观察窗口内不再变化。只有三项证据齐全时才记录 `TIMEOUT`；否则记录 `NEEDS_ATTENTION`。即使指定 `--continue-on-terminal-failure`，未确认停止或 workspace 仍变化的超时任务也不能进入下一题。

队列退出时会在 Harness 根目录生成 `execution-receipt.json`，汇总任务范围、attempt、自动化/正式状态、客户端与 Driver 版本、请求/实际模型、权限、Prompt/workspace 哈希和证据相对路径。生成回执时会重新计算每题 workspace SHA；`integrity.valid=true` 要求请求任务集合与 manifest 完全一致、记录齐全、身份和模型一致、所有任务均为终态，且当前 workspace 的候选文件仍等于 Driver 终态冻结值。若候选文件已漂移，队列改为 `FAILED`，不得进入评分。

被评 Harness 为运行或构建网站生成的 `.cache`、`.vite`、`node_modules` 属于可忽略运行时目录：Driver 不删除或修改它们，而是在回执中用 `wildclawbench.web-e2e-runtime-directory-policy/v1` 声明策略并逐题记录实际路径；它们不参与候选哈希，也不导致 `integrity.valid=false`。`.git` 仍是禁止目录，出现即使回执无效。只有显式声明该策略的新回执才能容忍运行时目录；旧回执继续使用严格规则。评分交接和离线回传只过滤可忽略目录，不从 execution 原件中清理它们。

如果 Driver 在 Prompt 发送前因 UI 自动化错误进入 `INFRA_FAILED`，且候选 workspace 没有任何变化，可在修复根因后使用 `--resume --retry-pre-send-failure`。旧 attempt 会移入相邻的 `.attempts/<task_id>/<attempt_id>/` 留存审计；发送后失败、超时或已有产物变化时拒绝自动重试。

## 执行约束

- 选择的是单题根目录 `execution/tasks/<task_id>/`，不是其中的 `workspace/`。
- WorkBuddy 5.5.3 优先通过其输入框 workspace provider 写入并回读绝对路径；只有该能力不存在时才退回 macOS 原生文件夹选择器。不能只凭同名目录标签确认工作空间。
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
- WorkBuddy、AstronStudio 和 QwenWork 始终保持 `ui_slots: 1`；新队列默认 `run_slots: 3`、最大 8。这里的并发只指已投递 Agent 在客户端后台并行运行，禁止同时启动多个 Playwright Driver 抢占窗口。首次换机、升级 Harness/Skill 或切换模型后，先用 3 个 L1 冒烟；未通过真实隔离验证的节点显式使用 `--run-slots 1`。

实现或审查其他 Driver 时，完整读取 [Driver 契约](references/driver-contract.md)。
