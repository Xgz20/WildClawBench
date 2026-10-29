---
id: 01_Information_Search_Organization_task_002_nonlinear_substructuring_author_bibliography
name: 非线性子结构法中的聚类分析及第一作者论文检索
category: 01_Information_Search_Organization
timeout_seconds: 3600
modality: pure-text
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.0
  llm_judge: 1.0
judge_evidence:
  required:
    - path: evaluator_evidence/reference_answer.md
      role: evaluator_reference_not_agent_output
tags:
  - custom
  - academic
  - general_task_e2e
---

## Prompt

找到2025年1月至2026年9月的计算力学领域中的论文，关于聚类分析clustering analysis在非线性的子结构法中的结合和应用，列出符合要求的所有论文，把这些论文一作的所有论文名（包含他非一作的论文，挂名即可）全部列出，按照不同作者分门别类。仅统计正式发表论文，预印本可另作补充。

## Expected Behavior

联网检索满足时间、领域和方法结合要求的正式发表论文，识别第一作者，再整理这些作者正式发表的历史署名论文。第二阶段不继续施加第一阶段的年份、研究主题或一作限制。真实且归属正确的预印本可作为中性补充，不计入必答范围，不加分、不扣分。按作者直接回答，允许标题列表、表格或清楚的自然语言，不要求生成文件。

判定方法实际用于非线性子结构分析；不把关键词共现、相关工作引用或未来应用设想直接当作满足主题。关联作者与论文时区分同名作者，合并同一论文的不同版本。支持多种检索路径，不规定工具、查询次数或操作顺序。

## Grading Criteria

评分规则版本：2026-10-16.1。参考事实范围保持不变。本题使用仓库 v2 Rubric。6 个语义检查点，LLM 预算 100 分；自动代码只在评分阶段导出隐藏参考材料，预算为 0，不检查或要求被测 Agent 创建文件。

| 完整输出 key | 类型 | 题目分值 | 检查对象 | 能力映射 |
|---|---|---:|---|---|
| llm_judge.topic_recall | LLM | 20 | 已确认主题论文的标题召回 | 不映射：业务结果覆盖 |
| llm_judge.topic_selection | LLM | 15 | 时间、领域、非线性、聚类与子结构实际结合的联合筛选 | reasoning_and_decision_making |
| llm_judge.first_author_binding | LLM | 10 | 主题论文与第一作者的关联 | state_awareness |
| llm_judge.historical_title_recall | LLM | 25 | 除主题论文外正式发表的历史署名标题召回 | 不映射：业务结果覆盖 |
| llm_judge.historical_author_binding | LLM | 25 | 历史条目与目标作者的署名归属、误归及虚构条目 | state_awareness |
| llm_judge.author_grouping | LLM | 5 | 回答按作者分类的可辨识程度 | 不映射：回答组织要求 |

题目分 = 20×topic_recall + 15×topic_selection + 10×first_author_binding + 25×historical_title_recall + 25×historical_author_binding + 5×author_grouping，满分 100。框架 overall_score 为此分数除以 100，并保留四位小数。参考版本 2026-10-16.1 的必答清单共四篇正式发表论文；主题论文已单独计分，历史增量召回按另外三篇等权计分，每篇 25/3 分。显示题目分时保留两位小数。

能力依据 `capabilities-2026-09-23-v1`：topic_selection 对应 `reasoning_and_decision_making#1`（规则组合推导）；两个 binding 项对应 `state_awareness#3`（分散事实关联），分别检查“主题论文→一作”与“历史论文→该作者”，不检查同一条关系两次。采用最终回答中可观察的分类与事实关联，不推断内部思考，不把回答正确当作执行过自检或调用过某种工具。

