---
id: 01_Office_Documents_task_010_capex_packet
name: 设备升级预算与资本申请一致性交付
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
    - path: results/budget.xlsx
      role: candidate_deliverable
    - path: results/application.docx
      role: candidate_deliverable
    - path: results/plan.html
      role: candidate_deliverable
    - path: results/assumptions.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 设备升级预算与资本申请一致性交付

## Prompt

请为澄川装配中心完成两阶段设备升级方案、可复算预算和资本申请。资料均为合成离线业务材料。先读取 /tmp_workspace/constraints.md 的C01–C05，再结合 /tmp_workspace/quotes/ 三份报价、/tmp_workspace/baseline.xlsx 台账与能耗及 /tmp_workspace/approval.docx 申请模板，形成预算、选择依据与交接。

完成 /tmp_workspace/results/budget.xlsx、/tmp_workspace/results/application.docx、/tmp_workspace/results/plan.html、/tmp_workspace/results/assumptions.json 四份实际文件。更新全部规定资产，在各阶段资本/费用、总现金、有效报价和交货/班组/停工限制内，以两阶段含预备费总现金最低为推荐，另比较至少一项有效组合；已过期或阶段下单前到期的报价可旁列为未确认条件，不能当作确定申请价格。申请保留待审批，P2以P1验收与采购放行为前置，不声称这些动作已完成。

预算工作簿遵守C05三张逻辑表字段；布局、sheet名称及行列顺序可变。数值采用原生数字，衍生额和台天用真正依赖数量、阶梯门槛/单价、税因子及费率的公式计算，不能只填静态数值或旧缓存。数量、门槛/单价、税因子、安装/保养费、阶段运费和预备费率应可编辑；可以直接放在对应字段，也可以用单单元格引用指向明确的原生数值输入。原报价、资产数量与约束是基线，不把评分侧一次性模型扰动当成业务范围变更。other_opex保留培训/迁移的税基和计算依据。预算与比较均按本题税基、分组阶梯、运费和舍入口径，未知不填零。

Word沿用模板的业务章节，包含原生推荐阶段金额表、对象/理由、报价比较、排期、收益与待确认项及审批/放行条件。HTML用静态正文和表格呈现同一方案，能直接离线打开，不含脚本、外部资源或真实办理交互。Word与HTML的推荐表应按C05明确phase/capex/opex/total_cash或相应中文表头；旁列方案清楚区分。两者的施工日历沿用四设备组line_id，逐组列出全部工作日期，而不是只写起止或概括已有安排。允许合理重分页、字体、表格样式、等价公式及满足约束的其他日期/组间次序。

assumptions.json按C05提供selected_vendors、phase_totals、schedule、quote_exclusions、unknowns、gates和evidence，不能代替另三份交付。报价排除和施工日期引用实际来源，收益未知保持null，gate保留待确认。预算定位支持实际Sheet!A1:D3范围；Word定位支持实际paragraph:N、table:N、table:N/row:R及原生cell节点，多个节点可用分号；HTML定位支持实际表#id及#id/tbody/tr:N（tbody行号从1起）。目标定位只写文件内部节点或坐标，须支持当前阶段和账本主张，不能仅填写存在的任意位置。源定位以/tmp_workspace为根写相对路径，或使用以/tmp_workspace/开头的规范路径，加PDF page:1/条款、台账sheet/rows:起-止或constraints.md#C01等标识，不硬编码宿主机路径。

六份输入原字节保持不变；所有新交付写results，临时文件写results或系统临时目录。离线完成，不访问网络、真实账号，不发送消息、下单、报批、付款或新建定时任务。不得虚构新设备能耗、年度节约、寿命、残值、ROI、回收期或任何审批/验收结果。

## Expected Behavior

