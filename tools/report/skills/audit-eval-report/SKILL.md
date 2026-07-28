---
name: audit-eval-report
description: Audit WildClawBench evaluation reports by independently recomputing metrics from raw results, reconciling Excel sheets and detail rows, detecting contradictory or counterintuitive statistics, and reviewing publication claims. Use after report generation or when totals, request counts, tool calls, difficulty trends, rankings, or conclusions look suspicious. Triggers on "评测报告审核", "报告数据复核", "指标口径检查", "难度倒挂", "audit eval report", and "report sanity check".
---

# WildClawBench 评测报告审核

在报告发布前，从原始结果独立复算关键指标并与 Excel 对账，再审查反常识统计和文字结论。不得只调用报告生成脚本的内部聚合逻辑进行自证。

## 输入与输出

- 必需：原始 round/model/unit 结果目录、待审核 `.xlsx`。
- 建议：`validate-eval-results` 产出的 validity JSON；可选领导版 Markdown、根因 analysis JSON。
- 默认输出 `<round>/report-workspace/audit/report_audit_<xlsx-stem>.json` 和 `.md`。
- 详细自动规则和人工审核问题见 [references/checklist.md](references/checklist.md)。

## 工作流

1. 确认 Excel 对应的原始 round，不得拿最新 Excel 对旧批次数据。
2. 运行独立审核：

```bash
python3 tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
  --result-root /path/to/round \
  --excel /path/to/report.xlsx \
  --validity /path/to/eval_result_validity.json \
  --fail-on never
```

3. 处理确定性对账错误：Sheet/列/unit/任务缺失，汇总、详情、维度、矩阵或分差不能从原始数据复现时判 `FAIL`。
4. 处理启发式告警：工具调用/请求数比例、难度倒挂等只能触发 `REVIEW`；结合样本数、任务构成和原始轨迹解释。
5. 打开 Excel 抽样核查高分、低分、零分、异常状态和指标边界；若有 Markdown，逐项核对数字、排序、强弱判断和案例证据。
6. 把人工结论写入审核记录。修复脚本或数据后重新生成 Excel，并再次从头审核。

## 门禁规则

- `PASS`：自动对账通过，且人工检查没有未解决问题。
- `REVIEW`：自动对账无确定性错误，但存在需解释的反常统计或前置 validity 未决项。
- `FAIL`：原始数据有效性失败，或报告存在结构、计算、回填、范围等确定性错误。

统计反常不等于计算错误。难度等级不是严格等距变量，不同等级题型和样本量也可能不同；只有多数 unit 在足够样本上出现显著倒挂时才告警，仍需检查标签和题目构成。

## 独立性要求

- 可以复用 `src/utils/tool_metrics.py` 这类统一底层事件解析器，但汇总和对账逻辑必须独立实现。
- 不允许仅比较 Excel 内部单元格，因为多个 Sheet 可能共同继承同一计算错误。
- validity `FAIL` 时审核结论必须为 `FAIL`；报告不能掩盖无效原始结果。
- 审核 Skill 可单独运行，不依赖 `eval-report`；`eval-report` 在生成后调用它作为发布门禁。

## 交付要求

- 给出结论、审核范围、每个问题的规则 ID、证据、影响和修复建议。
- 明确区分“数据计算错误”“统计反常待解释”“模型能力结论不成立”。
- 对 Markdown 的每个关键数字和典型案例保留来源定位，不接受凭印象重述 Excel。
