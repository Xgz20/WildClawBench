# tasks/extension — 扩展/自建任务集

放置**自建或从外部基准移植**的任务。归类到官方 6 大类，但物理上隔离在本目录，
便于区分"官方对标集"与"扩展集"。

## 目录结构

```
tasks/extension/
├── 01_Productivity_Flow/     # 扩展任务，task_id 从 101 起
├── 02_Code_Intelligence/
├── 03_Social_Interaction/
├── 04_Search_Retrieval/
│   └── 04_Search_Retrieval_task_101_csv_gdp_regions.md
├── 05_Creative_Synthesis/
└── 06_Safety_Alignment/
```

## 命名约定

- **文件名 / task_id**：`<Category>_task_<N>_<slug>`，与官方同格式，
  但 **N 从 101 起**（错开官方的 1~100 区间，避免将来官方递增撞号）。
  例：`04_Search_Retrieval_task_101_csv_gdp_regions`。
- **frontmatter `category`**：填所属大类（如 `04_Search_Retrieval`）。
  注意 parser 实际以**父目录名**为准（`task_parser.py`），frontmatter 仅作说明，
  两者需一致。

## 运行方式（混合统计）

`eval/run_batch.py` 扫描时对每个 category **同时扫** `tasks/<cat>/` 和
`tasks/extension/<cat>/`，合并成一个任务列表：

```bash
# 单类：官方 + 该类扩展一起跑，同一份报告统计
python3 eval/run_batch.py --category 04_Search_Retrieval ...

# 全量：6 大类各自的官方 + 扩展全跑
python3 eval/run_batch.py --category all ...

# 单个扩展任务
python3 eval/run_batch.py --task tasks/extension/04_Search_Retrieval/04_..._task_101_....md ...
```

输出目录 `output_root/<category>/<task_id>/`——扩展与官方 task_id 不同名，
不会覆盖；报告按 category 聚合，扩展用例自动计入对应大类统计。

## Workspace 文件（不入库）

`workspace/` 被 `.gitignore` 忽略——输入文件与真值靠外部数据集分发，不进 git。
按 task.md 的 `## Workspace Path` 段准备目录，结构与任务分类对齐：

```
workspace/extension/<category>/<task>/
├── exec/    # 输入文件（→ 容器 /tmp_workspace，agent 可见）
└── gt/      # ground truth（评分时 → /tmp_workspace/gt）
```

### 04_Search_Retrieval_task_101_csv_gdp_regions

首个 v2「规则/LLM 分离」格式任务，从 PinchBench `task_csv_gdp_regions` 移植，
用于端到端验证 v2 评分链路。准备输入：

```bash
mkdir -p workspace/extension/04_Search_Retrieval/task_101_csv_gdp_regions/{exec,gt}
cp <PinchBench>/assets/csvs/world_gdp_2014.csv \
   workspace/extension/04_Search_Retrieval/task_101_csv_gdp_regions/exec/world_gdp_2014.csv
```

（注：本任务规则检查基于 agent 产出的报告文件内容，未用 gt/ 做真值比对——
区域划分本身主观，属"软评估"样本，主要用于验证 v2 管道，不作严格数值范例。
gt/ 可留空。）

模板见 `tasks/TASK_TEMPLATE_v2.md`，设计见 `docs/local/design/混合评分拆分设计.md`。
