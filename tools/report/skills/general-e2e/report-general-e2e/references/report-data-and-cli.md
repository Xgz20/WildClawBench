# 报告数据与 CLI 适配

## 报告数据

`general_e2e_report_data.json` 使用 `wildclawbench.general-e2e-report-data/v1`。顶层包含：

- `scope`：唯一任务数、任务运行数、unit 数和冻结任务 ID。
- `overall`：有效评分、分类、难度、裁判分组、资源和耗时。
- `units`：每个 unit 使用相同口径的聚合。
- `tasks`：逐任务运行的执行、评分、资源与 lineage。
- `lineage`：批次 manifest、报告配置、导入选择和每个已选 package 的 SHA。
- `presentation`：Excel 与领导版 Markdown 共用的单元对比表、有效样本覆盖、显示名与公共字典 SHA；数据仍可由上述冻结输入复算。

同一任务可在多个 unit 中出现，报告以 `<unit_id>::<task_id>` 作为 `run_id`。唯一任务数和任务运行数不得混用。

## 分数状态

| `score_status` | `total_score` | 主均值 |
| --- | --- | --- |
| `valid` | `0.0–1.0` | 进入；`0.0` 保留 |
| `evaluation_error` | `null` | 不进入 |
| `unscored` | `null` | 不进入 |

候选错误或超时仍可能按原任务规则形成有效分；是否有效以已校验 score 为准。评测系统错误不得变成能力零分。

## 资源字段

每个字段包含：

- `total`：仅任务运行全集都完整覆盖时可用。
- `known_subtotal`：当前已知数值之和；没有任何已知数据时为 `null`。
- `coverage`：完整覆盖的任务运行数/任务运行分母。
- `source_coverage`：采集文件中的原生观察覆盖；分母未知时 `total=null`。
- `status_counts`：`observed / inferred / partial / masked / unverified / unavailable` 分布。

缓存读取和推理输出可能是输入/输出的子集，报告不把它们再次加到总 Token。

## 单元对比视图（report 0.4.0）

Excel 顺序固定为总览、效率对比、分类对比、难度对比、Agent能力对比、模态对比、工具调用对比、用例明细、资源覆盖与异常。前七张表由 `presentation.tables` 同源渲染到领导版 Markdown。评分展示为百分制，原始 `total_score` 及 CLI adapter 保持 0–1；未知量显示 `-`。

总览无成本、超时数和工具成功率等推断指标；`agent_duration_seconds` 展示为任务耗时，`duration_seconds` 展示为流程耗时，两者均为任务总和，不代替批次墙钟。原生完成数、执行错误数与评分有效性分别统计；评测异常取执行基础设施异常和评分异常任务的并集，取消、未评分和历史 timeout 仍在审计记录保留。

效率表平均 Token 使用全部冻结任务运行作为分母；仅有完整总 Token 时计算，不使用已知小计冒充总量。缓存输入映射 `cache_read_input_tokens`，缓存输出按用户约定指 Cache Write、映射 `cache_creation_input_tokens`，缺少原生字段则为空。缓存命中率使用完整缓存输入总量/完整输入总量，分母 0 或覆盖不全时为空。

七维能力映射随报告 Skill 冻结。自动规则读取被 score.evidence 的 SHA 绑定的 `rule-component.json/raw_scores`，语义读取 `evaluation.criteria`，按检查点命名空间对齐；同题维度内均值再取任务均值。缺失映射检查点的任务不参与该维度，同时保留涉及数和有效数。标准轨迹的工具调用按 task/call ID 去重、按工具名统计，明细与资源总数一致且轨迹完整才标为完整覆盖。均不需要新评分或 Harness 运行。

构建时从公共 `entities.yaml` 和 `checkpoint_capability_map7.yaml` 编译 JSON，独立包无需 YAML 依赖。原始字典、来源 SHA、单元身份与裁判协议保留在分发包、报告 JSON 和审计信息中；不能修改显示名后合并不同 unit。

## CLI 兼容目录

`cli-adapter/units/<unit-id>/<task-id>/` 提供旧流程常见文件名：

- `score.json`
- `usage.json`
- `execution_status.json`
- `task_output.json`

这些文件是显式适配视图，不是原始 CLI 产物。每个文件均带 `wildclawbench.general-e2e-cli-adapter/v1`、来源 SHA 和不补零声明。使用方必须读取 `score_status` 和资源覆盖，不能只凭文件名或 `overall_score` 判断有效性。