映射预算 W=15+10+25=50。有效能力总分 = 100×(15×topic_selection+10×first_author_binding+25×historical_author_binding)/50。推理与决策自身分为 100×topic_selection；状态感知自身分为 100×(10×first_author_binding+25×historical_author_binding)/35；两项对能力总分分别贡献最多 30、70 分。意图理解、工具调用、结果评估未覆盖，不能记为 0 分。题目分与能力分分别报告，同时报告主题召回、历史标题命中数及有效关联数；局部能力满分不表示完成了全部检索。

若某映射项因上游未找到对象、仅有待核关联、参考争议或记录缺失而不可判定，保留该状态，不把它等同于已证实能力失败，不删除后重归一，也不输出正式能力总分。接口只能返回数值时，按 Rubric 返回占位 0，并在 notes 标明受影响 key、状态及原因；占位不是有效能力得分。完整回答证实错误时，才属于可判定失败。

这些是本题数据集的五能力映射约定，沿用 `checkpoint_capability_map7.yaml` 存储；不表示现有七维报告器已实现上述五能力公式。缺证或争议状态也需评测端复核，不能仅依据原生数值文件发布正式结论。

## Automated Checks

```python
from hashlib import sha256
from pathlib import Path


def grade(transcript: list, workspace_path: str) -> dict:
    # Evidence preparation only. No automated candidate score is awarded.
    root = Path(workspace_path).resolve(strict=True)
    reference = root / "gt" / "reference_answer.md"
    if reference.is_symlink() or reference.parent.is_symlink():
        raise RuntimeError("Evaluator reference must not be a symlink")
    payload = reference.read_bytes()
    digest = sha256(payload).hexdigest()
    expected = "310a93fcc294add179c449eae1491579a099601b34ebc19e22a3484c531e3e70"
    if digest != expected:
        raise RuntimeError("Evaluator reference version mismatch; review GT and rubric together")
    content = payload.decode("utf-8")
    target_dir = root / "evaluator_evidence"
    if target_dir.is_symlink():
        raise RuntimeError("Evaluator evidence directory must not be a symlink")
    target_dir.mkdir(exist_ok=True)
    target = target_dir / "reference_answer.md"
    if target.is_symlink():
        raise RuntimeError("Evaluator evidence file must not be a symlink")
    exported = (
        "EVIDENCE ROLE: evaluator_reference_not_agent_output\n"
        "SOURCE: gt/reference_answer.md\n"
        f"SOURCE SHA256: {digest}\n"
        "TRUNCATED: false\n"
        "Generated after candidate execution. Do not credit this text as an agent answer.\n\n"
        + content
    )
    target.write_text(exported, encoding="utf-8")
    if target.read_text(encoding="utf-8") != exported:
        raise RuntimeError("Evaluator reference export verification failed")
    return {"diagnostics": {
        "status": "reference_exported",
        "role": "evaluator_reference_not_agent_output",
        "source": "gt/reference_answer.md",
        "sha256": digest,
        "output": "evaluator_evidence/reference_answer.md",
        "truncated": False,
    }}
```

## LLM Judge Rubric

### 共同判分规则

使用最终面向用户的回答及可见检索记录，对照 `evaluator_evidence/reference_answer.md`。该文件由评分代码在执行结束后从私有 GT 导出，永远不是候选回答。不得把工具输出中出现但未进入回答的标题计为已交付，也不得从内部思考推断过程。无需文件、DOI、发表日期、作者顺位、长篇纳入分析、引用格式或检索日志；这些辅助信息未写出不扣分。正确的简短分类回答可以满分。

先识别主题命中集、主题第一作者、历史标题和归属关系，再逐项判分。接受可唯一识别的译名、简称和正常格式变体；相同论文版本去重。明确列为排除项或待核候选的论文不算主题误纳。仅在正文或方法中实际结合聚类与非线性子结构分析才满足主题，不限定必须采用参考论文的特定技术路线。

当前参考 S={P1}，正式发表论文的历史增量 H={P2,P3,P4}，编号与正式标题见参考文件。P1 可在主题列表或作者清单中出现，无需重复写两遍。P4 的跨领域同人归属采用出题方给定信息且尚未独立交叉核实：列入该作者清单或明确关联该作者的待核小节，均计标题召回，不按同名误归扣分；不能将这一容许归属单独当作已独立确认身份的能力证据。

