# 控制推进记录

维护者：COMMON。更新：2026-09-21 +08:00。这是控制任务的调度/审查快照，不替代平台卡与技术验收，也不是跨进程桌面锁。没有配置定时巡检。

## 当前交付与下一项

当前直接在 `.agents/e2e-harness-contract` / `feat/e2e-harness-contract` 串行迭代，不再派发新平台 worktree。本次合并保留控制分支已有的 WorkBuddy/Qwen CB-B collector、WorkBuddy cleanup/readiness、Qwen metadata gate、Doubao finalizer/receipt/route/metrics，并吸收主工作分支 MiniMax Code 与统一超时语义。

题目或数据集的 `timeout_seconds` 不限制被评测 Harness 的运行时长；执行持续到可信原生终态、明确异常或需要人工处理。CDP/UI 单次操作、应用启动/停止与身份绑定、终态进程清理、评分 Worker/API deadline 仍是独立基础设施边界。题目时长和评分线程 deadline 不进入能力 Rubric；已确认最终完成且 `verify-score` 通过的迟到评分，只能经显式恢复入口登记并保留审计。

| 任务 | 已审查并集成的交付 | 正在推进 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | WorkBuddy 5.5.6 值守单槽五题执行/正式 collect 5/5，通过回传和同源报告链路；评分 4/5 valid；代码已支持迟到完成恢复 | 对 Colleague leave 复用冻结执行证据和现有有效 score 显式恢复，不重跑 Harness；随后重建 submission、return package 和报告并决定生产准入 |
| MAC-QWENWORK-GENERAL | `9081df5`；CB-B `acfc7a1`/`828bfb0`/`5263890`；metadata gate `679a1e3`；清单 `f1d5119`；真机预检 `e2541aa`；聚焦 Node 43/43 | SLOT04 已释放；项目 trigger 歧义导致 send=0；预检入口已就绪，仍待 1.0.6 真实日志、一次发送/恢复、正式 collect 与 cleanup |
| MAC-DOUBAOWORK-WEB | P2 `47dcaee`、公共 merge `ca7cc2e`、更正 `3a3057c`；离线加固 `40c2f71`/`2e21a54`/`5d7b6d9`；finalizer/bridge `9bb30aa`/`694536d`；public route `f38b66f`；v2 `3588c16`，控制接收 `e2c1d9e` | UI 等价绑定、Prompt 回读、进程重挂、恢复状态、driver-side finalizer、内存 bridge、离线 route 和原生 metrics 已加固；Driver 64/64、Web metrics 23/23；route 暂拒 batch/formal receipt，仍待可信 native terminal/cwd、公共 cleanup/finalizer 接线与新时段真机验收 |
| COMMON | CB-A/CB-B、三 Driver、平台 collector/cleanup/finalizer、MiniMax Code、无 Harness 总执行时限与评分恢复入口已汇合 | 完成合并后组合回归并登记精确 SHA；新增五项指标另属 COMMON-CM01 |

合并后 E2E 组合回归 578/578：General Node 162、General Python 80、Web Node 275、Web Python 61；MiniMax 新增测试 19/19、相关 tool/layout 67/67，Skill 查询和布局检查通过。更宽 anomaly 套件仍有 1 个既有 AstronClaw 样本断言失败，未归因于本次 E2E 合并。WorkBuddy v4 保持执行/采集 5/5、评分 4/5；尚未新建采用本次合并源码的生产发行包。

## 历史桌面时段与并行协作记录

以下内容只保留 2026-09-19 至 20 日审计链。当前没有并行平台任务，也没有活动桌面时段授权；后续改动直接在控制分支完成。

历史阶段采用过[macOS 三 Harness 真机协作计划](mac-live-session-plan.md)与[控制分支派发和回收流程](integration-workflow.md)；这些记录不再要求为下一项新建 worktree。

流程登记提交为 `1d61be3`，旧平台分支审计提交为 `c802ff4`。旧 worktree 继续保留 source→control 对账用途，不承接当前任务。

| 时段 ID | 独占任务 | 允许范围 | 状态 |
| --- | --- | --- | --- |
| SLOT-MAC-20260919-01 | MAC-DOUBAOWORK-WEB | 一题 Web L1，一次发送/同 attempt 恢复 | SLOT_RELEASED；最新有效 UI observation 无 busy/stop/pending；候选 HTTP 服务仍有残留，不等于 cleanup 完成 |
| SLOT-MAC-20260919-02 | MAC-WORKBUDDY-GENERAL | 启动/CDP/配置/原生状态与草稿检查 | SLOT_RELEASED；发现原 31 字草稿，未发送 |
| SLOT-MAC-20260919-03 | MAC-WORKBUDDY-GENERAL | 私有备份核验后临时移出草稿、一次开发尝试、精确恢复 | SLOT03_RELEASED；reservation=1、实际 click=0/send=0；原草稿正文/HTML SHA 已恢复 |
| SLOT-MAC-20260919-04 | MAC-QWENWORK-GENERAL | 无活动冲突后启动 QwenWork 9250；真实 General 单题、keep-current、一次发送/观察恢复 | SLOT04_RELEASED；send=0、无 attempt；最后由用户确认退出，9250/主进程/DB 写者均已消失 |
| SLOT-MAC-20260919-05 | MAC-WORKBUDDY-GENERAL | 输入修复后新调试 attempt、原草稿私有核验与恢复、真实单题一次发送/观察 | SLOT05_RELEASED；清空尝试失败后停止，未创建 attempt，click/send/native session=0；原草稿正文/HTML SHA 一致 |

