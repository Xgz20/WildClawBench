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
├── 05_Creative_Synthesis/
└── 06_Safety_Alignment/
```

（空类目录用 `.gitkeep` 占位保结构。）

## 命名约定

- **文件名 / task_id**：`<Category>_task_<N>_<slug>`，与官方同格式，
  但 **N 从 101 起**（错开官方的 1~100 区间，避免将来官方递增撞号）。
  例：`04_Search_Retrieval_task_101_xxx`。
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
python3 eval/run_batch.py --task tasks/extension/<cat>/<file>.md ...
```

输出目录 `output_root/<category>/<task_id>/`——扩展与官方 task_id 不同名，
不会覆盖；报告按 category 聚合，扩展用例自动计入对应大类统计。

## Workspace 文件

`workspace/extension/` **纳入 git 管理**——自建扩展任务的 `exec/` 输入与 `gt/`
真值随任务一起入库（前期无大文件，用 git 足够；后期若出现大文件再单独管理）。
唯一例外是本地测试任务的 workspace 数据（`.gitignore` 显式排除）。

> 对比：官方任务的 `workspace/<category>/` 仍整体忽略，靠外部数据集分发。

按 task.md 的 `## Workspace Path` 段准备目录，结构与任务分类对齐：

```
workspace/extension/<category>/<task>/
├── exec/    # 输入文件（→ 容器 /tmp_workspace，agent 可见）
└── gt/      # ground truth（评分时 → /tmp_workspace/gt）
```

## 新增扩展任务步骤

1. 在 `tasks/extension/<大类>/` 放 `<大类>_task_<N≥101>_<slug>.md`
   （参考 `tasks/TASK_TEMPLATE_v2.md`）。
2. 建 `workspace/extension/<大类>/<task>/{exec,gt}` 并放入输入/真值。
3. 单跑验证：`--task tasks/extension/<大类>/<file>.md`；
   或并入批量：`--category <大类>` / `--category all`。

模板见 `tasks/TASK_TEMPLATE_v2.md`，设计见 `docs/local/design/混合评分拆分设计.md`。
