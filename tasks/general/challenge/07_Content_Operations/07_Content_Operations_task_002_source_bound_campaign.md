---
id: 07_Content_Operations_task_002_source_bound_campaign
name: 古籍素材到多渠道内容方案
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
  - general-challenge
judge_evidence:
  required:
    - path: results/campaign.docx
      role: candidate_deliverable
    - path: results/citations.csv
      role: candidate_deliverable
    - path: results/calendar.xlsx
      role: candidate_deliverable
dataset_report: {"category": "content_operations", "category_name": "内容创作与运营", "category_order": 6, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["content_generation"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["content_generation"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 古籍素材到多渠道内容方案

## Prompt

研读八段古诗素材，为「把古诗读进日常」形成三个主题与三渠道内容方案。解释引文与选题的关联，不能编造古语、错配作者，或把同一正文机械截断。

先读/tmp_workspace/brand_brief.md、channel_rules.json和acceptance.md，再读source_texts/catalog.json与S01至S08.md。素材已在作者端核对固定网页转录版本、作者及异文，离线使用；未核纸本校勘版本的缺口也已标明，不能宣称你核过纸本。原作公版与现代网页译注版权分开，文案自行释义。

交付/tmp_workspace/results/campaign.docx、citations.csv、calendar.xlsx。Word含三个不同主题，每主题论点、至少两处素材依据、自己的释义、选题关联和延伸边界；全案至少六个source_id。每主题分别写公众号C1、小红书C2、短视频C3，共P11至P33九条。按acceptance的稳定编号与字段写可编辑原生段落/表格；其它措辞、选题、版式可不同。各条有标题、完整正文、标签、引文编号和适配说明，长度与结构以channel_rules为准。原句用“”括起，与个人读法、现代建议分开。

CSV记录实际原句、source_id、作者、版本、相邻行号、素材文件SHA和Word内容编号定位。所有引文必须来自给定行，不能引用记忆中未提供的版本；引用匹配忽略标点与空白，不替换简繁或异文。版本和作者不能用来源编号存在来蒙混。

Excel一条对应一篇，共九条一次性发布建议，原生日期或完整ISO日期均可，遵守2026年11月2日至8日、每日最多两条和同日同渠道最多一条。时段、虚构编辑角色、待人工确认状态和引用编号一并交接。不固定参考排期；无公式也有效，有公式须能被预置Office实际重算，不能依赖旧缓存。

只读取本题exec映射到/tmp_workspace的材料，GT不提供；全部新产物写results，保护输入不改。不联网、登录真实账号、发消息、实际发布或设置定时/循环任务。一次性日历只是建议，没有执行授权。使用已有原生办公读写/渲染能力，不安装外部依赖；若能力缺失须如实报告。区分事实、编辑读法、建议和未知，不虚构已核版本、效果或已完成操作。

评分端支持单表不超过3000行、100列的原生日历布局；合法但超出此读取profile的工作簿保留为未评估，不能据此补能力零分。
禁用表达不得用于各渠道标题和正文；主题边界说明中的明确否认须与肯定营销承诺区分，不能只按词语出现断言语义违规。

## Expected Behavior

形成有原文依据且适配三渠道的三主题九文案，交付原生Word、可追溯CSV和一次性Excel建议，不虚构引文或实际发布。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 43个固定规则机会：9条的结构/引用事实/实际原句/引用关系各4项，3主题的字段与多素材依据各2项，以及全案至少6段素材；语义不由关键词替代。
- [ ] `boundary_cases`: 48个固定机会：9条各4项渠道字数/标题/结构/标签禁用表达，3组非同文前缀，9条一次性日期容量与待人工确认状态。
- [ ] `delivery_integrity`: 三份原生文件可解析和实际Office可打开、输入SHA、9条日历跨产物图、可见Word记录与CSV字段；.35/.25/.25/.15。
- [ ] `evidence_binding`: 9条各有实际素材SHA与Word正文定位，共18个固定绑定机会。

### Judge group

- [ ] `decision_grounding`: 针对“古籍素材到多渠道内容方案”的结论、取舍和未决项是否由本题材料/独立oracle支持。 直接读冻结八段原文与三个原生交付。核三个论点、自己的释义与现代建议是否有据且边界明确；八位source不需全部使用，但每主题至少两段、全案至少六段。核古语真实性、作者/版本、S01年数异文、S03秋景、S05送别语境、S08不等于读书无用。检查三渠道是否各有实际重写和可用结构，字数达标与自动前缀检测不替代语义适配。允许不同主题、措辞、合法排期与文件版式，不按参考文案或排期匹配。一次性建议不等于已发布或自动任务。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 直接读冻结八段原文与三个原生交付。核三个论点、自己的释义与现代建议是否有据且边界明确；八位source不需全部使用，但每主题至少两段、全案至少六段。核古语真实性、作者/版本、S01年数异文、S03秋景、S05送别语境、S08不等于读书无用。检查三渠道是否各有实际重写和可用结构，字数达标与自动前缀检测不替代语义适配。允许不同主题、措辞、合法排期与文件版式，不按参考文案或排期匹配。一次性建议不等于已发布或自动任务。

## Automated Checks

```python
def grade(**kwargs):
    import runpy
    from pathlib import Path
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace')
    helper=root/'gt/grader.py'
    if not helper.is_file() or helper.is_symlink():raise RuntimeError('H058_GT_REQUIRED: grader.py')
    result=runpy.run_path(str(helper))['grade'](workspace_path=str(root),transcript=kwargs.get('transcript'))
    return {'business_correctness':result['business_correctness'],'boundary_cases':result['boundary_cases'],
            'delivery_integrity':result['delivery_integrity'],'evidence_binding':result['evidence_binding'],'overall_score':result['overall_score']}
```

## LLM Judge Rubric

### Criterion 1: 原文支持与渠道适配 (key: decision_grounding, weight: 0.7)

判据：针对“古籍素材到多渠道内容方案”的结论、取舍和未决项是否由本题材料/独立oracle支持。 直接读冻结八段原文与三个原生交付。核三个论点、自己的释义与现代建议是否有据且边界明确；八位source不需全部使用，但每主题至少两段、全案至少六段。核古语真实性、作者/版本、S01年数异文、S03秋景、S05送别语境、S08不等于读书无用。检查三渠道是否各有实际重写和可用结构，字数达标与自动前缀检测不替代语义适配。允许不同主题、措辞、合法排期与文件版式，不按参考文案或排期匹配。一次性建议不等于已发布或自动任务。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 内容交接可用性 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 直接读冻结八段原文与三个原生交付。核三个论点、自己的释义与现代建议是否有据且边界明确；八位source不需全部使用，但每主题至少两段、全案至少六段。核古语真实性、作者/版本、S01年数异文、S03秋景、S05送别语境、S08不等于读书无用。检查三渠道是否各有实际重写和可用结构，字数达标与自动前缀检测不替代语义适配。允许不同主题、措辞、合法排期与文件版式，不按参考文案或排期匹配。一次性建议不等于已发布或自动任务。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
workspace/general/challenge/07_Content_Operations/07_Content_Operations_task_002_source_bound_campaign
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 严格对应order58；L3为设计预估未做多模型实测，900秒为元数据。
- A=.55业务+.25边界+.15交付+.05证据，43/48/18固定机会；S=.70 decision_grounding+.30 usable_handoff，正式总分=.65A+.35S，仅生产hybrid评分器合成。作者仅跑规则不运行Judge/finalize。
- 八段原文、作者和网页版本先于参考，经固定revision逐行与不同出版方原文/作者两路径复核；异文差异不伪称一致。同一作者完成，不宣称人类盲审或已核纸本。
- 原作公版说明与现代整理译注版权分开；只发布古代原文、自行分行/释义和来源版本，不复制现代译注。联网仅作者素材核验，候选全程离线。不可访问与核验脚本失败均保留，不把摘要当已读。
- Word使用可见原生文字、Excel支持位置/工作表/行列次序等价；两套不同主题表述、九条文案和合法排期作为规则正例。语义支持与实际渠道重写交由独立Judge，不把规则满分宣称最终混合满分。
- 实际锁定LibreOffice和系统字体，Word转PDF，XLSX清缓存实际重开重算；静态日期允许，参考未要求虚构公式。渲染与派生证据写Worker临时/派生目录，候选冻结文件不变。
- 缺可信GT/库/Office/font/Worker或可信操作超时为评测异常；候选缺失/损坏原生文件、错误引用/排期按对应机会失分。只证明现有运行环境，不证明四端Harness可用或其它OS。
- 日历仅一次性建议，未创建任何定时任务或真实发布；受管作者控制不等同候选Harness轨迹。
- 来源原型与本题素材复核均为模型执行的作者审阅/独立路径计算，没有人类专家或盲审记录；历史蓝图人工复核字串不作为人类审核证据。此澄清仅外部元数据，不改原文、GT、参考与已运行规则。
- root v2修正合法大坐标日历被size ValueError误归候选损分；旧353文件冻结与26控制保留，当前仅受影响正例/typed重跑，不冒称26全部当前版本。
- 澄清既有词表在渠道标题/正文中的禁用与主题边界明确否认的区别；参考没有肯定疗效承诺，完整含义由35%Judge审阅。
