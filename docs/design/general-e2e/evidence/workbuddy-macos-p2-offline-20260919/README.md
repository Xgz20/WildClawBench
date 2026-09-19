# WorkBuddy macOS General P2 离线门禁与 canary 收口证据

日期：2026-09-19（Asia/Shanghai）。任务：`MAC-WORKBUDDY-GENERAL`。范围：单题一次发送入口、原生绑定、恢复、状态语义、锁与路径安全的离线实现，以及一次真实客户端 canary 的发送边界和用户草稿恢复。本文不证明 Prompt 已发送、模型已执行、真机终态、正式 collect、评分或生产准入。

## 结论

提交 `e388dfa43c0f38263ebcf57bf022ba1eb2c3cfeb` 提供 WorkBuddy macOS 5.5.3 的安全可恢复单题入口；COMMON-002 合并和精确组件绑定见 `4529352ca92bf213995fd00433c6d77af3f8fc32`、`b3ac3da374165d74a41a3198e13d05928d671552`。真实 canary 使用 `b3ac3da...` 构建的独立 release，成功准备单题，但旧 `fillPrompt` 直接写 DOM 后没有更新编辑器内部状态，发送控件仍 disabled。执行器在发送动作前停止：journal 消耗一次 reservation，实际 click/send/native session 均为 0，未绑定 conversation/request/cwd；同 attempt 恢复只观察，没有重发。

修复提交 `5bea7621e4c90222d3f2e0000ab1ca6093af6e0b` 改用 CDP `Input.insertText`，并把 Prompt 精确回读、唯一发送控件存在且 enabled 作为 armed 前置条件。该修复只有离线有状态 client fixture 和回归证据，没有真机或开发浏览器运行时证明；后续必须从该 revision 或更高 revision 重建 release，在控制任务重新分配桌面 slot 后创建全新 attempt。旧 attempt `3e554524-6599-4182-aecc-3257977867c0` 永不重发、重置或替换身份。

P2 整体仍未完成：当前只能证明发送前失败被安全收口、用户现场已恢复和修复后的离线门禁，不等于一次成功发送、可信终态或正式证据收口。

## 安全与恢复门禁

- execution manifest 的 task ID 只接受安全单段；Prompt/Workspace 原始相对路径先拒绝绝对路径、`..`、unit/task 越界和 ancestor/leaf symlink，再做 `realpath`。
- 原生 conversation/request/message/tool ID 只接受安全单段；history 的 index、conversation、message ancestor/leaf symlink 全部拒绝。
- JSON 通过 `O_NOFOLLOW` 的同一 fd 读取；读取前后对比 dev/inode/size/mtime/ctime，解析、SHA-256、size 和 metadata 来自同一 bytes。
- unit 级 `workbuddy-ui.lock` 与 task 级 `driver.lock` 在读取 journal 和发送期间均由同一 worker 持有。新锁使用 `open(..., "wx")` 排他创建，释放时按 dev/inode 校验所有权。
- stale lock 明确禁止自动接管。双 stale-reclaimer 反例中两个 worker 均退出、旧锁保持、总 dispatch 为 0；正常双 worker 竞争中第二个 worker被 owner lock 拒绝，总 dispatch 为 1。
- 已有 journal 只能使用 `--resume`；`dispatch_attempt_count=1` 后恢复只观察，发送临界异常也不重试。
- 首次发送前同时检查原生 session index 和 UI：running/pending/unknown session、非空编辑器、Stop/Cancel 控件或多个未知编辑器均阻断。
- `5bea762` 额外要求唯一空编辑器精确聚焦；只调用一次 `Input.insertText`；只有 Prompt 完整内容精确回读、唯一发送控件存在且 enabled 后才写 armed journal。disabled 超时保持 `dispatch_attempt_count=0`、`send_status=not_sent`、dispatch=0，不强点 disabled 控件。
- Driver 运行时固定 Node.js `>=22`，只用原生 fetch/WebSocket/AbortSignal；专属 `package.json/package-lock.json` 为零外部依赖闭包。

CLI 入口：

