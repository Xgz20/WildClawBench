# Loomy 原生证据与正式收口

输入是标准 execution unit、原运行配置及该题终态 dispatch journal。
每个采集输出使用新目录，原执行状态、候选工作区和旧证据保持原样。

```bash
node drivers/loomy/collector.mjs --unit-root /absolute/unit --task-id TASK_ID \
  --run-config /absolute/frozen-run-config.json
node drivers/loomy/finalize.mjs --unit-root /absolute/unit \
  --state-file /absolute/collection/execution/automation-state.json \
  --trace-index /absolute/collection/trace/trace-index.json \
  --resource-metrics /absolute/collection/resource-metrics.json --python /absolute/python
node drivers/loomy/finalize.mjs --verify-only --unit-root /absolute/unit --task-id TASK_ID
```

Collector 重新读取只读 SQLite 在线备份中精确绑定的根 session 及递归子树，保留
原始 message/part JSON 列、终态原件、初次绑定、发送 journal、冻结配置和全部 UI
准备证明。它核对唯一原 Prompt、cwd、模型／High、工具结果、原生结束与最终消息 ID，
输出通用 execution-state、trace-index v2、标准转录及最终回复。子会话内容标记为
独立原生身份，不冒充新的主用户发送或主最终答复。

普通工具失败保留原结果。工具调用与结果分别记录，原始内容原子计数守恒；未知类型
或缺失结果不能被声明为完整轨迹。该 Profile 的原生模型错误保留为被测端失败，不能
由采集器直接赋零分。问题工具不支持默认填成“人工介入 0 次”。

工具数来自绑定原生 call ID。流程耗时采用控制器发送到确认原生终态的同机时间；
原生耗时按同一 OpenCode 时钟的首条用户消息创建到主最终助手完成区间推导，并标记
`inferred`。新资源 Profile 为 `loomy-opencode-recorded-usage/v1`：

- 每条绑定 assistant 的 `tokens` 与 `step-finish.tokens` 为同一用量的重复投影，只计一次；包含递归子会话，排除控制器、裁判及无关 session。
- 输入总量=`input + cache.read + cache.write`，输出=`output + reasoning`，逐条与原生 `total` 对账。缓存分别单列，不能再次加到已含缓存的输入中。
- 原生 `total` 或必要分项缺失时，该条用量未知，不把初始化零计为真实零；记录已知小计、原生消息覆盖和缺失 ID。
- `finish=length` 的负输出分项，仅在合并推理后非负且与原生总量完全相等时接受合并输出；原值与异常 ID 留证，不钳制负值。此类推理分项保持未知。
- 请求数与既有 OpenCode CLI 一致，统计唯一 `step-finish` 记录；不是 assistant 消息数，也不包含没有 step-finish 的失败请求和未观测 HTTP 重试。`request_attempt_count` 保持未知。

历史资源不覆盖。使用新的工作副本及本 Skill 的离线补充入口后，报告再独立重验：

```bash
node scripts/supplement_resources.mjs create --unit-root /absolute/derived/unit \
  --execution-record /absolute/derived/unit/evidence/tasks/TASK/ATTEMPT/execution-record.json
node scripts/supplement_resources.mjs verify --unit-root /absolute/derived/unit \
  --execution-record /absolute/derived/unit/evidence/tasks/TASK/ATTEMPT/execution-record.json --task-id TASK
```

工作副本必须保留原执行、资源、trace-index、全部绑定原件及 SHA；补充只写新目录。
旧 `<=0.1.21` 资源 Profile 继续按原 null 口径独立回放，不追改历史原件。

正式 finalizer 使用真实 macOS Workspace 进程清理、安静窗口和通用候选树冻结。
发布与 `verify-only` 都会独立重放 Loomy 归一化、Prompt／模型绑定、完整路径准备
证明及资源计算；不依赖正在运行的 Loomy 来离线复验。多题 unit 先完成各题收口，
再使用完整采集回执逐题复验。标准评分与回传继续使用原冻结 rubric。

正式收口顺序为：全单元执行终态 → 全部原生 collector 输出 → 逐题 finalize → 全单元 verify-only。Loomy 后端可能以某题 Workspace 为 cwd，提前 finalize 会影响共享后端，因此入口校验完整屏障与全局原生活动。
