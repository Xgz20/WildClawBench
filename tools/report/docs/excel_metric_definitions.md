# WildClawBench 评测报告 Excel 指标口径审查

审查对象：`tools/report/scripts/generate_eval_report.py`、各 Harness Runner、`src/utils/tool_metrics.py` 当前实现及本地真实结果（2026-09-04）。Excel 中写入的是计算结果，不是单元格公式。

## 一、结论

1. **总平均分、分类、难度、模态、矩阵和分差的基本公式合理**：任务等权、缺失分按 0，口径简单，能够复算。
2. **工具调用指标不是所有 Harness 都已验证准确**。旧 Codex/AstronCode 结果中的请求数存在确定低估；OpenCode、ClaudeCode、HermesAgent 缺少成功真实样本。
3. **工具调用数存在多种来源**。OpenCode、DeepSeek Harness、HermesAgent 按 `tool_use` 尝试计数；AstronCode 普通工具按 `tool_result`、`tool_search` 按原始 `tool_search_call` 计数；其他 Harness 仍按收到的 `tool_result` 计数。
4. **格式准确率和成功率不能直接跨 Harness 排名**。OpenCode、DeepSeek Harness、HermesAgent 已改为报告侧格式校验，不再由执行状态反推；其他 Harness 仍依赖各自 classifier。
5. **能力分、多轮稳定性和资源效率需要带边界使用**。仍存在去污染名称不准、多轮字段混用、实际样本数不透明等问题。
6. **总分可用的前提**：各 unit 使用同一任务集合，评测有效性检查通过。否则分数差可能来自缺任务或评测异常，不是模型或 Harness 能力差。

## 二、公共口径

| 项目 | 口径 | 判断 |
|---|---|---|
| unit | 一个 `模型@Harness` 组合 | 合理，是报告的最小横向比较单元 |
| 用例原始分 | `score.json.overall_score`，范围通常为 0~1 | 合理，可直接对账原始结果 |
| 聚合分 | `100 × 算术平均(用例分)` | 合理，但默认每题等权 |
| 缺失分 | 聚合时按 0；用例明细仍显示 `-` | 作为保守口径可以接受，但必须保证所有 unit 任务集合一致 |
| 多轮用例分 | 所有有效 run 的 `overall_score` 算术平均 | 分数本身合理；其余字段仍取最新 run，存在混用 |
| 百分数 | 聚合 Sheet 存 0~100 数值并显示 `%`；详情 Sheet 保留 0~1 | 合理，但“分差”单位应称百分点 |

