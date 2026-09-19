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

只执行用户明确选择且对应单阶段 Skill 已具备所需能力的阶段。当前 `0.4.0/operational` 已实现批次/单元两级状态恢复、冻结输入校验、标准回传打包、安全导入、幂等与冲突选择；G4-03 已完成 AstronStudio macOS 五题执行、默认三槽评分、回传和同源报告闭环。该状态不外推 Windows、其他 Harness 或 60 题全量。不要以 Web E2E 或旧 `eval_e2e` 替代 General 阶段，也不要因“一条 Prompt”扩大用户授权。

新增 Harness 可按 [通用执行状态接口](references/adapter-execution-state.md) 接入 `record-execution`。该入口验证终态、业务身份、Workspace、原生会话证据与发送状态；新 Harness 的正式采集仍须等待公共收口器 CB-B，不因状态登记成功而宣称已具备执行回执或生产准入。

## 已实现入口

先建立显式状态；`--input role=/absolute/file` 会冻结评分包、报告配置等外部输入，恢复时重算 SHA：

```bash
python scripts/run_general_e2e.py init \
  --scope unit --root /absolute/unit-root \
  --stage execute,collect-evidence,score,package \
  --input scoring-package=/absolute/unit-scoring.zip

python scripts/run_general_e2e.py resume --root /absolute/unit-root
```

阶段开始、人工接管或失败使用 `set-stage`；完成不能手工填写，必须用 `record-execution`、`record-receipt`、`record-submission`、`package-return` 或 `import-return` 记录通过身份、终态、契约与哈希校验的产物。详细命令和恢复边界见 [流程状态与离线回传](references/flow-and-return.md)。

单元评分完成后生成确定性回传包：

```bash
python scripts/run_general_e2e.py package-return \
  --unit-root /absolute/unit-root \
  --orchestration-root /absolute/orchestration-root \
  --output-dir /absolute/returns
```

管理员侧导入时会手工解析 ZIP，拒绝越界路径、重复成员、未知类型、哈希漂移和越界符号链接。相同 archive SHA 幂等；同一批次单元的不同内容分别保存在 `returns/<unit-id>/<package-id>/`，并清除当前选择。只有显式 `select-import` 后，冲突单元才能继续报告阶段。

## 阶段与责任

稳定主链路为：`prepare → execute → collect-evidence → score → package → import-return → report`。

- 冻结阶段选择、数据集、Harness、模型、裁判及推理配置；恢复时沿用原配置。
- 每阶段只消费上游有效回执，保留 `NOT_SELECTED / PENDING / RUNNING / NEEDS_HUMAN / NEEDS_ATTENTION / COMPLETED / FAILED` 状态。
- `collect-evidence` 采集执行证据；`import-return` 导入管理员回传，二者不能混称 collect。
- 支持人工执行或离线交接，但不补造自动化证据，不覆盖冲突 attempt。
- 组合器不重写单阶段规则；具体执行、取证、评分和报告由对应 Skill 负责。
- batch scope 只管理 `prepare / import-return / report`；unit scope 只管理 `execute / collect-evidence / score / package`，不能把两类根目录混用。
- 回传包只收录冻结 unit manifest、正式 receipts/evidence、完整 submission、执行记录和评分 attempt；排除评分 `runtime/` 副本、缓存和常见凭据文件。
