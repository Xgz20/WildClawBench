# DoubaoWork macOS Web 多题接续证据（2026-09-25）

范围为 macOS x86_64、DoubaoWork 2.31.6、本地电脑模式、值守。原始项目/会话/request ID、截图、轨迹、候选和评分包只保存在 `/Users/gzx/debug-workspace/e2e-evaluate/`；[脱敏索引](evidence.json)登记完整 task ID、状态、发行版本、SHA 与指标边界。本记录从[单题同包闭环](../doubaowork-macos-web-20260925/README.md)接续，不回填旧 canary。

## 三题串行

`dw-web-serial3-20260925` 按 manifest 顺序执行 `task_001_daymark_product_website`、`task_002_focus_pomodoro_clock`、`task_035_today_and_all_todos`。队列只在上一题正式收口后派发下一题，三题各发送一次；模型 UI 均精确回读“自动 高”。受控 `SIGINT` 只中断观察 Worker，原生任务未停止；同一 run ID 恢复后 attempt 与发送次数不变。三题均为 `SUCCEEDED`，逐题 cleanup、候选哈希、正式发布与完整范围根回执通过。

首题遭遇图片 `Read` 的本地/轨迹固定文本差异：共享证据核心仅按同一调用 ID、图片路径、成功状态和精确文本对账，多模态附件内容覆盖保留 partial。执行/收口跨 Web execute 1.19.0→1.19.1、共享0.7.2→0.7.3，队列显式登记接续。后两题由1.19.1执行，不能把整个三题批次写为同发行包生产通过。

三份评分目录由 Codex Desktop 可见 UI 精确注册，评分前检通过；独立 `gpt-6-sol/high` 评分任务按3槽创建。产品页与待办清单两题的正式评分已完成。番茄钟评分 Agent 的 13 项中 11 项有有效操作结论；提示音与 Browser 无法提供 hidden 状态的两项保留 `evaluation_error`，协议总分不能解释为能力零分。该评分任务的最终结果晚于控制状态冻结的 deadline，`mark-complete` 明确拒绝接纳；评分控制状态为 `NEEDS_ATTENTION`，没有三题 submission、return/import 或报告。原评分文件和失败状态均保留，不改写 deadline。

## 五题三槽

`dw-web-five3-20260925` 冻结五道 L1 题，UI槽固定1，配置原生执行槽3。首次三题各发送一次，原生前台活动峰值只读核验为3；第二题正式收口时第四题动态补入，首题收口时第五题补入。第二、首题的工具轨迹分别暴露 `Edit FILE_NOT_FOUND`、`Write update` 与 `TaskOutput` 的不同固定展示；修订校验只接受同一调用 ID、结构化状态、完整路径/cwd 或完整 stdout 的精确对应，未知组合继续拒绝。队列两次显式记录控制器版本接续，属于**跨版本技术验收**。

截至上次原生只读检查，五题中的四题为 `SUCCEEDED`，各有逐题正式发布；最后一题有已绑定原生活动 request，IM 尚无助手终态。观察 Worker 已有界中断并释放锁；其后原生状态须重新检查，不能从旧快照推定现在仍运行或已经结束。根回执、评分与能力分母尚未产生。不能以任务等待时长、UI 部分回复或已有候选文件推定成功，也不从旧批次移植分数。恢复必须沿同一 run ID 和 attempt 只读观察。

## 指标与准入边界

原生智能体耗时来自已绑定 `elapsed_block`；流程耗时、工具调用总数或已知小计分别记录在逐题执行记录。多模态结果内容或跨来源顺序缺口保持 partial；Token、模型请求数、费用和底层模型 ID 无可信账本，保留 `null/unavailable`。SDK 传输重试计数不等于模型请求次数。

Web1.20.3、共享0.7.6 的源码已在 `4951d02` 提交，发行内容仍以独立 Skill ZIP/content SHA 为准。后续的工具上传失败部分采集修复不回填本批次，也不改变既有回执。三题串行与五题动态补位的上述结果不能证明**同发行包**多题主流程、完整五题并发评分或无人值守生产准入。General 与 Web 共用原生核心，各自的发行与验收继续独立；General 2.31.3 的历史成绩及并发证据不迁移到当前 Web。
