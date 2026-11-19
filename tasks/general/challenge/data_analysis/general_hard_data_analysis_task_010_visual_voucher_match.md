---
id: general_hard_data_analysis_task_010_visual_voucher_match
name: 扫描凭据状态与账目匹配
category: data_analysis
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
  - general-challenge
judge_evidence:
  required:
    - path: results/voucher_match.xlsx
      role: candidate_deliverable
    - path: results/adjustment_proposal.json
      role: candidate_deliverable
    - path: results/visual_evidence.json
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["retrieval_verification"], "llm_judge.decision_grounding": ["data_processing", "reasoning_planning"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 扫描凭据状态与账目匹配

## Prompt

请依据扫描凭据的实际视觉状态与账目逐笔核对，交付可复核的原生核对底稿和待审批调账建议，保留未知，不修改原账。

只读取/tmp_workspace/policy.md、/tmp_workspace/ledger.csv和/tmp_workspace/vouchers/voucher_01.png至voucher_12.png。共12张原始PNG、18条账目，全部组织、编号、日期、金额和印记为合成练习，无真实报销、付款或审批效力。必须实际查看原图；OCR文本、文件名、相近金额或页上预印词语不能代替图像判断。voucher_03.png与voucher_04.png确为字节相同副本：取得两文件并核实同SHA后，可复用同一次实际像素观察，不强制12次重复图像工具调用；12个源文件仍必须全部可取得、可定位并逐图记录，不得只按文件名推测内容或状态。按policy.md的P1–P6执行，不增加汇率、税费、科目或真实业务操作。

本轮只核对业务日期2026-09-01至2026-09-30（含首尾）、CNY、expense且posted的行。其它行仍保留并标排除，不参与首笔或重复处理。唯一经济键为(voucher_no,counterparty_id,business_date,currency,direction)，名称不能替代编码，O/0、I/1和其它相似字符保留原串，不猜配。以状态确认三格中核验章的中心落格判断有效/作废/待核；一般复核不是状态章。同键有明确作废即作废优先，各适用posted行按自身原额冲回，不再叠加重复冲销。

只有未被划销且位于“更正复核”格内的独立复核章才批准手写更正；划线、一般复核格章或交叉划销章不授权新值。按P4判断副本的获批更正、冲突和金额未决；不能把无批准的手写改动退回打印原值冒充确认。已确认组只支持一个经济事项，适用posted行按posted_at实际时点、再entry_id升序选首笔，不按CSV行序或最接近凭据金额选。首笔keep或correct_amount，其余reverse_duplicate；待核或无完整键凭据用hold。未入账已确认组才可create；未入账待核组单列，不能凭打印额补账。

全部新交付写/tmp_workspace/results，每份不超过5MiB，提交以下三份实际文件：

1. voucher_match.xlsx：自包含、可编辑原生工作簿，无宏或外部数据链接。提供可见的一行语义表头，表头可用下列英文键或清楚对应的中文别名；Sheet名称、坐标、行列顺序、辅助列以及分表/合表均不限。各对象唯一，不能用隐藏结果代替可读表。完整正确的静态核算表或能实际重算的公式均接受，不要求动态参数模型或指定公式数量。
- 逐图images表，12图各一行：file, voucher_no, counterparty_id, counterparty_name, business_date, currency, direction, printed_amount, has_handwritten_correction, handwritten_amount, status_selection, approval_location, approval_crossed_out, correction_status。
- 逐笔ledger核对表，原18条entry_id各一行：entry_id, voucher_no, counterparty_id, business_date, currency, direction, ledger_amount, scope_status, match_status, canonical_entry_id, action, target_amount, proposed_delta, source_files, reason。
- 经济组group表，完整五字段键各一行：voucher_no, counterparty_id, business_date, currency, direction, state, effective_amount, canonical_entry_id, source_files, reason。
- 汇总summary表，key/value两列或明确中文；至少包含：eligible_book_amount, proposed_delta_sum, book_amount_after_proposals, unresolved_book_amount, unresolved_entry_count, proposal_count, unbooked_pending_group_count。
- 完整保留原ledger全部18行及原字段，可单独源表或与核对表合并：entry_id, voucher_no, counterparty_id, counterparty_name, business_date, currency, direction, amount, book_status, posted_at。保留原amount；ledger_amount是核对表中的原账金额，不能用目标值覆盖。

status_selection用valid/void/pending/unknown；approval_location用correction/general/unknown；correction_status用none/approved/unapproved/unknown；direction用expense表示费用，允许清楚等价中文。group.state用confirmed/void/pending。scope_status用eligible/excluded_period/excluded_currency/excluded_status或明确等价；match_status应区分已确认匹配、作废匹配、待核匹配、无完整键凭据和范围排除，命名可等价。action用keep/correct_amount/reverse_duplicate/reverse_void/hold/excluded；新增动作在建议JSON中用create。

金额用实际数值或清楚的数字串，到分表达，真实0不能当空。无手写金额和未知值为null；Excel可用空单元格或明确null/未知标记，但须与0区分。hold/excluded的target_amount与proposed_delta必须未知/不适用，不填0。pending组effective_amount为null；void组effective_amount可为null或0，均表示不确认费用，但每笔reverse_void的目标必须0、差额为负原额。confirmed组实际0仍为有效金额。source_files列可用JSON数组或清楚分隔的真实相对路径。被排除行可附同键图作审计引用，不能因此称为本轮财务匹配或列金额动作。

2. adjustment_proposal.json：UTF-8 JSON对象，顶层包含approval_required: true、approval_status: "pending"、applied: false，以及proposals、pending_items、summary。
- proposals只列correct_amount、reverse_duplicate、reverse_void及create。每项含action、entry_id（create为null）、key（上述完整五字段对象）、delta_amount、target_amount、source_files（数组）、reason，以及每项approval_required: true、approval_status: "pending"、applied: false。原账动作唯一绑定entry_id；create的目标和差额均为有效新增金额。keep、hold、excluded不制造金额建议。
- pending_items分别列每笔ledger_hold和每个unbooked_pending组；每项用kind区分ledger_hold/unbooked_pending（type为同义字段可接受），含entry_id（未入账为null）、完整五字段key、source_files和reason。无匹配凭据时source_files可为空数组；不能虚构来源或将相似键认作匹配。
- summary至少包含上述七项汇总，数值与XLSX一致。金额可用JSON数字或数字串，未知用真正null；记录顺序不限。明确说明book_amount_after_proposals只是全部已列建议假设获批后的账面测算，包含未建议变动的待核账面保留额，不等于最终确认费用或已核清净额。尚未入账的待核凭据另计，不以0宣称已清。

3. visual_evidence.json：UTF-8 JSON对象，顶层images数组完整覆盖12图。每项含file、sha256（原PNG字节的SHA-256）、width、height和observations数组。每条observation含feature、bbox:[x0,y0,x1,y1]、coordinate_system（pixel或normalized）、observation（实际看到什么及如何支持判断）。左上为原点；pixel用原图像素，normalized用0至1。
每图必须覆盖identity、date_currency_direction、amount、status_context四类feature；有手写更正的图还必须有local_review。可按同一feature给多个局部框。identity须支持编号和往来方绑定；amount覆盖原额、手写值及划线；status_context须连同相应有效/作废/待核标签与格边界，足以判断章中心落格；local_review须连同更正复核/一般复核标签及边界，支持章的位置和是否划销。接受真实支持结论的不同合理区域，不能只框一个无法判断绑定栏位的章、给整页无信息矩形或无关位置。观察文字须与原图和XLSX实际读数一致，不从账面金额补猜图上值。

保存前核对三文件的经济键、原始字段、逐笔排序、动作、金额、来源及待核项一致。输入保持原字节且只读，不覆盖、删除或实改ledger.csv；所有建议等待审批且未应用。离线完成，不发消息、不连接真实账号或付费接口，不付款、不执行真实调账。不虚构已查看图片、已验证、专家意见或审批结果。

## Expected Behavior

实际逐张读取原始视觉凭据，按五字段键与P1–P6判组及逐笔动作；正确处理章落格、局部批准/划销、作废优先、首笔排序、相似编号/编码、真实0、范围排除和未知。交付原账完整且可回查原图的XLSX、待审批未应用建议JSON及区域证据JSON，不把测算账面额称为最终确认费用。L4为设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 核对12图的14项原始视觉字段、完整五字段经济键、组状态与有效金额、18条账目逐笔动作及待审批建议和汇总。按实际posted_at/entry_id选择适用首笔，允许合理别名、不同布局及完整正确静态表，不以整组总额相同替代逐笔正确。
- [ ] `boundary_cases`: 核作废副本优先且不叠加重复冲销、一般复核与局部更正/划销、获批更正覆盖副本、O/0与往来方编码不同、真实0、draft/reversed/期外/异币排除、待核/无凭据保留null及未入账待核不补账；所有建议待审批且未应用。
- [ ] `delivery_integrity`: 三份交付可解析且原生表可见可用，原ledger全部18行原字段保留，跨产物对象/动作/金额/汇总一致且输入字节未改。若使用公式，依据独立Office副本的真实重算值；不要求动态参数模型或公式数量。
- [ ] `evidence_binding`: visual_evidence逐图绑定实际源PNG的SHA/尺寸与有信息量的区域，identity/date_currency_direction/amount/status_context完整，手写图具local_review；机械核坐标合法及来源绑定，实际章落格、局部更正关系和解释另由语义Judge查看同SHA原图判断。

### Judge group

- [ ] `decision_grounding`: 必须实际取得与冻结SHA一致的12张原始PNG，同时读取候选XLSX和两个JSON、ledger及policy，逐图核编号/往来方/日期/币种/方向/原额/手写值，状态章中心与带标签格边界，更正复核/一般复核的栏位关系与章是否划销。voucher_03.png与voucher_04.png是字节相同副本，可在取得两文件并核实同SHA后复用同一次实际像素观察；12个源文件仍须可取得、可定位并逐图记录，不强制12次重复工具调用，不得按文件名猜状态。逐组逐笔检查解释是否真正支持作废优先、获批更正、副本只计一事、按适用posted时点选首笔、相似编号与编码不猜配、真实0及未知/范围边界。解释必须与原图及产物实际数据一致，不能因代码状态或自动分正确就给满分。取不到关键原图、SHA不符或无法解码时保持unresolved/评测异常，不用OCR、文件名、自动分或GT文字补看图，不补能力零分。
- [ ] `usable_handoff`: 实际打开候选原生XLSX或可信原生渲染，并读取两份JSON及原图，判断同事能否从逐图观察、经济组和entry_id回查原账、区域、理由、建议和未决项。接受不同合理Sheet、坐标、行列顺序、中文/英文明确别名、等价匹配状态和静态/可重算公式；summary采用key/value表，pending_items用kind区分类别，type为同义字段可接受。接受SHA绑定的高效读图：voucher_03.png与voucher_04.png确为字节相同副本，候选和Judge可复用同一次实际像素观察，前提是12个源文件全部可取得、可定位且分别记录；不以重复图像工具调用次数评价交接质量，不按文件名猜状态。不锁作者区域矩形或要求动态模型。检查可读性和跨文件一致性，不以XML中藏有正确值或聊天自述代替可用交付。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores = runpy.run_path(str(root / "gt/grader.py"))["grade"](root)
    return {
        "business_correctness": scores["business_correctness"],
        "boundary_cases": scores["boundary_cases"],
        "delivery_integrity": scores["delivery_integrity"],
        "evidence_binding": scores["evidence_binding"],
        "overall_score": (
            0.55 * scores["business_correctness"]
            + 0.25 * scores["boundary_cases"]
            + 0.15 * scores["delivery_integrity"]
            + 0.05 * scores["evidence_binding"]
        ),
    }
```

## LLM Judge Rubric

### Criterion 1: 原图证据与逐笔判断依据 (key: decision_grounding, weight: 0.7)

判据：必须实际取得与冻结SHA一致的12张原始PNG，同时读取候选XLSX和两个JSON、ledger及policy，逐图核编号/往来方/日期/币种/方向/原额/手写值，状态章中心与带标签格边界，更正复核/一般复核的栏位关系与章是否划销。voucher_03.png与voucher_04.png是字节相同副本，可在取得两文件并核实同SHA后复用同一次实际像素观察；12个源文件仍须可取得、可定位并逐图记录，不强制12次重复工具调用，不得按文件名猜状态。逐组逐笔检查解释是否真正支持作废优先、获批更正、副本只计一事、按适用posted时点选首笔、相似编号与编码不猜配、真实0及未知/范围边界。解释必须与原图及产物实际数据一致，不能因代码状态或自动分正确就给满分。取不到关键原图、SHA不符或无法解码时保持unresolved/评测异常，不用OCR、文件名、自动分或GT文字补看图，不补能力零分。

**Score 1.0**: 12图关键读数和空间关系均有真实区域支持；组与18条账目解释准确，明确区分作废/重复/更正/待核/无匹配/排除，首笔选择可回查时间；未知和真实0分明。待审批建议未冒称已应用，含待核保留额的测算账面额未冒称最终确认费用。

**Score 0.75**: 全部关键图像状态、金额、经济键及逐笔动作解释正确，仅少量非决定性读数或局部定位说明不完整；无反向解释、虚构读数或错误费用确认。逐项指出缺口及原图。

**Score 0.5**: 有可核实的主要图像与账目推理，但至少一个经济组或逐笔依据存在关键错误/遗漏，例如把一般复核解释成更正授权、未说明首笔排序或将未知置零；按实际受影响对象和证据说明扣分，正确短码不能抵消错误理由。

**Score 0.25**: 只完成少数可信原图/账目解释，多项关键章落格、局部复核、键绑定或逐笔边界被误读/无依据；或仍把未审批测算宣称为已核清费用。须列明实际对象及证据。

**Score 0.0**: 已取得必要材料但没有完成核心视觉及逐笔推理，或核心解释整体被原图/规则反驳、凭空编造关键值/审批；无实际交付支持。缺失评分图像本身属于unresolved/异常，不使用本档代替基础设施失败。

### Criterion 2: 可复核原生核对与待审批交接 (key: usable_handoff, weight: 0.3)

判据：实际打开候选原生XLSX或可信原生渲染，并读取两份JSON及原图，判断同事能否从逐图观察、经济组和entry_id回查原账、区域、理由、建议和未决项。接受不同合理Sheet、坐标、行列顺序、中文/英文明确别名、等价匹配状态和静态/可重算公式；summary采用key/value表，pending_items用kind区分类别，type为同义字段可接受。接受SHA绑定的高效读图：voucher_03.png与voucher_04.png确为字节相同副本，候选和Judge可复用同一次实际像素观察，前提是12个源文件全部可取得、可定位且分别记录；不以重复图像工具调用次数评价交接质量，不按文件名猜状态。不锁作者区域矩形或要求动态模型。检查可读性和跨文件一致性，不以XML中藏有正确值或聊天自述代替可用交付。

**Score 1.0**: 原18行账及逐图/组/逐笔/汇总表清楚可编辑，三文件可从对象追溯至源图和具体区域；待审批动作与ledger_hold/unbooked_pending分开，未知/排除/真实0无歧义，审批旗标和测算边界一致，可直接继续复核与补证。

**Score 0.5**: 核心对象、金额动作及待核事项可复核，三文件主要一致；只有不改变财务判断的非关键布局、别名说明或个别定位/下一步说明缺口。具体指出缺口。

**Score 0.0**: 核心交付缺失/损坏/隐藏不可读，原账或关键对象无法对应，来源不能回查，三文件在关键动作/审批/未知金额上相互矛盾，或只能依赖聊天解释补齐。

## Workspace Path

```
workspace/general/challenge/data_analysis/general_hard_data_analysis_task_010_visual_voucher_match
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- wb-office仅为方法启发，无线上用途原型或直接复制题目；所有组织、编号、日期、金额、印记及输入均合成。此题是既定视觉任务，保留实际图片理解链路；允许Harness辅助理解，不强制底层主模型原生多模态。
- 源先行GT已核验12图、9经济组、18条账及7条金额建议。两名隔离模型各实际先看12原图、先落图片观察再读18账行，原始记录和差异保留；属于independent_model_annotation，human_expert=false，并非人工财务专家或正式候选语义Judge。
- 作废组effective_amount=null或0为等价不确认费用表达，逐笔reverse_void目标仍必须0且精确冲回原账；pending有效金额/目标/差额始终null，confirmed真实0不能当空。匹配状态命名接受清楚等价表达。范围排除行可附同键图作审计引用，不因此形成财务匹配或金额动作。
- 自动内部权重business_correctness/boundary_cases/delivery_integrity/evidence_binding为.55/.25/.15/.05，外层自动.75、语义.25；语义decision_grounding .7与usable_handoff .3。总体分不重复映射能力。
- 允许合理Sheet名、坐标、行列顺序、中文/英文表头、清楚别名与完整静态表；若候选用公式，在独立副本清缓存后实际Office重算，不要求动态模型或公式数量。原ledger输入只读，全部18行原字段需在交付保留。
- 自动证据检查只机械核来源、SHA/尺寸、feature覆盖和几何绑定；不证明实际理解了章落格、局部更正/划销或对象绑定。语义Judge必须取得同SHA12原图与候选XLSX/两个JSON，实际查看并逐项解释，不能以自动正确短码或作者GT文本代替读图。voucher_03.png与voucher_04.png字节相同，候选/Judge可核实SHA后复用一次实际像素观察，但12文件仍须可取得、可定位且逐图记录，不强制12次重复工具调用；作者两名模型各实际查看12张的原始标注记录保持不变。接受非唯一但有真实支持的区域，整页无信息矩形不接受。这是等价性约定，不表示已有独立候选语义成绩。
- 本题12图已用独立ZIP SDK实际逐图解码和原字节SHA绑定，图片合计1915645字节；API Judge图片预算需容纳全部必要原图。max_images=12时均可附加，设11时末图会明确标image_omitted_budget；这不是实际API提供方视觉或语义评分成绩，缺图不按能力零分补判。
- adjustment_proposal.pending_items统一用kind区分ledger_hold和unbooked_pending，type作为同义字段可接受；每项完整key及reason保留未知依据。工作簿summary为key/value表。proposals顶层及逐项均approval_required=true、approval_status=pending、applied=false。测算保留的待核账面额不等于确认费用，不宣称最终核清、已审批或已应用。
- GT打包排除construction_geometry.json及pyc/cache，保留其余私有GT、源复核记录、评分代码和reference。构图几何不作为语义或视觉oracle；最终区域依据为模型原始像素观察与作者复核。
- 候选错题、缺交及业务错误按冻结规则处理；缺GT/helper、受管Office上下文、引擎/锁漂移、规则崩溃、关键原图缺失/解码失败或SHA漂移保持evaluation_error/unresolved，不补能力零分。
- 900仅任务元数据，不设置候选总执行截止或据此扣能力分。作者参考/控制或静态格式通过不证明独立候选语义成绩、真实Harness成绩、L4难度梯度或组合区分度；四端运行和整版校准仍需实际证据。
