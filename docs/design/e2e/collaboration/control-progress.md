# 控制推进记录

维护者：COMMON。更新：2026-09-19 19:30 +08:00。这是控制任务的调度/审查快照，不替代任务卡和技术验收，也不是跨进程桌面锁。

## 第二轮目标

首轮 P1 交付已收到；继续三个原任务，完成客户端执行入口、已发现正确性问题、受控真机采样与 CB-B 公共收口。未经审查的平台分支不直接合入工作分支。源码变化均在指定 worktree。

| 任务 | 已收到的交付 HEAD | 控制任务已安排的下一项 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | `975f21aaf5b356ea2632acca55cf6b7d8cd0439a` | 修复取消/中断和冲突终态映射、原生来源路径和工具成功语义，再完成 P2 journal/执行/恢复入口与离线测试 |
| MAC-QWENWORK-GENERAL | P2 实现 `0b732fb432674eb2c1fd388018b1e66ede790066`，交接 `2a5c3af` | 25 Node + 3 Python 离线通过；继续修复 stale owner-lock 双接管竞争、装配独立依赖，采用 CB-B 后接正式 collector |
| MAC-DOUBAOWORK-WEB | `c098a2e386baec6b04ed4af615349bea974f0746` | 修复工具ID作用域/重复统计、损坏轨迹行和来源路径/不可覆盖输出；使用真实 prepare 输入做单题开发采样 |
| COMMON-CB05 | `eb23784a7ed25b0f0364db0392783de277b22b96` | 第一批通用机制完成，General 94 + Web 61 组合回归通过；COMMON-002 派发平台接入 |

本轮推荐源码 `eb23784` 包含 Doubao macOS 原生 discovery 1.2.0、general-contracts 1.2.0 与通用收口。155 项组合测试通过；[COMMON-002](handoffs/COMMON-002.md) 列明全部 Skill 版本和平台动作。三个平台专属代码仍待审查集成，不属于本公共源码的新平台支持声明。

## 桌面时段

| 时段 ID | 独占任务 | 允许范围 | 当前状态 |
| --- | --- | --- | --- |
| SLOT-MAC-20260919-01 | MAC-DOUBAOWORK-WEB | 检查无冲突活动任务后，本地项目完整路径/模型权限回读、一次发送、新会话绑定和同attempt只读恢复；一个全新L1开发采样 | 已分配；等待明确 SLOT_RELEASED / SLOT_HELD 回报 |

其他两个任务只允许代码、fixtures 与只读文件盘点，不操作桌面。采样不是正式评测通过：不伪造其他 Harness manifest，不代答未知交互，不重发不确定发送，不在终态/停止未确认时冻结或生成有效回执。

时段结束必须报告客户端仍活动的 task/session/attempt 和恢复路径；存在未确认停止的运行时不得仅按时间到期自动转让。没有活动状态则明确释放，由控制任务再分配下一项。

## 审查与公共依赖

- WorkBuddy 首轮用取消/中断状态产生 candidate_error，可能绕过停止确认；已退回专属任务修复，未据此宣布执行可用。
- 两个 General 原生解析器需要将工具完成与业务成功分开；明确 exit_code/业务结果不足时保留 unknown。
- DoubaoWork 首轮统计声称唯一 call_id 但按行计数且未隔离 agent；已要求作用域/冲突反例。原生终态、cwd 和清理依然是当前重点采样缺口。
- prepare 已有 DoubaoWork Harness 名称与通用 slug 支持，不再把准备入口误记为必然缺失；execute/run/metrics 的实际接入分别核验。
- 新 trace-index v2 保留 v1，原生缺少 thread/turn/lifecycle 时显式 null。新通用收口没有可信、受支持的 cleanup hook 就拒绝正式冻结；旧 Astron 行为需通过兼容回归。
- general-contracts 1.2.0、collect-general-e2e 0.5.0；其他受影响版本见 COMMON-002。尚未新建生产发行。
- 三任务实际执行入口必须持有 owner lock，覆盖 journal/UI/send/绑定。除了空锁双 worker，还需 stale 锁双接管反例：不允许后一个回收者移走新建活锁。Qwen 交付存在此竞态，已退回修复；其他两任务同步自查。

Windows 从 COMMON-001/002 和最新 baseline 接续；完成约定基线检查后推进本机 G5-01。未收到 Windows 本机接收与真机记录，不代填通过。
