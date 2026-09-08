---
name: prepare-web-e2e-workspaces
description: 为自建或 ArtifactsBench Web 站点端到端评测按用例 ID 和 Harness 生成隔离执行/评分包、五个独立阶段 Skill ZIP、批次配置和跨平台兜底；自动选择详细或轻量指标 Profile，不调用 WildClawBench 执行或评分流程。
---

# 准备 Web E2E 工作空间

管理员使用本 Skill 生成多人可分发批次。必须明确 `task_ids`、一个或多个 `harnesses` 和 `output_dir`。若用户未指定 `batch_id`，按本机时间自动生成 `web-e2e-YYYYMMDD-HHMMSS`；不得只使用年月日，以免同一天重跑时撞目录。用户显式指定批次号时保持其值。模型与推理强度映射维护在批次根的报告 YAML；准备阶段的执行模板可暂时没有模型。测试人员应在被评 Harness 中预先配置默认模型和推理强度；执行 Skill 未收到显式模型时保持客户端当前配置，只回读实际模型。执行 Driver 必须把实际模型写入 `execution_record.json` 和 `execution-receipt.json`，评分与 submission 不再接受缺失的模型身份。推理强度只作为报告配置中的用户声明值，不由桌面自动化选择或回读。

```bash
python3 .agents/skills/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py \
  --task-id @product_task_ids.txt \
  --harness astronstudio --harness codex --harness workbuddy --harness trae \
  --metric-profile auto \
  --model-map astronstudio=model-a --model-map codex=model-b \
  --reasoning-effort-map astronstudio=high --reasoning-effort-map codex=max \
  --output-dir /absolute/output/path
```

例如 2026-08-20 14:35:42 触发时，默认批次目录为 `<output-dir>/web-e2e-20260820-143542/`。需要固定名称时再显式传 `--batch-id`。

正常准备时在批次根生成 `<batch_id>__report-config.yaml`。`--model` 和 `--reasoning-effort` 设置全部 Harness 的默认值；`--model-map harness=model` 和 `--reasoning-effort-map harness=effort` 可逐 Harness 覆盖。未提供模型时保留空 `model_id` 并标记为 `requires_model_mapping`，报告脚本会拒绝误用；管理员在汇总前补全即可。该配置不进入 execution/scoring ZIP。

默认不生成执行状态和资源记录。确实需要记录 Token、耗时或执行错误时，显式增加 `--include-execution-record`；只有此时每题才生成 `execution_record.json`，并可配合模型参数预填原始模型 ID。

## 指标 Profile

同一批次只能使用一个 Profile，并写入 `task_contract.json`、Harness/batch manifest、回传包和报告配置：

- `web-e2e-detailed-v1`：现有自建题。要求初始 Workspace 的 `exec/`、功能一级/二级维度和独立美观度指标。
- `artifactsbench-web-v1`：ArtifactsBench 开源题。允许仓库中没有初始 Workspace，准备时生成只含 `.gitkeep` 的空 `workspace/`；Criterion 按原始 0–10 整数评分并归一化，只汇总总分和难度等级，不生成独立美观度指标。

默认 `--metric-profile auto`：优先读取题目显式 `metric_profile`，否则 `source.benchmark: ArtifactsBench` 选择轻量 Profile，其余 Web 题选择详细 Profile。只有需要验证或覆盖来源元数据时才显式传 Profile；批次中自动识别出多种 Profile 时停止，不能静默混包。

只需重新发布最新版评分 Skill 时，不必重复准备用例和 Harness 工作空间：

```bash
python3 .agents/skills/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py \
  --score-skill-only \
  --batch-id web-e2e-20260820-105921 \
  --output-dir /absolute/output/path
```

此模式不需要 `--task-id` 或 `--harness`，直接生成 `<output-dir>/score-web-e2e-skill-v<version>.zip`，并输出版本、文件数、内容 SHA-256 和 ZIP SHA-256；不会创建批次子目录、execution/scoring 包或 manifest。目标 ZIP 已存在时拒绝覆盖。

## 分包契约

每个 Harness 生成两个 ZIP，整个批次另生成五个互相独立的 Skill ZIP，并在批次根保留 `skills-manifest.json` 和报告配置。独立打包只表示可按需安装，不绑定阶段、角色或机器：

- `__execution.zip`：带固定 Harness 根目录，包含 `execution/tasks/`、预置空 `score/`、最小批次 manifest、人工清单和 Python 兜底文件；先发送给执行人员。
- `__scoring.zip`：不带 Harness 根目录，只包含 `score/tasks/` 增量；Harness 执行完成并备份后再发送。
- `execute-web-e2e-skill-v<version>.zip`：可独立导入执行控制智能体；负责 WorkBuddy 等被评 Harness 做题。
- `score-web-e2e-skill-v<version>.zip`：可独立导入评分智能体；每台评分客户端按版本安装一次，后续可单独升级。
- `orchestrate-web-e2e-skill-v<version>.zip`：可独立导入控制智能体；负责执行结果交接、Playwright 注册 Codex Desktop 项目以及通过内置任务接口调度评分，不执行单题评分。
- `report-web-e2e-skill-v<version>.zip`：可独立导入报告生成智能体；不依赖 WildClawBench 评分流程。
- `run-web-e2e-skill-v<version>.zip`：可选的跨阶段组合器；只运行用户 Prompt 明确选择的阶段并维护可恢复状态、离线回传和收集，不替代其他 Skill。
- `packages/skills-manifest.json`：记录以上 Skill 的名称、版本、支持阶段、兼容 Profile、相对路径、文件数、内容 SHA-256 和 ZIP SHA-256，供离线选择、安装去重与验包。
- `<batch_id>__report-config.yaml`：管理员侧批次配置，记录模型、Harness、推理强度和展示顺序；与回传包一起交给报告 Skill，但不分发给执行或评分人员。

