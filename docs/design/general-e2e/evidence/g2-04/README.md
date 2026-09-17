# G2-04 AstronStudio 资源采集与覆盖状态映射证据

## 结论

2026-09-18 使用 `collect-general-e2e` `0.3.0` 的资源子能力，对 G2-02 已完成、G2-03 已冻结轨迹的 S1 和 S4 做只读重放。没有重启 AStudio、没有发送新 Prompt，也没有访问热写数据库。

两题的 `resource-metrics-v1` 均为 `collection.status=complete`：已暴露的 Token、缓存读取、推理输出、工具调用和两类耗时全部完成原生对账；请求次数明确标记为 `inferred`。AStudio 不暴露缓存写入和底层 HTTP 尝试，因此这两个字段保持 `null/unavailable`，覆盖分别为 `0/N` 和 `0/null`，并列入 `excluded_scope`，未补零。

这些结果只完成 G2-04。候选冻结、任务进程收口和正式 execution receipt 仍属于 G2-05；`collect-general-e2e` 整体继续标记 `interface_only`。

## 真机指标

| 样本 | 输入 / 输出 / 总 Token | 缓存读取 / 推理输出 | 请求 / 工具 | 流程壁钟 / 原生 Agent 耗时 | 产物 SHA-256 |
| --- | --- | --- | --- | --- | --- |
| S1 `02_Code_Intelligence_task_001_temperature_cli_fix` | 167237 / 1318 / 168555 | 145152 / 83 | 7 inferred / 5 observed | 49.006s / 32.476s | `dd4ef3cec86b2cc06773cf2037f7c6f3e2d19c653fa14bfb970bca8d3a0fad30` |
| S4 `01_Productivity_Flow_task_003_retro_agenda` | 22803 / 831 / 23634 | 20480 / 274 | 1 inferred / 0 observed | 85.432s / 22.751s | `5a9c912d643d1722b87fa55aa9056fd177d21e6dd9e692ebaf5d387e966481a4` |

产物：

- [S1 resource metrics](s1/resource-metrics.json)
- [S4 resource metrics](s4/resource-metrics.json)

输入 Token 已包含缓存读取，输出 Token 已包含推理输出，上表没有重复相加。流程壁钟来自 Driver attempt 开始到终态观察；原生 Agent 耗时按精确 turn 的 `turn.started.createdAt` 到 `turn.completed.createdAt` 计算。S4 的 85.432 秒流程壁钟包含此前记录的热写 SQLite 快照恢复等待，而 22.751 秒只表示原生 turn 活跃区间。

## Token 与请求对账

S1 原始轨迹包含 7 个唯一 `thread.token-usage.updated` 推进。每个推进的 `lastInputTokens / lastOutputTokens / lastUsedTokens / lastCachedInputTokens / lastReasoningOutputTokens` 分别求和，并逐项验证：

- 本次累计值 = 上一个累计值 + 本次 `last*`；首个累计值先减首个 `last*` 得到既往基线；
- 每次及总量均满足 `used = input + output`；
- cache read 不大于 input；reasoning output 不大于 output；
- 最终得到 167237 + 1318 = 168555，且 7/7 个 usage observation 完整。

S4 只有 1 个 usage 推进，按同一口径得到 22803 + 831 = 23634，覆盖为 1/1。请求数来自完成上述对账的 usage 推进次数，所以只能写作 `inferred`，不能表述为底层 HTTP 请求数。`request_attempt_count` 没有原生来源，保持 `null`。

## 工具与覆盖对账

S1 原始 `item.started` 中有 5 个唯一工具 call ID，与 G2-03 trace index 的 5 个调用集合完全一致；`item.completed` 不重复计数。S4 在完整 turn 范围内没有工具调用，trace index 的 calls 也为空，因此 `call_count=0 / observed` 是有完整边界支持的真实零值，而不是缺失时补零。

每个指标都有 `collection.coverage` 和 `collection.metric_sources`。部分或受损输入的回归测试要求：标准 `value` 保持 `null`，安全已知值仅写入 `known_subtotals`；原始轨迹不完整时事件派生指标降级为 `partial`，独立完整的 Driver 壁钟仍可保持 `observed`。

## 来源和验证边界

- S1 来源：G2-02 state SHA `dbbc4d7b41586dc469d519d2d243ce24fdfe067c535a8dd3aaba09ec1c912e7d`、G2-03 index SHA `6c1df7aee6dbc225492f1c96c7748fe9f3e08ed31ca64de88004d74bebf6a20b`、raw SHA `7181fd47a6811190a0c03854e5bf382b0d99cd2aa90e0962998911a5bd499cd0`。
- S4 来源：G2-02 state SHA `ba40caab885433d4b098df853f8777f16ebcd045142ed35221a5d2a39dcd2697`、G2-03 index SHA `a57b5e534a47458885f58005f1971e028c76d148d5234692b7e8631da63d25e5`、raw SHA `5a04620f463cb3f5c7491a31165a9b748aef1ef0887ef6ec5b6793dd8d20b709`。
- 采集器在读取前复核 identity/session/cwd/lifecycle、文件边界、size、SHA、event count 和 sequence range；篡改或跨 attempt 输入失败关闭。
- Node 资源专项覆盖累计基线、重复快照、部分字段、known subtotal、部分轨迹、Token 语义冲突和产物篡改；Python 语义验证器覆盖逐字段 coverage/source/subtotal 约束。
- `collected_at` 使用冻结执行状态的终态观察时间作为该 attempt 的有效采集截止点，使同一冻结输入可确定性重建。
