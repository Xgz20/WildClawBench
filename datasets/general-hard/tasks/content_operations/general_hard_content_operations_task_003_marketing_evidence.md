---
id: general_hard_content_operations_task_003_marketing_evidence
name: 营销热点材料的证据分层与选题
category: content_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.65
  llm_judge: 0.35
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/brief.docx
      role: candidate_deliverable
    - path: results/evidence.xlsx
      role: candidate_deliverable
    - path: results/uncertainties.json
      role: candidate_deliverable
dataset_report: {"category": "content_operations", "category_name": "内容创作与运营", "category_order": 6, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["content_generation"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["content_generation"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 营销热点材料的证据分层与选题

## Prompt

请对本批营销热点材料去重、分层并形成热点、竞品动作与2至3个有据选题，只做一次性简报，不创建定时任务。

先读/tmp_workspace/brand_constraints.md与acceptance.md，再读snapshots/S01.md至S08.md和metrics.csv。全部主体、账号、数据和报道均为自有合成材料，不代表现实公司。按事件日期判断本周新旧，不能把转载上架时间当新动作，也不能把媒体/个人意见升级成独立试验或市场需求。

交付/tmp_workspace/results/brief.docx、evidence.xlsx、uncertainties.json。Word区分厂商宣称、媒体/个人观点、编辑推断与unknown，交代为何保留或剔除材料，提出适合20至100人企业行政运营负责人的2至3个选题及优先级理由。允许不同合法主题与排序，不用热度数字代替证据。不得虚构本品牌试验、用户调研、比较性能、定价、采用率、合格线索或商业转化。

Excel用原生表格交接8份来源的直接/追溯转载图、事件组、两种日期、是否本周和独立原始材料数；核对6指标的分子、分母、采样平台/窗口、比例、状态、付费数与指定跨项可比性。支持关系记录实际原文、物理行号、来源文件SHA、判断和Word定位。列名/逻辑表字段以acceptance为准，可分工作表、换位置或重排行列；源引据可通过source_id关联，不能把来源编号当语义支持。原生日期或完整ISO日期可用，正确静态比例可用；公式会清缓存后由预置Office真实重算，不可信旧缓存。

JSON列六类未决问题、来源/指标、unknown状态和可继续办理的人工核验动作；类别标签不是问题解释的替代。0分母与缺失分母分开，undefined、unknown都不能擅填0%，点击、表单提交与付费不得混用。Word、Excel、JSON中的对象、状态和依据相互对应。使用可编辑原生文字/单元格，不用截图或整本JSON单元格代替办公文件。

仅读取本题exec映射到/tmp_workspace的材料，GT不提供。全部新交付写results，原输入只读。不联网、不登录真实账号、不发消息、不买产品、不追加采集、不实际发布或设置定时/循环任务。下一步核验只是交接建议，没有执行授权。使用已有原生办公工具，不安装外部依赖；缺能力如实报告。事实、推断与未知分开，不虚构已经验证或执行的动作。

来源表和支持关系表可以共享引文记录：quote、line_start、line_end、source_sha256可集中放在支持关系表，不要求在来源表重复同一信息；每份S01至S08仍须有实际原文记录并与来源追溯对应。

## Expected Behavior

去重事件与观点，核事件日期和指标分母，交付受证据约束的2至3选题及原生可追溯材料，保留unknown且不执行发布或自动任务。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 64个固定客观机会：8来源各6项追溯/两日期/类型/新旧，4事件分组，6指标各口径身份与比例状态。实际原文是否支持编辑判断另由Judge。
- [ ] `boundary_cases`: 22个固定机会：4组独立原始数、2旧闻、2不可比指标对、0/unknown两边界、6付费未知、6类有结构的未决项；不是关键词替代语义。
- [ ] `delivery_integrity`: 原生解析/真实Office(.35)、保护输入(.25)、4原始组判断到Word定位(.25)、JSON时点与引用结构(.15)。
- [ ] `evidence_binding`: 8来源各SHA、实际原文与实际行区间三绑定，共24固定机会；来源编号存在不等于原文语义支持。

### Judge group

- [ ] `decision_grounding`: 针对“营销热点材料的证据分层与选题”的结论、取舍和未决项是否由本题材料/独立oracle支持。 直接读三份原生产物与冻结原始材料，判断主要主张能否由实际原文支持，而非只检查source_id、quote存在或层级标签。核厂商宣称不等于独立试验/采用、转载不等于交叉验证、旧闻不当新、个人意见不冒充调查、9/12不是准确率/工时，审批CSV不等于合规认证。核互动/点击/提交与付费、不同平台窗口分母、0和unknown的解释。评2至3选题与目标受众、优先级、取舍和核验动作是否有据且可继续办理；允许不同合法题目、排序、版式与数据布局，不按参考措辞匹配。当前不得声称已发布或建立周期任务。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 直接读三份原生产物与冻结原始材料，判断主要主张能否由实际原文支持，而非只检查source_id、quote存在或层级标签。核厂商宣称不等于独立试验/采用、转载不等于交叉验证、旧闻不当新、个人意见不冒充调查、9/12不是准确率/工时，审批CSV不等于合规认证。核互动/点击/提交与付费、不同平台窗口分母、0和unknown的解释。评2至3选题与目标受众、优先级、取舍和核验动作是否有据且可继续办理；允许不同合法题目、排序、版式与数据布局，不按参考措辞匹配。当前不得声称已发布或建立周期任务。

## Automated Checks

```python
def grade(**kwargs):
    import runpy
    from pathlib import Path
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace');helper=root/'gt/grader.py'
    if not helper.is_file() or helper.is_symlink():raise RuntimeError('H059_GT_REQUIRED: grader.py')
    result=runpy.run_path(str(helper))['grade'](workspace_path=str(root),transcript=kwargs.get('transcript'))
    return {'business_correctness':result['business_correctness'],'boundary_cases':result['boundary_cases'],
            'delivery_integrity':result['delivery_integrity'],'evidence_binding':result['evidence_binding'],'overall_score':result['overall_score']}
```

## LLM Judge Rubric

### Criterion 1: 证据分层与选题依据 (key: decision_grounding, weight: 0.7)

判据：针对“营销热点材料的证据分层与选题”的结论、取舍和未决项是否由本题材料/独立oracle支持。 直接读三份原生产物与冻结原始材料，判断主要主张能否由实际原文支持，而非只检查source_id、quote存在或层级标签。核厂商宣称不等于独立试验/采用、转载不等于交叉验证、旧闻不当新、个人意见不冒充调查、9/12不是准确率/工时，审批CSV不等于合规认证。核互动/点击/提交与付费、不同平台窗口分母、0和unknown的解释。评2至3选题与目标受众、优先级、取舍和核验动作是否有据且可继续办理；允许不同合法题目、排序、版式与数据布局，不按参考措辞匹配。当前不得声称已发布或建立周期任务。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 简报与未决项交接 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 直接读三份原生产物与冻结原始材料，判断主要主张能否由实际原文支持，而非只检查source_id、quote存在或层级标签。核厂商宣称不等于独立试验/采用、转载不等于交叉验证、旧闻不当新、个人意见不冒充调查、9/12不是准确率/工时，审批CSV不等于合规认证。核互动/点击/提交与付费、不同平台窗口分母、0和unknown的解释。评2至3选题与目标受众、优先级、取舍和核验动作是否有据且可继续办理；允许不同合法题目、排序、版式与数据布局，不按参考措辞匹配。当前不得声称已发布或建立周期任务。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
datasets/general-hard/workspace/content_operations/general_hard_content_operations_task_003_marketing_evidence
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 对应order59；L3为未做多模型实测的设计预估，900秒仅元数据。
- A=.55业务+.25边界+.15交付+.05证据，固定64/22/24；S=.70 decision_grounding+.30 usable_handoff，正式混合=.65A+.35S，作者不Judge/finalize。
- root模型先合成10输入并用Python/Node独立计算；另一模型先只读10exec、冻结自己的逐源观察后才读truth比对。父任务汇总计数已知，不宣称盲审或人类专家。原10输入字节不改，仅补公开acceptance。
- 4原始组、3转载链、2旧闻、2不可比指标对、6指标含0/unknown在reference前核验冻结；来源编号只定位，语义支持另由35%Judge。
- 两套不同选题数量/排序、列顺序与原生排版；一套比例公式，一套正确静态值。源引据可经source_id合并到逻辑来源表，无固定Sheet/坐标/列顺序。稀疏存储单元格读取不因无值样式在第3001行而候选失分。
- 预置锁定Office/字体实际Word转PDF、Excel清缓存重开；作者另对参考公式做受控数值扰动，记录0与unknown边界，原文件不变。静态值也是合法解，不把参考实验冒称全候选刷新保证。
- 缺可信GT/依赖/Office/font/Worker或可信操作超时为typed评测异常，无能力零分；候选缺失/损坏/不合契约产物按对应机会失分，JSON嵌套字段校验。
- 素材与评审均模型工作，不独立确认原线上自然用户来源；按蓝图保守记为内部评测工作形态参考，重构合成材料，不直接搬题或原分数。
- 原始10输入与事实oracle不变；首次参考后发现合法3.33%文本被过严容差扣分，已真实复现并保留旧GT/合同/attempt。v2只公开澄清比例绝对容差0.00005并修正规则，初始13文件manifest保留，acceptance修订另有前后SHA，不冒称该合同字节从未修改。
- v3在真实合法格式误扣复现后，只补短定位、源式as_of、大小写/空白归一化，并区分计数与比例单位、物理整数行号；旧GT和分版本控制保留。完整36控制单独收口，附加空样式max_row作者假设失败不冒称通过；实际数据平移后3006至3013行的正例另已验证。
- 仅证明本机预置运行环境，不宣称四端Harness或其它OS已通过。离线一次性建议，未发消息、采集、真实发布或创建任务。
- root仅澄清来源表和支持表共享引文元数据，避免要求无业务意义的重复列；既有8来源固定证据单元仍逐一验证，原11exec/23GT/两参考及36控制字节不变。
