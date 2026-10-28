---
id: general_hard_research_verification_task_007_directed_notice_timeline
name: 定向官网检索：跨部门通知与办理时间线
category: research_verification
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/notice_timeline.xlsx
      role: candidate_deliverable
    - path: results/source_ledger.json
      role: candidate_deliverable
    - path: results/action_plan.docx
      role: candidate_deliverable
scoring_runtime:
  research_sources: true
  office: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.citation_resolution": ["retrieval_verification"], "automated.protected_delivery": ["verification_delivery"], "automated.record_contract": ["data_processing"], "automated.time_and_scope": ["reasoning_planning"], "llm_judge.bounded_conclusions": ["reasoning_planning"], "llm_judge.coverage_and_independence": ["retrieval_verification"], "llm_judge.factual_support": ["retrieval_verification"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 定向官网检索：跨部门通知与办理时间线

## Prompt

请以给定的河北大学三部门官方入口为起点，自行检索2026年九月发布的重要通知，围绕合成学生的关注主题建立可追溯的跨部门时间线和有条件行动计划。先阅读 /tmp_workspace/delivery_contract.md，再结合 /tmp_workspace/official_entries.json、/tmp_workspace/research_window.json 和 /tmp_workspace/user_profile.md 完成工作。

合成画像是河北大学法学院2023级、四年制在籍法学本科生，预期2027届。关注推免、研究生招生与本科教务，但申请意愿、资格、名单、缴费和办理状态均未知，不能替其决定报考或推断已完成。

研究范围为研究生院、法学院、教务处公开站点、目录、详情页和公开附件。学校主站仅可使用 official_entries.json 列明的两个身份核验页；官方法学院别名须有实际链接或导航依据。可用公开搜索、站内搜索或目录导航及其组合自行发现，不预给具体通知URL。不得因同名或相似域名扩大范围。

网页发布日期决定2026-09-01（含）至2026-10-01（不含）的九月发布窗；正文落款、附件版本、实际访问和动作期限各自保留角色与原精度。窗内通知的窗外办理节点可以纳入，必要窗外关联文书须标context_only，不混成九月通知。核验原发/转载、同文书载体、事项、附件和后续阶段，若有明确更正、延期或冲突则追溯证据与适用条件；未发现应说明调查边界，不构造事件或宣称全站不存在。

交付到 /tmp_workspace/results/：
- notice_timeline.xlsx：可提取原生单元格的通知身份、版本/载体、对象条件、日期角色、期限、依赖与状态，允许合理的自由Sheet/列/布局和静态值。
- source_ledger.json：按 delivery_contract.md 的公开结构记录实际发现、读取、来源、文书、事项、主张、行动、关系和未知。carriers[].citations提供短引、实际格式定位和RFC6901 supports_fields；保留搜索候选、实际读取及最终引用的差别。
- action_plan.docx：可提取原生文本的有条件待办、优先级、依赖/互斥路径、冲突或未发现边界与下一步核验，个人状态保留unknown。

不设固定通知、事项、Query或引用数量；调查与证据须足以支撑所选相关事项及重要排除。摘要只支持其明确内容，URL或HTTP200不证明读到正文/原生附件。验证码HTML、登录响应、旧格式不可读等分别记录，不猜附件内容，不复制真实学生个人行。候选不需接入任何专用评分采集器。

所有输入只读，所有新交付只写results；不进入登录/统一认证或私人群，不用真实账号、不发消息、不提交申请注册报名、不调用付费或真实办理接口，不获取/识别/提交验证码或绕过门禁，不运行附件宏或外部链接。不得读取私有GT。保留事实、推断、未知和真实访问时点，不将后取原件称作发布日期当天的历史快照，不补造23:59、时区或确认时长。核心判据来自可提取文本/元数据，不要求额外视觉理解。

## Expected Behavior

从给定官方入口自主发现并实际读取范围内公开通知和原生附件，建立足够但非穷尽的通知/事项/版本和日期证据链；围绕合成2027届法学本科画像给出有条件行动，保留个人状态未知。按公开契约交付三件一致、可复核的原生产物。

## Grading Criteria

### Automated group

- [ ] `record_contract`: 公开JSON schema、实体/CID唯一性、引用图及RFC6901目标；固定结构检查，增加正确padding不稀释错误。
- [ ] `time_and_scope`: 给定公开来源范围、日期角色与原精度、九月网页发布窗、个人状态unknown及日期CID绑定；不把机械通过称为源语义正确。
- [ ] `citation_resolution`: 在评分侧独立取得并生产封存的policy-v2实际源中，按实际HTML/PDF/DOCX/XLSX定位核短引与原生值角色；不使用参考URL白名单。
- [ ] `protected_delivery`: 保护四份输入原字节，三件交付可解析且Office为原生文本/单元格；静态值等价，若有公式须锁定引擎实际重算并读回。

