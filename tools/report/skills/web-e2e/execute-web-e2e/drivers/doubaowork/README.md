# DoubaoWork macOS Web E2E 客户端适配

当前目录是 `MAC-DOUBAOWORK-WEB` 的客户端专属开发面，版本 `0.3.0`。现阶段提供：应用/CDP 身份严格核验的只读 probe、macOS 原生目录选择 helper、显式 session 目录发现、脱敏 fixture、原生 `trajectory.jsonl` 的旁路提取器、发送意图 journal，以及仅用于真机开发 canary 的单次投递与只读恢复入口。

这不是完整生产 Driver。COMMON 的 General CB-A 对本 Web Driver 不适用；Web 公共接入独立依赖 CB-B、execute/run/metrics 与发行装配。当前实现不会生成正式 `execution_record.json` 或 execution receipt，也没有实现可信原生终态、安全停止、任务进程清理、公共 finalizer 或评分交接；不得把本目录测试或旧 smoke 写成完整 Web E2E 通过。

## 只读 probe

probe 不启动或重启客户端，不点击、不输入、不切换模型/权限、不发送 Prompt。它要求：

- `/Applications/DoubaoWork.app` 是普通 app 目录，Bundle ID 精确为 `com.work.pc.doubao`；
- CDP 地址是带显式端口、无凭据/路径的 loopback HTTP；
- 监听者恰好一个，进程路径属于该 app 内的 `DoubaoWork Browser`；
- HTTP discovery 与 Playwright 各恰好一个 `doubaowork-chat` target；多 target 失败关闭，不按最近页面猜测；
- 默认仅保存结构化 DOM 计数和 conversation ID 哈希。只有显式 `--capture-sensitive-artifacts` 才保存 aria/screenshot，且必须放在仓库外私有目录。

```bash
npm ci --ignore-scripts --no-audit --no-fund
node probe.mjs \
  --endpoint http://127.0.0.1:9260 \
  --app-path /Applications/DoubaoWork.app \
  --output-dir /Users/<user>/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/probe
```

`status=passed` 只说明只读控制面可唯一连接；不说明桌面空闲、任务可发送或终态/Token 可采集。当前实机若有两个 chat target，会以非零退出码写出 `failed` 报告。

## 原生目录选择 helper

调用方先用 Web UI 打开“添加本地文件夹”的 macOS 原生面板，再执行：

```bash
swift select-folder.swift com.work.pc.doubao /absolute/task/workspace 8
```

helper 要求现有 Accessibility 权限、唯一 DoubaoWork 主应用、普通绝对目录且路径不含符号链接；它恢复原剪贴板，并在前台身份核对后执行键盘粘贴。helper 成功只证明原生面板选择完成。调用方仍须 hover `project-shared-project-folder-item`，读取 tooltip 完整路径，仅展开开头 `~/`，与请求绝对路径严格比较后才能创建项目。

当前阶段只做 `swiftc -typecheck`；没有桌面独占时段时禁止运行 helper。

## 原生证据旁路提取

当前 2.28.12 只读样本确认 UI conversation ID 与以下 session 目录名一致：

```text
~/Library/Application Support/DoubaoWork/Default/.doubaowork/
  agent_mode/workspace/.sessions/<conversation-id>/agents/<agent-id>/system/trajectory.jsonl
```

提取器必须接收发送后已捕获的数字 session ID，不扫描“最近目录”：

```bash
node native-evidence.mjs \
  --session-id <captured-native-id> \
  --workspace /absolute/task/workspace \
  --output /Users/<user>/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/native-evidence.json
```

输出是 `wildclawbench.doubaowork-native-evidence/v1` 私有旁路证据，不是公共 execution Schema。当前 trajectory 可提供消息角色、tool call ID/name/arguments 和 tool result 关联，但没有可信 cwd、turn ID、终态、时间戳或 usage。因此：

- `native_cwd`、`turn_id`、Token、请求数、两类耗时和积分均为 `null`；
- requested workspace 只保留为请求值，`workspace_binding.status=unverified`；
- 工具次数是 `partial` 的 known subtotal，coverage denominator 为 `null`；
- UI 最终回复不能把 `terminal.status` 提升为成功；
- 原始 trajectory 不复制进输出，只保存规范化事件、相对路径、大小和 SHA-256。完整原始文件仍留本机受限目录。

