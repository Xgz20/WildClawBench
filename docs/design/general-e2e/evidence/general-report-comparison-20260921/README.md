# General 单元对比报告与效率指标

2026-09-21，在 `feature/astroncode-eval` 串行完成。仅更新报告层，复用 WorkBuddy v8 冻结回传，未启动 Harness、发送 Prompt、重做评分或 push。

## 实现与发行

- `f34bcda61402232cb71fdcb9dd23ce97bf082116`：模型@Harness 单元对比、效率/维度/工具次数、领导版 Markdown 与单独审计报告。
- `a6eca00df53dfae4a2e96a69d822e3e35ad786ee`：按最新要求拆分普通输入、缓存命中输入、缓存写入输入、输出 Token。
- `3ff8ea9750128a8af4afe344a5666a3197a1f27a`：独立 `sheet_order` 固定 Excel 和 Markdown 顺序，避免 JSON 键排序改变报告布局。
- report Skill `0.4.2`，其余阶段版本不变。新增 `report-reference-data 1.0.0`，从公共实体显示名与七维检查点 YAML 在构建时编译 JSON；源文件、SHA 和内容哈希随包冻结，脱仓无需 PyYAML。
- 当前发行：`report-workspace/general-e2e/releases/general-report-comparison-20260921-v042`。
- suite SHA：`1761c00ddd4db92a673505cea4ef256c61c3c0bfeaa99985aa676a49d17c97dd`。
- catalog SHA：`02c1837d40b930edbc4ce930d38735d58d763b7d3dcfc9930ded82612973efeb`。
- report ZIP SHA：`47258f05d04d5e073697a1e36fe74e8c26e948fcee0ce893ab934493ce33cb9f`。
- release-root、suite 和七个 Skill 均验包通过。早期 0.4.0/0.4.1 构建与预览保留，正式使用上述 v042。

## 报告布局与口径

九 Sheet 顺序：总览 → 效率对比 → 分类对比 → 难度对比 → Agent能力对比 → 模态对比 → 工具调用对比 → 用例明细 → 资源覆盖与异常。

总览按模型@Harness 每单元一行；已核验模型优先显示友好名，未知模型有占位，重复显示名保留 unit 区分。不显示成本和超时数；任务耗时使用原生请求耗时总和，流程耗时包含发送/排队等待。有效分数分母保持原契约，评测异常不补能力零分。显示百分制，原 score 和 CLI adapter 保持 0–1。

效率表保留总 Token、平均 Token 和缓存命中率。四项明细依次为普通输入、缓存命中输入、缓存写入输入、输出。普通输入=归一化输入总量−缓存读取−缓存写入，仅三项全部可观测时计算；Cache Write 缺失不能当作 0。命中率仍以含缓存的输入总量为分母。缓存已经包含于输入，不再次相加。

七维能力复用现有公共映射，当前 General 60/60 题在映射中；v8 的 21 个检查点从冻结回传取得。规则分由 score.evidence SHA 绑定的 `rule-component.json/raw_scores` 读取，语义分使用 score.criteria。任务内映射点平均、再对任务平均；缺失映射点的任务不进入该维度，有效/涉及样本数保留。无检索验证样本时为空，不能推断其能力为零。

工具只统计总数与工具名分类，按 task/call ID 去重。格式准确率、执行成功率和不确定占比按用户要求暂缓；原生 `completed` 不代表工具业务成功。

## v8 当前结果

`GLM-5.2@WorkBuddy`：5/5 valid、82.75 分、正常完成 5；模型响应 21、工具调用 19；任务耗时 306.295 秒、流程耗时 511.448 秒。

| 效率指标 | 值 |
| --- | ---: |
| 总 Token | 773465 |
| 平均 Token | 154693 |
| 普通输入 Token | - |
| 缓存命中输入 Token | 703040 |
| 缓存写入输入 Token | - |
| 输出 Token | 4347 |
| 缓存命中率 | 91.4086% |

归一化输入总量 769118 仍在资源审计中保留。普通输入为空是因为 Cache Write 未暴露、无法准确分离，不表示没有普通输入。工具分类：Read 6、Bash 5、Write 4、present_files 2、Edit 1、Glob 1，合计 19。

七维能力分：代码生成 100、工具调用 100、数据处理 100、检索验证无样本、推理规划 73.9583、内容生成 68.75、验证交付 75。工具调用能力分来自任务检查点，和上面的实际调用次数含义不同；样本覆盖分别保留，不对小样本做强弱排名。

## 本地产物与验证

原件根：`/Users/gzx/debug-workspace/e2e-evaluate/wb3/v8`。当前报告目录：`p/wb3-v8/reports/workbuddy-comparison-v042/`。

- `general_e2e_report_data.json`：SHA `e24ef0ae290c72ce7a59f8b8e6b8fdf0ab1b88b0eab7ad02e360ff5939469818`。
- `通用场景端到端自动化评测报告.xlsx`：SHA `1334972c04307e720c99a3a1c85326c396524104b96ac8d1e38b2d65196a20d7`。
- `通用场景端到端自动化评测报告.md`：无根因领导版，SHA `b57a69c02661929dd1610b66e6a953a3a0bad66b165e9bac2e7890778fe68749`。
- `通用场景端到端评测审计.md`：SHA `c8fcc261b8a8206b38f7a720bebdbc5fb81fc6fd5385df3c791a51070fd353cd`。
- 沿用已选择的回传包 `e153170edbf98413fe0e250fc1f602fa989da5297300f6a16d507cd7f6e311df`，不需要重新打包执行或评分证据。新的 report receipt 已登记，batch/unit 均 `recommended_actions=[]`。
- `report-comparison/before.json` 与 `verification.json`：982 个原文件哈希不变，原评分、资源数值及 lineage 全量对照相同。
- `report-comparison/verify-publication.py`：从导出的 XLSX 独立解析九表顺序和七张主表的 120 个单元格，与 JSON 逐格核对，数字类型、零/缺失、缓存命中率与工具加总通过。
- 九表初版预览与最终受影响表复查通过，公式错误 0、关键范围 9；缓存缺失值右对齐，审计身份换行展示，哈希显示前 12 位、完整值保留 JSON。
- Python report/views/build/layout/run 聚焦 55/55；后续 Token 明细与顺序修订后 report/views/layout 22/22；源码布局、diff、Node 语法通过。测试覆盖非零/零/未知 Cache Write、完整分母、缓存总和冲突、七维平均顺序与缺项、规则 SHA 漂移、工具 ID 去重/身份污染、模型占位与重复标签、异常去重及无 YAML 独立分发。

本轮结论只覆盖报告建设与 v8 冻结证据复算。WorkBuddy 原生请求重叠峰值仍为 2，原生三路同时执行待验收；QwenWork/DoubaoWork/Windows 集成状态均未提升。
