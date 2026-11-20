---
id: 01_Office_Documents_task_016_docx_structure_repair
name: 长文档结构修复与引用完整性
category: office_documents
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general-hard
  - general-challenge
judge_evidence:
  required:
    - path: results/repaired.docx
      role: candidate_deliverable
    - path: results/repair_log.json
      role: candidate_deliverable
    - path: results/readme.md
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 长文档结构修复与引用完整性

## Prompt

请修复/tmp_workspace/damaged_styles.docx的标题层级、编号、目录、表题和交叉引用。依据/tmp_workspace/style_reference.docx和/tmp_workspace/protected_content.json，只修复文档结构及相关显示，保留全部原业务正文、段落及表格顺序、表格数据、原有批注与同一原文选区。材料为虚构文档管理练习，离线完成。

原稿18页，内容完整，结构存在12处根缺陷；修复后允许合理分页变化。规范要求26个标题（12主章、9个二级、2个三级、3个无编号附录），主章和小节接在同一可连续维护的原生多级编号链上，5个办理步骤使用独立连续列表。标题采用原生段落样式及相符的大纲层级，不能仅靠字号或手写数字伪装。附录保留一级标题语义但不参加主章编号。

目录保留原生可更新TOC域，覆盖三级标题与三个附录；26个条目的文字、层级、原生页引用及内部跳转均对应实际标题。表T01-T06各有原生Table SEQ表题，按全文顺序连续1至6，不能混入Figure计数或中途重置。正文三处REF分别应指向采样复核记录的表号、资料类别与保留范围的表号、异常与未决事项的章号；目标存在还必须与引用内容相符。更新域后显示正确，不能用静态数字代替可维护关系，也不能只修缓存。

公开P0001等段落书签及表格替代文字标题中的T01-T06身份必须保留；允许等价的样式ID、编号ID、内部数值bookmark/comment ID和内部表号书签名。段落书签是身份锚点，不要求每个都覆盖整段。原批注正文、作者、时间、状态及所选原文字符范围均保留；允许等价时区表示和新增独立修复批注。正文事实、空白、零和待确认状态不能改写；不添加新的业务结论，不留下未处理修订。

交付三份真实文件：
1. /tmp_workspace/results/repaired.docx：结构完整、原生可编辑、可阅读的修复文档。无需复制规范版式或作者XML坐标，保留业务内容、关系和顺序。
2. /tmp_workspace/results/repair_log.json：JSON对象包含repairs数组；每项有source_file、source_locator、result_file、result_locator、action、preservation，可附自定repair_id。定位使用公开段落/表ID、标题文字、TOC条目或等价可复查的原生字段对象；源为damaged_styles.docx、结果为repaired.docx。逐项或合理合并记录实际问题、修复节点、动作及保留范围，不要求恰好12行，也不要求猜测私有缺陷ID。仅写“已经修复”或不存在的位置不足以核验。
3. /tmp_workspace/results/readme.md：写明打开文件、更新全部域和整个目录的方法、批注检查方法、已经验证及尚未验证的环境和限制。不能在未实际验证时声称Microsoft Word GUI或四个客户端已全部验证。

原三份输入保持只读，所有新交付写入results；不访问网络、真实账号或付费接口，不对外发送或执行真实业务。

## Expected Behavior

保留全部业务内容与六批注原文范围，恢复原生样式/编号/TOC/SEQ/REF关系、正确实际显示及可复查修复记录；诚实说明验证环境边界。难度L4为设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 修复标题层级、编号、目录、表题和交叉引用，同时保持正文、批注和表格数据；交付修复日志和可复查版本。
- [ ] `boundary_cases`: 逐项识别并正确处理：重排内容掩盖缺陷；引用指向失效；批注丢失。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 检查修复日志是否忠实描述实际源缺陷与结果，是否有遗漏或虚假修复，批注及正文的业务限定是否保留；特别核对已有但无关的引用、未知/未决状态和未实施的Word GUI或四端验证主张。
- [ ] `usable_handoff`: 打开实际交付及全部派生页，检查文字、表格、目录、跳转和批注是否可复查；核对遮挡、对比度、版式及更新说明。规则的PDF文本/页边界检查不能替代逐页视觉审阅。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    import pdfplumber
    import pypdf
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    required={"business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score"}
    if set(scores)!=required:raise ValueError("H016 scoring key mismatch")
    return scores
```

## LLM Judge Rubric

### Criterion 1: decision_grounding (key: decision_grounding, weight: 0.7)

判据：检查修复日志是否忠实描述实际源缺陷与结果，是否有遗漏或虚假修复，批注及正文的业务限定是否保留；特别核对已有但无关的引用、未知/未决状态和未实施的Word GUI或四端验证主张。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: usable_handoff (key: usable_handoff, weight: 0.3)

判据：打开实际交付及全部派生页，检查文字、表格、目录、跳转和批注是否可复查；核对遮挡、对比度、版式及更新说明。规则的PDF文本/页边界检查不能替代逐页视觉审阅。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
workspace/general/challenge/01_Office_Documents/01_Office_Documents_task_016_docx_structure_repair
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- GT来自先形成的干净合成原稿及独立原生/库读取和真实固定Office渲染，随后注入12处源缺陷。材料构造规格为历史记录，候选评分以scoring_contract及其源码绑定为准。
- 允许等价样式/编号/书签与评论ID、原生simple/complex域、内容控件包装和合理日志合并；不强制作者物理XML坐标、内部CAP名字或固定18页。
- 规则按0.55/0.25/0.15/0.05汇总。业务正文、数据、顺序、批注或可见性被破坏时，business_correctness最高0.5，delivery_integrity为0；其它检查仍按观察返回。
- 评分侧固定Office字体/引擎渲染且派生证据在冻结Workspace之外；缺GT/helper/声明依赖、锁漂移、规则崩溃或渲染基础设施失败属于评测异常，不能补能力零分。
- 规则满分不能证明日志真实性、视觉可用性或所有业务限定正确。语义Judge必须读真实文件和全部页，并核对虚假GUI/四端兼容主张；作者控制不等于独立人工专家或真实Harness评测。
- 900为任务元数据，不设置候选执行总截止。四端未实测，整体60题与冻结/校准仍待完成。
