# 质量审计指标

- 任务均值先在 `model@harness` 内按有效 run 平均，再在共同任务集合上比较模型；0 分是有效能力分数，不当作缺失。
- 过易使用满分率，过难使用零分率。默认达到 80% 才触发 `REVIEW`，这是人工复核提示，不是能力定论。
- 模型区分度要求至少两个模型和共同有效任务；报告任务级分差、绝对分差和达到 0.1 分默认差异阈值的比例。
- Harness 敏感性要求至少两个 Harness，并固定同一模型与任务交集。单 Harness 只报告样本不足，不把模型差异改写成 Harness 结论。
- 多 run 才计算总体标准差；单 run 标记稳定性证据不足。`run_metadata.json.supersedes_run` 通过 `src.utils.run_selection.select_effective_run_dirs()` 排除被替代 run。
- `difficulty` 是标签而非等距量。分组均值倒挂只产生 `REVIEW`，报告样本量和任务构成，不自动修改标签或发布门禁。
- 多个有效 model@harness 在同一任务共同接近 0 分时，报告会有限扫描轨迹中的完成/错误/评分契约信号；这只能形成“疑似检查点过严”候选，必须人工对照轨迹、`Automated Checks`、`LLM Judge Rubric` 和 ground truth。
- `report.json.summary.action_summary` 和 Markdown 的“结论摘要”按 task ID 聚合为需要修改、需要人工审核和未发现问题三类，不应用问题数量代替质量分。
