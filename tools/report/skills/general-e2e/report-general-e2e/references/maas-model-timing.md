# MaaS模型耗时

只在报告生成阶段运行。`report_general_e2e.py generate` 与 `selected_report.py` 接受互斥的 `--maas-es-cache ABS`、`--maas-es-config ABS`。无此选项时模型列显示 `-`，原生任务耗时仍正常生成。Skill随包分发全部实现，不依赖AstronCode源码、执行Harness或Judge。

## 来源与口径

每题先验证原execution record SHA、task/unit/attempt身份、verified session及主turn；只读取绑定SHA的rollout和provider事件。rollout的 `response_item.payload.id` 中，`rs_<sid>_<序号>`、`resp_<sid>_<序号>` 合并为同一个SID。provider的 `turn.gateway-usage.updated` 请求账本用于补足重试、失败、取消及compaction请求。重复通知不重复计数。不同任务共享SID时不能归属到任一任务。旧版本缺少完整请求账本时，只有rollout SID数与已验证的用量推进数对账且无stream error/compaction，才能确认完整覆盖。

精确查询 `model.keyword=spark-x2.5`、`serviceName=maas_cube` 和绑定SID集合，分页读取全部命中。只保留SID、模型、服务、请求起止、perf、结果和ES文档引用等最小字段。禁止跨服务累加，也不把latest500的样本当作历史全量。相同SID的语义相同日志去重，perf或请求起止冲突时保持不可用。HTTP错误、分页不完整或ES分片失败不发布缓存。

每题模型耗时 = 唯一且有效的请求 `maas_cube.perf` 之和 ÷ 1000。成功、失败、取消请求均纳入。此口径是服务请求累计耗时，不能解释为纯推理时间或任务墙钟占用；并行和服务端尾部处理可使占比超过100%，不能截断。

单元总模型耗时为逐题累计值之和。平均值以当前比较题数为分母，P50/P90是逐题累计模型耗时的线性插值分位数，不是单次请求时延分位数。占比为总模型耗时÷总原生任务耗时，不能平均逐题比例。总任务耗时继续来自 `agent_duration_seconds`，不替换为流程耗时。

仅当前视图的全部任务及请求完整覆盖时，展示模型总量、均值、占比及分位数。否则显示 `-`，逐题已知小计和缺失原因保留于审计。真正观测到的0保留。无法确定请求总数时显示“总数未知”。统一剔除视图按相同task ID集合复算，可出现全量不可用而共同58题完整的情况。

## 离线缓存

生成器会在输出的 `model-timing/` 保存 `request-ledger.json`、`es-cache.json`、`coverage.json`，并加入报告回执。派生字段位于报告JSON的 `tasks[].model_timing` 和 `model_timing_provenance`；不加入或修改冻结的resource-metrics契约。

已有报告可先补采缓存，再向新文件补充派生统计；原报告不能作为输出覆盖：

```bash
python scripts/maas_model_timing.py fetch --report-json /abs/general_e2e_report_data.json \
  --config /abs/es-config.json --output-cache /abs/es-cache.json
python scripts/maas_model_timing.py enrich --input-json /abs/general_e2e_report_data.json \
  --es-cache /abs/es-cache.json --output-json /abs/new-report/general_e2e_report_data.json
```

`enrich`只生成JSON，随后须用同源渲染器生成Excel及领导版Markdown，并核验两处耗时表。已有附加视图必须提供 `resource_exclusion_analysis.included_task_ids`，不得猜测筛选范围。

## ES配置与认证

配置示例只含连接和查询参数：

```json
{"kibana_url":"https://kibana.example/app/discover","index":"cube-log-*","model":"spark-x2.5","page_size":500,"sid_batch_size":100,"timeout_seconds":45}
```

也可用 `es_url` 直接连接ES，与 `kibana_url` 互斥。认证从 `ES_API_KEY`、`ES_BEARER_TOKEN` 或 `ES_USERNAME`/`ES_PASSWORD` 读取，任选一种；CA可通过 `ca_cert` 或 `ES_CA_CERT` 提供。不得把凭据写入配置、代码、报告、缓存、日志或命令参数。
