# AstronStudio 资源指标采集

## 输入与身份门禁

采集器接受一个终态 `automation-state.json` 和一个 G2-03 `trace-index.json`。它会重新校验 task/attempt identity、thread、turn、provider session、cwd、lifecycle generation、原始 JSONL 的路径边界、size、SHA-256、事件数和 sequence 范围。任一身份或哈希不一致即失败关闭，不从最近任务、界面数字或最终文件反推资源数据。

输入必须已确认 Prompt 只发送一次。采集器只读取冻结文件，不访问 AstronStudio 热写数据库、不调用模型、不修改客户端状态。

## 字段口径

| 字段 | 口径 | 状态 |
| --- | --- | --- |
| input/output/total Token | 每个唯一 usage 推进的原生 `last*` 增量求和，并逐步与累计 `total*` 对账 | 完整时 `observed` |
| cache read | `lastCachedInputTokens` 之和，属于输入 Token 子集 | 完整时 `observed` |
| cache creation | 当前 provider runtime event 不暴露 | `null / unavailable` |
| reasoning output | `lastReasoningOutputTokens` 之和，属于输出 Token 子集 | 完整时 `observed` |
| request count | 已完成上述对账的唯一 usage 推进次数 | `inferred`，不是 HTTP 次数 |
| request attempt count | 不可见的 HTTP 尝试或重试 | `null / unavailable` |
| tool call count | 唯一 `item.started` call ID，与 trace index 调用集合对账；result 不重复计数 | 完整时 `observed` |
| duration | Driver attempt 开始到终态观察的壁钟耗时 | `observed` |
| agent duration | 精确 turn 的原生 `turn.started` 到 `turn.completed` | 完整时 `observed` |

输入已经包含 cache read，输出已经包含 reasoning output，汇总时不能重复相加。若 thread 有既往使用量，采集器从第一个累计值减去本次首个 `last*` 得到基线，再逐个推进，因此不会把前轮 Token 记入本题。

## 覆盖与部分数据

每个指标同时写入：

- `metrics.*.{value,status,basis}`：标准值与来源状态；
- `collection.coverage`：已知观察数、应有总数和观察单位；
- `collection.metric_sources`：可定位到 state、trace index 或 raw line 的引用；
- `collection.known_subtotals`：只有 `partial/unverified` 字段可写的安全已知小计。

原始轨迹不完整时，事件派生值降级为 `partial + null`，已知值只进入 `known_subtotals`；Driver 壁钟若自身仍完整可继续保持 `observed`。客户端按设计不暴露的字段不会使整个 collection 自动失败，但必须进入 `excluded_scope`。

## 输出边界

默认在 trace index 同目录生成 `resource-metrics.json`。输出只是 G2-04 资源证据；G2-05 完成候选冻结、进程收口和正式 execution receipt 前，不能进入评分。