提交四份一致的原生资金申请与离线方案，正确核算分期税基/阶梯/运费/费用与预备费，模型可重算、排期可行，收益及审批保持未知/待确认且证据可回指。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 对实际原生预算的源参数、四设备组金额/台天、分期资本/费用/预备费/额度及可用替代方案作独立核算；分别核实际Word、静态HTML和账本中的推荐金额，检查确定预算下总现金最小的选择。
- [ ] `boundary_cases`: 从候选真实输入位置做数量阶梯、门槛、单价、税因子、安装/保养费、运费和预备费扰动并清缓存重算；另核报价有效期、共享班组/停工/交货限制、真实日期一致性与未知/待确认状态。
- [ ] `delivery_integrity`: 四份实际交付可解析，预算具有原生公式、Word保留原生段落与表、HTML自包含且有可见预算表；可信Writer PDF实际呈现原生内容，输入保持不变。
- [ ] `evidence_binding`: 账本预算、日历和排除理由的来源真实；预算范围、Word节点和HTML推荐表定位到实际支持当前账本的内容。路径存在或自述正确不能代替内容绑定。

### Judge group

- [ ] `decision_grounding`: 独立对照三份原报价、台账和C01–C05，检查真实原生预算/公式与重算变体、Word、HTML、账本的关键结论、金额口径、范围和条件。
- [ ] `usable_handoff`: 直接查看真实Word、预算工作簿、离线HTML与账本及冻结派生证据，核对可读/可编辑、对应关系、来源及后续动作，而非只看作者参考或路径。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    import pdfplumber
    import pypdf
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:scores[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 资本申请依据与约束判断 (key: decision_grounding, weight: 0.7)

判据：独立对照三份原报价、台账和C01–C05，检查真实原生预算/公式与重算变体、Word、HTML、账本的关键结论、金额口径、范围和条件。

**Score 1.0**: 全部12台范围、阶段和计税/分组阶梯/运费/预备费/费用归属正确；推荐为有效报价下最低总现金，替代和过期报价处理可复核；排期无冲突且满足交货/停工，审批与阶段放行保留条件，收益未知且无虚构承诺，各产物一致。

**Score 0.5**: 所有关键金额、范围、可行性和条件正确，仅遗漏一项不影响资金申请的非关键解释或引用细节。

**Score 0.0**: 关键金额或税基/费用归属/资产范围错误，将过期价或未确认事项当确定事实，核心模型写死或不能重算，排期不可行，编造节能/ROI/回收期/审批，或账本与实际文档关键矛盾；证据不充分时保持未决，不猜测。

### Criterion 2: 四产物的可用交接 (key: usable_handoff, weight: 0.3)

判据：直接查看真实Word、预算工作簿、离线HTML与账本及冻结派生证据，核对可读/可编辑、对应关系、来源及后续动作，而非只看作者参考或路径。

**Score 1.0**: 原生Word和公式预算可继续办理，离线页面完整可读，表格/关键数字/日期实际可见；四产物对应同一推荐方案，来源和节点可复核，责任角色、待确认项和放行条件清楚，未改输入。允许等价版式、公式和可行日历。

**Score 0.5**: 全部关键产物完整正确且可使用，仅一项非关键排版、定位或交接细节不足，不影响复核办理。

**Score 0.0**: 主要文件缺失/损坏/非原生，核心计算写死，关键内容隐藏、裁切或无法读用，只有聊天/元数据陈述，核心来源或对应关系不成立，或未提供可执行的条件交接。

## Workspace Path

```
workspace/general/challenge/01_Office_Documents/01_Office_Documents_task_010_capex_packet
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 保留线上需求形态与去身份原型，全部数值与附件合成自建；GDPval仅方法参考，未复制原题。L4为实测前设计预估，未验证四端兼容或区分度。
- 原始事实及实际PDF/台账独立提取先于参考，81组合用Decimal和整数分数路径交叉核算；参考不是唯一合法布局、公式或排期。
- 自动规则核实际原生表、真实输入扰动/清缓存重算、冻结Word→PDF文字及边界、保守静态HTML与账本；完整视觉遮挡、对比度、版式、理由和未决语义由独立Judge核验。
- 评分需core0.11/score0.19或具备相同数值输入变体证据链；私有Office与独立DOCX/字体锁及PDF依赖均须真实probe，不沿用PPTX渲染Profile。HTML正式观察按独立离线字节/截图协议。
- 49项作者控制和参考规则分不是hybrid完整分，25%独立语义未运行。没有据此产生正式Harness成绩或冻结发行。
- 缺GT/helper、依赖/锁/引擎/字体漂移或规则失败为评测异常，不补能力零分；候选漏交、数据或业务错误按各检查点处理。900为任务元数据，不据此给候选设总截止。
