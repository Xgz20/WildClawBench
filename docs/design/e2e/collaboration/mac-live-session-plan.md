# macOS 三 Harness 真机协作计划

## 角色和并行边界

当前控制会话负责公共集成、slot 授予、源码 SHA、交接台账和最终准入判断。三个独立任务分别负责 WorkBuddy General、QwenWork General、DoubaoWork Web；每个任务只使用自己的 Git worktree、证据根和 Harness 客户端。

代码、离线预检、日志解析和回执审查可以并行。三台客户端不在同一台 macOS 上同时点击、发送或恢复；真机阶段使用独占 slot 串行执行，避免前台窗口、CDP 端口、数据库写者和进程清理相互污染。

## 固定绑定

| 任务 | 分支 / worktree | 本地证据根 | 真机范围 |
| --- | --- | --- | --- |
| WorkBuddy General | `feat/workbuddy-macos-general-e2e` / `.agents/workbuddy-macos-general-e2e` | `/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/` | 全新 General attempt，一次发送、观察恢复、CB-B collect、cleanup |
| QwenWork General | `feat/qwenwork-macos-general-e2e` / `.agents/qwenwork-macos-general-e2e` | `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/` | QwenWorkCN 1.0.6，一次发送、metadata 采集、观察恢复、cleanup |
| DoubaoWork Web | `feat/doubaowork-macos-web-e2e` / `.agents/doubaowork-macos-web-e2e` | `/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/` | 一个 Web L1，一次发送、候选冻结、native evidence、cleanup |

三个任务必须从控制会话指定的集成 SHA 开始。不要把旧 canary、旧 attempt、旧 `execution-receipt.json` 或旧客户端状态当作新时段输入。

## 每个独立任务的启动提示

### WorkBuddy General

从集成 SHA 创建或刷新 `feat/workbuddy-macos-general-e2e` worktree。先运行 `drivers/workbuddy/preflight.mjs`，再只读确认 5.5.3、loopback CDP、唯一页面和无活动会话。获得控制会话授予的独占 slot 后，创建全新 attempt，发送一次 Prompt；发送状态不确定时立即停止，不重发。终态必须同时提供原生 request turn、conversation session、native cwd、terminal status、CB-B trace-index/resource metrics、cleanup 前后进程快照和 quiet window。缺失字段进入 `NEEDS_ATTENTION`，不生成正式回执。

### QwenWork General

从集成 SHA 创建或刷新 `feat/qwenwork-macos-general-e2e` worktree。先执行 `tools/qwenwork_metadata_preflight.py` 对本题原始日志根做只读检查，确认 `sessionId`、绝对 `cwd` 和 segment coverage；无日志时保持 `blocked`。获得 slot 后只允许一个全新 attempt，发送前必须有唯一当前 project trigger；发送或恢复边界不明时停止，不重发。正式 collect 必须保留 metadata coverage、原生 session/cwd、Prompt digest、终态、CB-B trace 和 cleanup 证据；usage/terminal 未验证时保持 `null/unverified`。

### DoubaoWork Web

从集成 SHA 创建或刷新 `feat/doubaowork-macos-web-e2e` worktree。先运行 probe、native trajectory candidate audit 和现有 receipt bridge/finalizer fixtures。当前 route 明确拒绝 `--batch` 与 `--formal-receipt`；只有控制会话确认 native terminal/cwd、candidate freeze、cleanup 和 finalizer assessment 全部通过后，才允许申请新 Web slot。真机只发送一次 Prompt，必须保存 UI 等价绑定、Prompt 回读、原生 session identity、候选 workspace SHA、native evidence 和清理安静窗口；任一门禁失败保持 `NEEDS_ATTENTION`。

## Slot 交接顺序

1. 独立任务回报 worktree SHA、客户端版本、预检结果、证据根和预计操作范围。
2. 控制会话核对没有其它 Harness 活动、旧进程、活动数据库写者或未恢复草稿，再授予一个唯一 slot。
3. 独立任务执行一次发送和只读观察；任何不确定交互都立即冻结现场并回报，不代答对话框。
4. 独立任务完成原生采集、候选冻结、cleanup 和正式回执预检后释放 slot。未达到完整门禁时只能交付 `NEEDS_ATTENTION`，不能补发或覆盖历史证据。
5. 控制会话审查交付并 cherry-pick 到 `feat/e2e-harness-contract`，更新平台卡和 [控制推进记录](control-progress.md)，再安排下一个 Harness 的真机 slot。

## 必须回报的字段

每次交接至少包含 `source_revision`、客户端版本、Driver/Skill 版本、batch/unit/task/attempt、真实 session/request/turn/cwd（未知为 null）、Prompt digest、发送次数、终态、trace/resource 原件路径和 SHA、cleanup 前后进程数量、quiet window、receipt 状态、阻塞原因和恢复路径。控制会话不代填缺失字段，也不把离线测试或历史 canary 写成真机通过。