### Judge group

- [ ] `factual_support`: 独立核原件上下文与终态三交付，判断对象、主体、日期角色/精度、数值/单位、版本、主张和引用关系；同一句引用命中不等于支持所有目标。
- [ ] `coverage_and_independence`: 结合完整可观测轨迹判断从三入口自主调查及选取/排除是否足以支撑画像关注主题，区分原件、转载、附件、文书版本与业务阶段，不按URL或事项数计覆盖。
- [ ] `bounded_conclusions`: 核合成画像、未知个人状态、有条件行动与互斥路径，必要前置和后续核查，以及未发现更正/冲突/最新有效状态的调查边界。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import json
    import runpy
    from pathlib import Path
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    rule = runpy.run_path(str(root / "gt/grader.py"))
    result = rule["grade"](transcript=kwargs.get("transcript"), workspace_path=str(root))
    print(json.dumps({"source_author_grade_return": result}, ensure_ascii=False))
    return {key: result[key] for key in ("record_contract", "time_and_scope", "citation_resolution", "protected_delivery", "overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 事实与原件支撑 (key: factual_support, weight: 0.5)

判据：独立核原件上下文与终态三交付，判断对象、主体、日期角色/精度、数值/单位、版本、主张和引用关系；同一句引用命中不等于支持所有目标。

**Score 1.0**: 关键事实、对象与日期角色均可回到实际原件，相关条件与未知准确，没有由摘要、文件名、状态或URL猜正文。

**Score 0.5**: 主要范围和结论有可定位依据，但存在非关键条件、证据或交接遗漏；无核心虚构或明显错配。

**Score 0.0**: 核心来源或事实错误、关键日期/对象错配、缺失内容被虚构，或主要结论与实际原件矛盾。

### Criterion 2: 范围与独立性 (key: coverage_and_independence, weight: 0.3)

判据：结合完整可观测轨迹判断从三入口自主调查及选取/排除是否足以支撑画像关注主题，区分原件、转载、附件、文书版本与业务阶段，不按URL或事项数计覆盖。

**Score 1.0**: 调查覆盖题定入口和主题，所选相关事项与重要排除有依据，文书/载体/事项及版本、独立支持关系清楚；未读或未核范围明确。

**Score 0.5**: 主要范围和结论有可定位依据，但存在非关键条件、证据或交接遗漏；无核心虚构或明显错配。

**Score 0.0**: 核心主题或入口未实质调查，重复载体当多项独立支持，跨事项合并或将窗外发布材料充作九月通知，导致核心范围失真。

### Criterion 3: 有边界的行动结论 (key: bounded_conclusions, weight: 0.2)

判据：核合成画像、未知个人状态、有条件行动与互斥路径，必要前置和后续核查，以及未发现更正/冲突/最新有效状态的调查边界。

**Score 1.0**: 行动主体、条件、日期角色与先后依赖明确，个人状态和意愿保留unknown，冲突或未发现的边界准确，不无条件推动所有路径。

**Score 0.5**: 主要范围和结论有可定位依据，但存在非关键条件、证据或交接遗漏；无核心虚构或明显错配。

**Score 0.0**: 把研究生专属或不满足条件的通知套给画像，擅自判资格/名单/缴费/完成或意愿，虚构延期冲突/确认时长，或把未发现当全站不存在。

## Workspace Path

```
datasets/general-hard/workspace/research_verification/general_hard_research_verification_task_007_directed_notice_timeline
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- source-first非盲模型作者阶段，无人工专家、Harness或Judge验收；L4为设计估计。
- 900仅运行元数据，不作候选能力截止；评分Worker基础设施保护独立配置。
- A=.20记录+.25时间范围+.40定位+.15保护交付；S=.50事实+.30覆盖独立+.20边界；Final=.40A+.60S。独立Judge未完成不生成hybrid。
- 任何参考来源池、65条作者事实、示例引用或参考交付都不是自动答案白名单，不按记录/Query/通知数量机械计覆盖。
- 缺可信源/GT/helper、实际来源取得失败、合法但未支持定位为typed评测异常或待复核，不补候选能力0。
- 来源policy-v2保留实际格式、原始响应、body/part/hash和访问时间；后取原件不证明历史发布日期字节。
- 静态Office等价，公式可选；实际出现时只在独立派生副本用锁定bundled引擎清缓存重算，不用候选缓存冒充真值。