真实且作者归属正确的预印本不在必答范围，裁判仅在 notes 标注“预印本补充，不加分、不扣分”；列出或遗漏均不改变得分，也不作为已确认历史关联的得分依据。无需候选回答额外填写发表状态。已正式发表论文的预印本版本仍按同一成果识别，不能因此拒绝已命中的正式论文标题。该中性规则不豁免已证实的虚构论文、错误作者归属或错误主题纳入。

所有新发现及反证按参考文件的统一复核规则处理，不把“参考外”自动等同于错误。确需更新参考时，notes 写 `reference_review_required`、相关条目及受影响 key；未核实且实质影响判分的项使用 0 作接口占位，状态为 `uncertain`，不能据此形成正式排名或能力总分。实际缺失、截断的最终回答记录须标 `evaluator_evidence_missing`，不能当作 Agent 没有作答。完整记录证明没有回答时，各项业务分为 0；无可观察关联的能力项记 `upstream_blocked`。参考加载异常由自动代码报评分器错误，不归因于候选。

notes 简要记录各项依据，至少包含 `topic_hits/1`、`historical_title_hits/3`、已确认正式发表历史论文的关联数、已证实误纳/误归项、预印本中性标注及需要复核的事项。没有争议时无需附加状态。不得仅凭数量声称检索宇宙穷尽。

### Criterion 1: 主题论文标题召回 (key: topic_recall, weight: 20)

只检查 P1 的标题是否在最终回答中作为检索结果被唯一识别，不再评价其归属或主题分类。标题可在作者清单中出现；仅在明确排除项中提到 P1 不算交付。P1 不在 Criterion 4 重复计分。

**Score 1.0**: 回答包含可唯一识别的 P1 标题。
**Score 0.0**: 未交付可唯一识别的 P1 标题，或明确把 P1 排除。

### Criterion 2: 主题筛选准确性 (key: topic_selection, weight: 15)

检查回答明确或由上下文清楚认定为主题命中的论文，是否同时满足时间、领域、非线性和聚类实际用于子结构分析。只评纳入决策，不以少列历史标题扣分。作者分类下明确称为“全部署名论文”的条目不自动视为全部主题命中；只有一份未区分用途的混合清单时，不能替其猜测纳入决策，业务分为 0、能力记不可判定。P2 的主题资格需有实际应用证据，不能仅据名称或与 P1 的关系认定。

**Score 1.0**: 至少作出一项正确主题纳入，且没有已证实的错误主题纳入。
**Score 0.5**: 至少作出一项正确主题纳入，但另有恰好一篇已证实不满足条件的论文被作为主题命中。
**Score 0.0**: 至少两篇错误主题纳入；或全部明确纳入均不符合条件；或没有可判定的主题纳入决策。最后一种无对象情况在能力层记不可判定，不凭空认定推理错误。

### Criterion 3: 主题论文第一作者关联 (key: first_author_binding, weight: 10)

检查 P1 与 Jingcheng Miao 的一作关系。接受上下文可唯一识别同人的拼写、译名或简称，不要求额外介绍机构或 ORCID。错误主题纳入引入的其他作者由 Criterion 2 处理，不在这里再次扣分。

**Score 1.0**: P1 被正确关联到第一作者 Jingcheng Miao，或语境明确等价。
**Score 0.0**: 一作被错指为其他人、无法唯一确定，或未建立该关联。P1 本身没有检出而无关联对象时，能力层标 upstream_blocked；有明确错误关联时为可判定失败。

### Criterion 4: 历史署名论文增量召回 (key: historical_title_recall, weight: 25)

