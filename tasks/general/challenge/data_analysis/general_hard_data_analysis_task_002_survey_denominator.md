---
id: general_hard_data_analysis_task_002_survey_denominator
name: 问卷口径、缺失值与加权汇总
category: data_analysis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 问卷口径、缺失值与加权汇总

## Prompt

请完成服务体验问卷的清洗、题级原始/加权比例分析及可追溯报告。全部材料为合成练习，统计截止时点固定为2026年9月30日23时59分59秒（+08:00）。

读取/tmp_workspace/responses.csv（240条提交）、/tmp_workspace/codebook.xlsx（题目、规则、指标）和/tmp_workspace/weights.csv（四层固定权重）。以代码本为业务口径：先判断整条资格，再按规范化受访者ID选择最新有效提交；同时间以较大record_id数值后缀决定。不能按CSV物理顺序取最后行，无效晚提交不会替换较早有效提交。按题处理路由、缺失、非法编码及多选，不能统一用总保留人数当全部分母，也不能因一题无效删除其余有效回答。

交付三份真实文件：
1. /tmp_workspace/results/analysis.xlsx：清洗记录保留全部240原始行及原字段，时间原文和时区、原ID/大小写/空白保留，规范化值另存；原数字回答编码可用等值数字单元格。含keep、reason、related_record_id。题级底稿应能按record_id回查保留记录、规范化受访者/分层、weight及各题有效/命中标记；可以和清洗记录合表，也可用带marker_key/marker_value的长表。原始q2_sat评分与满意命中标记需清楚区分，合表时可将后者命名q2_sat_flag。标记包括q1_valid/q1_yes、q2_valid/q2_sat、q3_valid/q3_A/q3_B/q3_C/q3_D/q3_N、q4_valid/q4_yes，允许语义等价中文表头。
提供按stratum/weight可发现的真实可编辑数值权重入口；若保留固定源权重快照或展示代理，应标明实际使用入口。按代码本8个metric_id，用公式报告raw_num、raw_den、raw_rate、weighted_num、weighted_den、weighted_rate，比例以0至1保存，可用百分比格式显示。底稿标记可用数值、布尔或普通标量公式，不要求指定公式或作者坐标。改变权重或题级标记后，对应汇总应更新；本题不要求自动重新清洗原CSV、重新判定去重或改写Word。全权重为0时加权分子和分母为0，加权比例显示n/a或不适用，不能补0比例。相关底稿、汇总和权重入口保持可见可复查。工作表名、行列序和合理布局不限。
2. /tmp_workspace/results/summary.docx：原生可编辑报告，用可复查表格给出全部8指标的原始分子、有效分母、原始比例和加权比例（可到0.1个百分点），以及原始提交数、保留人数、整条无效数、被替代数、全部整条排除数。按原文引用代码本R-scope和R-multi，并标明规则ID和来源。关键数字与当前保存的analysis.xlsx一致，不把固定自选样本推广成总体无偏或因果结论。
3. /tmp_workspace/results/exclusions.csv：UTF-8，至少含stage,record_id,respondent_id,source_row,reason,related_record_id。未保留提交各有一条record层排除；保留但某题无效/不适用的回答另以Q1至Q4层记录。source_row指responses.csv真实物理行；superseded关联到保留提交，其余related_record_id空白。名称存在不等于定位正确，不静默丢弃跳题或未决信息。

三份输入只读，所有新交付写入results，离线完成；不访问真实账号，不发消息或调用付费接口，不执行真实业务。每份交付不超过5MiB，不要求交付代码。保存后验证数字、范围、公式、排除定位和文件实际可读性。

## Expected Behavior

按原始来源保留、整条资格/最新有效提交/逐题路由与缺失口径形成底稿，原始和加权六类汇总使用可重算公式，保留完整排除关联，报告真实基线和源限制。L2仅设计预估。

## Grading Criteria

- [ ] `business_correctness`: 去除无效重提交，按题目口径计算原始和加权比例，生成报告及可追溯底稿，禁止统一用总人数当全部分母。
- [ ] `boundary_cases`: 逐项识别并正确处理：忽略跳题；重复计数；加权与原始比例混淆。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    import pypdf
    import pdfplumber
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:scores[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/data_analysis/general_hard_data_analysis_task_002_survey_denominator
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- GT由真实CSV和代码本两路径读取、独立去重/SQL窗口与多选拆分、Decimal/Fraction计算形成，先于最终参考；不从候选或参考实现反推真值。原137材料与155 SDK验收绑定保留。正式权威为runtime_contract/scoring_contract及绑定helpers，旧材料pending记录为历史。
- 按.55/.25/.15/.05汇总。原始行集合/原文、保留模型集合或基本可见性破坏时业务分最高.5；输入改动使边界/交付/证据为0。缺GT/helper/运行时/字体锁漂移及未支持的合法干预结构保持评测异常，不补能力零分。
- 基线完整正确后才给公式依赖验证分。用实际Office清缓存重算基线和四组响应；对30条题级记录干预所有12标记（含原值0的公式），360格分四步重放，语义非零变化142格。只测试汇总函数，不要求重新清洗原始CSV或改写Word。
- 行列序/Sheet名、明确中文/英文表头、宽表/长表、合并清洗/模型、转置权重、源快照、普通标量公式及合法标记表示均允许，不强制作者XML坐标。普通数值输入Profile保持原协议；真正权重源不由展示代理猜测。
- core0.13标记Profile支持普通标量公式与二进制数值/布尔/文本。共享/数组/元数据型标记、不能独立寻址的合并标记、接口未覆盖的正确输入形式保留运行时能力异常，不给合法候选补0。四端仍需预检和校准。
- 自动规则核数字、集合、源关联、指定原文引用和有限可见性；不构成完整视觉/开放语义评价。实际发送或对外动作必须查绑定执行轨迹，文件自述不证明发生。
- Word使用锁定引擎/字体渲染，派生文件在冻结Workspace外，不改原报告。没有人工专家或独立语义Judge成绩；900为元数据，不设置候选总执行截止。
