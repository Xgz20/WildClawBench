# 控制推进记录

维护者：COMMON。更新：2026-09-21 +08:00。这是控制任务的调度/审查快照，不替代平台卡与技术验收，也不是跨进程桌面锁。没有配置定时巡检。

## 当前交付与下一项

当前直接在 `feature/astroncode-eval` 控制分支逐项迭代，不再并行派发平台 worktree。本轮统一题目 `timeout_seconds` 的执行语义：它不限制被评测 Harness 的运行时长；执行持续到可信原生终态、明确异常或需要人工处理。CDP/UI 单次操作、应用启动/停止与身份绑定、终态进程清理、评分 Worker/API 仍保留各自基础设施超时。

| 任务 | 已审查并集成的交付 | 正在推进 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | 原开发 Driver、输入修复与既有真机证据保持原 revision 身份 | General Driver 0.3.0 去除题目执行 deadline 后，重新做只读 probe 与 L1 smoke，再继续正式收口 |
| MAC-QWENWORK-GENERAL | 原 Driver 与 selector/SQLite 加固保留；旧 SLOT04 `send=0` 边界不变 | General Driver 0.3.0 删除旧超时终态注入入口；仍需 selector/关闭库 probe 和新版本 L1 smoke |
| MAC-DOUBAOWORK-WEB | 原 Web Driver、receipt 接入与既有 canary 证据保持原 revision 身份 | `--observe-seconds` 仅是开发期只读观察窗口；继续完成精确 cleanup、正式 collect/finalizer/评分/报告验收 |
| COMMON | General `0563b94`、Web `7a2142a`、QwenWork General `9885a4c` 已本地提交 | 推送前维持本地基线身份；各平台新版本 probe + L1 smoke 后再更新生产准入，新增五项指标另属 COMMON-CM01 |

本轮聚焦回归 369/369：General Python 63、General Node 57（QwenWork 32、AstronStudio/WorkBuddy 25）、Web Node 188（WorkBuddy 94、QwenWork 45、AstronStudio 49）、Web Python 61。General execute 升为 0.8.3，Web execute 升为 1.16.0；正式 Driver 实现不再包含旧 Harness 总执行超时逻辑。尚未新建生产发行包，也没有把旧真机结果提升为新版本准入。

## 历史桌面时段（2026-09-19）

以下表格只保留原始调试审计链，不代表当前仍有独占安排。当前没有并行平台任务，也没有活动桌面时段授权；后续真机验证在控制分支逐项执行。

| 时段 ID | 独占任务 | 允许范围 | 状态 |
| --- | --- | --- | --- |
| SLOT-MAC-20260919-01 | MAC-DOUBAOWORK-WEB | 一题 Web L1，一次发送/同 attempt 恢复 | SLOT_RELEASED；最新有效 UI observation 无 busy/stop/pending；候选 HTTP 服务仍有残留，不等于 cleanup 完成 |
| SLOT-MAC-20260919-02 | MAC-WORKBUDDY-GENERAL | 启动/CDP/配置/原生状态与草稿检查 | SLOT_RELEASED；发现原 31 字草稿，未发送 |
| SLOT-MAC-20260919-03 | MAC-WORKBUDDY-GENERAL | 私有备份核验后临时移出草稿、一次开发尝试、精确恢复 | SLOT03_RELEASED；reservation=1、实际 click=0/send=0；原草稿正文/HTML SHA 已恢复 |
| SLOT-MAC-20260919-04 | MAC-QWENWORK-GENERAL | 无活动冲突后启动 QwenWork 9250；真实 General 单题、keep-current、一次发送/观察恢复 | SLOT04_RELEASED；send=0、无 attempt；最后由用户确认退出，9250/主进程/DB 写者均已消失 |
| SLOT-MAC-20260919-05 | MAC-WORKBUDDY-GENERAL | 输入修复后新调试 attempt、原草稿私有核验与恢复、真实单题一次发送/观察 | 历史授权，不延续到当前控制分支；当前无活动独占时段 |

历史时段不能作为当前操作授权。不可为补证据重发不确定发送，不代答未知对话框。每次真机验证仍须报告真实 task/session/attempt、未停止状态、残留进程和恢复路径。

## WorkBuddy SLOT03

attempt `3e554524-6599-4182-aecc-3257977867c0` 在发送前已冻结 628 字符 Prompt，DOM SHA 与 manifest 一致，但发送按钮 disabled，`dispatchPrompt` 返回可用按钮 0。journal 已 reservation=1，实际 click=0/send=0，原生候选会话为 0；不能算模型执行失败或任务已发送。

同 attempt 只读 resume 没有重发，仍无 native 身份。未发送 Prompt 已移出，原 31 字用户草稿正文与 HTML SHA 均恢复；只有动态 style 属性不同。备份、恢复截图和证据权限为 0600，正文不入 Git。WorkBuddy 保持本轮启动的 PID 33343 / CDP 9229，模型 xopglm52、权限 default-sandbox；再次操作前必须重验现场，不能把此快照当作实时状态。

平台修复 `5bea762` 使用 Input.insertText 并在 armed 前确认 enabled，不绕过 disabled。独立 Node 25/25、实际 DOM 表达式 VM guards 7/7 通过；这些不是 React 真机证据。SLOT05 当时曾授予，当前授权已失效；若复核该历史 attempt，旧 attempt 计数仍不得重置。

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

Windows 接收 COMMON-001/002/003/004、最新 baseline 和本轮三笔代码提交后继续本机 G5-01，无需等待 Mac 平台新 smoke 或新增指标完成。由于当前本地提交尚未推送，Windows 暂不能把 `9885a4c` 记为已采用；推送后以固定 SHA 同步。Windows 真机记录由接收方回写，本控制任务未操作或代填其通过状态。活动批次不切源码/Skill。

Doubao 0f6d2c6 cleanup 独立审查未通过，未合入：父退出后 reparent 子进程丢失、PID复用后再次发信号、归属在信号前过期，以及 ..cache 合法路径/workspace实体变化反例已退回平台。未调用真实canary清理；修复后再复核。
