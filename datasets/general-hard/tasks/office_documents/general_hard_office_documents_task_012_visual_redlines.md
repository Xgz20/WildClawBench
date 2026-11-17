---
id: general_hard_office_documents_task_012_visual_redlines
name: 扫描件红线与签章状态核对
category: office_documents
timeout_seconds: 900
modality: multimodal
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/redline_matrix.xlsx
      role: candidate_deliverable
    - path: results/execution.docx
      role: candidate_deliverable
    - path: results/uncertain.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 扫描件红线与签章状态核对

## Prompt

请核对澄岚设备维护协议纸面修订，整理出可复核的差异矩阵和可编辑执行草稿。全部材料为合成离线资料；所有样例章仅按本题规则解释，不作现实法律效力判断。

读取 /tmp_workspace/unsigned.docx、/tmp_workspace/authority.md，以及 /tmp_workspace/signed_pages/scan_01.png 至 scan_05.png 五张原始图。底稿仅作版本对照，红色提议、勾选、局部确认、划销和条件以实际原图为准。必须逐张实际查看图片，按authority.md逐项核对R01–R17及对应C01–C17；不能把页面已阅章、备查印记或邻条确认当作本条确认，不能把不可辨认的关键内容补成猜测值。

交付三份文件：
1. /tmp_workspace/results/redline_matrix.xlsx：原生可编辑工作簿，逐项包含revision_id、clause_id、base_text、proposed_text、status、adopted_text、condition、rule_ids、evidence。可使用等价中文表头；status用authority.md六种英文标签或对应中文。提议文字可保留可读片段，看不清的字段用空值或unknown；adopted_text仅可确认采用项目填入，其余不填执行文本。保留前置条件、具体规则依据及图像证据，不把整页当成局部判定依据。
evidence可以是单元格中JSON对象/数组，也可以用同一工作簿中的证据明细表，以revision_id关联，至少含revision_id、file、bbox、observation。file指向signed_pages下原图；bbox默认是原始1500×2100像素的[x1,y1,x2,y2]，或明确coordinate_space为normalized_xyxy/pixel_xywh。observation解释区域可见信息如何支持本条判断；可提供多个区域，覆盖选择、局部确认、划销或条件等必要特征。仅列文件名、SHA或“已看图”不够。
2. /tmp_workspace/results/execution.docx：原生可编辑内部草稿。清楚区分“执行正文”“条件未满足暂不执行”“非执行状态附表”三个分区及对应含义。执行正文仅收录可确认采用项目，保留条款ID与条件；条件未满足项目仅列在相应附表，明确暂不执行。其余只列状态和待确认原因，不能把未采用提议或未签底稿当成已生效的执行指令。可以合理改变样式、页序、分页与表格/段落布局，不宣称现实验收、付款、采购或其他审批已经完成。
3. /tmp_workspace/results/uncertain.json：用JSON数组，或JSON对象中的items数组列出未决修订。每条至少有revision_id、unknown_fields、visible_text、reason、evidence、next_action，证据结构同矩阵。unknown_fields指出具体缺口，如提议金额、乙方确认或关键条件，而不是把整页都标成未知；缺值用null或明确unknown。只列真实未决，其他清晰项目按规则判定。

离线完成，所有七份原始输入保持原字节，只读不覆盖；新文件写results或系统临时目录。不访问真实账号、不联网、不发送消息、报批、付款或新建定时任务。

## Expected Behavior

根据原图和效力规则逐项给出状态，只把可确认条款放执行正文，保留未满足条件和具体不可读字段，形成证据可追溯的原生矩阵、执行稿及未决交接。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 逐项检查17项状态、条款及前后文本，实际Word执行分区与三处具体未知字段；不以矩阵自述代替原生产物。
- [ ] `boundary_cases`: 核对框内/备查确认、底稿划线/红提议划销、不采用/双选/空选、条件满足状态、遮挡未知及未签旧稿边界。
- [ ] `delivery_integrity`: 三文件可解析、17项完整无重复、未决集合准确、原生Word经锁定Office导出且文字可见、原输入保持不变。
- [ ] `evidence_binding`: 核对逐项实际图片与区域，覆盖必要视觉特征，拒绝错误页面、无关框、整页泛指及仅SHA。坐标不能替代语义核验。

