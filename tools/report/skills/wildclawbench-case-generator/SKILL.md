---
name: wildclawbench-case-generator
description: 将真实用户 Query 和可选本地素材转换、登记为 WildClawBench v2 通用场景评测用例；支持旧扩展集和catalog注册数据集的独立分类，不用于Web、PPT、图片等专项评分协议。
---

# WildClawBench Case Generator

把真实 Query 转换为可执行、可评分、可追溯且等待人工审核的 v2 扩展用例。结构化分析由 Agent 完成，编号、Markdown、Workspace、来源登记、能力映射和静态门禁由脚本确定性完成。

## 转换边界

- 不指定数据集时继续支持 `01_Productivity_Flow` 至 `06_Safety_Alignment` 六类，写入 `tasks/general/regression/`。指定`dataset_id`或`--dataset-id`时，从catalog注册定义读取该系列的分类、双标签、任务/Workspace根、来源表和能力映射。
- 遇到网站生成、Playwright、PPT/图片专项指标协议时使用对应专项流程；原生办公文件交付和图片理解可以按已批准的通用业务契约制作，不因为格式自动加入专项标签。
- 不从一条 Query 推断评测集难度梯度或模型区分度。生成结果必须标记为需要人工审核，后续需用真实多模型/多 Harness 结果审计质量。
- 不覆盖已有任务、Workspace、来源登记或能力映射；冲突时停止并报告。

## 工作流

1. 读取 [references/category-guide.md](references/category-guide.md)；注册数据集以其`dataset.yaml`分类为准。根据业务成功条件选择主类，不仅按交付文件类型分类。
2. 读取 [references/generic-v2-contract.md](references/generic-v2-contract.md)，把 Query 收敛为可复现 Prompt、可观察交付物和独立评分点。核对 Query 引用的本地文件、Skill、Env 与 Warmup 是否真实可用。
3. 读取 [references/case-spec-schema.md](references/case-spec-schema.md)，在 `report-workspace/case-generator/` 下创建临时 `case-spec.json`。不得把密钥值写入 spec；Env 只写变量名。
4. 先预检并查看计划分配的 ID：

   ```bash
   .venv/bin/python .agents/skills/wildclawbench-case-generator/scripts/assemble_case.py \
     report-workspace/case-generator/case-spec.json --dry-run
   ```

   若仓库没有 `.venv/bin/python`，先确认 `python3` 已安装 `requirements.txt` 中的 `pyyaml` 和 `python-dotenv`，再用同一命令入口。

5. 修正所有预检问题后去掉 `--dry-run`。脚本会一次性创建任务和 `exec/gt`，更新 `task_sources.yaml` 与 `checkpoint_capability_map7.yaml`，并调用现有 `validate-eval-dataset`；最终校验失败会回滚本次生成物。
6. 检查新任务、Workspace 和两份登记文件的差异。至少人工确认题意无歧义、输入足够、真值未泄露、评分点彼此独立、自动评分不会误杀合理答案、Rubric 档位可判、难度与超时合理。


注册数据集示例：在spec中设`"dataset_id": "general-challenge"`，或在命令中加`--dataset-id general-challenge`。规划清单内的编号只能生成同ID、同slug且状态为`building`的任务；`ready/frozen`版本的编号不可复用。新增源池任务不自动改变任何版本清单。注册数据集要求真实GT，首次创建来源表和能力映射时若最终门禁失败，也会移除本次创建的登记文件。正式整版验收另运行`validate_eval_dataset.py --dataset-id general-challenge`，逐题生成通过不能代替60题齐全及配额检查。

## 交付说明

报告创建的 task ID、任务文件、Workspace、来源登记、能力映射和静态校验状态。明确说明 `PASS` 仅表示格式与静态前置条件通过，不代表评分代码已在容器中执行，也不代表用例质量、难度梯度或区分度已经由评测结果证明。
