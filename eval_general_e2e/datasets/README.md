# General E2E 数据集包

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
