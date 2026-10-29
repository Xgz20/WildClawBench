# General E2E 数据集包

当前支持两个独立的冻结数据集，使用同一套七阶段 Skill：

| dataset ID | 任务来源 | 题量 | 能力映射 |
| --- | --- | ---: | --- |
| `general-custom60-v1`（默认） | `tasks/extension` | 60 | 原七维，原 manifest 和映射内容保持不变 |
| `general-custom116-v1` | `tasks/general_e2e`（递归扫描） | 116 | 独立五维，检索 20、Office 30、数据分析 66 |

旧命令仍默认构建 60 题。新数据集使用显式选择：

```bash
python -m eval_general_e2e.datasets.bundle build --dataset general-custom116-v1
```

命令读取对应 `manifests/<dataset-id>.json`，核对全部任务、公开材料和私有评分材料的摘要，
输出到 `report-workspace/general-e2e/datasets/<dataset-id>/<dataset-id>.dataset.zip`。
新题来源登记在 `tasks/general_e2e/task_sources.yaml`，导入锚点是 `9bee3a12`；
实际任务和适配后的契约以 manifest 内逐项 SHA 为准。新增题目或材料变更经审核后，
只更新对应数据集的 lock：

```bash
python -m eval_general_e2e.datasets.bundle update-lock --dataset general-custom116-v1
```

从同一套 release 安装 `prepare-general-e2e-workspaces`，给新数据集使用
`references/prepare-config.general116.example.json`（三类各选一题）；全量评测时将 manifest
中全部 `tasks[].task_id` 按原顺序填入批次和 unit 的 `task_ids`。
prepare 输入的 `--dataset-bundle` 决定数据集，后续 execute、collect、orchestrate、score、
run、report 都沿用该 ID/digest 和冻结题目范围。旧 60 题使用原配置及 bundle。

新旧数据集分别建批，分别保存历史执行、评分和报告；不覆盖已冻结的 Skill、包或裁判身份。
数据集原始材料约 619 MiB，完整私有评分包的受限总量上限为 1 GiB，单成员仍为 64 MiB。
评分运行时继续使用 Python 3.11 和带 SHA-256 的依赖锁；新增加 Office/PDF/Excel 解析依赖。
部分题目需要系统 Office/LibreOffice 等原生工具，按对应任务要求准备；缺失时保留为评测环境异常。

新题的 Rubric 原文保留，分值预算通过冻结 `semantic_weight_scale` 转为组内权重，
不重复乘 100 或改变自动/语义组预算。规则诊断保存在 Worker `raw_result` 中，
不进入分数；规则权重为零的代码仍执行证据准备，失败时不能跳过。
报告分别使用 `checkpoint_capability_map7.yaml` 与 `checkpoint_capability_map5.yaml`，
新五维兼容视图与旧七维都保留有效样本覆盖，不做维度折算。

`general-custom60-v1` 是首版冻结通用自建评测集。仓库提交 manifest lock，ZIP 作为构建制品输出到被忽略的 `report-workspace/`；General release catalog 锁定阶段 Skill，prepare 生成的批次 manifest 同时冻结 dataset、suite 和 Skill SHA。

更新 manifest lock 是显式变更，只能在任务、exec 或私有评分素材经过审核后执行：

```bash
.venv/bin/python -m eval_general_e2e.datasets.bundle update-lock
```

按 lock 构建并立即校验 bundle：

```bash
.venv/bin/python -m eval_general_e2e.datasets.bundle build
```

脱离任务源码校验已有 bundle：

```bash
python -m eval_general_e2e.datasets.bundle verify \
  --bundle /path/to/general-custom60-v1.dataset.zip
```

bundle 顶层包含 manifest、JSON Schema、来源登记、60 份任务原文，以及按题隔离的 `execution/` 和 `private-scoring/`。它是管理员 prepare 输入，不应直接交给被评 Harness。

## 构建发行包与准备批次

构建并自校验七个 General Skill、release catalog 和 suite ZIP：

```bash
.venv/bin/python tools/e2e-build/build_general_release.py build \
  --repo-root . \
  --release-id general-e2e-dev \
  --output-dir report-workspace/general-e2e/releases/general-e2e-dev
```

从 release 根目录取得 `general-e2e-suite-general-e2e-dev.zip`，从 suite 中安装 `prepare-general-e2e-workspaces`，按 Skill 内的 `references/prepare-config.example.json` 生成配置。已安装 Skill 不需要 WildClawBench checkout：

```bash
python scripts/prepare_general_e2e_workspaces.py prepare \
  --dataset-bundle /path/to/general-custom60-v1.dataset.zip \
  --release-suite /path/to/general-e2e-suite-general-e2e-dev.zip \
  --config /path/to/prepare-config.json \
  --output-dir /path/to/prepared
```

每个 unit 生成一个 `__execution.zip` 和一个 `__scoring.zip`。execution 包只含映射后的 Prompt 和初始 Workspace；scoring 包只在执行冻结后由控制端合入，包含任务原文、评分契约和 GT。批次根目录另保留七个锁定 Skill ZIP、`release-catalog.json`、`report-config.json` 和可复核 SHA。

## 能力审计矩阵

G0-04 的逐题静态能力矩阵由确定性生成器维护。生成器会先验证当前任务与 Workspace 仍匹配 manifest lock，再以 AST 检查 grader；不会导入或执行任务评分代码：

```bash
.venv/bin/python -m eval_general_e2e.datasets.capability_audit generate
.venv/bin/python -m eval_general_e2e.datasets.capability_audit check
```

提交产物位于 `audits/general-custom60-v1-capability-matrix.{json,md}`。JSON 保留逐题环境、网络、命令、执行/评分素材、产物路径、grader imports、轨迹字段、工具别名和 Windows 风险；Markdown 是审核入口。`check` 用于确认提交产物没有因题目、素材或生成器变化而过期。
