---
name: score-general-e2e
description: 对一个冻结的 General E2E 任务运行自动规则与指定语义裁判，生成证据可追溯的标准评分；不负责批量调度、执行 Harness 或报告汇总。
---

# 评分 General E2E 单题

在独立评分工作空间中完成单题规则分、语义分、合分和评分审计。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name score-general-e2e --json
```

只有 `implementation_status` 为 `operational` 时才形成正式评分。当前 `interface_only` 表示评分 core 尚未抽取；应报告未就绪并保留评分输入，不得调用旧 CLI grading 后把结果改名为 General E2E 分数。

## 责任边界

- 输入：单题评分工作空间、冻结候选/轨迹和裁判配置。
- 输出：自动规则分、语义分、证据引用、评分审计和标准 `score.json`。
- 保持任务原规则、rubric、权重和分值锚点；缺证据时保留未判定或评测错误。
- 语义判断必须引用可定位证据，长轨迹可分页回查，不能只用截断摘要替代原文。
- 不创建下一题任务，不重跑被测 Harness，不聚合跨题结果。