源码：[`effective_score` 与聚合公式](../scripts/generate_eval_report.py#L378)、[多轮分数与最新轮字段](../scripts/generate_eval_report.py#L274)。

## 三、按 Sheet 说明

### 1. 总览

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 总平均分 | `100 × Σ effective_score / 用例数`；缺失分按 0 | 合理；任务集合不同则不可直接比较 |
| 用例数 | unit 实际加载的任务目录数 | 合理；应与 validity 中的预期任务数对账 |
| 正常完成数 | `outcome == finished` | 合理 |
| 执行错误数 | 模型或 Harness 归因的执行错误数 | 合理；环境、框架、外部服务和未定责错误不在此列 |
| 超时数 | 最新 run 标记为超时，且未先归为评测异常 | 合理；四种状态互斥 |
| 评测异常数 | 判分错误，或环境、框架、外部服务、未定责异常 | 合理，避免把评测侧故障算作模型能力失败 |
| 完成率 | `正常完成数 / 用例数 × 100%` | 合理；不是“有分率”或“无异常率” |
| 平均轮数 | 对 `runs > 0` 的任务计算 `Σ有效得分轮数 / 任务数` | 可用；只统计产出有效分的 run |
| 总tokens | 各任务最新 run 的 `usage.json.total_tokens` 之和 | 名称过宽；仅被测模型推理 token，不含裁判和工具侧消耗 |
| 总请求数 | 各任务最新 run 的 `usage.json.request_count` 之和；具体计数事件由 Harness Runner 决定 | 名称过宽；不是统一采集口径，多轮时也不是全轮总数 |
| 总耗时(s) | 各任务最新 run 的 `usage.json.elapsed_time` 之和 | 不等于完整评测墙钟时间；与详情 Sheet 的耗时来源不同 |
| 总成本(USD) | 有 registry 和 `pricing_date` 时重算各任务最新 run 的推理成本；否则读取 `usage.json.cost_usd`，仅 `cost_status=unavailable` 明确记为不可估；任一任务不可估算则整项为 `-` | 未标 `unavailable` 且缺少 `cost_usd` 时会回退为 0；不含裁判、搜索、工具和外部 API 成本 |
| 平均首 Token 响应时间 | 未被执行状态显式判为失败、超时或取消，且 `usage.json.time_to_first_token_ms` 有效的未被替代 run 算术平均 | Judge 异常但执行未失败的 run 仍可能计入；缺失值不按 0 计 |
| 首 Token 响应时间 P50/P90 | 同一有效样本集合的线性插值第 50/90 百分位 | 是 AstronCode Core 收到首个有效模型事件的时间，不等于客户端首次可见上屏 |
| 首 Token 指标覆盖率 | `有效首响样本数 / 未被替代 run 总数 × 100%` | 旧镜像缺字段和显式执行失败会降低覆盖率；Judge 异常不一定被排除 |
| 首 Token 响应有效样本数 | 参与平均值及分位数计算的 run 数 | 与覆盖率一起展示，避免低覆盖率统计被误用 |
| 工具调用数 | OpenCode、DeepSeek Harness、HermesAgent 按最新 run 的 `tool_use` 尝试数；AstronCode 普通工具按 `tool_result`、`tool_search` 按原始 `tool_search_call`；其他 Harness 按 `tool_result` 数 | AstronCode 不再漏掉独立协议的 `tool_search`；其余按结果计数的 Harness 仍可能漏掉无结果尝试 |
| 格式准确率 | `(total - format_error) / total` | 公式清楚；不同 Harness 的分类能力不同，不宜跨 Harness 排名 |
| 执行成功率 | `success / (success + failure)` | 合理；排除 `unclear` 和 `format_error` |
| 不确定占比 | `unclear / total` | 合理，建议与执行成功率同时看 |
| 检索命中率 | `tool_search` 参数有效且返回非空 `tools` 的次数 / 参数有效、输出存在且 `tools` 可判定的次数 | 只在“工具调用对比”Sheet 展示；空列表通常表示未命中，但 AstronCode 的中止响应也会写成 `completed + []`，该极端情况无法仅靠现有轨迹区分 |

ClaudeCode 的 `request_count` 优先读取显式 `model_request`、`query_start` 或 `modelUsage.requestCount`；官方 `stream-json` 未提供这些字段时，按唯一 assistant `message.id` 统计模型响应次数，不使用包含工具轮次的 `result.num_turns`。其他 Harness 的请求数来源见“工具调用对比”。

四态分类见 [`classify_report_outcome`](../../../src/utils/anomalies.py#L432)；总览写表见 [`write_overview_sheet`](../scripts/generate_eval_report.py#L1133)。

成本公式：

```text
(未缓存输入 token × 未缓存输入单价
 + 缓存输入 token × 缓存输入单价
 + 缓存写入 token × 缓存写入单价
 + 输出 token × 输出单价) / 定价单位 token
```

CNY 定价再除以定价日 `CNY/USD`；分档模型按逐请求输入 token 选档。源码见 [`report_entities.py`](../scripts/report_entities.py#L272)。

### 2. 分类对比、难度对比、模态对比

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 总平均分 | 与总览一致 | 合理 |
| `<分组>平均分(N例)` | `100 × unit 在该组实际存在任务的 effective_score 均值` | 公式合理；表头 `N` 来自所有 unit 的任务并集，不一定是该行实际样本数 |
| 分类 | 任务所属 suite | 合理 |
| 难度、模态 | 任务 Markdown 元数据 | 合理；依赖元数据完整、准确 |
| 固定 Harness：模型对比 | 从主表筛出同一 Harness，不重新计算 | 合理的控制变量视图 |
| 固定模型：Harness 对比 | 从主表筛出同一模型，不重新计算 | 合理的控制变量视图 |

公式见 [`write_dimension_sheet_transposed`](../scripts/generate_eval_report.py#L2188)，控制变量视图见 [`append_controlled_views`](../scripts/generate_eval_report.py#L1027)。

### 3. Agent能力对比

七维：代码生成、工具调用、数据处理、检索验证、推理规划、内容生成、验证交付。

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 维度分 | 检查点归一化 → 任务内映射检查点均值 → 跨任务等权均值 → `×100` | 方法可解释，但结果受映射键数量和覆盖率影响，不是独立量表 |
| 检查点归一化 | 0~1 直接使用；`X_earned / X_max`；诊断计数键排除 | 合理 |
| 涉及用例数 | 该 unit、该维度实际产生有效能力分的任务数；写在批注中 | 合理，但应直接展示，不能只放批注 |
| 模型强项 | 涉及任务数不少于 5 的维度中取 Top 3 | 仅作相对描述；不同维度题集不同 |
| 模型短板 | 同一集合中取 Bottom 3 | 仅作相对描述；候选维度为 5 个时会与强项重叠 |

**单分制任务口径**：即使 `checkpoints` 为空，只要任务存在有效 `overall_score` 且映射文件显式引用该键，仍会进入对应能力维度；不会再因缺少检查点明细而被跳过。

**重复计权边界**：已有组成项进入映射时，其 `classify_score`、`metadata_score`、`points_earned` 等汇总项不再映射；单分制任务仅使用 `overall_score`。不同能力维度仍基于各自实际覆盖的任务和检查点，不是可互换的独立量表。

### 4. Agent能力对比·去污染

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 数据处理、推理规划、内容生成·去落盘污染 | 沿用能力分公式；若任务存在文件类检查点且其均值 `<0.5`，排除该任务 | 名称与实现不一致 |

文件类检查点按键名包含 `exist/created/saved/written/parseable` 识别。**没有文件类检查点的任务仍被保留**，因此该 Sheet 不是“仅产物落盘成功的用例”。批注中的该表述不成立。源码见 [`FILE_CKPT_RE` 与筛选条件](../scripts/generate_eval_report.py#L143)、[批注](../scripts/generate_eval_report.py#L1467)。

### 5. 多轮稳定性分析

仅存在至少一个多轮任务时生成。成功阈值默认 `overall_score >= 0.99`，可由 CLI 覆盖。

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 轮数 | unit 多轮任务中的最大有效轮数 | 名称不准确；任务轮数不一致时不能代表全部任务 |
| 多轮题数 | `runs > 1` 的任务数 | 合理 |
| mean | 各有效轮得分算术平均 | 合理 |
| Std | `pstdev(各轮分数)`，总体标准差 | 适合描述已跑轮次，不是总体不确定性估计 |
| 高抖题数 | `Std > 0.15` 的多轮任务数 | 阈值是经验规则，需对外声明 |
| 不稳定率 | `高抖题数 / 多轮题数` | 合理 |
| pass@k | `1 - C(n-c,k)/C(n,k)` | 公式正确，但当前固定 `k=n`，退化为“是否至少一轮通过” |
| pass^k | `C(c,k)/C(n,k)` | 公式正确，但当前固定 `k=n`，退化为“是否全部轮通过” |
| 能力上界优秀率 | `pass@k >= 0.95` 的题数 / 多轮题数 | 当前实际等于“至少一轮通过的题占比” |
| 可靠性优秀率 | `pass^k >= 0.8` 的题数 / 多轮题数 | 当前实际等于“全部轮通过的题占比” |
| 各分布 | 按固定区间统计题数和占比 | 展示分布比平均 Std 更合理；pass 指标仍是二元值 |
| 高抖题明细 | 列出 `Std > 0.15` 的任务、各轮分数和上述指标 | 合理 |

公式见 [`multirun_stats.py`](../../../src/utils/multirun_stats.py#L15)，写表逻辑见 [`write_stability_sheet`](../scripts/generate_eval_report.py#L2559)。当前“概率”“能力上界”“可靠性下界”的措辞过强。

### 6. 模型×Harness矩阵

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 单元格得分 | 对应 `模型@Harness` 的总平均分 | 合理 |
| 缺失组合 | 显示 `-` | 合理 |
| 排序 | 模型按其最佳 Harness 分降序；Harness 按列均分降序 | 仅影响展示，不影响分数 |

源码见 [`write_matrix_sheet`](../scripts/generate_eval_report.py#L1241)。

### 7. 工具调用对比

按 Harness 分块，每个模型先列全部工具，再按调用数降序列单工具。

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 调用数 | OpenCode、DeepSeek Harness、HermesAgent 按 `tool_use` 尝试数；其他 Harness 按 `tool_result` 数 | 三类 Harness 的无结果尝试进入“不确定”；其他 Harness 仍可能漏计 |
| 成功、失败、格式错误、不确定 | 三类 Harness 先做报告侧格式校验，再对已返回结果使用原 classifier；其他 Harness 直接使用 classifier | 分类规则仍不是跨 Harness 同一把尺 |
| 成功率 | `success / total` | 与总览“执行成功率”的分母不同 |
| 格式准确率 | `(total - format_error) / total` | 三类 Harness 按调用尝试校验；存在无法判定格式的调用时显示 `-`，不猜测为 100% |
| 检索命中率（tool_search） | `search_hit / (search_hit + search_miss)` | 仅 AstronCode 原始 `tool_search_output.tools` 可判定时有值；非法参数和缺输出不进分母，其他工具显示 `-` |

总览“执行成功率”=`success/(success+failure)`；本 Sheet“成功率”=`success/total`。前者排除格式错误和不确定结果，后者是综合成功率。同一报告中名称接近、分母不同，容易误读。

核验样本为 `wcb-output` 下 44 个 run，加 `output/codex` 下 3 个 run及 `output/astroncode` 下 2 个含 `tool_search` 的 run。该范围是当前本地证据，不代表生产全量。本次变更后，工具指标 39 项、工具 Sheet 1 项、报告流水线 75 项全部通过；真实 DeepSeek Harness 单 unit Excel 生成及独立审核为 PASS。

#### 分 Harness 请求数和工具状态口径

| Harness | 请求数来源 | 工具状态来源 | 真实样本核验 | 结论 |
|---|---|---|---|---|
| Codex | 去重后的 `token_count` 事件；旧格式回退逐轮用量或 assistant 消息 | `tool_result.content` 的固定文本标记 | 本地 3 个 run、29 次工具调用全部配对；2 个旧 run 的请求数分别为 `5→8`、`3→21`，另 1 个一致 | 当前事件格式下可复算；异常请求或无 token 请求仍可能漏计，旧结果需重解析 |
| AstronCode | 去重后的 `token_count` 事件；旧格式回退逐轮用量或 assistant 消息 | 普通工具使用结构化状态及返回契约；`tool_search` 读取原始 call/output 状态 | 原有 477 次配对结论只覆盖归一化普通工具；另有 2 个本地 run 共 3 次参数有效的 `completed + []`，当前口径计成功未命中，调用数分别由 29→31、6→7 | 当前报告可复算 `tool_search` 调用和非空返回率；中止也可能编码为 `completed + []`，空结果存在无法消除的歧义；无 token 请求仍可能漏计 |
| OpenCode | SQLite 中 `type=step-finish` 的记录数 | 执行状态用 `state.status`；格式按 `tool_use` 参数结构和明确拒绝结果校验 | 本地 3 个 run 均在 warmup、鉴权或模型请求阶段失败，请求数和工具数均为 0 | 只有代码和单元测试证据；未产生 `step-finish` 的失败请求不计；无结果且格式不可判定时显示 `-` |
| OpenClaw / AstronClaw | 归一化轨迹中的 assistant 消息数 | 原生 `details.status`，有限错误文本识别格式错误 | OpenClaw 2 个 run 的请求数为 11、10；21 次工具调用中成功 18、失败 2、不确定 1。AstronClaw 唯一样本是异常 run，只有 1 次请求、无工具调用 | OpenClaw 小样本可复算；AstronClaw 正常链路待验证；assistant 消息无稳定请求 ID，格式错误也可能漏判 |
| DeepSeek Harness | 带 usage 的 `assistant/message` 事件数 | 执行状态用原生 `tool_result.status`；格式按 `request/header.tools` 的实际 Schema 校验原始 `tool/call` | 1 个 run：6 次请求、7 次工具调用，7 次均为 `completed`；新口径复算格式准确率为 100% | 当前成功样本一致；仍缺少真实非法参数和未知工具样本 |
| HermesAgent | 优先 assistant 消息；回退 API 响应日志或 session assistant 消息 | 执行状态用结果 JSON 的 `status/success`；格式校验原始参数结构和明确拒绝结果 | 无本地真实 run | 待确认；无稳定请求 ID；无结果且格式不可判定时显示 `-` |
| ClaudeCode | `model_request`、`query_start`、`modelUsage.requestCount`，最后按唯一 assistant message ID 回退 | 优先 `tool_result.is_error`，再匹配有限格式错误文本 | 无本地真实 run | 待确认；回退口径统计响应消息，不能证明包含异常或无响应请求 |

#### 已确认问题

1. `wcb-output/reports/4/report.xlsx` 的总请求数是 116；按当前权威事件重算应为 203。该报告的工具调用数 202、成功 176、失败 6、格式错误 1、不确定 19，以及 99.5%/96.7%/9.4% 三项比例均可复算一致。
2. 旧报告中的 AstronCode `tool_search` 没有进入归一化轨迹，存在确定漏算；新报告已从原始 `chat.jsonl` 补计。OpenCode、DeepSeek Harness、HermesAgent 按 `tool_use` 尝试计数；`total=0` 仍无法区分“确实未调用”“轨迹缺失”和“轨迹解析失败”。
3. OpenCode、DeepSeek Harness、HermesAgent 的 classifier 本身仍不产生 `format_error`，但新报告已增加独立格式校验。OpenClaw、ClaudeCode 仍只匹配有限错误文本，跨 Harness 排名仍不成立。
4. AstronCode 把 approval policy 拒绝也归为 `format_error`，这不是纯粹的工具名或参数格式错误，会混入运行策略限制。
5. `reparse_codex_usage.py` 曾未按 Harness 过滤：对 DeepSeek Harness 或 ClaudeCode 结果目录 dry-run，会把请求数错误建议为 `6→0`、`109→0`。现已强制读取 `execution_status.harness`，只处理 Codex/AstronCode；其他 Harness、缺失或损坏的状态文件均安全跳过。即使 Harness 匹配，只要重解析 token 与原记录漂移，也不会推断或写回请求数。
6. 多轮任务只取最新有效 run 的请求数和工具指标，不是多轮总量，也不是轮均值。

OpenCode 的 `completed` 一律记为成功，包括业务错误 JSON；`running/pending` 记为不确定。ClaudeCode 优先使用归一化轨迹保留的 `tool_result.is_error`；命令成功返回业务错误 JSON 仍记为工具执行成功。工具指标适合单 Harness 内诊断，不适合直接跨 Harness 排名。源码见 [`tool_result` 配对](../../../src/utils/tool_metrics.py#L98)、[OpenCode 分类](../../../src/utils/tool_metrics.py#L697)、[报告侧格式校验](../../../src/utils/tool_metrics.py#L878)、[派生比率](../../../src/utils/tool_metrics.py#L949)。

指定设计文档 `docs/local/design/Harness工具调用指标设计.md` 是历史方案，不是当前实现状态：文档仍写“尚未编码”和只支持 3 类 Harness，当前代码已注册 7 类。文档示例中的“不确定占比”写成 `683/4145=16.5%`，与正文公式 `unclear/total` 冲突；按正文应为 `683/6071=11.25%`。

#### 工具指标修正状态

本次已实现：OpenCode、DeepSeek Harness、HermesAgent 仅在生成报告时按调用尝试计算格式准确率；DeepSeek Harness 使用会话内实际工具 Schema；AstronCode 报告从原始轨迹补计 `tool_search`，并在“工具调用对比”Sheet 展示检索命中率。明确非法参数、未知工具和拒绝结果计格式错误；格式无法判定时显示 `-`。`reparse_codex_usage.py` 也已增加 Harness 白名单和混合目录保护。上述改动不修改 Harness、执行流程或评分；报告指标计算只读结果目录，历史 usage 回填仍必须显式传入 `--apply`。按要求，Excel 和领导版报告不增加轨迹覆盖状态字段。

其余改造仍为建议：

| 优先级 | 改动 | 验收口径 |
|---|---|---|
| P0 | 每个 Runner 写入 `request_count_source` 和 `request_count_status=observed/estimated/unavailable`；只在存在稳定请求 ID 或原生请求计数时标为 `observed` | 报告不再把 assistant 消息数、`step-finish` 数或 token 事件数无条件展示为精确请求数 |
| P0 | 同时统计 `tool_use_total`、`tool_result_total`、`matched_count`、`missing_result_count`、`orphan_result_count`、`duplicate_result_count` | `tool_use_total = matched_count + missing_result_count`，`tool_result_total` 可与原始轨迹逐条对账 |
| P0 | 内部审计区分 `no_calls/missing_transcript/parse_error`，不写入 Excel 或领导版报告 | `0` 只表示已确认没有调用；轨迹缺失和解析失败时相关比率显示 `-` |
| P0 | 从 Harness 调度层保存工具调用是否被接受及拒绝原因；仅 `unsupported_tool`、`invalid_arguments` 计格式错误，`policy_denied` 单列 | 无法捕获拒绝事件的 Harness，格式准确率显示 `-`，不显示 100% |
| P0 | 报告生成前增加请求数对账 | 旧 Codex/AstronCode 结果完成显式回填后，重生成报告的请求数与权威事件一致 |
| P1 | 工具执行状态优先使用原生 `completed/error/running/pending`；文本推断仅作 fallback，并记录 `classification_source` | HermesAgent 无状态非空结果不再直接判成功；可统计 fallback 占比 |
| P1 | 多轮报告同时展示全轮总量、轮均值和最新轮快照，停止把最新轮工具量与多轮平均分并列为同一口径 | 每个资源指标明确 `all_runs/latest_run/per_run_avg`，三者可相互复算 |
| P1 | 元数据记录 classifier 版本；为 OpenCode、AstronClaw、ClaudeCode、HermesAgent 补正常与异常真实样本 | 每个 Harness 至少覆盖成功、执行失败、格式拒绝、超时/中断四类样本；未覆盖项标为待确认 |

### 8. 站点评测指标、_站点评测指标口径

仅存在 `web-site-gen` 任务时生成。

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 得分率 | Web 任务 `effective_score` 按任务等权平均 | 合理；缺失分按 0 |
| 满分率 | `overall_score == 1.0` 的任务数 / Web 任务数 | 是严格满分率，不是完成率 |
| L1/L2 题目得分率 | 对应难度任务按任务等权平均 | 合理；需同时看样本数 |
| 三个一级维度 | 内容与结构、交互与功能、视觉与布局的任务级分数等权平均 | 不同证据模式不能混为同一种测量：`source_semantic` 只证源码，`browser_runtime+visual_llm` 才含运行与视觉证据 |
| 运行耗时平均/P50/P90 | 所有未被替代 run 的 `execution_status.elapsed_time` | 多轮按 run 统计，与总览最新 run 总量口径不同 |
| 首 Token 指标 | 与总览相同，排除执行状态显式失败、超时、取消及缺字段 run | Judge 异常但执行未失败的 run 仍可能计入；必须同时展示覆盖率和样本数 |
| 单次运行平均成本 | 有 registry 和 `pricing_date` 时逐 run 重算，否则读取 `usage.json.cost_usd`；任一应估 run 不可估则显示 `-` | 回退口径仍存在“缺值但未标 unavailable 时按 0”问题 |
| 单次运行平均 Token | 未被替代 run 的对应 token 算术平均 | 只含被测模型推理 token |
| 一级/二级维度汇总 | 先计算任务内维度分，再跨任务等权平均 | 合理；二级维度样本集合可能不同 |

隐藏 Sheet `_站点评测指标口径` 按 unit、指标记录单位、样本数和计算方法，用于对账，不参与评分。源码见 [`_website_unit_metrics`](../scripts/generate_eval_report.py#L1648) 和 [`write_website_metrics_sheet`](../scripts/generate_eval_report.py#L1947)。

### 9. 评测契约一致性

按任务列出 `execution_contract_sha256`、`scoring_contract_sha256`、`task_sha256` 的版本数和缺失数。执行或评分契约不一致只给提示，不改变分数，也不阻断报告；`task_sha256` 仅用于追溯。该 Sheet 能暴露混用版本，但不能替代正式 validity 门禁。源码见 [`write_provenance_consistency_sheet`](../scripts/generate_eval_report.py#L2336)。

### 10. 用例对比明细

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 每 unit 得分 | 原始 0~1 分；多轮时为有效轮均分 | 分数可比，但检查点明细只来自最新 run |
| 检查点 | 任务定义键与实测键并集；单元格展示最新 run 检查点值 | 合理用于追溯单轮；不能解释多轮均分 |
| 最优单元 | 仅在非空得分中取最大值 | 与总览“缺失分按 0”不一致 |
| 最大分差 | 非空得分的 `max - min`；少于两个有效分显示 `-` | 与总览口径不一致；单位为 0~1 原始分 |

源码见 [`write_case_compare_sheet`](../scripts/generate_eval_report.py#L1312)。

### 11. 分差矩阵

| 指标 | 计算口径 | 判断与边界 |
|---|---|---|
| 行 unit - 列 unit | `行总平均分 - 列总平均分` | 合理；单位是百分点，不是百分比 |
| 对角线 | 0 | 合理 |

源码见 [`write_diff_matrix_sheet`](../scripts/generate_eval_report.py#L2321)。

### 12. 评分详情_&lt;unit&gt;

| 字段组 | 来源或计算口径 | 判断与边界 |
|---|---|---|
| 分类、名称、难度、超时、模态、Prompt、预期、评分标准、Automated Checks、Workspace、Skills、Env、Warmup | 任务 Markdown | 原始定义信息，不是指标 |
| 状态 | 最新 run 的原始 `execution_status.status`，超时则追加标记 | 与总览使用的四态 `outcome` 不是同一字段，可能无法直接对账 |
| 总得分 | 单轮原始分；多轮为有效轮均分 | 合理 |
| 轮数、Std、各轮分数 | 多轮口径同稳定性 Sheet | 合理 |
| 检查点、失分点、裁判判词、执行错误 | 最新 run 的 `score.json` 和 `execution_status.json` | 多轮时不能直接解释均分 |
| 总tokens、请求数 | 最新 run 的 `usage.json` | 不是多轮总量或轮均值 |
| 耗时 | 最新 run 的 `execution_status.json.elapsed_time` | 总览取 `usage.json.elapsed_time`，来源不一致 |
| 执行记录 | 最新 run 的轨迹原文 | 合理，但内容可能很长 |
| 结果分析、根因分析 | 外部分析 JSON 回填 | 不是生成器计算指标 |
| 四项工具指标 | 最新 run，公式同总览 | 口径边界同工具调用对比 |

Sheet 名按 Excel 31 字符限制直接截断。长 unit 可能名称冲突，隐藏元数据也未记录 unit 与详情 Sheet 的映射。源码见 [`write_detail_sheet`](../scripts/generate_eval_report.py#L2603)。

### 13. _报告元数据（隐藏）

记录模型、Harness、unit 的原始 ID 与展示名，成本定价档案、成本状态和失败原因，实体配置版本、定价日、汇率及目标 unit。**不参与评分计算**，用于追溯和复算，设计合理。

不足：未记录报告生成器版本、Git commit、任务集摘要、pass 阈值、能力映射摘要、详情 Sheet 名映射。源码见 [`write_report_metadata_sheet`](../scripts/generate_eval_report.py#L2399)。

## 四、问题清单

### 高优先级：对外评审前应修正

| 问题 | 事实 | 影响 |
|---|---|---|
| 去污染口径名实不符 | 仅排除“存在文件检查点且均值低于 0.5”的任务 | 无文件检查点任务仍保留，不能声称“仅落盘成功” |
| 多轮字段混用 | 分数取全轮均值；状态、检查点、资源、成本、工具和判词取最新轮 | 同一行字段不属于同一统计对象，容易产生错误归因 |
| 分组样本数不透明 | 表头 N 取任务并集；每行按该 unit 实际任务计算 | 缺任务的 unit 可能用更小样本得到更高或更低均值 |
| 缺失分处理不一致 | 聚合按 0；最优单元和最大分差排除空值 | 总览与用例比较无法严格对账 |
| 历史请求数未自动修复 | 报告直接读取 `usage.json.request_count` | 旧 Codex/AstronCode 报告会保留 Runner 已修复前的低估值 |
| 工具数据缺失不可辨 | `total=0` 同时表示无调用、无轨迹或解析失败 | 0 次调用无法作为确定事实对外解释 |

### 中优先级：需改名、披露或限制用途

| 问题 | 处理建议 |
|---|---|
| `pass@k/pass^k` 固定 `k=n` 后退化为二元值 | 改名为“至少一次满分率/全轮满分率”，或使用固定且小于 n 的 k |
| token、请求、耗时、成本名称过宽 | 改为“被测模型推理 token/请求/执行耗时/估算推理成本”，注明最新轮 |
| 未传 `--pricing-date` 时缺失成本回退为 0 | 缺失应显示 `-`，不能把未知当零成本 |
| 成本任一任务缺失则整项为 `-` | 同时展示已估算成本、可估算任务数和总任务数 |
| 工具指标跨 Harness 不同尺 | 仅做 Harness 内比较；对外表中披露 classifier 版本和未配对调用数 |
| 两种“成功率”分母不同 | 明确改名为“综合成功率”和“已执行调用成功率” |
| 强项与短板可能重叠 | 候选维度不足 6 个时减少 Top/Bottom 数量 |
| 总览和详情耗时来源不同 | 统一来源并增加自动对账 |
| 总览四态与详情原始状态不同 | 详情增加“报告状态(outcome)”列 |
| 详情 Sheet 名可能冲突 | 生成唯一短名，并在元数据记录映射 |

### 解释边界

- 1~2 例分组的均值没有代表性；报告未给置信区间。
- `pstdev` 只描述已跑轮次，不支持推断未来运行波动。
- 当前审核脚本主要复算生成器定义，无法发现生成器与审核器共享的设计问题。
- 分数差必须写“百分点差”；用例详情中的 0~1 差值除外。

## 五、对外发布条件

1. 修正高优先级问题，并为每个分组、每个 unit 直接展示实际样本数。
2. 多轮报告统一为“全轮汇总”或“最新轮快照”，不能在同一行混用；资源建议同时给总量和轮均值。
3. 能力分发布前冻结映射版本，保持汇总项与组成项不重复计权，并输出维度覆盖任务清单。
4. 历史 Codex/AstronCode 结果先独立重算请求数；对当前报告执行请求数与原始事件对账。
5. 工具指标限制为同 Harness 比较；跨 Harness 仅展示原始计数、分类规则和无法判定时的 `-`，不做排名；不在 Excel 或领导版报告新增轨迹覆盖状态。
6. OpenCode、ClaudeCode、HermesAgent 在取得正常真实 run 前，工具指标标为“仅代码验证”或“待确认”。
7. 元数据补充代码版本、任务集摘要、pass 阈值、能力映射摘要、classifier 版本和详情 Sheet 映射，保证报告可复现。