```bash
node tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/execute.mjs \
  --unit-root /absolute/extracted-unit \
  --task-id <完整任务ID> \
  --endpoint http://127.0.0.1:<端口> \
  --expected-permission <full-access|default-sandbox> \
  --detach-after-submit
```

恢复入口在相同参数后增加 `--resume --observe-once`。stale owner lock 不自动删除；必须先由控制者核对旧 owner 确已退出并显式处置锁，不能让多个 worker 竞争回收。

## 离线验证

`5bea762` 上的结果：

```text
WorkBuddy wildcard                                 25/25
General E2E 全量 Node                              93/93
General/COMMON 相关 Python（仓库 .venv）           60/60
node --check（ui.mjs / execute.mjs）               PASS
npm ci / npm ls --depth=0（WorkBuddy 专属目录）    PASS / empty
git diff --check                                   PASS
```

新增 fixture 明确断言：`Input.insertText` 只调用一次；DOM 内容正确但发送控件 disabled 时超时；disabled 发生在 armed 前，journal 保持 attempt count 0，dispatch 为 0。隔离开发浏览器的 `data:` fixture 被浏览器安全策略拒绝，且策略禁止改用原始 CDP 或其他浏览器面绕过，因此没有把离线 fixture 写成浏览器事件或真实 WorkBuddy 证明。

COMMON-002 的通用 finalizer、trace-index v2 和 macOS task-process 原语仅完成公共接收回归。本轮新增 WorkBuddy 专属离线 collector 与原生 v2 输出 fixture，已用公共契约校验；仍没有真实 WorkBuddy 子进程验证的 cleanup hook，不把离线 fixture PASS 写成 WorkBuddy 正式收口通过。

## 真实 prepare 与 canary

真实 prepare 使用 source revision `b3ac3da374165d74a41a3198e13d05928d671552` 构建并验证七 Skill release，suite SHA-256 为 `54f4f7934413646b89b5fc3fba50db9d2a4ee4e750eeec8d70971759e1e8ad3e`。按 `prepare-general-e2e-workspaces` 的独立 Skill ZIP 构建单题 `01_Productivity_Flow_task_001_expense_policy_check`，execution/scoring 双包与 batch verify 均 PASS。第一次直接调用 checkout 源码 prepare 因缺少 vendored dataset verifier 返回 `DATASET_VERIFIER_UNAVAILABLE`，没有产生 execution unit；正式准备改用 release 内独立 Skill 后通过。

canary 使用模型 `xopglm52`、权限 `default-sandbox`，Prompt SHA-256 为 `deb5f6554a69c93afe1e6ad1f1fb6d678adedfc8860dda0875afaa6d4281e621`。attempt `3e554524-6599-4182-aecc-3257977867c0` 的 journal 记录：

- `dispatch_attempt_count=1`、`dispatch_armed_at` 有值、`dispatch_returned_at=null`；
- `dispatchPrompt` 回报可用发送控件 0，`send_status=uncertain`；
- 实际 candidate click 0、send 0、native session 0；conversation/request/cwd 均为 null；
- phase 为 `NEEDS_ATTENTION`，错误为 `WORKBUDDY_PROMPT_SEND_UNCERTAIN`；
- 同 attempt 的 `--resume --observe-once` 只追加第二次 `NATIVE_BINDING_UNAVAILABLE`，没有 redispatch。

旧实现通过 `textContent + InputEvent` 使 DOM Prompt SHA 与 manifest 一致，但未驱动 WorkBuddy 编辑器内部状态，发送按钮保持 disabled。这是本次失败的直接运行时证据；不把它归因于模型、任务或 General 数据集，也不把 reservation 记成实际发送。

结构化 journal 原件位于：

```text
/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/slot02/canary-worker/unit/
  workbuddy-macos-canary-20260919-01__workbuddy-macos-xopglm52-canary-01/
  .general-e2e/execution/01_Productivity_Flow_task_001_expense_policy_check/workbuddy/dispatch-journal.json
```

