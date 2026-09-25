# DoubaoWork macOS Web E2E 单题证据（2026-09-25）

范围为 macOS x86_64、DoubaoWork 2.31.6、本地电脑模式、用户值守。任务为 `07_Website_Generation_task_035_today_and_all_todos`（L1）。原始会话 ID、截图、日志、候选和评分包保留在仓库外；[脱敏索引](evidence.json)仅登记版本、哈希、可复算指标和验收边界。批次及运行原件位于 `/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-web-20260925/`。

## 结果与版本

- R5 首次发送使用 Web execute 1.18.2。原生工具观察器、生命周期、Prompt 和会话身份均绑定；第一次正式收口因 `Edit` 结构化成功结果与会话轨迹中的固定文本不同而被拒绝。经核验同一调用 ID、工具名、成功状态、文件完整路径、diff 头和精确轨迹文本后，共享组件 0.7.2 加入窄范围等价映射；1.18.3 对原 attempt 只读恢复并形成有效回执。该材料属于**跨版本执行/收口**。独立评分任务完成，submission 和报告已生成；不能把分数追溯为 1.18.3 同包执行成绩。
- R7 用 Web execute 1.18.3 独立发行包首次发送、恢复和正式收口。原生成功终态、完整 cwd/Prompt/项目绑定、前后台空闲、任务进程清理、候选冻结与回执复验通过，`execution-receipt.json.integrity.valid=true`。R7独立评分通过：12/12功能检查点、功能总分100/100，独立美观度90.25/100；submission、同源JSON/Markdown/三Sheet Excel报告均已生成；return ZIP及外置回执已按现有`run-web-e2e`契约导出、导入，重复导入返回幂等。
- 两次真实执行均只发送一次。R3 是先前缺少本地工具观察器的真实失败样本，状态保持 `NEEDS_ATTENTION`，没有正式回执；没有为它补造工具证据或重发原 attempt。

## 来源与指标

Web 和 General 共用 `tools/report/e2e-shared/doubaowork/` 的 GUI、发送恢复、原生消息、工具事件、轨迹融合与进程清理核心；Web 独立验证 prepared task、生成记录、冻结候选和发布单题回执。发行内容以 [evidence.json](evidence.json) 中的 Skill content SHA 与 ZIP SHA 为准；仓库基线 `81312dd` 只代表此前提交的 General 加固，不能代替此处尚未提交的 Web 工作区源码身份。

R7 的 `execution_record.json` 记录流程耗时 258.425 秒、原生智能体耗时 244 秒、完整工具调用 15 次。R5 的对应值为 277.06 秒、260 秒、工具已知小计 24 次，总数仍为 `null/partial`；其功能总分100/100、美观度89.42/100均只归属R5候选。两批均没有可信的 Token、模型请求/重试或费用原生账本，维持 `null/unavailable`。客户端实际 UI 模型显示为“自动 高”，底层模型 ID 未证实；评分裁判的 `gpt-6-sol/high` 是另一身份。

## 回归与边界

最终聚焦 Node 171/171、Python 17/17 通过；Web独立Skill包与新版General完整suite构建、验包通过，21份共享源码在三处vendor一致。R7收尾只读检查显示前后台活动0、观察器0、UI锁无残留，batch入口在发送前拒绝。General 五份真实材料在共享证据模块抽取后重新采集通过，旧回执不覆盖。Codex Desktop 26.917 的可见项目注册按钮可能在对话框已打开后才使 Playwright click 超时；注册器只在唯一目标对话框或原生文件选择器有正向证据时继续，未使用私有 renderer bridge。

本轮准入只覆盖值守单题。Web 批量、并发补位、人工交互正式回执和 Windows/Apple Silicon 尚无本版证据；General 2.31.3 的历史成绩及并发结论不迁移到 2.31.6。历史 Web canary 仍保持原来的 `NEEDS_ATTENTION` 身份。

后续串行与并发队列见[多题接续证据](../doubaowork-macos-web-batches-20260925/README.md)。
