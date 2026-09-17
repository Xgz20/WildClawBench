# General E2E 数据集包

`general-custom60-v1` 是首版冻结通用自建评测集。仓库提交 manifest lock，ZIP 作为构建制品输出到被忽略的 `report-workspace/`；后续 release catalog 再登记正式发行物 SHA。

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

bundle 顶层包含 manifest、JSON Schema、来源登记、60 份任务原文，以及按题隔离的 `execution/` 和 `private-scoring/`。它是管理员 prepare 输入，不应直接交给被评 Harness；执行/评分分包在 G1-05 实现。

## 能力审计矩阵

G0-04 的逐题静态能力矩阵由确定性生成器维护。生成器会先验证当前任务与 Workspace 仍匹配 manifest lock，再以 AST 检查 grader；不会导入或执行任务评分代码：

```bash
.venv/bin/python -m eval_general_e2e.datasets.capability_audit generate
.venv/bin/python -m eval_general_e2e.datasets.capability_audit check
```

提交产物位于 `audits/general-custom60-v1-capability-matrix.{json,md}`。JSON 保留逐题环境、网络、命令、执行/评分素材、产物路径、grader imports、轨迹字段、工具别名和 Windows 风险；Markdown 是审核入口。`check` 用于确认提交产物没有因题目、素材或生成器变化而过期。
