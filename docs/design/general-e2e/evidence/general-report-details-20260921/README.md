# 用例对比明细与单元评分详情

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

2026-09-21，直接在 `feature/astroncode-eval` 完成。源码提交 `89d13d0657ffecf9d26117ec2969403b44d47b62`，report Skill `0.5.0`。本轮只读取已有 v8 冻结回传和评分，未启动 Harness、发送 Prompt、重判或 push。

## 本次变化

1. 总览尾部列顺序为总 Token、总请求数、工具调用数、任务耗时、流程耗时。
2. 原“用例明细”改为“用例对比明细”：分类、用例ID、名称、难度、模态、标签、Prompt、预期行为、评分标准、检查点，随后每个单元一列总分/检查点，末尾为最优单元与最大分差。列宽、换行、冻结前两列与顶部表头参照常规报告。
3. 每单元生成 `评分详情_<模型@Harness>`，长名截断并加 unit 摘要，JSON 保留名称映射。v8 新增 `评分详情_GLM-5.2@WorkBuddy`，五题各一行，包含题面、规则、状态、评分、检查点、失分点、判词、错误、资源与轨迹引用。

## 字段可行性与边界

v8 五个 scoring attempt 均保存 `private/task.md`、`contract.json`、attempt manifest 和评分。新读取器核对 dataset、执行/评分 attempt 身份以及 task/contract SHA 后提取元数据，不读取当前仓库 `tasks/` 或 `tasks/cn/` 替换历史题面。同题不同单元的基础元数据或冻结定义冲突会拒绝生成。

| 字段 | 本次支持情况 |
| --- | --- |
| 分类/ID/名称/难度/模态 | 冻结 unit manifest |
| 标签、Prompt、Workspace/Skills/Env/Warmup | 冻结 task.md；Env 仅为题目声明，不读取实际环境变量值 |
| 预期行为、评分标准、Automated Checks | 冻结 contract.json |
| 总分、检查点、失分点、裁判判词、执行/评分错误 | 原 execution record、score.criteria 与规则组件；不产生新判分 |
| Token、请求、工具次数、双耗时 | 原资源指标及已验证补采，未知不补零 |
| 执行记录(jsonl) | 原回传包 unit 下标准 transcript 路径引用，避免整段轨迹塞入单元格 |
| 超时、多轮统计、根因分析、工具质量比率 | 本版不加入：分别为不适用、缺少多轮契约、未执行分析和用户要求暂缓 |

原始量纲检查点保留原值，组件总分及诊断计数不作为检查点/失分点；总分与最大分差用百分制。有效单元不足两个时“最优单元/最大分差”为 `-`，并列最优全部保留。当前 v8 只有一个单元，最优和分差均为空，不伪造横向比较。多单元行为使用 fixture 验证。

长题面、规则、判词显示最多 550 字符/12 行且明确标记节选，完整值在报告 JSON；JSONL 全文仍保留于原回传。对比得分格使用总分背景色，未复刻常规报告逐检查点富文本局部着色。旧包没有评分题面时相应列显示 `-`。详细映射见 [Skill 字段说明](../../../../../tools/report/skills/general-e2e/report-general-e2e/references/report-data-and-cli.md)。

## 发行与本地产物

发行目录：`report-workspace/general-e2e/releases/general-report-details-20260921`，source revision 为上述实现提交。

- suite SHA：`c215952270623799a3588688bf83b5e97f3fe65d087066380cc2dd0d15af7391`。
- catalog SHA：`48a693aa04c86396151306700733481ad2982b89d66abf8d84278e0bd4ace0bb`。
- report ZIP SHA：`f1568f9a1a06b78eba17055ec740f402dbd184f3e58a961adb6521a8bf05052d`。
- release-root、suite 及七 Skill 验包通过，最终报告由独立解包的 report Skill 生成。

本地原件根：`/Users/gzx/debug-workspace/e2e-evaluate/wb3/v8`。最新报告目录：`p/wb3-v8/reports/workbuddy-details-v050/`。

- 报告 JSON SHA：`3a994252205dc4dc0e8b3ed166760ef1c7c21a46943851527fd7ff9b4fa19347`。
- Excel SHA：`db4662a4fb9edf3b6bf8f6f898f022d5b714ecba4daf8665fbc9c30168f52a2e`。
- 领导版 Markdown SHA：`625b4210064d8cd3184bf62b410f5efd9e879a15b0d119489d3a9a2e8e454c57`。
- 审计 Markdown SHA：`9df8f9df7ffe08fdcb6d29daf621f2ba97ef720dc87d02c20840e73156b3666a`。
- 新报告回执已登记，`recommended_actions=[]`；沿用已选回传包 `e153170edbf98413fe0e250fc1f602fa989da5297300f6a16d507cd7f6e311df`，不需要重新打包执行/评分证据。

## 验证

Python report/views/build/layout/run 60/60；清理声明字段代码围栏后 views 12/12；Node 语法、布局与 diff 检查通过。新增覆盖：多单元一题一行、有效零分、并列最优、无效/缺席单元、单单元不排名、题面身份与 SHA 漂移、同题定义冲突、Sheet 名长度/重名/非法字符、组件总分与诊断计数过滤。

`report-details/before.json` 与 `verification.json` 记录 1055 个旧文件 SHA 不变，原得分、资源值与 lineage 均与 v042 一致。`verify-publication.py` 独立解析最终 XLSX，确认十张表顺序、九张数据表的 360 个单元格与 JSON 一致，工具数与效率数据对账通过。最终工作簿 10 Sheet、10 个关键范围、公式错误 0；新总览、对比表、评分详情及局部放大预览已检查。旧 v042 与开发预览均保留。

5/5 valid、总平均分 82.75、21 个模型响应、19 次工具调用及原生/流程耗时均不变。平台集成进度、原生三路并发和其它 Harness 的准入状态不因本次报告改造而提升。
