# 控制推进记录

维护者：COMMON。更新：2026-09-19 19:56 +08:00。这是控制任务的调度/审查快照，不替代任务卡和技术验收，也不是跨进程桌面锁。

## 第二轮目标

首轮 P1 交付已收到；继续三个原任务，完成客户端执行入口、已发现正确性问题、受控真机采样与 CB-B 公共收口。未经审查的平台分支不直接合入工作分支。源码变化均在指定 worktree。

| 任务 | 已收到的交付 HEAD | 控制任务已安排的下一项 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | `975f21aaf5b356ea2632acca55cf6b7d8cd0439a`；P2 `e388dfa43c0f38263ebcf57bf022ba1eb2c3cfeb` | 本轮修复复核通过，控制任务独立 WorkBuddy 23/23；SLOT02 允许公共基线/真实输入/配置与空闲核验后一次开发 canary |
| MAC-QWENWORK-GENERAL | `d9eabf0` 已采用 COMMON-002；锁修复/依赖 `7dcba74` | 26 Node 通过，stale 自动接管已关闭；追加审查发现 UI/session 停止绑定、面板归属、过期 probe 恢复、终态状态重放四项，修复后再进入 live |
| MAC-DOUBAOWORK-WEB | `c098a2e386baec6b04ed4af615349bea974f0746`；P2 修复/采样工作区待交付 | 一题真实发送、绑定和同 attempt 恢复已观察；SLOT01 已释放，离线修复锁祖先/重试回读/唯一证据快照并提交 |
| COMMON-CB05 | `eb23784a7ed25b0f0364db0392783de277b22b96` | 第一批通用机制完成，General 94 + Web 61 组合回归通过；COMMON-002 派发平台接入 |

本轮推荐源码 `eb23784` 包含 Doubao macOS 原生 discovery 1.2.0、general-contracts 1.2.0 与通用收口。155 项组合测试通过；[COMMON-002](handoffs/COMMON-002.md) 列明全部 Skill 版本和平台动作。三个平台专属代码仍待审查集成，不属于本公共源码的新平台支持声明。

## 桌面时段

| 时段 ID | 独占任务 | 允许范围 | 当前状态 |
| --- | --- | --- | --- |
| SLOT-MAC-20260919-01 | MAC-DOUBAOWORK-WEB | 一题 L1 开发采样、一次发送/同 attempt 恢复 | SLOT_RELEASED；最新 19:47:06 +08:00 observation busy/stop/pending 均 0，任务已明确转离线 |
| SLOT-MAC-20260919-02 | MAC-WORKBUDDY-GENERAL | 无冲突检查后启动/核验 CDP、回读模型权限、真实 General 单题一次发送与同 attempt 观察恢复 | 已授予；P2 e388dfa 经控制复核及 23 项专属测试通过，等待实际 preflight/执行结果 |

SLOT02 期间 QwenWork、DoubaoWork 只允许代码、fixtures 与只读文件盘点，不操作桌面。采样不是正式评测通过：不伪造其他 Harness manifest，不代答未知交互，不重发不确定发送，不在终态/停止未确认时冻结或生成有效回执。

时段结束必须报告客户端仍活动的 task/session/attempt 和恢复路径；存在未确认停止的运行时不得仅按时间到期自动转让。没有活动状态则明确释放，由控制任务再分配下一项。

## 审查与公共依赖

- WorkBuddy 首轮用取消/中断状态产生 candidate_error，可能绕过停止确认；已退回专属任务修复，未据此宣布执行可用。
- 两个 General 原生解析器需要将工具完成与业务成功分开；明确 exit_code/业务结果不足时保留 unknown。
- DoubaoWork 首轮统计声称唯一 call_id 但按行计数且未隔离 agent；已要求作用域/冲突反例。原生终态、cwd 和清理依然是当前重点采样缺口。
- prepare 已有 DoubaoWork Harness 名称与通用 slug 支持，不再把准备入口误记为必然缺失；execute/run/metrics 的实际接入分别核验。
- 新 trace-index v2 保留 v1，原生缺少 thread/turn/lifecycle 时显式 null。新通用收口没有可信、受支持的 cleanup hook 就拒绝正式冻结；旧 Astron 行为需通过兼容回归。
- general-contracts 1.2.0、collect-general-e2e 0.5.0；其他受影响版本见 COMMON-002。尚未新建生产发行。
- 三任务实际执行入口必须持有 owner lock，覆盖 journal/UI/send/绑定。除了空锁双 worker，还需 stale 锁双接管反例：不允许后一个回收者移走新建活锁。Qwen 交付存在此竞态，已退回修复；其他两任务同步自查。

## SLOT01 证据边界

真实任务 `07_Website_Generation_task_023_important_day_countdown`，批次 `web-e2e-20260919-doubaowork-canary-01`，唯一已发送 attempt `f2d106cc-aeb4-4f56-a863-9a82edec5c6e`，dispatch=1；保持客户端原模型显示“自动 高”和权限“按需确认”。发送前失败与未发送 attempts 由平台证据索引保留，不计为多次发送。

控制任务只读核验的本机目录：`/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/slot-mac-20260919-01-canary/development-run-03/`。`development-observation-1789817972965.json` 的 busy=1 但误记释放，已作废完成/释放结论；Driver 修复后 `development-observation-1789818426079.json`（19:47:06 +08:00）busy/stop/dialog/question/approval 均 0，最终回复观测 1893 字节，分类仍为不可信 UI 完成候选。

旧固定回复/native 文件可能仅覆盖此前部分轨迹，不能引用为最新完整证据。平台改用每次唯一 snapshot 文件、同次 DOM/hash 对账并保存旧原件；最新归档是否完整以其后续已提交索引为准。当前没有正式 execution record/receipt、native cwd/terminal 或进程清理通过声明；不重发来补证据。

Windows 从 COMMON-001/002 和最新 baseline 接续；完成约定基线检查后推进本机 G5-01。未收到 Windows 本机接收与真机记录，不代填通过。
