---
name: validate-eval-results
description: Validate WildClawBench raw evaluation results before reporting by checking completeness, run status, environment failures, metric integrity, and cross-model comparability. Use when asked to check evaluation validity, identify environment-caused score distortion, decide whether a round can be reported, or investigate suspicious raw results. Triggers on "评测结果有效性检查", "环境异常检查", "结果是否可信", "validate eval results", and "evaluation validity".
---

# WildClawBench 评测结果有效性检查

在生成报告前检查原始结果是否完整、可信、可比，输出证据化问题清单和 `PASS / REVIEW / FAIL` 门禁结论。本 Skill 不依赖 Excel 或 `eval-report`，可单独运行。

## 输入与输出

- 输入可为 round、model 或 unit 目录，支持双层 `<round>/<model>/<harness>` 与三层 `<round>/<harness>/<model>/<harness>`。
- 默认输出固定到 `<round>/report-workspace/validity/eval_result_validity.json` 和 `.md`；只有用户显式传 `--output-dir` 才改变位置。
- 详细规则、误报边界与人工复核项见 [references/checklist.md](references/checklist.md)。

## 工作流

1. 确认评测范围、预期模型/harness、任务集、轮数和 timeout 配置。
2. 执行确定性扫描：

```bash
python3 tools/report/skills/validate-eval-results/scripts/validate_eval_results.py \
  --result-root /path/to/round \
  --fail-on never
```

3. 阅读 JSON 的 `findings[].evidence`，按 checklist 复核启发式告警。不要仅根据数量判断。
4. 对环境故障定位影响范围：单模型、单 harness、单任务，还是多数 unit 共因。
5. 记录每个 `REVIEW` 的人工结论。修复确定性问题并重跑后再次检查。

## 门禁规则

- `PASS`：未发现评测框架、数据或共因环境问题，可进入报告生成；允许存在已归因为模型/Harness 的运行结果记录。
- `REVIEW`：存在无法自动区分评测框架与模型/Harness 责任的执行或环境信号；完成归因并记录后才能继续。
- `FAIL`：任务/文件缺失、判分失败、得分非法、任务集合或轮数不可比、确定的指标漂移、评测框架错误、跨 unit 共因环境故障等；默认阻断报告生成。

超时、Harness 进程非零退出、过早结束、工具名或工具协议不兼容，默认是模型/Harness 组合的能力结果，只记 `info`，不影响有效性门禁。只有证据明确指向评测 runner、任务准备、容器调度、轨迹采集、grader、数据解析，或多数 unit 的共因环境故障时，才判 `FAIL`。无法自动归因的执行错误判 `REVIEW`，不能仅凭 `execution_status.status=error` 判评测无效。

## 与报告链路的关系

- 由 `eval-report` 在生成 Excel 前调用，属于前置门禁。
- 不依赖 `eval-report`、`low-score-analysis` 或 Excel，可用于补跑决策和独立排障。
- 结果供 `audit-eval-report` 读取；有效性为 `FAIL` 时，报告审核不能给出 `PASS`。

## 交付要求

- 报告必须说明范围、结论、确定性错误、待复核项、受影响用例/unit、证据和处置建议。
- 不允许仅输出“环境有问题”；必须区分模型行为、模型专属通道、共享环境、harness、评分系统和数据管道。
- 保留 JSON 作为下游机器可读输入，Markdown 作为人工审核记录。
