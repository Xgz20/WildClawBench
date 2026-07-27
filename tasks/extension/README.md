# tasks/extension — 扩展/自建任务集

放置**自建或从外部基准移植**的任务，与 `tasks/0X_*` 官方对标集隔离：

- `--category all` 只遍历硬编码的 6 个官方分类（`run_batch.py:ALL_CATEGORIES`），
  **不会扫到本目录**，因此不污染官方对标数据。
- 单任务运行：`--task tasks/extension/<file>.md`。
- 文件名需含 `task_`（category 批量模式的 glob 约定）。

## Workspace 文件（不入库）

`workspace/` 被 `.gitignore` 忽略——输入文件与真值靠外部数据集分发，不进 git。
运行任务前需按 task.md 的 `## Workspace Path` 段准备目录：

```
workspace/extension/<task>/
├── exec/    # 输入文件（→ 容器 /tmp_workspace，agent 可见）
└── gt/      # ground truth（评分时 → /tmp_workspace/gt）
```

### extension_task_1_csv_gdp_regions

首个 v2「规则/LLM 分离」格式任务，从 PinchBench `task_csv_gdp_regions` 移植，
用于端到端验证 v2 评分链路。准备输入：

```bash
mkdir -p workspace/extension/task_1_csv_gdp_regions/{exec,gt}
cp <PinchBench>/assets/csvs/world_gdp_2014.csv \
   workspace/extension/task_1_csv_gdp_regions/exec/world_gdp_2014.csv
```

（本任务规则检查基于 agent 产出的报告文件内容，gt/ 可留空。）

模板见 `tasks/TASK_TEMPLATE_v2.md`，设计见 `docs/local/design/混合评分拆分设计.md`。
