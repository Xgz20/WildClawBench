# 评测判分可靠性设计

## 目标

修复网站生成端到端测试暴露的三类可靠性问题，同时保持现有 Harness、旧任务格式和历史结果目录兼容：

1. v2 Rubric Judge 的响应 token 上限可配置，默认 1000；
2. `_grading.llm_notes` 中明确的裁判调用或输出异常进入统一异常门禁；
3. 有效性校验按本批次计划执行范围判断任务完整性，而不是默认要求全量任务。

## 共享 Judge 配置

`src/utils/grading.py::run_grading()` 是所有 Harness 完成模型执行后的共享评分入口。新增环境变量 `JUDGE_MAX_TOKENS`，仅控制 v2 Rubric Judge 的 `max_tokens`：

- 未配置时使用 1000；
- 正整数配置原样生效；
- 空值、非整数和非正数回退 1000，并记录 warning；
- 不修改各 Harness runner 内用于其他模型请求的同名参数；
- legacy `grade()` 任务保持原行为。

## 裁判异常识别

`src/utils/anomalies.py` 继续作为 run 级异常的唯一来源。评分异常按以下优先级读取：

1. 顶层 `score.error`；
2. 顶层 `score.llm_error`；
3. `_grading.llm_notes` 中具有明确机器故障语义的内容。

第三类只匹配稳定异常信号，例如 `judge failed:`、`judge_call_failed:`、无有效 JSON、JSON 解析失败、裁判响应截断或超时。普通自然语言判词不触发异常。命中后生成 `GRADING_SCRIPT_ERROR`，归因 `evaluation_framework`，有效性影响为 `fail`，报告通过同一 anomalies 结果统计为“评测异常”。

## 动态执行范围

新批次在 unit 根目录（与 `run.log` 同级）写入 `evaluation_scope.json`。文件在任务筛选完成、任务执行开始前生成，内容包括：

- schema version；
- task/category 模式；
- category、modality、include/exclude tags；
- 计划任务的 category、task ID 和来源；
- 计划任务数。

有效性校验优先使用该文件的计划任务集合，因此仍能发现选中范围内的真实漏跑。历史结果没有结构化文件时，回退解析 `run.log`：先用 `Category:` 限定分类，再应用 modality/tag/exclude-tag 过滤。若两种证据都不存在，保留原有全量兼容行为。

单任务模式同样写入结构化范围。resume 模式记录筛选后的完整计划集合，包括本次复用和待执行任务，避免把复用任务误判为不在范围内。

## 验证

- 单元测试覆盖 Judge 默认值、自定义值和非法值回退；
- 单元测试覆盖明确 Judge 异常与正常 `llm_notes`；
- 单元测试覆盖结构化范围、历史 category 日志回退和范围内漏题；
- 使用现有网站 round1 验证：不再产生其他分类的 123 个误报，task 005 被识别为判分失败；
- 重新生成 Excel，确认“评测异常数”为 1，正式有效性门禁仍因 task 005 Judge 失败而阻断。