## 发送意图 journal 与恢复边界

`state.mjs` 使用现有 Web automation state 标识，但当前只写客户端专属控制状态，不生成正式 execution record。调用顺序必须是：

1. workspace tooltip、实际权限和实际模型全部回读；
2. `recordSendIntent` 将 `READY_TO_SEND` 与 Prompt SHA 落盘；
3. **在任何 UI click 前**调用 `persistBeforeDispatch`，原子写入 `dispatch_attempt_count=1` 和 `dispatch_started_at`；
4. click 被客户端接受后才能 `recordPromptAccepted`；
5. 发送后对照发送前保存的 UI conversation 与原生 session 目录两组基线；只有两侧各自恰好出现一个新 ID 且相等时，才做 tentative binding；native cwd/turn 仍为 null。

恢复只在 `READY_TO_SEND + dispatch_attempt_count=0` 时允许首次发送。计数已为 1、会话缺失/多候选、或已绑定 session 无法重新确认时一律 `NEEDS_ATTENTION`/observe-only，禁止自动重发。单测验证状态文件拒绝符号链接、dispatch start 先于 click 落盘和所有发送临界窗口。

开发入口还会在输出目录创建 no-clobber 排他 worker lock，记录 host、PID、进程启动身份和本次实例 ID。输出目录任一既有祖先为符号链接时，在创建、读取或释放 lock 前失败关闭。第二个存活 worker、foreign/stale lock 或不可验证身份一律拒绝；Driver 不自动删除不属于当前实例的 lock。状态加载、journal 写入和 UI 发送都在持锁区间内，`--resume` 只观察已登记一次发送的 attempt。

## 开发 canary 投递与只读恢复

新投递只接受 `wildclawbench.web-e2e-batch/v3` 的真实 prepared execution 单题根目录，自动化输出必须位于单题目录外。输出包含客户端私有状态、截图和脱敏索引，只能放在仓库外 debug root，不得提交：

```bash
node driver.mjs \
  --task-root /absolute/batch/harnesses/doubaowork/execution/tasks/<task_id> \
  --output-dir /absolute/debug-root/development-run-01 \
  --project-name WCB-DoubaoWork-L1-01
```

首次进程只完成发送、UI/native session 唯一绑定后退出。随后用同一输出目录只读观察；该入口不会新建项目或重发 Prompt：

```bash
node driver.mjs --resume \
  --output-dir /absolute/debug-root/development-run-01 \
  --observe-seconds 900
```

若新执行明确在发送意图落盘前失败、`dispatch_attempt_count=0`、session 为空且 workspace tooltip 已精确确认，可在修复根因后显式续跑同一已创建项目：

```bash
node driver.mjs --resume --retry-pre-send-failure \
  --output-dir /absolute/debug-root/development-run-01
```

该路径先把旧状态 no-clobber 归档到 `.attempts/`，重新核对 prepared task/Prompt/manifest、客户端空闲状态、当前唯一项目 ID 与旧状态保存的 project ID 哈希、工具栏项目名，再创建新 attempt。任一身份漂移、旧状态缺 project ID、已进入发送临界区或旧归档冲突都会失败关闭；普通 `--resume` 始终只读。

即使 UI 最终回复稳定出现，当前版本仍把它记录为 `NEEDS_ATTENTION` 的非可信完成候选。停止控件与当前 conversation 的 sidebar busy 标记都属于 running 门禁；两者任一存在时不能释放槽位或采信完成候选。每次完成观察使用同一个 observation ID 生成唯一回复、截图和 native evidence 文件，回复原件的字节数与 SHA-256 必须和同次 DOM 快照一致，禁止复用更早的部分回复。native terminal、精确 cwd、任务进程清理和公共 finalizer 未补齐前，不生成正式 `execution_record.json` 或 execution receipt。

## 离线验证

```bash
npm test
node --check driver.mjs
node --check lib.mjs
node --check platform.mjs
node --check native-evidence.mjs
node --check probe.mjs
node --check state.mjs
swiftc -typecheck select-folder.swift
```

fixture 已替换 Prompt、文件内容、工具结果、真实会话/agent ID 和绝对路径，不包含认证信息、历史侧栏或截图。
