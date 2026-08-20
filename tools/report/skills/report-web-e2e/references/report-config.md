# Web E2E 批次报告配置

每个批次在 WildClawBench 工程中维护一个配置文件：

```text
tools/report/config/web-e2e/<batch_id>.yaml
```

该文件不进入 execution、scoring 或回传 ZIP。报告脚本读取友好名称、推理强度和输出顺序。回传中有原始 `model_id` 时使用 `model_id + harness_id` 精确匹配；`model_id` 为空时按 `harness_id` 匹配，因此同一批次的配置必须保证该 Harness 只对应一个模型。

```yaml
schema_version: wildclawbench.web-e2e-report-config/v1
batch_id: web-e2e-20260820
units:
  - model_id: gpt-5.5
    model_display_name: GPT-5.5
    harness_id: codex
    harness_display_name: Codex
    reasoning_effort: high
    order: 1
  - model_id: glm-5.2
    model_display_name: GLM-5.2
    harness_id: astronstudio
    harness_display_name: AstronStudio
    reasoning_effort: max
    order: 2
```

约束：

- `batch_id` 必须与全部回传包一致；
- 每个 `model_id + harness_id` 和 `order` 必须唯一；若回传不填写 `model_id`，对应 `harness_id` 在配置中也必须唯一；
- 配置声明的单元必须与本次全部回传包完全一致，缺失或多出均停止生成；
- `reasoning_effort` 保留原始配置值，写入报告数据 JSON 和报告；模型及 Harness 展示名称只取本配置，不信任分发包内的友好名称。
