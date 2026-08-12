# Web 站点评测报告指标补齐设计

## 1. 目标与范围

在现有 Excel `站点评测指标` Sheet 中补齐网站生成评测集的结果、分层和效率指标，并让领导版数据与 Markdown 报告使用同一统计结果。

本次不计算“美观度”，不改变通用 `总览` Sheet 的列结构，也不引入站点启动、浏览器渲染或动态点击测试。非 Web 任务以及未来 PPT、图片生成等其他 `metric_profile` 不进入本次指标统计。

## 2. 识别范围

仅统计 `score.json._dimensions` 同时满足以下条件的任务：

- `metric_profile == "web-site-gen"`
- `evidence_mode == "source_semantic"`

任务得分和分层指标以任务为统计单位；效率指标以这些任务下未被替代的实际 run 为统计单位。任务已经通过 frontmatter `web-site-gen` tag 识别、但因执行或评分异常没有 `score.json._dimensions` 时仍属于 Web 范围，得分按框架 `effective_score=0` 纳入分母。run 选择统一复用 `src/utils/run_selection.py::select_effective_run_dirs()`，确保 `run_metadata.json.supersedes_run` 指向的旧 run 不再参与报告。

## 3. Excel 展示

在 `站点评测指标` Sheet 顶部说明之后、现有一级维度汇总之前，新增“结果与效率指标汇总”区域。每个参评 `模型@Harness` 分别输出一组指标，列为：

| 指标分类 | 指标名称 | 数值 | 样本数 | 计算方法 |
|---|---|---:|---:|---|
| 结果指标 | 得分率 | 百分比 | Web 任务数 | 各任务 `overall_score` 按任务等权平均 |
| 结果指标 | 满分率 | 百分比 | Web 任务数 | `overall_score == 1.0` 的任务数 / Web 任务数 |
| 分层分析 | L1 题目得分率 | 百分比或 `-` | L1 任务数 | 按任务 frontmatter `difficulty=L1` 分组后等权平均 |
| 分层分析 | L2 题目得分率 | 百分比或 `-` | L2 任务数 | 按任务 frontmatter `difficulty=L2` 分组后等权平均 |
| 分层分析 | 内容与结构得分率 | 百分比 | 有该维度的任务数 | `_dimensions.primary.content_structure.score` 等权平均 |
| 分层分析 | 交互与功能得分率 | 百分比 | 有该维度的任务数 | `_dimensions.primary.interaction_function.score` 等权平均 |
| 分层分析 | 视觉与布局得分率 | 百分比 | 有该维度的任务数 | `_dimensions.primary.visual_layout.score` 等权平均 |
| 效率指标 | 运行耗时平均值 | 秒 | 有耗时的 run 数 | run 的 `execution_status.json.elapsed_time` 算术平均 |
| 效率指标 | 运行耗时 P50 | 秒 | 有耗时的 run 数 | run 耗时的第 50 百分位 |
| 效率指标 | 运行耗时 P90 | 秒 | 有耗时的 run 数 | run 耗时的第 90 百分位 |
| 效率指标 | 单次运行平均成本 | USD | 成本可计算的 run 数 | 按 `tools/report/data/entities.yaml` 中模型在定价日期有效的单价逐 run 复算后求平均 |
| 效率指标 | 单次运行平均总 Token | Token | 有 usage 的 run 数 | 各 run `total_tokens` 算术平均 |
| 效率指标 | 单次运行平均输入 Token | Token | 有 usage 的 run 数 | 各 run `input_tokens` 算术平均 |
| 效率指标 | 单次运行平均输出 Token | Token | 有 usage 的 run 数 | 各 run `output_tokens` 算术平均 |

“满分”严格表示原始比例分 `overall_score == 1.0`，即报告百分制的 100 分，不复用可配置的 pass threshold。

耗时口径包含通过、失败和无效运行，只要 run 未被替代且 `elapsed_time` 是有效数值。Token 指标只纳入对应字段为有效数值的 run，并显示实际样本数；缺失字段不按 0 计算。

P50/P90 使用与 Python `statistics.quantiles` 无关的确定性线性插值百分位算法，使单样本、少量样本和跨 Python 版本结果稳定。

## 4. 运行级数据与成本

现有 `TaskRecord` 的 `usage`、`elapsed` 和 `cost_estimate` 只对应展示用最新 run，不能直接用于多轮效率统计。新增独立的运行级记录或聚合辅助函数，对每个 Web 任务重新取得有效 run，并读取：

- `execution_status.json`
- `usage.json`
- 当前 run 目录中的逐请求 Token 证据

成本必须逐 run 复用现有 `report_entities` 定价与分档计费逻辑：

- 定价来源是 `tools/report/data/entities.yaml`；
- 使用命令传入的 `--pricing-date` 选择生效价格；
- 单档价格按 run usage 计算；
- 分档价格按该 run 的逐请求输入 Token 计算；
- 缺价格、缺逐请求证据或 token 语义不明确时，该组合平均成本显示 `-`，并保留不可用原因，不能按 0 处理。

为了避免“只平均可定价 run”造成误导，只有全部纳入效率统计且存在 usage 的 run 都能完成成本复算时，才展示单次运行平均成本；否则显示 `-`，样本数同时标示为 `可计算数/应计算数`。

## 5. 领导版报告同步

`extract_leader_report_data.py` 从 `站点评测指标` 的固定标题和表头提取结构化 `website_metrics`，只在该 Sheet 存在时输出有效数据；非 Web 报告返回空结构或不含 Web 指标，不影响现有维度数据。

领导版 Markdown 在存在 `website_metrics` 时增加“站点评测指标”章节，数字全部来自 leader data JSON。章节展示结果指标、L1/L2 与三个一级能力维度、耗时和成本/Token；不展示“美观度”。无 Web 指标时整节省略。

## 6. 兼容性与异常处理

- 不修改 `总览` Sheet 的既有表头、顺序和计算逻辑。
- 不改变现有一级维度、二级维度和逐任务明细区域的含义。
- 非 Web 任务不参与 Web 汇总；混合评测报告中 Web Sheet 只反映 Web 子集。
- 某个分组或指标无样本时显示 `-` 和样本数 0，不制造 0 分或 0 成本。
- 被替代 run 不参与得分、耗时、成本或 Token 统计。
- 失败或无效 Web 任务若缺少 score，按 0 分进入得分率、满分率和 L1/L2 分母；其有效耗时和 usage 同时进入效率指标。

## 7. 验证

增加自动化测试覆盖：

1. 得分率、严格满分率以及 L1/L2 分组。
2. 三个一级能力维度聚合，且不生成“美观度”。
3. 平均耗时、P50、P90 的单样本和多样本结果。
4. 平均总 Token、输入 Token、输出 Token。
5. 基于 `entities.yaml` 的逐 run 成本复算及成本不可用分支。
6. 多轮 run 全部计入，被 `supersedes_run` 替代的 run 排除。
7. 失败或无效 run 进入效率指标但不制造得分。
8. 非 Web 报告的 Sheet 与原有表头保持不变。
9. leader data 和 Markdown 的 Web 指标与 Excel 一致。

最后使用 round1 的 `GLM-5.2@AstronCode` 数据重新生成 Excel、leader data 和领导版 Markdown，执行有效性门禁、报告审计以及工作簿公式错误扫描。