### Judge group

- [ ] `decision_grounding`: 独立逐张查看五原图并对照未签Word、效力规则和实际三份交付，判断状态、依据与不确定性；不得只采信作者坐标或候选自述。
- [ ] `usable_handoff`: 实际查看原生矩阵、Word及可信派生预览和JSON，判断读者能否区分可执行与暂不执行、查证依据并跟进具体缺口。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    import pdfplumber
    import pypdf
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:result[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 纸面状态和视觉证据 (key: decision_grounding, weight: 0.7)

判据：独立逐张查看五原图并对照未签Word、效力规则和实际三份交付，判断状态、依据与不确定性；不得只采信作者坐标或候选自述。

**Score 1.0**: 全部17项正确区分提议、选择、本条确认、划销与条件；证据实际支持判断，具体未知不猜值、不扩大；矩阵、执行稿和JSON一致，未把样例章或纸面材料状态扩展为现实签署/验收/付款/采购完成。

**Score 0.5**: 关键状态、文字和执行边界均正确，仅一处不影响业务结论的非关键解释或定位不足。

**Score 0.0**: 任一关键状态/执行边界错误，猜测金额/确认/条件、误认备查为局部确认、忽略选择或划销，未知范围不准确，证据观察与原图矛盾，或虚构现实办理。规则分不能抵消这些关键错误。

### Criterion 2: 原生交付和未决交接 (key: usable_handoff, weight: 0.3)

判据：实际查看原生矩阵、Word及可信派生预览和JSON，判断读者能否区分可执行与暂不执行、查证依据并跟进具体缺口。

**Score 1.0**: 三份文件完整、可编辑和清晰可读，条款ID、执行/附表状态、条件、具体区域和下一步可对应复核；允许等价布局、中文表头、措辞和声明的坐标表示。

**Score 0.5**: 主要内容完整正确且可使用，仅一处非关键排版或交接说明不足，不影响核对与后续编辑。

**Score 0.0**: 主要交付缺失、损坏、截图代替可编辑正文，重要内容遮挡或无法阅读，分区混淆、跨产物矛盾，未决无法据此跟进，或只能依赖聊天中的解释。

## Workspace Path

```
datasets/general-hard/workspace/office_documents/general_hard_office_documents_task_012_visual_redlines
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- AStudio去身份需求原型仅保留工作形态，输入为合成自建；GAIA仅作为视觉取证方法参考，未复制原题。本题是既定六题视觉任务之一，不增加10%配额。
- 五张PNG无文本层/EXIF或答案型隐藏字段；双模型隔离逐图标注加作者原图对账先于参考，原始JSON和SHA保留；明确非人工专家复核，两个同模型观察可能共享错误。
- 2430组合规则路径交叉验证不能替代实际像素标注。DOM文本通道存在空间关系碰撞，实际OCR输出有差异；尚无模型性能消融或四端图片链路实测。
- 11合法表达、33业务/边界/交付/坐标负例、5基础设施门禁、2项须语义裁判判断的规则满分反例；只属于作者验收。规则1.0只是作者参考验收，不是hybrid总分、独立语义或正式Harness成绩。
- 规则只判断受控状态、原生文本/值与坐标覆盖；任意非空观察、现实完成主张和完整改写语义必须由独立Judge查看五原图和真实交付核验。
- 评分端需要声明并probe PDF依赖与匹配Office/Word渲染锁；缺GT/helper/依赖、锁/引擎漂移与规则崩溃保持评测异常。900仅任务元数据，不据此设置候选总截止。
