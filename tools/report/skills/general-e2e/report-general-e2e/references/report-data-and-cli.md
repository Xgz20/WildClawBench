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

## 单元对比视图（report 0.5.0）

Excel 顺序固定为总览、效率对比、分类对比、难度对比、Agent能力对比、模态对比、工具调用对比、用例对比明细、各单元评分详情、资源覆盖与异常，共 `9 + unit 数` 张表。前七张表由 `presentation.tables` 同源渲染到领导版 Markdown，使用独立 `presentation.sheet_order` 固定顺序，不依赖 JSON 对象键的序列化顺序。评分展示为百分制，原始 `total_score` 及 CLI adapter 保持 0–1；未知量显示 `-`。

总览无成本、超时数和工具成功率等推断指标；`agent_duration_seconds` 展示为任务耗时，`duration_seconds` 展示为流程耗时，两者均为任务总和，不代替批次墙钟。原生完成数、执行错误数与评分有效性分别统计；评测异常取执行基础设施异常和评分异常任务的并集，取消、未评分和历史 timeout 仍在审计记录保留。

效率表平均 Token 使用全部冻结任务运行作为分母；仅有完整总 Token 时计算，不使用已知小计冒充总量。Token 明细依次为普通输入、缓存命中输入（Cache Read）、缓存写入输入（Cache Write）、输出。普通输入由归一化输入总量减去完整缓存读取、完整缓存写入得到；任一依赖未知时不默认 0，而是空值。两项缓存分别映射 `cache_read_input_tokens`、`cache_creation_input_tokens`。缓存命中率使用完整缓存命中输入总量/含缓存的完整输入总量，分母 0 或覆盖不全时为空。

七维能力映射随报告 Skill 冻结。自动规则读取被 score.evidence 的 SHA 绑定的 `rule-component.json/raw_scores`，语义读取 `evaluation.criteria`，按检查点命名空间对齐；同题维度内均值再取任务均值。缺失映射检查点的任务不参与该维度，同时保留涉及数和有效数。标准轨迹的工具调用按 task/call ID 去重、按工具名统计，明细与资源总数一致且轨迹完整才标为完整覆盖。均不需要新评分或 Harness 运行。

构建时从公共 `entities.yaml` 和 `checkpoint_capability_map7.yaml` 编译 JSON，独立包无需 YAML 依赖。原始字典、来源 SHA、单元身份与裁判协议保留在分发包、报告 JSON 和审计信息中；不能修改显示名后合并不同 unit。

## 与常规用例/评分明细的对应关系

`presentation.case_comparison` 使用每题一行、每单元一列得分的常规布局；前十列名称及顺序保持一致。总分和最大分差使用百分制，检查点使用原始量纲；有至少两个有效单元才比较，缺席/异常不补零，并列最优全部列出。`presentation.score_details` 按单元生成详情表，`score_detail_order` 与 `score_detail_sheet_names` 固定顺序、保留名称映射。

| 常规字段 | General 来源/支持情况 |
| --- | --- |
| 分类、ID、名称、难度、模态 | 冻结 unit manifest，可用 |
| 标签、Prompt、Workspace/Skills/Env/Warmup 声明 | 已选评分 attempt 的冻结 `private/task.md`；核对 attempt 身份、dataset 与 task SHA；不读取运行期 Env 值 |
| 预期行为、评分标准、Automated Checks | 冻结评分 `contract.json`，核对 contract SHA 和 task ID；旧包缺少元数据时显示 `-` |
| 状态、总分、检查点、失分点、裁判判词、执行/评分错误 | execution record、score.criteria、经 SHA 绑定的规则结果；不重新判分，组件总分/诊断计数不作为检查点 |
| 总 Token、请求、工具数、任务/流程耗时 | 已验证资源指标，覆盖不全时未知量不补零 |
| 执行记录(jsonl) | 展示所选回传包 unit 根下的标准 transcript 路径，完整轨迹保留原包，不复制成超长单元格 |
| 超时时间、超时统计 | 本链路不以题目 timeout 控制执行或评分，不加入展示 |
| 多轮数、Std、各轮分数 | 当前 General 为选定 attempt 的单次结果，本版不引入 |
| 结果/根因分析 | 当前未运行根因分析，本版不引入 |
| 工具格式准确率、执行成功率、不确定占比 | 按用户要求暂缓，本版不引入 |

题面及判词等长字段按最多 550 字符/12 行显示有标注节选，全文留在报告 JSON。列宽、冻结前两列、顶端表头和自动换行接近常规报告；对比得分格使用总分背景色，不复刻逐检查点富文本局部着色。不同单元同题的冻结定义或元数据冲突时拒绝生成，不能任选一方填入共享题面列。

## CLI 兼容目录

`cli-adapter/units/<unit-id>/<task-id>/` 提供旧流程常见文件名：

- `score.json`
- `usage.json`
- `execution_status.json`
- `task_output.json`

这些文件是显式适配视图，不是原始 CLI 产物。每个文件均带 `wildclawbench.general-e2e-cli-adapter/v1`、来源 SHA 和不补零声明。使用方必须读取 `score_status` 和资源覆盖，不能只凭文件名或 `overall_score` 判断有效性。
