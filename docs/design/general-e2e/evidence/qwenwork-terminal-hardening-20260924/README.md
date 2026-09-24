# QwenWork macOS 异常终态加固证据

日期：2026-09-24。范围：macOS Intel / QwenWorkCN 1.2.0 / 值守技术样本。唯一进度见[统一接入契约](../../../e2e/端到端自动化评测Harness接入契约.md#qwenwork-剩余生产准入事项)；[脱敏索引与原件 SHA](terminal-r40-r44.json)保留各冻结包及失败尝试。原始日志、截图、原生 ID 和运行目录均在仓库外。所有技术样本不评分、不计能力分母。

- **客户端中断**：r40 在确认唯一活动任务、原生 Prompt/session/project/cwd、主 turn 已开始后，对精确核验 PID/启动身份的测试客户端注入 SIGKILL。正常重启后原 session 为 `interrupted`、stream 为空，其他任务状态变化为 0；原 attempt 恢复得到 `FAILED / infrastructure_error / QWENWORK_INTERRUPTED`，发送始终为 1。
- **中断正式采集**：原 collector 因没有 `turn.finished` 拒绝；r41 新增共用 `qwenwork-native-state`，General execute/collect 分别 vendor，同一只读 SQLite 核心没有跨 Skill 运行依赖。collector 独立取新鲜在线备份，核验完整身份和原生中断状态，仅归档选中原生行与来源摘要。首次 collect、真实 cleanup/finalize、单题 receipt、verify-only 均 PASS，不补造主 turn 结束。该样本是 **r40 执行/r41 采集的跨版本回归**。
- **原生最终错误**：r43 独立批次使用冻结 r41 发行；完成一次无害 Read 后，在已绑定的 SDK worker 推理地址解析处临时修改受支持的服务地址。SDK 自身触发 `CustomProviderAccessError / 403`，原生主 turn 为 `error`，数据库为 `failed`。Driver、collector 与正式回执一致归为基础设施异常，首次 collect/finalize/receipt/verify 全部 PASS，发送 1 次。没有改写数据库、事件或工具结果。实际错误发生在 SDK 请求准备阶段，**不声称验证了网络重试或全部服务错误类型**。
- **失败尝试保留**：r41 启动时覆盖地址导致 SDK 初始化卡住、缺少 session ID，不算最终错误通过；r42 的锁屏/环境准备失败均发生在发送前，恢复后单次发送。该次注入因 worker 已有客户端设置的网关而在修改前拒绝，任务正常完成，也不算最终错误通过。未覆写这些原件。
- **指标边界**：中断样本 Token、模型请求数和工具数总量为 null/partial；已验证小计为请求 2、工具 2、Input 73239、Output 638、Cache Read 36424、Total 73877。流程耗时 497.504 秒包含恢复停机时间，智能体耗时为 null。最终错误样本请求 2、工具 1，流程耗时 44.443 秒、原生耗时 6.944 秒；因请求/响应未完整对账，Token 总量继续为 null/partial。HTTP attempts、Cache Write、reasoning Token 仍不可用。

r44 将中断 Token 小计进一步限制为精确已准入 Profile 且响应逐个对应已见 request ID；孤立响应、未知 Profile 和 null 耗时均有反例。用新的独立 collector 对两个真实样本重新采集，指标与原结果一致，并复验原不可变回执，未改写正式 evidence/receipt。这是新 collector 对旧真实材料的回归，不是新发行的完整重跑。

最终候选：General execute **0.11.12**、Driver **0.3.12**、collect **0.8.12**、collector **0.1.5**，共享原生状态组件 **1.0.0**。General Node **127/127**、Python **28/28**；Web Node **47/47**、布局 Python **4/4**。General execute/collect 与 Web execute 的独立包、完整 General suite 构建及验证均 PASS。Web 未发送新任务，正式单题闭环尚未开始。

测试结束后已恢复 worker 原网关，正常重启客户端以移除临时 Node Inspector，核验调试端口关闭、原服务地址覆盖为空、Token 开关保留；本机故障 TCP 服务已停止。服务累计连接数跨越旧初始化失败尝试，不能归因于 r43 或作为 HTTP 重试次数。用户模型/权限配置未改变。

CV07 已列终态分支已有真实材料与回执；整体仍保留轨迹异常、候选材料、评分发布中断和报告分母四项证据审计，不据局部通过声明全面生产准入。
