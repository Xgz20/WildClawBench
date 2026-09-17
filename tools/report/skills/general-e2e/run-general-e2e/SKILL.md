---
name: run-general-e2e
description: 按用户明确选择的阶段串联 General E2E 准备、执行、证据、评分、回传和报告，并维护恢复状态；不替代各阶段 Skill 的判断与契约。
---

# 运行 General E2E 全流程

组合已实现的单阶段能力，支持单 Prompt 自动链路与人机协作交接，同时保持阶段级恢复和失败关闭。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --json
python -m eval_general_e2e check-layout
```

只执行用户明确选择且 `implementation_status` 为 `operational` 的阶段。当前七个入口均为 `interface_only`，所以不得启动完整评测；应列出未实现阶段并停止。不要以 Web E2E 或旧 `eval_e2e` 替代缺失阶段，也不要因“一条 Prompt”扩大用户授权。

## 阶段与责任

稳定主链路为：`prepare → execute → collect-evidence → score → package → import-return → report`。

- 冻结阶段选择、数据集、Harness、模型、裁判及推理配置；恢复时沿用原配置。
- 每阶段只消费上游有效回执，保留 `NOT_SELECTED / PENDING / RUNNING / NEEDS_HUMAN / NEEDS_ATTENTION / COMPLETED / FAILED` 状态。
- `collect-evidence` 采集执行证据；`import-return` 导入管理员回传，二者不能混称 collect。
- 支持人工执行或离线交接，但不补造自动化证据，不覆盖冲突 attempt。
- 组合器不重写单阶段规则；具体执行、取证、评分和报告由对应 Skill 负责。
