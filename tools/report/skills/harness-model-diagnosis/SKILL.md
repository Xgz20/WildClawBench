---
name: harness-model-diagnosis
description: 从 WildClawBench 现有评测结果诊断指定 Harness 或模型的问题、能力短板和资源优化项，结合跨单元统计、原始轨迹及可选源码核验，输出带 run_id 的 Markdown 诊断或研发排查报告与可复算数据。用于“这个 Harness/模型有哪些问题、如何改进”，不替代两单元分差报告。
---

# Harness 与模型诊断

分析对象是指定 Harness 或模型，评测单元是证据来源。支持只指定一个目标或同时指定两类目标，不把目标诊断改成两单元排名。

只读原始结果和源码，不因诊断而重跑、重评、修改实现或覆盖历史报告。需要修复实验时提出可执行验收方案，待获得授权后执行。当前源码不自动代表历史评测二进制。

## 范围与证据

输入：结果根目录、目标 Harness/模型（至少一个）、可选模型与 Harness 范围、任务范围、源码目录和输出目录。

1. 明确证据面：默认 `target-union` 是“目标 Harness 的所有模型 **或** 目标模型的所有 Harness”。用户要求整个选定矩阵时用 `selected-matrix` 并显式列出模型和 Harness，不能把 5 单元十字对照说成 9 单元全矩阵。
2. 使用共享有效 run 选择规则；分离被重跑替代的历史 run、重复样本、执行状态、评分可用性与异常。用户明确要求重跑前后都分析时，另列历史样本，不把它们悄悄混入当前有效 run 总分。
3. 全量结构化扫描后，再深读有分差、共性失败、效率长尾及成功恢复/满分反例的任务。分别公布统计扫描覆盖与语义深读覆盖，未深读不等于无问题。
4. 按历史任务、workspace、ground truth、Skill 和评分契约哈希核对可比性；缺失是 unknown。记录 API、端点、输出上限、推理配置、并发、超时、日期、Judge 与版本。相同模型名不等于这些变量均已控制。

仅指定一个目标时默认可能缺少跨 Harness 或跨模型的一侧证据。可在用户给定结果范围内选择明确的对照矩阵；没有对侧就保留缺口，不证明问题为该目标独有。

## 工作方式

- 做根因诊断或研发交接时，先读 [证据与归因规则](references/evidence-and-attribution.md)。它定义工具问题分叉、源码核验、问题账本与 `run_id` 证据契约。
- 建立统计、比较 token/请求/耗时或生成报告时，读 [统计与报告脚本](references/metrics-and-reporting.md)。复用脚本完成资源归一化、配对切片、指纹校验与 Markdown 渲染，避免再次编写针对三个模型的一次性统计逻辑。
- 只请求统计时可以不深挖源码；没有源码/线上请求证据时保留归因边界，不阻断可完成的日志分析。输出统计观察，不伪装成完整根因报告。

默认新产物放在 `<round>/report-workspace/harness-model-diagnosis/<target>/`：

- `diagnosis_profile.json`：选中 run、契约、分数、资源口径及原始文件指纹。
- `diagnosis_analysis.json`：全量汇总、同任务配对及敏感性分析。
- `diagnosis_findings.json`：人工核实的问题、反例、因果边界和验收计划；脚本不自动生成根因。
- `diagnosis_report.md`：按目标组织的中文诊断报告；用户要研发排查材料时使用 `rd_report.md`。

报告包含“确认的问题 / 优化候选 / 尚未证明”，每项有具体统计分母、完整任务 ID、`run_id`、可定位日志、影响和反例。不得只交付聊天回答或 JSON；若用户只需口头答复或指定其他格式，遵循用户要求。统计脚本与结构校验通过不等于模型/Harness 修复实验通过。

## 迁移边界

本 Skill 原名 `entity-eval-diagnosis`。旧发现入口撤下，避免重复触发；历史报告及其 `entity-*` 目录不改名。仓库旧脚本 `tools/report/skills/entity-eval-diagnosis/scripts/build_entity_profile.py` 保留 CLI 和常用函数导入转发。新产物采用 schema v2：不完整资源总量为 null，并给出已知小计/覆盖率；不承诺旧 JSON 的所有自定义字段不变。
