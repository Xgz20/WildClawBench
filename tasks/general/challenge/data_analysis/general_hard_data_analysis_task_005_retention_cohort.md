---
id: general_hard_data_analysis_task_005_retention_cohort
name: 用户流失口径核验与队列复算
category: data_analysis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
judge_evidence:
  required:
    - path: results/cohorts.xlsx
      role: candidate_deliverable
    - path: results/anomalies.json
      role: candidate_deliverable
    - path: results/report.html
      role: candidate_deliverable
scoring_runtime:
  office: true
  html_render: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 用户流失口径核验与队列复算

## Prompt

请重建新老用户D1流失曲线，并核实旧看板的异常日期。交付应让同事能从分子、分母和原始用户/事件明细复核结果，不能只修改图形。

输入为/tmp_workspace/events.csv、/tmp_workspace/definitions.md和/tmp_workspace/old_dashboard.xlsx。按definitions.md的R-clean、R-active、R-cohort和R-dashboard规则处理全部给定历史，汇总2026-09-01至2026-09-15的new/old两类。分析截止为2026-09-15T23:59:59+08:00，业务日统一Asia/Shanghai；不能用截止后的事件补齐观察窗口。received_at只是接收元数据。输入已覆盖本题人群首次有效活动，无需联网或推测更早注册。

写入三个可用文件，每份不超过5MiB：
1. /tmp_workspace/results/cohorts.xlsx：原生可编辑的30条日期×队列汇总，含metric_date、cohort、denominator、numerator、rate、observable、reason。rate存比率数值；不可计算用空值/n/a/不适用，不能补0。保留完整底稿：全部1200个record_id/source_row/decision/canonical_record_id审计，全部有效用户日的user_id/activity_date/first_active_date/event_ids/record_ids，以及每个基准日成员的metric_date/cohort/user_id/first_active_date/returned_next/lost/base_event_ids/next_event_ids。source_row是CSV含表头的物理行。未观察成员的returned_next/lost留空，次日证据不能偷用未来数据。
允许完整静态明细或公式，不要求交付代码，不强制动态公式模型。允许Sheet改名、行列重排、平移、同Sheet多表和清楚的中英文等价表头。ID列表可用JSON数组或明确分隔的集合；每个有效用户日/成员至少保留足够的真实规范见证，并能由完整审计重建来源，不要求逐字复制全部见证。汇总与底稿须可见、唯一、互相一致；工作簿自包含，不使用外部数据链接或宏。
decision用active、duplicate_transport、after_deactivation、ineffective、invalid_format、deactivation、after_cutoff、conflicting_event或明确对应的中文类别；分别表示有效活动、相同payload重传、注销时点及之后、业务无效、基础格式无效、成功注销、发生时点超截和同事件ID冲突隔离。reason正常留空，空队列用empty_cohort，观察未完成用unobserved，或明确中文等价类别。
2. /tmp_workspace/results/anomalies.json：顶层含analysis_cutoff、business_timezone和anomalies数组。每项含metric_date、cohort、mechanism、old与corrected（各有numerator/denominator/rate）及evidence。mechanism使用duplicate_event_rows（重传记录计权）、utc_day_cutover（UTC切日错误）、wrong_cohort_denominator（错误队列分母）或other，不能只因曲线同形判同因。evidence包含affected_users、trace_ids、record_ids、event_ids；可加source_rows，必须定位真实材料。受影响用户须形成完整、明确的对象集合；分母混用时可清楚标示正确基准集合、错用集合或两者并集。trace要选能直接支持机制的lost/return_evidence/denominator等行，并由真实CSV事件共同支持，不能只列无关base凭证或复制ID装饰。
3. /tmp_workspace/results/report.html：离线展示新老流失曲线，横轴明确基准日，纵轴有数值刻度，图例或标题区分队列，可同图或分图。不可适用和未完成观察点留缺口，不画成0、不连接跨越缺口。配一张可见的30条每日数值表，至少有日期、队列、分子、分母、比率及观察状态，与工作簿/JSON一致。异常用带日期的小节或可见明细表，写出旧/新分子分母（可用X/Y表达），至少一组直接相关的trace_id、record_id和event_id示例及依据；完整集合可在JSON及底稿回查。说明截止时点、去重/时区/首次日与观察限制，保留真实变化，不从处理凭证推断营销、停机或用户行为因果。
可用内嵌SVG、Canvas等合理图表；文件中放入正确隐藏JSON不能代替可见表/图正确。不得依赖CDN、远程脚本或外部字体。全部输入只读，全部新交付写results，不连接真实账号、不发消息、不执行真实业务。保存前复核唯一集合、分子分母、空值与跨文件一致性。评分在独立副本清缓存实际重算并检查离线渲染，不改原交付。

## Expected Behavior

按实际事件清洗及上海日重建完整用户日、首次日和基准成员，复算30个新老D1指标；区分三项旧处理异常、真实变化、空队列和未观察，交付可复查原生底稿与真实离线曲线。L3为设计预估。

## Grading Criteria

- [ ] `business_correctness`: 重建新老用户流失曲线，定位异常日期，交付按队列复算的分子分母和解释，不仅改图形。
- [ ] `boundary_cases`: 逐项识别并正确处理：把新增用户当活跃存量；事件重复；图对而底稿错。以独立反例验证，不只检索关键词。
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
workspace/general/challenge/data_analysis/general_hard_data_analysis_task_005_retention_cohort
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 线上需求只保留脱敏用途原型，1200条事件及216条旧凭证全部合成。SpreadsheetBench仅作方法参考，L3、模型/组合区分度与四端兼容性均待实测。
- 原118材料与179 HTML SDK证据绑定保留不变。新增runtime/scoring_contract为本题评分权威；评分侧使用冻结Office及HTML Node/Playwright/Chrome锁，不向候选Env注入。
- 四项按.55/.25/.15/.05加权。业务比较汇总、成员、首次日、JSON数值机制和实际曲线；边界分组平衡事件判定与空值/未观察，不能让大量简单有效行淹没少量冲突/注销边界。
- 允许完整静态可复算底稿和足够真实见证，不沿用H020全公式/数值干预契约。图形从实际日期/比率刻度、队列图例及原生笔画/截图像素推断，不固定作者选择器、viewBox或坐标。
- HTML可见异常证据须在对应日期小节或明细行，核对旧/新分子分母及直接role对应的真实trace-record-event，不用全页关键词列表代替。开放措辞风格、任意经营因果和原生应用交互不在自动规则证明范围。
- 缺少完整事件/用户日/成员底稿时业务分最高.5；输入变化使边界、交付和证据为0且业务最高.5。缺GT/依赖/锁漂移、合法但未支持的坐标轴/图例或渲染形式保持evaluation_error/null，不补候选零分。
- 900仅为任务元数据，不作为能力评分扣分条件。作者正反例、实际Office/浏览器和受管规则Worker验收不代表真实Harness成绩；正式整版仍需60题完整冻结及后续校准。
