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

只有 `implementation_status` 为 `operational` 时才形成正式评分。当前 `0.3.0/interface_only` 已提供可独立装配的 runtime-neutral 评分 core，以及不依赖 Docker 的私有评分目录和本地受管规则 Worker；真实 Codex/API Judge transport、合分审计与标准 `score.json` 尚未交付。因此可以运行和审计自动规则子能力，但不得把规则组件冒充完整 General E2E 分数，也不得调用旧 CLI grading 后改名发布。

## 责任边界

- 输入：单题评分工作空间、冻结候选/轨迹和裁判配置。
- 输出：自动规则分、语义分、证据引用、评分审计和标准 `score.json`。
- 保持任务原规则、rubric、权重和分值锚点；缺证据时保留未判定或评测错误。
- 语义判断必须引用可定位证据，长轨迹可分页回查，不能只用截断摘要替代原文。
- 不创建下一题任务，不重跑被测 Harness，不聚合跨题结果。

## 已交付规则子能力与后续边界

需要开发、校验或接入评分 core 时，读取[评分 core 接口](references/grading-core.md)。当前四个公开 API 可用于确定性契约验证和受管 backend 接入；`run_rules()` 不会自行执行不可信规则，`evaluate_semantics()` 也不会自行调用模型。

需要准备、复核或执行本地规则时，读取[本地受管规则运行时](references/local-rule-runtime.md)，使用 `scripts/score_general_e2e.py`。该入口强制候选原件只读、一次性 runtime 副本、GT 后置、真实本机 workspace 路径、冻结 transcript、专用虚拟环境、环境白名单、超时、独立进程组和进程树清理；不得要求 Docker。

真实 `codex-agent-judge-v1` 与 `api-judge-v1` transport 分别由后续阶段交付；在语义评分、合分审计和标准产物完成前保持 `interface_only`。