五个 Skill 同时兼容自建详细 Profile 与 ArtifactsBench Profile，不因批次或题集重新发布。Skill ZIP 文件名不带 `batch_id`；控制 Harness 先根据 execution 包 `manifest.json.required_skills` 或 `packages/skills-manifest.json` 比对已安装 Skill 的名称、版本和内容 SHA-256，完全一致时跳过安装。版本相同但内容 SHA 不同必须失败关闭，不能把不同内容当作同一发布版本。

被评 Harness 每题选择：

```text
<harness-package-root>/execution/tasks/<task_id>/
```

该目录只保留一个有效 `PROMPT.md`；`/tmp_workspace` 已改写为 `./workspace`。原始题目由仓库与哈希审计，不把两个 Prompt 同时放进 Agent 可见工作空间。

评分前人工主流程：

1. 将整个 Harness 根目录压缩备份并移到根目录外；
2. 按 `manifest.tasks` 将每个 `execution/tasks/<task_id>/` 复制到根目录已有的 `score/tasks/`；不得复制 `.execute-web-e2e` 等执行控制目录；
3. 将 `__scoring.zip` 解压到 Harness 根目录，选择合并目录，不能替换整个 `score/`；
4. 检查每题同时存在 `workspace/`、`private-scoring/` 和 `.web-e2e-scoring-ready`；评分 Skill 从客户端已安装位置加载，不在题目目录内。

推荐直接把 `__scoring.zip` 放在 Harness 根目录同级或根目录内，保持预置的 `score/` 没有真实内容，再双击根目录中的 `准备评分工作空间.command`（macOS）或 `准备评分工作空间.cmd`（Windows）。封装会调用标准库脚本 `tools/prepare_scoring_workspace.py`，要求有效 `execution-receipt.json`，在复制前、复制后和发布前核对最终候选 SHA，严格按 manifest 中的题目目录创建临时副本，生成 `private-scoring/candidate_artifact.json`，同时锁定执行回执文件 SHA 和实际回读模型，排除 `.execute-web-e2e` 等执行控制目录，安全解压评分包并在全部校验通过后填充 `score/`；空目录以及 `.DS_Store`、`Thumbs.db` 等系统元数据会被安全清理，真实文件、评分结果和符号链接仍会触发拒绝覆盖。本机没有 Python 时再回退到上述人工 ZIP 流程，但人工流程也必须生成并核对同等冻结记录后才能自动编排。

## 隔离与路径

- `execution/tasks/<task_id>/workspace/` 对详细 Profile 只复制源 Workspace 的 `exec/`；ArtifactsBench Profile 允许生成空目录。两者都不能包含 `eval/`、`gt/`、checker 或 Rubric。
- execution 单题目录默认只有 `PROMPT.md` 和 `workspace/`；不生成单题 `task_manifest.json`，也不暴露任何私有评分路径。
- scoring ZIP 严禁包含 `workspace/`、`PROMPT.md`、`execution_record.json` 或 `task_manifest.json`，只能向 `score/tasks/<task_id>/` 添加评分材料。
- Rubric 引用的 `/tmp_workspace_eval/<file>` 只复制实际引用文件到 `private-scoring/fixtures/`，不能无条件复制整个 `eval/`。
- 评分契约中 `/tmp_workspace` 改写为 `./workspace`，`/tmp_workspace_eval` 改写为 `./private-scoring/fixtures`。
- 每个评分工作空间只含一个用例；评分 Agent 选择 `score/tasks/<task_id>/`，不能选择 Harness 根目录。
- 候选 `workspace/` 任一层级都不得包含 `.git`、`.cache`、`.vite` 或 `node_modules`。这些目录属于运行时状态，若被评 Harness 将其留在终态产物中，准备评分必须失败并重新执行，不能在冻结后由控制 Agent 清理。

详细 Profile 的页面美观度默认使用评分 Skill 内置的 `web-aesthetic-v1` 标准，并在 task contract 中记录版本、来源和 `joint_screenshot_set` 判定方式。`--aesthetic-rubric` 仅用于增加详细 Profile 的批次补充说明，不能替换内置的 6 个维度、权重和 32 个检查项；ArtifactsBench Profile 禁止传该参数。

验收 `batch_manifest.json`、`skills-manifest.json`、批次报告配置、每个 Harness staging 根、每 Harness 两个 ZIP、批次级 run/execute/score/orchestrate/report 五个版本化 Skill ZIP 及其内容/ZIP SHA-256。batch manifest 必须分别记录 `run_skill_archive`、`execute_skill_archive`、`score_skill_archive`、`orchestrate_skill_archive`、`report_skill_archive`、`required_skills`、`skills_manifest`、`report_config`、`scoring_skill` 名称/版本/Profile 能力和配置就绪状态。execution ZIP 不得含私有评分材料，scoring ZIP 不得含候选 Workspace、报告配置或 Skill 副本。
