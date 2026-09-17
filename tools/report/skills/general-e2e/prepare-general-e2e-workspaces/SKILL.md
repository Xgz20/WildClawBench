---
name: prepare-general-e2e-workspaces
description: 从版本化数据集构建 General E2E 批次、执行包和私有评分包；用于准备隔离工作空间，不负责启动 Harness、收集证据、评分或报告。
---

# 准备 General E2E 工作空间

从冻结的 dataset bundle 生成可审计批次，并保持执行材料与私有评分材料隔离。

## 输入与入口

需要三个文件：管理员持有的 dataset bundle、General E2E suite ZIP 和 prepare 配置 JSON。已安装 Skill 内执行：

```bash
python scripts/prepare_general_e2e_workspaces.py prepare \
  --dataset-bundle /path/to/general-custom60-v1.dataset.zip \
  --release-suite /path/to/general-e2e-suite-general-e2e-dev.zip \
  --config /path/to/prepare-config.json \
  --output-dir /path/to/output
```

配置必须符合 [prepare-config-v1.schema.json](references/prepare-config-v1.schema.json)，可从 [prepare-config.example.json](references/prepare-config.example.json) 修改。批次和 unit 的 `task_ids` 都要沿用 dataset manifest 顺序；unit 合集必须覆盖批次任务。执行前先校验 dataset 和 release 的协议、摘要、成员集合及 Skill ZIP；任何未知版本、重复/越界路径、符号链接类型不一致或哈希漂移都失败关闭。不得改用 Web E2E prepare 或旧 `eval_e2e`。

输出目录中每个 unit 都有独立 `__execution.zip` 和 `__scoring.zip`。只把 execution ZIP 交给被评 Harness；执行终态冻结后再由控制端合入 scoring ZIP。可用以下命令复核既有批次：

```bash
python scripts/prepare_general_e2e_workspaces.py verify-batch \
  --batch-root /path/to/output/general-smoke
```

## 责任边界

- 输入：版本化 dataset bundle、Harness 配置和输出位置。
- 输出：批次 manifest、execution/scoring ZIP、报告配置及所需 Skill 清单。
- 对 dataset digest、任务全集、目标 Harness 和冻结配置做失败关闭校验。
- execution 包不得包含 GT、rubric、grader 或其他私有评分材料。
- scoring 包不得包含候选 Workspace 或执行 Prompt。
- `/tmp_workspace` 只允许确定性映射为 `./workspace`，并记录原始与发送 Prompt SHA。
- 保持 dataset manifest 的任务顺序和 ZIP 中受限符号链接元数据；不跟随链接读取宿主文件。
- 不启动桌面客户端，不产生执行回执，不决定任何分数。
