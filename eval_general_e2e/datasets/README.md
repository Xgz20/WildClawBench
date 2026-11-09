# General E2E 数据集包

以下冻结数据集，使用同一套七阶段 Skill：

| dataset ID | 任务来源 | 题量 | 能力映射 |
| --- | --- | ---: | --- |
| `general-custom60-v1`（默认） | `tasks/extension` | 60 | 原七维，原 manifest 和映射内容保持不变 |
| `general-custom116-v1` | `tasks/general_e2e`（递归扫描） | 116 | 独立五维，检索 20、Office 30、数据分析 66 |
| `general-custom70-v2` | 归档题源，按独立定义显式选择 | 70 | 独立五维；检索20、Office30、数据分析001—020 |
| `general-custom70-v3` | 归档题源，回灌后续8道Office规则修复 | 70 | 同一70题范围及独立五维 |
| `general-custom70-v4` | 冻结杨联芬原刊参考 | 70 | 同一70题范围及独立五维 |
| `general-custom70-v5` | 补齐Info002作者消歧与Info004董炳月、王吉鹏／荆亚平原刊证据 | 70 | 同一70题范围及独立五维 |

下一轮70题评测选择 `general-custom70-v5`，并配套 Score 0.10.94 / Orchestrate 0.11.78 或经核验的后续版本。
新版私有评分材料可离线核对新增来源。构建使用 `python -m eval_general_e2e.datasets.bundle build --dataset general-custom70-v5`。
v4的68道其余题、全部公开Prompt及执行材料摘要保持一致。旧批次使用原数据锁。

v3题内规则、CLI独立原因复核、E2E精确版本登记及
历史影响审计见[2026-11-04同步说明](../../../docs/general-e2e/general70-source-sync-20261104.md)。
v2已评分轮次所需的8份原题源保存在`source-snapshots/general-custom70-v2/`；
旧v2 manifest、bundle及已完成评分保持原摘要，不原地升级。

`general-custom70-v2` 将已验证的解析修复直接写入题内 Python、参考材料和公开评分契约，
CLI 与 Skill 读取同一份代码。Info004 增加分级参考证据及SHA索引；裁判缺证保留null，
不能扣模型分或删项归一。旧60题入口和七维映射不变；其他46题没有修改。

```bash
python -m eval_general_e2e.datasets.bundle build --dataset general-custom70-v2
python eval/run_batch.py --dataset general-custom70-v2 --parallel 3 --model <已配置模型>
python -m eval_general_e2e.datasets.bundle build --dataset general-custom70-v3
python eval/run_batch.py --dataset general-custom70-v3 --parallel 3 --model <已配置模型>
```

CLI显式70题入口先核验当前源码与manifest一致，拒绝通过tag/modality过滤缩小冻结范围。
语义裁判使用结构化criterion状态，未知项不参与平均；零权重能力诊断缺证不冒充业务失败，
有业务预算的未知项使正式总分保留空值。原最终总分封顶在两入口一致应用。

历史116-v1的原题源及Info004原参考保存在 `source-snapshots/general-custom116-v1/`，
逐文件SHA绑定；编译v1显式读取该快照，并只排除v2新增的Info004证据文件。
未登记的素材仍按原manifest检测漂移。v1 manifest与已发行包、执行、评分和报告不覆盖。
当前目录下的70题是修复后的源版本；重现v1必须选择v1 bundle或快照，不能把当前源题冒称v1。

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
