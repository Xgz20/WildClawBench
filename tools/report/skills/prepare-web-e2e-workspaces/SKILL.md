---
name: prepare-web-e2e-workspaces
description: 为独立 Web 站点端到端评测按用例 ID 和 Harness 生成最小 execution/tasks 执行包、score/tasks 增量评分包、独立评分 Skill ZIP、人工清单和跨平台 Python 兜底；只读取题目与初始 Workspace，不调用 WildClawBench 执行或评分流程。
---

# 准备 Web E2E 工作空间

管理员使用本 Skill 生成多人可分发批次。必须明确 `task_ids`、一个或多个 `harnesses` 和 `output_dir`。若用户未指定 `batch_id`，按本机时间自动生成 `web-e2e-YYYYMMDD-HHMMSS`；不得只使用年月日，以免同一天重跑时撞目录。用户显式指定批次号时保持其值。模型映射维护在工程内的报告 YAML，不要求测试人员在分发包中填写；执行记录中的原始 `model.id` 可为空，不能填 0。

```bash
python3 .agents/skills/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py \
  --task-id @product_task_ids.txt \
  --harness astronstudio --harness codex --harness workbuddy --harness trae \
  --output-dir /absolute/output/path
```

例如 2026-08-20 14:35:42 触发时，默认批次目录为 `<output-dir>/web-e2e-20260820-143542/`。需要固定名称时再显式传 `--batch-id`。

默认不生成执行状态和资源记录。确实需要记录 Token、耗时或执行错误时，显式增加 `--include-execution-record`；只有此时每题才生成 `execution_record.json`，并可配合 `--model` 或 `--model-map` 预填原始模型 ID。

## 分包契约

每个 Harness 生成两个 ZIP，整个批次另生成一份评分 Skill ZIP：

- `__execution.zip`：带固定 Harness 根目录，包含 `execution/tasks/`、预置空 `score/`、最小批次 manifest、人工清单和 Python 兜底文件；先发送给执行人员。
- `__scoring.zip`：不带 Harness 根目录，只包含 `score/tasks/` 增量；Harness 执行完成并备份后再发送。
- `__score-web-e2e-skill.zip`：可独立导入评分智能体；每个批次只生成一份，每台评分客户端安装一次，后续可单独升级。

被评 Harness 每题选择：

```text
<harness-package-root>/execution/tasks/<task_id>/
```

该目录只保留一个有效 `PROMPT.md`；`/tmp_workspace` 已改写为 `./workspace`。原始题目由仓库与哈希审计，不把两个 Prompt 同时放进 Agent 可见工作空间。

评分前人工主流程：

1. 将整个 Harness 根目录压缩备份并移到根目录外；
2. 将 `execution/tasks/` 整个复制到根目录已有的 `score/` 下，得到 `score/tasks/`；
3. 将 `__scoring.zip` 解压到 Harness 根目录，选择合并目录，不能替换整个 `score/`；
4. 检查每题同时存在 `workspace/`、`private-scoring/` 和 `.web-e2e-scoring-ready`；评分 Skill 从客户端已安装位置加载，不在题目目录内。

若 ZIP 工具不能合并，把 `__scoring.zip` 放在 Harness 根目录同级或根目录内，保持预置的 `score/` 为空，再双击根目录中的 `准备评分工作空间.command`（macOS）或 `准备评分工作空间.cmd`（Windows）。封装会调用标准库脚本 `tools/prepare_scoring_workspace.py`，从 `execution/tasks` 创建临时副本、安全解压评分包并在全部校验通过后填充 `score/`；本机没有 Python 时回退人工 ZIP 流程。

## 隔离与路径

- `execution/tasks/<task_id>/workspace/` 只复制源 Workspace 的 `exec/`，不能包含 `eval/`、`gt/`、checker 或 Rubric。
- execution 单题目录默认只有 `PROMPT.md` 和 `workspace/`；不生成单题 `task_manifest.json`，也不暴露任何私有评分路径。
- scoring ZIP 严禁包含 `workspace/`、`PROMPT.md`、`execution_record.json` 或 `task_manifest.json`，只能向 `score/tasks/<task_id>/` 添加评分材料。
- Rubric 引用的 `/tmp_workspace_eval/<file>` 只复制实际引用文件到 `private-scoring/fixtures/`，不能无条件复制整个 `eval/`。
- 评分契约中 `/tmp_workspace` 改写为 `./workspace`，`/tmp_workspace_eval` 改写为 `./private-scoring/fixtures`。
- 每个评分工作空间只含一个用例；评分 Agent 选择 `score/tasks/<task_id>/`，不能选择 Harness 根目录。

页面美观度正式定义提供后可使用 `--aesthetic-rubric`；未提供时只保留 0–100 待定义字段，不实际赋分。

验收 `batch_manifest.json`、每个 Harness staging 根、每 Harness 两个 ZIP、批次级评分 Skill ZIP 及其 SHA-256。execution ZIP 不得含私有评分材料，scoring ZIP 不得含候选 Workspace或评分 Skill 副本。
