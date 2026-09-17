# General E2E 运行契约

本目录定义 `general-e2e-contract-v1` 的运行产物：执行记录、标准轨迹事件、轨迹索引、资源指标、单题评分、submission 和阶段回执。JSON Schema 用于跨语言交换，`validator.py` 额外校验跨字段语义。

关键约束：

- `schema_id` 与整数 `schema_version` 必须同时匹配；未知版本拒绝读取。
- 资源真实零值使用 `value: 0` 和可验证状态；`masked`、`unavailable` 必须使用 `value: null`。
- 资源可附带逐字段 `coverage`、`metric_sources` 和仅限 `partial/unverified` 的 `known_subtotals`；完整观测的覆盖数必须等于分母，未知总量使用 `total: null`，不能用零分母伪装完整。
- 有效零分仍是 `result.valid: true`、`total_score: 0`，并保留逐项证据；缺证据或裁判失败使用 `valid: false`、`total_score: null`。
- task 身份固定为 `batch_id / unit_id / task_id / attempt_id`；submission 和 receipt 的任务顺序必须与冻结 scope 一致。
- trace index 可附带 adapter、原生会话绑定、原始事件范围和标准化统计；其中的原生/标准事件数必须分别与 event range 和 transcript artifact 一致。

运行示例测试：

```bash
.venv/bin/python -m unittest tests.general_e2e.test_contracts -v
```
