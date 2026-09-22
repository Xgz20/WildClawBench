---
name: report-general-e2e
description: 校验并汇总 General E2E submission 和回传包，生成同源 JSON、Markdown 与 Excel 报告；不执行用例、补评分或把评测异常计为能力零分。
---

# 汇总 General E2E 报告

从通过身份、哈希和协议校验的回传包生成可复算汇总，显式披露范围、覆盖率与异常分母。

## 当前能力

先运行：

```bash
python -m eval_general_e2e skills --name report-general-e2e --json
```

`0.5.1/operational` 支持按模型@Harness 展示 General 结果、效率和维度对比、每题各单元并列的用例对比明细，以及每单元独立评分详情，生成不含根因分析的领导版 Markdown、Excel 与单独审计报告。合法 `partial` collect receipt 可进入报告，未知 Token/cache 等字段继续显示为不可用，不补零。保留 WorkBuddy 已冻结评分后的 JSONL 和耗时补采。仍须使用真实回传包；不得把 Web 报告或旧 CLI 报告仅改标题后发布。

## 责任边界

- 输入：校验通过的 submission、回传包和冻结报告配置。
- 输出：同源可复算 JSON、Markdown、Excel，以及资源覆盖率和异常分母。
- 枚举冻结任务全集；失败和未评任务保持显式状态，不能缩小分母。
- 未全量覆盖的资源指标只展示已知小计与覆盖数；全缺失不补零。
- 不调用被测 Harness、不补做 criterion 判断、不覆盖旧 attempt。

## 运行前提

- 批次根目录含 `manifest.json`、`report-config.json` 和 `.general-e2e/run-general-e2e-import-index.json`。
- 每个 unit 必须已有唯一显式选择的 return package；冲突未选择时失败关闭。
- 使用带 `@oai/artifact-tool` 的 Node runtime。通过 `--node-modules` 指向该 runtime 的 `node_modules`，或设置 `GENERAL_E2E_NODE_MODULES`；可用 `GENERAL_E2E_NODE` 固定 Node 可执行文件。
- Skill ZIP 内已 vendoring `general-contracts`，运行时不读取 WildClawBench checkout。

## 输入校验

先独立校验批次和回传内容：

```bash
python scripts/report_general_e2e.py validate-inputs \
  --batch-root /absolute/path/to/batch
```

校验会重算已选 package 的成员 SHA、package ID、unit manifest、collect/package/import receipt、submission、execution record、score 和 resource metrics；导入后的漂移仍会失败。

若回传包含 `unit/evidence/resource-supplements/<task-id>/`，报告端用随包 `workbuddy-jsonl-metrics` 组件重验原 execution/resource/collect receipt 的 SHA、session/cwd/Prompt/请求归属，并复算每个补采数值。验证命令需要 Node（默认 PATH，可用 `GENERAL_E2E_NODE` 指定）。失败不能回退为旧值。补采仅替换报告的资源观测；score、submission 与原 execution record 保持原哈希，JSON lineage 同时保留新旧指标及补充清单哈希。旧 WorkBuddy 顶层 request=1 不能继续冒充模型调用次数，未补采时该值展示为 unavailable。

## 生成报告

若回传包含 `unit/evidence/timing-supplements/<task-id>/`，须按归档的运行时请求起止时间和原 execution record 的 `prompt.sent_at` 复算，同时核对它绑定的 Token 补采 SHA。原生请求生命周期为 `agent_duration_seconds`，发送到原生完成的流程时间为 `duration_seconds`；不等同于模型推理时间，批次墙钟时间仍按冻结 execution record 计算。任一补采漂移均拒绝报告，不覆盖旧评分、原始证据或旧报告。

```bash
python scripts/report_general_e2e.py generate \
  --batch-root /absolute/path/to/batch \
  --output-dir /absolute/path/to/batch/reports/report-id \
  --node /absolute/path/to/node \
  --node-modules /absolute/path/to/node_modules
```

默认渲染 `9 + 单元数` 个工作表及其 PNG 预览，顺序为：总览、效率对比、分类对比、难度对比、Agent能力对比、模态对比、工具调用对比、用例对比明细、各单元评分详情、资源覆盖与异常。只有明确不需要预览时才传 `--skip-preview`；这不会跳过工作簿结构、关键范围和公式错误扫描。

`--output-dir` 必须位于 batch root 内，使 report receipt 的 artifact 路径能由 `run-general-e2e` 以 batch root 为基准重验。最终目录必须不存在或为空；生成器使用同父目录暂存并原子发布。

## 输出

- `general_e2e_report_data.json`：唯一可复算数据源。
- `通用场景端到端自动化评测报告.md`：不带根因分析的领导版报告，与 Excel 使用同一组单元对比表。
- `通用场景端到端评测审计.md`：执行状态、裁判协议、资源覆盖及谱系，保留异常、未评分和历史状态。
- `通用场景端到端自动化评测报告.xlsx`：九张公共表加每单元一张评分详情。
- `previews/excel-validation.json`：Sheet、关键范围和公式错误扫描记录。
- `previews/*.png`：各 Sheet 视觉检查图（未使用 `--skip-preview` 时）。
- `cli-adapter/`：`score.json / usage.json / execution_status.json / task_output.json` 兼容视图；异常和缺失仍为 `null`，不会补零。
- `receipts/report-receipt.json`：可供 `run-general-e2e record-receipt --stage report` 登记的标准回执。

