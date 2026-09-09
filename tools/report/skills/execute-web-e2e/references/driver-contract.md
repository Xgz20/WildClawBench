# Web E2E 桌面 Harness Driver 契约

## 生命周期

每个 Driver 需要提供等价于以下能力的实现：

| 能力 | 必须产生的可审计结果 |
| --- | --- |
| `probe` | 客户端版本、控制后端、终态来源和权限/依赖状态 |
| `launch` | 连接或启动目标客户端；不得破坏无关任务 |
| `createTask` | 为当前用例建立全新客户端任务 |
| `selectWorkspace` | 选择并回读确认单题绝对路径或稳定标识；仅有 basename 标签不足以确认 |
| `configurePermissions` | 按运行参数幂等回读或设置权限模式；高权限模式必须显式请求并保存确认结果 |
| `selectModel` | 调用者显式指定时选择并回读 UI 实际值；未指定时保持当前设置并回读实际值 |
| `submitPrompt` | 在发送前持久化 attempt ID 和 Prompt SHA-256 |
| `inspect` | 返回明确终态、运行态、可见异常或未知状态 |
| `handleExpectedApproval` | 只处理严格匹配白名单、限定在候选工作空间内的一次性普通授权；保存规则和命令哈希 |
| `collect` | 保存最终回复、截图、客户端 session ID 和 workspace 变化 |
| `cleanup` | 关闭本题临时 UI，不删除候选产物 |

## 状态机

```text
PREPARED
  -> CLIENT_READY
  -> WORKSPACE_CONFIRMED
  -> PERMISSION_CONFIRMED
  -> MODEL_CONFIRMED
  -> READY_TO_SEND
  -> PROMPT_SENT
  -> RUNNING
  -> SUCCEEDED

任意非终态 -> NEEDS_ATTENTION / INFRA_FAILED
PROMPT_SENT / RUNNING -> TIMEOUT
```

终态只有 `SUCCEEDED`、`INFRA_FAILED` 和 `TIMEOUT`。`NEEDS_ATTENTION` 不是完成；控制面必须等待人工处理或显式恢复。

Prompt 发送采用失败关闭语义：写入 `READY_TO_SEND` 后到确认 conversation ID 之间发生中断时，恢复流程必须先查 Harness session。不能因为没有及时写入 `PROMPT_SENT` 就再次点击发送。

控制 Worker 必须持久化自身和当前 Driver 的精确 PID。优雅中断只终止观察 Driver，不终止 Harness 内正在执行的任务；恢复前若遗留 Driver 仍存活，必须拒绝启动第二个 Driver。客户端重启恢复必须依赖发送后捕获的稳定会话 ID，不能按标题、时间或当前页面猜测。

`TIMEOUT` 只有在 Driver 已请求停止、Harness 明确进入非运行态，并且候选 workspace 在限定观察窗口内保持静默时才是安全终态。任何一项无法确认都进入 `NEEDS_ATTENTION`，控制面不得继续下一题。

## 终态证据优先级

1. Harness 官方 turn/session 完成事件；
2. 本地 session 数据库、JSONL 或日志中的明确终态；
3. Electron DOM 中明确的完成标识；
4. Computer Use 对稳定视觉终态的判断。

workspace 哈希和文件稳定只能作为产物证据，不能单独判定 Agent 已完成。未知显式状态不得映射为成功。

## 状态文件与正式记录

丰富状态使用 `wildclawbench.web-e2e-automation-state/v1`，保存在候选单题目录外。正式 `execution_record.json` 保持 `wildclawbench.web-e2e-execution/v1`，不得增加自动化私有字段。

Harness 级 Worker 使用 `wildclawbench.web-e2e-execution-receipt/v1` 汇总完整任务范围。回执只有在请求任务集合与 manifest 一致、每题 automation/execution 记录存在、身份、`execution_record.model` 和模型回读一致、所有题均为终态时才能声明 `integrity.valid=true`。显式模型模式要求请求值等于实际值；保持当前配置模式允许 `requested_model=null`，但必须保存非空实际值。回执顶层 `model` 使用 Harness 实际回读模型；初始 manifest 未声明模型时也不能留空。人工介入必须记录原因和时间，但不能直接把未知终态改写为成功。

若被评 Harness 在候选中生成 `.cache`、`.vite` 或 `node_modules`，Worker 不得删除、清理或修改原件。新回执必须声明 `wildclawbench.web-e2e-runtime-directory-policy/v1`：`ignored_directories` 固定为这三个目录，`forbidden_directories` 固定为 `.git`，评分复制和回传都使用 `exclude-ignored-directories`。可忽略目录不参与候选哈希，逐题 workspace 快照仍记录其实际相对路径；`.git` 继续使完整性失败。没有该策略的旧回执仍严格拒绝可忽略目录。评分副本和回传 ZIP 必须过滤可忽略目录，但 execution 原件保持不变。

映射规则：

| 自动化状态 | 正式执行状态 |
| --- | --- |
| `SUCCEEDED` | `completed` |
| `INFRA_FAILED` | `execution_error` |
| `TIMEOUT` | `timeout` |
| 其他 | `pending` |

若正式记录不存在，Driver 只能从批次 `manifest.json` 的精确路径映射，或从调用者显式提供的 `batch_id`、`task_id` 和模型身份创建；不得根据目录 basename 猜测身份。

## 安全与并发

- 执行工作空间不能包含 Rubric、Expected Behavior、checker、`eval/` 或 `gt/`。
- 操作系统隐私授权、管理员认证和未知敏感授权不能自动批准。
- Harness 正常结束并向用户追问属于候选结果，不由控制 Agent 代答。
- GUI 焦点、文件选择器和授权弹窗受全局 UI 锁保护，`ui_slots` 必须为 1。已验证的 Driver 可以让已捕获稳定 session/conversation ID 的任务在后台运行，并用单一 UI Driver 轮流恢复观察；`run_slots` 必须有显式上限和冻结配置。未完成 session、cwd、模型、授权路由和真实客户端隔离验证的 Driver 仍保持 `run_slots=1`。
