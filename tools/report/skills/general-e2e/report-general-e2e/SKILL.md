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

`0.3.2/operational` 支持从批次导入选择生成正式报告，以及 WorkBuddy 已冻结评分后的 JSONL 和原生耗时补采，Excel 耗时依据自动适配行高。仍须使用真实回传包；不得把 Web 报告或旧 CLI 报告仅改标题后发布。

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

默认渲染四个工作表及其 PNG 预览。只有明确不需要预览时才传 `--skip-preview`；这不会跳过工作簿结构、关键范围和公式错误扫描。

`--output-dir` 必须位于 batch root 内，使 report receipt 的 artifact 路径能由 `run-general-e2e` 以 batch root 为基准重验。最终目录必须不存在或为空；生成器使用同父目录暂存并原子发布。

## 输出

- `general_e2e_report_data.json`：唯一可复算数据源。
- `通用场景端到端自动化评测报告.md`：读者版报告。
- `通用场景端到端自动化评测报告.xlsx`：四 Sheet 报告。
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

更多字段说明见 [报告数据与 CLI 适配](references/report-data-and-cli.md)。
