# 控制推进记录

维护者：COMMON。更新：2026-09-19 21:10 +08:00。这是控制任务的调度/审查快照，不替代平台卡与技术验收，也不是跨进程桌面锁。没有配置定时巡检。

## 当前交付与下一项

本轮把三个平台的开发 Driver 集成到公共分支，完成 252 项组合测试，COMMON-003 源码为 `dc5ff64c3d7b91ae0ecc6669583f5bd3d69c13c3`；后续输入修复源码 `2023b4d5d1d703c81ff8ed15e0d5ada29cd0dca4` 见 [COMMON-004](handoffs/COMMON-004.md)。源码全部在 `.agents/e2e-harness-contract` 集成；不把开发 canary 或离线测试写成正式 E2E 完成。

| 任务 | 已审查并集成的交付 | 正在推进 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | P2 `e388dfa`、组件绑定 `b3ac3da`；独立 Node 23/23 | SLOT03 发送前失败已安全恢复草稿、释放；输入修复 `5bea762` 审查通过，Node 25/25 与 VM guards 7/7；SLOT05 新 canary 已授予，先采用 COMMON-003/冻结身份；collector 独立推进 |
| MAC-QWENWORK-GENERAL | `9081df5`；独立 Node 32 + Python 3；Swift typecheck | SLOT04 已释放；项目 trigger 歧义导致 send=0；修可见控件 selector、关闭数据库的只读 probe；collector 独立交付 |
| MAC-DOUBAOWORK-WEB | P2 `47dcaee`、公共 merge `ca7cc2e`、更正 `3a3057c`；Node 39/39 | 离线审计原生 terminal/完整 workspace 绑定、实现精确 cleanup 及反例；COMMON 审查最小 Web 公共接口复用 |
| COMMON | CB-A/CB-B、三 Driver、发行版本与 Qwen CLI 路径别名修复 | 发布 COMMON-003，接收下一批平台修复/collector；新增五项指标另属 COMMON-CM01 |

公共/平台组合回归：General Python 63、Node 128（公共 34、WorkBuddy 23、Qwen 32、Doubao 39）、Web Python 61。General execute 本批升为 0.8.1（WorkBuddy25、General Python46复跑通过）、Web execute 1.15.0；其他 COMMON-002 版本保持。尚未新建生产发行包。

## 桌面时段

| 时段 ID | 独占任务 | 允许范围 | 状态 |
| --- | --- | --- | --- |
| SLOT-MAC-20260919-01 | MAC-DOUBAOWORK-WEB | 一题 Web L1，一次发送/同 attempt 恢复 | SLOT_RELEASED；最新有效 UI observation 无 busy/stop/pending；候选 HTTP 服务仍有残留，不等于 cleanup 完成 |
| SLOT-MAC-20260919-02 | MAC-WORKBUDDY-GENERAL | 启动/CDP/配置/原生状态与草稿检查 | SLOT_RELEASED；发现原 31 字草稿，未发送 |
| SLOT-MAC-20260919-03 | MAC-WORKBUDDY-GENERAL | 私有备份核验后临时移出草稿、一次开发尝试、精确恢复 | SLOT03_RELEASED；reservation=1、实际 click=0/send=0；原草稿正文/HTML SHA 已恢复 |
| SLOT-MAC-20260919-04 | MAC-QWENWORK-GENERAL | 无活动冲突后启动 QwenWork 9250；真实 General 单题、keep-current、一次发送/观察恢复 | SLOT04_RELEASED；send=0、无 attempt；最后由用户确认退出，9250/主进程/DB 写者均已消失 |
| SLOT-MAC-20260919-05 | MAC-WORKBUDDY-GENERAL | 输入修复后新调试 attempt、原草稿私有核验与恢复、真实单题一次发送/观察 | 已授予；在新文档/COMMON-003 合并并冻结源码后开始；待明确安全释放 |

SLOT05 仅 WorkBuddy 可操作桌面，Qwen/Doubao 继续离线修复/collector。后续时段由控制任务在修复审查后明确授予，不能自动开始。不可为补证据重发不确定发送，不代答未知对话框。结束时必须报告真实 task/session/attempt、未停止状态、残留进程和恢复路径；只有安全交接后才分配下一时段。

## WorkBuddy SLOT03

attempt `3e554524-6599-4182-aecc-3257977867c0` 在发送前已冻结 628 字符 Prompt，DOM SHA 与 manifest 一致，但发送按钮 disabled，`dispatchPrompt` 返回可用按钮 0。journal 已 reservation=1，实际 click=0/send=0，原生候选会话为 0；不能算模型执行失败或任务已发送。

同 attempt 只读 resume 没有重发，仍无 native 身份。未发送 Prompt 已移出，原 31 字用户草稿正文与 HTML SHA 均恢复；只有动态 style 属性不同。备份、恢复截图和证据权限为 0600，正文不入 Git。WorkBuddy 保持本轮启动的 PID 33343 / CDP 9229，模型 xopglm52、权限 default-sandbox；再次操作前必须重验现场，不能把此快照当作实时状态。

平台修复 `5bea762` 使用 Input.insertText 并在 armed 前确认 enabled，不绕过 disabled。独立 Node 25/25、实际 DOM 表达式 VM guards 7/7 通过；这些不是 React 真机证据。SLOT05 已授予，重新核验私有草稿备份与当前内容后才临时移出，新建调试 attempt 验证，旧 attempt 计数不重置。

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

Windows 接收 COMMON-001/002/003/004 和最新 baseline 后继续本机 G5-01，无需等待三个 Mac 或新增指标完成。Windows 真机记录由接收方回写，本控制任务未操作或代填其通过状态。两机以固定 SHA 和新增 handoff 接续，活动批次不切源码/Skill。

Doubao 0f6d2c6 cleanup 独立审查未通过，未合入：父退出后 reparent 子进程丢失、PID复用后再次发信号、归属在信号前过期，以及 ..cache 合法路径/workspace实体变化反例已退回平台。未调用真实canary清理；修复后再复核。