本地目录名沿用 `slot02`，本次 canary 对应的控制桌面分配最终状态为 `SLOT03_RELEASED`。目录名不是仍持有 SLOT02/SLOT03 的证据；后续运行必须重新取得 slot 并重新核验进程、CDP、原生 session、UI 空闲、模型和权限。

## SLOT05 冻结发行与发送前门禁

为验证 `Input.insertText`，控制任务另行授予 `SLOT-MAC-20260919-05`。按 COMMON-004 的要求，本次活动先冻结 COMMON-003 时代的 `0eddf84e34f2cd8f738f819eebdd963acda3ae77`，使用 execute Skill `0.8.0` 构建 release `workbuddy-macos-p2-0eddf84`；suite SHA-256 `05107dfc13116e68e6afbe5a27d3ed600463d4f4d943d93f060acaf33f5a5cb5`，dataset bundle SHA-256 `181f718f4309cb85bd009e8eccba6b2581a9e9d1a41df17a4908dcf828e263f0`。独立 `prepare-general-e2e-workspaces` Skill 产生的新 batch `workbuddy-macos-canary-20260919-02` 和 execution/scoring 双包均通过 verify；Prompt SHA 保持 `deb5f6554a69c93afe1e6ad1f1fb6d678adedfc8860dda0875afaa6d4281e621`。

发送前只读 probe 于 `2026-09-19T13:43:42.656Z` 返回 `PASS`：WorkBuddy 5.5.3/x86_64、主进程 PID 33343、CDP `127.0.0.1:9229`、唯一 page target、原生 session index 仅 1 个历史 `Completed`。随后对当前编辑器做哈希和附件门禁：31 字符正文 SHA `48c34111a769d3367a62c87f1b06a90e1e34bdcd5c8f9137c37dd26679844141`、HTML SHA `14263d5c4a28339da5db126c07e6ba2f6e88e31b97079ed33ce86f67197c53a6` 均与私有备份一致；Workspace/conversation 为空，模型/权限为 `xopglm52/default-sandbox`，附件输入/选中文件/可见附件元素均为 0。

按已授权的临时移出路径只尝试一次真实清空：编辑器可聚焦，但 CDP Meta+A/Backspace 后等待 500ms，正文长度和哈希完全不变。没有点击“新建任务”、没有填入 canary Prompt、没有创建新 attempt、没有 click/send，也没有修改旧草稿；失败原件为 `slot05/pre-canary-draft-clear-failure-01.json`。按门禁立即停止，草稿仍与备份一致；SLOT05 应由控制任务标记 `SLOT05_RELEASED`，后续不再重试该清空路径。

## 用户草稿恢复

canary 前保护的用户旧草稿已恢复。私有恢复证据显示：正文长度 31；正文 SHA-256 `48c34111a769d3367a62c87f1b06a90e1e34bdcd5c8f9137c37dd26679844141`；HTML SHA-256 `14263d5c4a28339da5db126c07e6ba2f6e88e31b97079ed33ce86f67197c53a6`。恢复后正文和 HTML 均与备份一致，属性差异仅为动态 `style`；candidate Prompt 已移除，Workspace/conversation 为空，模型/权限与备份一致。

备份与恢复证据位于：

```text
/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/slot02/
  private-user-draft-backup/pre-canary-01/
```

目录权限为 0700，四个文件均为 0600。草稿正文和私有截图不进入 Git、候选或评分包；仓库只记录长度、哈希、一致性结论和权限。

## 尚未证明

- `5bea762` 的 `Input.insertText + pre-arm enabled` 在真实 WorkBuddy 5.5.3 上能驱动编辑器状态和发送控件。
- SLOT05 冻结发行下的真实 `Input.insertText` canary 尚未启动；阻塞点是无法在不改变用户草稿的前提下完成一次安全临时移出。
- 全新 canary 的一次实际发送、conversation/request/cwd 增量绑定、可信完成态与同 attempt 恢复。
- 真实授权/追问/失败/取消/超时和停止确认。
- WorkBuddy 真机 trace-index v2、正式资源、候选冻结、cleanup hook、评分/回传/报告；离线 collector 仅证明输入布局和公共 Schema 可消费。
- 三题串行、五题动态补位和仓库外发行。
