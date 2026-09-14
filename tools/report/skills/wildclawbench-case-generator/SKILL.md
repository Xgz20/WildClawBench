---
name: wildclawbench-case-generator
description: 将真实用户 Query 和可选本地素材转换、登记为 WildClawBench v2 通用场景评测用例；适用于六大通用分类的新自建任务，不用于 Web、PPT、图片等专项评测协议。
---

# WildClawBench Case Generator

把真实 Query 转换为可执行、可评分、可追溯且等待人工审核的 v2 扩展用例。结构化分析由 Agent 完成，编号、Markdown、Workspace、来源登记、能力映射和静态门禁由脚本确定性完成。

## 转换边界

- 首版只支持 `01_Productivity_Flow` 至 `06_Safety_Alignment` 六类通用场景。
- 遇到网站生成、Playwright、PPT、图片或其他专项指标协议时停止生成，说明需要对应专项流程；不要降级伪装成通用用例。
- 不从一条 Query 推断评测集难度梯度或模型区分度。生成结果必须标记为需要人工审核，后续需用真实多模型/多 Harness 结果审计质量。
- 不覆盖已有任务、Workspace、来源登记或能力映射；冲突时停止并报告。

## 工作流

1. 读取 [references/category-guide.md](references/category-guide.md)，只根据待测核心能力选择一个分类。类别不明确时先澄清，不要仅按交付文件类型分类。
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

当前仓库的 `tasks/extension/README.md` 曾引用不存在的 `tools/validate_extension_tasks.py`。不要把该命令当作门禁；以组装脚本的登记一致性检查和 `validate-eval-dataset` 结果为准，除非仓库后来真实新增了该脚本。

## 交付说明

报告创建的 task ID、任务文件、Workspace、来源登记、能力映射和静态校验状态。明确说明 `PASS` 仅表示格式与静态前置条件通过，不代表评分代码已在容器中执行，也不代表用例质量、难度梯度或区分度已经由评测结果证明。
