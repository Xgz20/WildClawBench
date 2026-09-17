---
name: prepare-general-e2e-workspaces
description: 从版本化数据集构建 General E2E 批次、执行包和私有评分包；用于准备隔离工作空间，不负责启动 Harness、收集证据、评分或报告。
---

# 准备 General E2E 工作空间

从冻结的 dataset bundle 生成可审计批次，并保持执行材料与私有评分材料隔离。

## 当前能力门禁

先在 WildClawBench checkout 中运行：

```bash
python -m eval_general_e2e skills --name prepare-general-e2e-workspaces --json
```

只有 `implementation_status` 为 `operational` 时才执行批次准备。当前 `interface_only` 表示正式名称、阶段和契约边界已经建立，但 G1-05 的独立装配实现尚未交付；应明确报告未就绪并停止。不要改用 Web E2E prepare 或旧 `eval_e2e` 生成看似兼容的包。

## 责任边界

- 输入：版本化 dataset bundle、Harness 配置和输出位置。
- 输出：批次 manifest、execution/scoring ZIP、报告配置及所需 Skill 清单。
- 对 dataset digest、任务全集、目标 Harness 和冻结配置做失败关闭校验。
- execution 包不得包含 GT、rubric、grader 或其他私有评分材料。
- 不启动桌面客户端，不产生执行回执，不决定任何分数。