## 统计口径

- 主均值分母仅含 `score_status=valid`；真实 `0.0` 是有效能力零分。
- `evaluation_error` 和 `unscored` 保留在冻结全集但不进入能力均值。
- 分类、难度、unit 与裁判协议均复用同一任务运行集合；裁判按 protocol、model、reasoning effort 分组。
- 每个资源字段独立统计。仅所有任务运行均完整覆盖时写 `total`；否则为 `null`，并展示 `known_subtotal`、任务运行覆盖和原生事件覆盖。
- 批次壁钟按最早任务开始至最晚任务结束计算；任务耗时之和单独展示。

## 对比报告口径

- 总览每个 `模型@Harness` 一行，优先使用执行记录中已核验的实际模型；无法确认显示“未知模型”，单个 unit 中实际模型混杂时显式显示“混合模型”。显示名重复时加 unit ID，不能自动合并。
- 总览不展示成本、超时数；拆分“任务耗时(s)”（原生请求/Agent 耗时之和）与“流程耗时(s)”（含发送及等待）。保留有效评分数、未评分数；评测异常数按执行基础设施异常或评分异常的任务并集计数。完成率仅指原生正常完成率，不是正确率。
- 效率对比：模型@Harness、总 Token、平均 Token、普通输入 Token、缓存命中输入 Token、缓存写入输入 Token、输出 Token、缓存命中率。普通输入=归一化输入总量−Cache Read−Cache Write；三项完整可观测时才计算，未知缓存不能按 0 扣减。Cache Read/Write 分别映射 `cache_read_input_tokens`/`cache_creation_input_tokens`，缺失显示 `-`。平均 Token 分母为冻结任务运行数；缓存命中率仍使用缓存命中输入/含缓存的输入总量，不能改除普通输入。输入为 0 或覆盖不全时为空，不平均逐题比例或重复累加缓存。
- 工具指标本版只展示调用数与按工具名分组的已知数量，标准 transcript 中每题 call ID 去重，与原指标对账后标注明细覆盖。`completed` 不等于工具成功；不实现格式准确率、执行成功率、不确定占比。
- 七维能力复用公共 `checkpoint_capability_map7.yaml`。自动检查点来自评分引用并带 SHA 的 `rule-component.json/raw_scores`；语义检查点来自 score.criteria，按规则/语义命名空间对齐。任务内映射检查点均值再对任务取均值，缺少任一映射检查点的该任务不进入该维度；同时披露有效/涉及样本数，缺失不补零。不重做判分、不把任务总分替代未映射检查点。
- 构建时冻结公共实体显示名和能力映射为 `data/report-reference.json`，随包携带 canonical YAML 及 SHA；脱仓报告无需 PyYAML。公共字典来源在 JSON 和资源审计表保留。
- 分数展示统一为 0–100；底层评分与 CLI adapter 保持 0–1。Excel 和领导 Markdown 都读取 `presentation.tables`，禁止在渲染层另算分数。单元题目范围不同或模型/Harness 同时改变时，明确属于组合对照，不做单因果归因。

## 用例对比与单元评分详情

- 总览“工具调用数”紧随“总请求数”，后接任务耗时与流程耗时。
- 用例对比明细沿用常规报告前十列：分类、用例ID、用例名称、难度、模态、标签、输入(Prompt)、预期行为、评分标准、检查点；后接每个模型@Harness 的总分与检查点明细，以及最优单元、最大分差。每题一行，缺席/无效评分不补零；至少两个有效单元才计算最优和分差，并列最优全部保留。
- 从已选 return 的 scoring attempt 读取 `attempt-manifest.json`，核对 dataset、执行/评分身份与 task/contract SHA，再读取冻结 `private/task.md` 和 `contract.json`。不读取当前仓库题目补写历史；旧包缺少题面时显示 `-`。同题不同单元的题面哈希或基础元数据冲突时失败关闭。
- 评分详情每 unit 一张，名称 `评分详情_<模型@Harness>`，超过 Excel 31 字限制或发生重名时截断并加 unit 摘要；`presentation.score_detail_sheet_names` 保留精确映射。
- 详情可展示冻结题面、预期、规则、Workspace/Skills/Env/Warmup 声明，执行/评分状态、总分、检查点、失分点、裁判判词、执行/评分错误、Token/请求/工具数、双耗时、标准 JSONL 引用。Env 仅为题目声明，不读取运行期环境变量值。未加入超时、多轮统计、根因分析或工具质量比率。
- 题面、规则和判词等长字段显示明确标注的节选，全文保留报告 JSON；执行记录展示回传包内标准 JSONL 路径，不将整段轨迹塞进单元格。对比格以总分背景色提示，不使用颜色推断各检查点结论。组件总分和诊断计数不冒充检查点或失分点。

更多字段说明见 [报告数据与 CLI 适配](references/report-data-and-cli.md)。
