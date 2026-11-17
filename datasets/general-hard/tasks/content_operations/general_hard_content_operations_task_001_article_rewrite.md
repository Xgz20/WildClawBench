---
id: general_hard_content_operations_task_001_article_rewrite
name: 公众号草稿改写与可复制交付
category: content_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.65
  llm_judge: 0.35
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/article.html
      role: candidate_deliverable
    - path: results/fact_map.csv
      role: candidate_deliverable
    - path: results/edit_notes.md
      role: candidate_deliverable
scoring_runtime:
  html_render: true
dataset_report: {"category": "content_operations", "category_name": "内容创作与运营", "category_order": 6, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["content_generation"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["content_generation"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 公众号草稿改写与可复制交付

## Prompt

请完成以下工作：重写成有明确论点的文章，保留事实和限定条件，交付可直接复制的自包含HTML与事实映射，不调用发布账号。

输入材料：
- /tmp_workspace/draft.md：结构松散且含重复论点的草稿
- /tmp_workspace/facts.csv：允许引用的12项事实
- /tmp_workspace/editorial.md：受众、禁用承诺与HTML约束

交付：
- /tmp_workspace/results/article.html：自包含、可读可复制内容
- /tmp_workspace/results/fact_map.csv：事实到段落
- /tmp_workspace/results/edit_notes.md：结构调整依据

约束：
- 仅读取本题exec映射到/tmp_workspace的材料；GT和评分说明不提供给候选。
- 不访问真实账号、不发送消息、不调用真实付费接口；输入和保护文件保持不变。
- 结论区分事实、推断和未知；不得虚构缺失信息。
- 所有新交付写入/tmp_workspace/results；原输入只读，不删除或覆盖。
- 离线完成，不访问网络。

请完整阅读editorial.md的16项事实/限定映射、正文结构和HTML约束；它是本题公开交付合同。源数据为原创合成试点，不是实际公司或性能证明。字数建议700–1300，允许600–2000非空白字符；使用一个h1、至少三个带h2的论证部分与可选择的原生文字。fact_map逐条列F01–F12、Q01–Q04的源短引、唯一HTML id和正文短引；允许换结构/措辞、同段多事实、中文列名、BOM及行列重排。不能只改同义词，不能把计划和未知写成既成事实。

## Expected Behavior

从12事实/4限定重构论证清晰、来源可回查的自包含原生HTML；不夸大、免人工或把计划当执行；不发布真实账号。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 原生正文/标题结构、逐行像素非单色等必要条件与12事实结构覆盖；通过不证明完整可读性、字形绘制或事实语义，实际PNG仍须Judge核验。(weight 0.55)
- [ ] `boundary_cases`: 4个限定的结构覆盖及自包含、无脚本/事件/表单/远程资源；实际含义、夸大和仅润色由语义Judge核验。(weight 0.25)
- [ ] `delivery_integrity`: 三件交付可解析，原输入与修改范围保持；不把单一输入违规归零其它业务项。(weight 0.15)
- [ ] `evidence_binding`: 源短引、唯一原HTML目标及原生文字/逐行像素必要条件绑定；不把定位/非单色当语义蕴含或完整字形证明。(weight 0.05) 每个已声明来源ID为固定检查单元，同源多处引用须全部有效，正确padding不稀释既有错误；缺记录由覆盖项负责。

### Judge group

- [ ] `decision_grounding`: 逐项用F01–F12、Q01–Q04核正文/标题/注释：对象、分母、时间、人工复核口径、计划/未知状态和限制是否正确。拒绝从84/62推出因果、把36/40叫自动准确率、宣称免人工/已全量上线；否定或明确驳回禁止说法不算违规。观察文章是否以清晰论点重组草稿并用证据支撑，而非同义润色/数字罗列。规则结构A不能替代本项语义核验。
- [ ] `usable_handoff`: 独立阅读实际渲染及原HTML、fact_map和edit_notes，判断原生文章能否作为离线可复制交付；定位和编辑说明是否足以复核结构取舍、四限定、删除/降级的无依据主张和未决事项。不得因文件存在/自述已复制给满分，也不要求访问真实公众号或唯一参考配色/标题。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib,runpy
    from PIL import Image
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    helper=root/"gt/grader.py"
    if not helper.is_file() or helper.is_symlink() or hashlib.sha256(helper.read_bytes()).hexdigest()!="23627f3bae4ca790283386ac242b82adcc21ad9adfdf9d0e3e39543a694744f5":
        raise RuntimeError("H057_TRUSTED_HELPER_MISSING_OR_DRIFT")
    result=runpy.run_path(str(helper))["grade"](workspace_path=str(root))
    return {"business_correctness":result["business_correctness"],"boundary_cases":result["boundary_cases"],"delivery_integrity":result["delivery_integrity"],"evidence_binding":result["evidence_binding"],"overall_score":result["overall_score"]}
```

## LLM Judge Rubric

### Criterion 1: 事实依据与论证重构 (key: decision_grounding, weight: 0.7)

判据：逐项用F01–F12、Q01–Q04核正文/标题/注释：对象、分母、时间、人工复核口径、计划/未知状态和限制是否正确。拒绝从84/62推出因果、把36/40叫自动准确率、宣称免人工/已全量上线；否定或明确驳回禁止说法不算违规。观察文章是否以清晰论点重组草稿并用证据支撑，而非同义润色/数字罗列。规则结构A不能替代本项语义核验。

**Score 1.0**: 事实对象和口径正确、四限定均明确，未知和待批状态准确；主论点/证据/行动形成连贯论证，无禁止主张或虚构。

**Score 0.5**: 主论点和关键事实正确，无核心夸大；一项非关键事实/解释或段落衔接不充分。

**Score 0.0**: 关键事实/分母/状态被改写，关键限定丢失、核心禁止主张未明确驳回，或仍是重复口号、未实质重构论证。

### Criterion 2: 可用交接 (key: usable_handoff, weight: 0.3)

判据：独立阅读实际渲染及原HTML、fact_map和edit_notes，判断原生文章能否作为离线可复制交付；定位和编辑说明是否足以复核结构取舍、四限定、删除/降级的无依据主张和未决事项。不得因文件存在/自述已复制给满分，也不要求访问真实公众号或唯一参考配色/标题。

**Score 1.0**: 正文可读、层次和定位清楚，编辑说明具体并与成稿一致，未决/后续动作准确，不依赖聊天补充或远程资源。

**Score 0.5**: 主要内容可用可复核，但一个非关键定位或交接说明欠清楚，不影响核心使用。

**Score 0.0**: 主要交付不可读/正文为图片或隐藏内容，事实映射/说明与正文矛盾或主要定位不可用，必须靠聊天才能使用。

## Workspace Path

```
datasets/general-hard/workspace/content_operations/general_hard_content_operations_task_001_article_rewrite
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 视觉输入为0；评分器浏览HTML不改变题目模态。
- 自动.65/语义.35，结构/定位/原生渲染不等于事实蕴含或好文章；作者只A组件，Judge/S/hybrid均未运行。
- 两条源先行计算路径在参考前冻结，模型作者与计算复核非人工专家。
- 允许合法不同结构/措辞/ID/版式，不能按参考文章字面给分。
- 锁定既有Node/Playwright/Chromium离线观察原HTML；无安装、真实平台复制/发布或消息。
- 缺GT/锁/浏览器/观测能力保留typed异常；L2难度和四端兼容待实测。
- v3仅加实际PNG严格单色、逐行同色及已观测透明前景的必要条件。非单色不等于可读，禁止把A1解释为完整paint/语义通过；独立Judge必须看实际PNG。合法透明复合文字超出受支持面时typed待审而非0。
