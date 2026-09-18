# 报告数据与 CLI 适配

## 报告数据

`general_e2e_report_data.json` 使用 `wildclawbench.general-e2e-report-data/v1`。顶层包含：

- `scope`：唯一任务数、任务运行数、unit 数和冻结任务 ID。
- `overall`：有效评分、分类、难度、裁判分组、资源和耗时。
- `units`：每个 unit 使用相同口径的聚合。
- `tasks`：逐任务运行的执行、评分、资源与 lineage。
- `lineage`：批次 manifest、报告配置、导入选择和每个已选 package 的 SHA。

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

## CLI 兼容目录

`cli-adapter/units/<unit-id>/<task-id>/` 提供旧流程常见文件名：

- `score.json`
- `usage.json`
- `execution_status.json`
- `task_output.json`

这些文件是显式适配视图，不是原始 CLI 产物。每个文件均带 `wildclawbench.general-e2e-cli-adapter/v1`、来源 SHA 和不补零声明。使用方必须读取 `score_status` 和资源覆盖，不能只凭文件名或 `overall_score` 判断有效性。
