---
id: general_hard_data_analysis_task_001_heterogeneous_join
name: 异构工作表字段对齐与匹配审计
category: data_analysis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
tags:
  - custom
  - general-hard
scoring_runtime:
  office: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 异构工作表字段对齐与匹配审计

## Prompt

请把四张不同结构源表中的实际服务记录对齐到目标模板，完成可复查的字段提取与匹配审计。

读取/tmp_workspace/sources.xlsx、/tmp_workspace/target_template.xlsx及/tmp_workspace/mapping_rules.md。来源包含146条合成记录，目标模板120行；按表头组识别实际与预算同名字段，按规则把金额统一为CNY元、工时为小时、记录数为次。需要保留真实零、负调整和缺失值。

目标项目编号非空时，仅使用项目编号加服务月份连接；只有项目编号为空时才能回退到合同编号加服务月份。具体规范化规则、单位、状态和CSV列以mapping_rules.md为准。编号作为文本保留前导零，不从项目名称、相似度或邻月猜测。不把无法匹配的非空项目号改用合同号继续找。

交付两份真实文件：
1. /tmp_workspace/results/aligned.xlsx：主结果保留全部120个target_id及原五个目标字段，每目标一行，并填写status、match_count、amount_cny、hours、count，或明确等价中文表头。唯一匹配提取值；一对多在主表保留条数并让三项实际值空白，所有来源逐条保留到审计CSV，不求和、不取第一条、不按业务值去重。另有未匹配视图，分别列明未匹配/空键目标和未被任何目标使用的源行，含side、record_id、reason。允许结果行序、列序或工作表名变化，原始目标字段值保持。静态提取结果或正确原生公式均可。
2. /tmp_workspace/results/join_audit.csv：UTF-8，按规则列出每条实际连接、每个未匹配目标和每个未使用源。source_sheet/source_row定位到原输入，target_sheet/target_row定位到实际输出；保留source_id及target_id。相同业务值的两个不同source_id分别记录，未匹配行不静默丢弃。路径或“已核对”自述不能替代实际定位。

在最终保存的文件中核对键集合、状态、数量、单位和定位。三份输入只读，所有新交付写入results。离线完成，不访问真实账号，不发送消息，不调用付费接口或执行真实业务。每份交付不超过5MiB；不要求交付代码，也不要求特定公式或版式。

## Expected Behavior

依实际表头组提取发生值，按项目/月优先与空项目合同/月回退规则连接，保留原目标字段、全部多来源和未匹配记录；实际文件与审计定位一致。L2为设计预估。

## Grading Criteria

- [ ] `business_correctness`: 按规则提取字段填入目标表，保留一对多和无法唯一匹配记录的审计信息，不靠姓名猜测主键。
- [ ] `boundary_cases`: 逐项识别并正确处理：按列位置复制；重名错误合并；静默丢弃未匹配。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:scores[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

## Workspace Path

```
datasets/general-hard/workspace/data_analysis/general_hard_data_analysis_task_001_heterogeneous_join
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 原生输入的两路径读取、Decimal/Fraction单位换算、索引连接与SQLite JOIN在参考前形成GT。参考是一种正确表达，不强制工作表名、列序、行序或作者物理坐标。
- 按0.55/0.25/0.15/0.05汇总。原目标字段、唯一目标集合或基本可见性破坏时business_correctness最高0.5。输入被改则边界/交付/证据为0；缺GT/helper、运行时或引擎锁漂移及规则自身错误保留评测异常。
- 纯自动评分沿用蓝图，无语义Rubric。材料阶段evidence_requirements.json中的semantic_judge:true为作者笔误，已由runtime_contract.json显式更正；旧构造规格按原摘要保留，正式权威为运行时契约与绑定源码。
- 允许静态或实际重算正确的公式。规则先清除公式缓存并在固定Office引擎一次性副本中重算，派生文件在冻结Workspace之外；旧缓存正确不能掩盖实际计算错误。
- 作者预览工具会抑制纯数字文本编号前导零；真实输入、参考及固定Office实际加载另存均保留0001与1的区别。评分以原生数据为准，不以预览显示补改事实。
- 规则核定量字段、完整连接/未匹配集合、原目标值及实际行定位，基本可见性覆盖隐藏Sheet/行/列及部分隐藏格式；这不是完整视觉可用性审查。现实动作和权限约束需绑定执行轨迹，工作簿中的自述不证明已执行。
- 私有validate_authoring.py可用--office-lock、--output-dir与--dataset-workspace复跑独立副本控制，--list-cases只列规格；作者控制需lxml等作者环境，不作为候选或评分运行时依赖。
- 900仅任务元数据，不设置候选执行总截止。四端和实测难度/区分度尚未校准，整版仍building。