只数 H 中三个不同的正式发表历史论文标题的交付数量 n，分母固定为本参考版本的 3。P1 的标题已经在 Criterion 1 计分。预印本补充不计入 n 或分母，不能补偿缺失的正式论文。此项不再评价作者姓名、分类、署名顺位或主题资格；标题已列出但作者关联错误仍计检索分，由 Criterion 5 评价关联。仅在明确排除项中提到不计入；P4 的合理同人待核列法按共同规则计入。忽略第一阶段时间或领域限制而错误漏掉 P3/P4，只通过本项的缺失数量失分，不另设“非一作遗漏”扣分。

**Score 1.0**: n=3，P2、P3、P4 三篇正式发表历史论文标题均已交付。
**Score 0.666667**: n=2，交付其中两篇标题。
**Score 0.333333**: n=1，交付其中一篇标题。
**Score 0.0**: n=0，三篇历史论文标题均未交付。

### Criterion 5: 历史论文署名归属准确性 (key: historical_author_binding, weight: 25)

仅检查历史论文与正确主题一作 Jingcheng Miao 的关联：包括 H 中已交付标题的归属，以及额外声称属于该作者的历史条目。评价同名作者混淆、错归和虚构，不重评 P1 的一作身份、未列出的标题、题外主题作者或重复版本数量。P2/P3 可提供已确认历史关联；P4 的给定归属或待核标注不算错误，但不单独提供已确认关联。真实且归属正确的预印本中性处理；虚构或误归的条目即使标为预印本，仍按错误论文扣分。同一错误论文去重后计数。新正式发表历史论文需按统一参考复核规则处理。

建立去重后的历史归属台账：C为已核实、正式发表且正确归属的关系数；E为已证实错误的历史归属或虚构论文数；其中V为已证实虚构的论文数（V≤E）。同一论文的错误作者、虚构标题等表象只占一个E；V只用于该事件的严重性，不再跨检查点另扣。P4的给定/待核归属、真实且正确的预印本、明确待核或排除项不进入C/E/V。不能仅因未检索到就认定虚构。未列标题仅由召回项处理，不加入E。

C≥1时，先计算r=C/(C+E)，再取Score=min(max(0,1-(E+V)/4), floor(4×r)/4)。这是错误数量与准确比例两种约束取较严者，不把两种损失相加。增加正确条目不能抵销固定错误事件罚分；确认虚构的单次事件相当于两个普通错误单位。C=0且E>0时为有效0；C=E=0时业务0，能力为upstream_blocked或uncertain，不能伪造失败或满分。P2/P3已独立正确关联时，不因P1一作错漏再次阻断。

**Score 1.0**: 公式结果为1；至少一个已确认关系且E=0。
**Score 0.75**: 公式结果为0.75。
**Score 0.5**: 公式结果为0.5。
**Score 0.25**: 公式结果为0.25。
**Score 0.0**: 公式结果为0，或无可确认关系时的无效占位；状态必须区分。

错误归因顺序：错误主题纳入只归topic_selection，不把由此出现的题外作者再次记历史误归；正确目标作者下的错误历史归属只归本项，不取消已交付真实标题的召回或分类形式分。notes列出C/E/V、r、两个分值约束与唯一错误事件ID，便于核对没有重复扣分。

### Criterion 6: 按作者分类回答 (key: author_grouping, weight: 5)

只评价组织形式是否能看出作者与条目属于哪个分类，不重复评价作者姓名真假、标题覆盖或同人归属。可用标题、表格作者列、自然语言引导；当前只有一位作者时，一个明确标注作者的清单即可。无需另写文件，也不要求完整文献引用格式。

**Score 1.0**: 已交付的作者论文清单具有清楚的作者分类，所有已列条目都能判断放在哪个分类下。
**Score 0.5**: 存在作者分类且至少一条论文归组清楚，但部分条目的分类指向不明。
**Score 0.0**: 只有未分类的论文列表、只有作者名没有论文，或未作答。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_002_nonlinear_substructuring_author_bibliography

## Skills

## Env

## Warmup