所有历史 SLOT 均已释放。不可为补证据重发不确定发送，不代答未知对话框；后续真机验证仍须报告真实 task/session/attempt、未停止状态、残留进程和恢复路径。

## WorkBuddy SLOT03

attempt `3e554524-6599-4182-aecc-3257977867c0` 在发送前已冻结 628 字符 Prompt，DOM SHA 与 manifest 一致，但发送按钮 disabled，`dispatchPrompt` 返回可用按钮 0。journal 已 reservation=1，实际 click=0/send=0，原生候选会话为 0；不能算模型执行失败或任务已发送。

同 attempt 只读 resume 没有重发，仍无 native 身份。未发送 Prompt 已移出，原 31 字用户草稿正文与 HTML SHA 均恢复；只有动态 style 属性不同。备份、恢复截图和证据权限为 0600，正文不入 Git。WorkBuddy 保持本轮启动的 PID 33343 / CDP 9229，模型 xopglm52、权限 default-sandbox；再次操作前必须重验现场，不能把此快照当作实时状态。

平台修复 `5bea762` 使用 Input.insertText 并在 armed 前确认 enabled，不绕过 disabled。独立 Node 25/25、实际 DOM 表达式 VM guards 7/7 通过；这些不是 React 真机证据。SLOT05 已释放，清空门禁失败后没有新 attempt，旧 attempt 计数不重置；重新验证安全隔离路径前不得再次操作桌面。

## QwenWork SLOT04

单题 prepare 与 verify-batch 通过，live 仍固定源码 9081df5。发送前项目 trigger 返回 2 个候选，唯一性门禁拒绝继续；没有选目录、建项目、填 Prompt 或 attempt journal，send=0。平台将按当前可见视图修 selector，不使用首个元素绕过歧义。

退出最后依赖用户手动确认，不能计为自动退出/恢复通过。释放时精确主进程不存在、9250 无监听、agents.db/WAL/SHM 无占用。关闭后 WAL/SHM 消失，原 probe 与 sqlite3 -readonly 报 error 14；没有生成 probe-after-restore-final.json。无写者后补充 immutable 读取 quick_check=ok、21 个 session、active/pending=0，只是恢复旁证。平台需补无 sidecar 关闭库及活动 WAL/并发写入反例，probe 不得创建/删除/修复用户 sidecar。

## DoubaoWork SLOT01

真实任务 `07_Website_Generation_task_023_important_day_countdown`，批次 `web-e2e-20260919-doubaowork-canary-01`，唯一实际发送 attempt `f2d106cc-aeb4-4f56-a863-9a82edec5c6e`。模型“自动 高”、权限“按需确认”；UI/native session 唯一绑定。已消费旧交接不改写，更正见 [MAC-DOUBAOWORK-WEB-002](handoffs/MAC-DOUBAOWORK-WEB-002.md)。

- 19:39:32 的 observation busy=1，却误记释放；该完成/释放结论无效。
- 19:47:06 的 observation busy/stop/dialog/question/approval 均 0，回复候选 1,893 字节，但最新回复/截图未唯一归档，旧 145 字节回复不能代替它；当前源码已修唯一快照，尚未真机复验。
- 后续只读核对已确认倒计时 HTML 18,216 字节及两张截图；“只有 .gitkeep”判断已更正。HTML mtime 晚于截图，未证明它们对应当前 HTML。
- 候选 Bash/Python 进程组仍以 `workspace/countdown` 为 cwd，Python 监听 8848；尚未清理。缺 native terminal/cwd、正式 execution record/receipt、score/report，保持 NEEDS_ATTENTION。
- prepared input 冻结在 c098...；live Driver 是未提交迭代且未留精确文件哈希/dirty diff。47dcaee 包含事后修复，不是精确 live source。

本机原件位于 `/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/slot-mac-20260919-01-canary/`。不为了补齐来源身份重发原 Prompt。

## 公共接口与跨平台

General trace v2 / common finalizer 已由 COMMON-002 提供；平台真实 collector 和 cleanup hook 单独审查，不能复制或绕过正式门禁。General wire 不直接用于 Doubao Web；已明确[最小公共接入方案](doubaowork-web-integration.md)：复用现有 Web v1 writer/receipt，平台补可归档等价绑定和 cleanup，COMMON 注册 parser/route 与专属严格 gate。discovery 1.2.0 与 prepare 的 Doubao 支持已经交付，不再列为全缺。

原生工具 completed 不等于业务成功；缺失指标保持 null、known subtotal、coverage。取消/中断、来源路径、锁 stale 双接管和恢复状态反例已经分别复核，不能以此替代尚未进行的真实恢复/cleanup/评分验收。

Windows 接收 COMMON-001/002/003/004、最新 baseline 和本次控制分支合并提交后继续本机 G5-01，无需等待 Mac 平台后续任务或新增指标完成。本轮提交尚未推送，Windows 暂不能记为已采用；推送后以固定 SHA 同步。Windows 真机记录由接收方回写，本控制任务未操作或代填其通过状态，活动批次不切源码/Skill。

Doubao 原 `0f6d2c6` cleanup 已由 `40c2f71` 及 `5d7b6d9` 离线修订并接收，覆盖父退出后 reparent 子进程、PID 复用、归属复核、`..cache` 合法路径和 workspace 实体变化反例；`9bb30aa` 已加入 driver-side finalizer assessment，但尚未接入公共 route/receipt 或调用真实 canary 清理。UI `verified` 仍只表示等价绑定，不提升为 native/trusted 终态。
