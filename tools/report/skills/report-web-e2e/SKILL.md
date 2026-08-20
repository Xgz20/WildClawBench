---
name: report-web-e2e
description: 汇总多个独立 Web E2E 评分回传包，校验批次与用例范围一致性，生成只包含 Web 指标的领导版 Markdown、报告数据 JSON 和三 Sheet Excel；不调用 WildClawBench 既有评分或 generate_eval_report.py。
---

# 汇总 Web E2E 报告

本 Skill 处理 `score-web-e2e` 生成的 `submission.json`，或测试人员用 ZIP 工具压缩的完整 Harness 根目录。ZIP 内必须恰好存在一个 `submission.json`。默认要求全部回传包具有相同 `batch_id`、`source_revision` 和完整一致的 `task_ids`；不一致时停止，不能静默混算。

模型、Harness 友好名称和推理强度映射只从 WildClawBench 工程内的 `tools/report/config/web-e2e/<batch_id>.yaml` 读取，不进入 execution/scoring ZIP。回传保留 `harness_id`；原始 `model_id` 可留空，由本批次唯一的 Harness 映射补全。配置格式与完整性门禁见 [references/report-config.md](references/report-config.md)。

## 产物

- `web_e2e_report_data.json`：可复算的统一数据源；
- `Web站点端到端评测领导版.md`：仅含“结论、总览、难度等级、一级维度、二级维度”；
- `Web站点端到端评测报告.xlsx`：仅含 `站点评测指标`、`难度对比`、`用例对比明细`。

页面美观度与总分并列展示，但永远不参与总分、得分率或满分率。没有正式定义时显示 `-` 和“待定义”，不能使用视觉与布局分数替代。

## 运行

先生成统一数据和 Markdown：

```bash
python3 .agents/skills/report-web-e2e/scripts/aggregate_web_e2e_results.py \
  --input /path/a.zip --input /path/b.tar.gz \
  --config tools/report/config/web-e2e/<batch_id>.yaml \
  --output-dir /absolute/report-output
```

在 WildClawBench 工程根目录运行时可省略 `--config`，脚本按回传包的 `batch_id` 读取上述默认路径。

再使用当前 Codex 工作区提供的 Node.js 和 `@oai/artifact-tool` 生成 Excel。必须先按 `spreadsheets` Skill 要求加载工作区依赖、创建临时 `node_modules` 链接，并执行一次 artifact operation 标记；不得改用系统 `openpyxl`。

```bash
node .agents/skills/report-web-e2e/scripts/build_web_e2e_workbook.mjs \
  --input /absolute/report-output/web_e2e_report_data.json \
  --output /absolute/report-output/Web站点端到端评测报告.xlsx \
  --preview-dir /tmp/web-e2e-report-preview
```

生成后检查三张 Sheet 名称和顺序，逐表渲染预览，扫描公式错误，并核对 Excel 总平均分、完成率和用例数与 JSON/Markdown 一致。

## 统计边界

- 总平均分：全部声明用例等权平均；执行错误、超时和评测异常按标准 task score 的 0 分纳入。
- 正常完成：执行状态和评测状态均为 `completed`。
- 完成率：正常完成数 / 用例数。
- 资源总量：只有该 unit 所有题目都提供该字段时才展示总和；缺失显示 `-`，不把未知量当 0。
- 格式准确率：优先按工具调用数加权；缺调用数但全部题目都有准确率时取题目等权平均。
- 一级、二级维度：按题目等权平均；异常题目的维度分为 0。
