# 控制推进记录

维护者：COMMON。更新：2026-09-19 19:07 +08:00。这是控制任务的调度/审查快照，不替代任务卡和技术验收，也不是跨进程桌面锁。

## 第二轮目标

首轮 P1 交付已收到；继续三个原任务，完成客户端执行入口、已发现正确性问题、受控真机采样与 CB-B 公共收口。未经审查的平台分支不直接合入工作分支。源码变化均在指定 worktree。

| 任务 | 已收到的交付 HEAD | 控制任务已安排的下一项 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | `975f21aaf5b356ea2632acca55cf6b7d8cd0439a` | 修复取消/中断和冲突终态映射、原生来源路径和工具成功语义，再完成 P2 journal/执行/恢复入口与离线测试 |
| MAC-QWENWORK-GENERAL | `dac06696142969195c2af93f7442cd39d5a279fb` | 修复终态/stream冲突、绝对cwd和发送基线选择、工具完成≠成功，再完成 P2 Driver/恢复与离线测试 |
| MAC-DOUBAOWORK-WEB | `c098a2e386baec6b04ed4af615349bea974f0746` | 修复工具ID作用域/重复统计、损坏轨迹行和来源路径/不可覆盖输出；使用真实 prepare 输入做单题开发采样 |
| COMMON-CB05 | 已批准接口方案，实现中 | trace-index v2、多raw/binding来源、共用finalizer与旧Astron薄wrapper、可信cleanup hook和脱仓验证 |

本轮公共发现源码 `de8b23de3bbffada05e115f365cc70747f490efa` 增加 DoubaoWork macOS 原生应用 Profile，discovery 组件拟 1.2.0；13 项 discovery 测试及实际安装只读检查通过。组件 catalog/绑定版本由 CB-B 负责人统一装配，组合校验前不作为新公开基线。

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
- general-contracts 拟 1.2.0、collect-general-e2e 拟 0.5.0，版本/发行以最终集成交接为准。未发布版本不能被平台借用作生产证据。

Windows 继续消费 COMMON-001；本轮尚无新的已发布公共接口，不因另一个平台分支的未提交代码改变其工作基线。下一次公共提交完成后另发 COMMON-002，列明必须回归的范围。
