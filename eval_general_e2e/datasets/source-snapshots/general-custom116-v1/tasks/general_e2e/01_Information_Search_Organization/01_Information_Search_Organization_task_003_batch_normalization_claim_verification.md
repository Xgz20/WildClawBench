---
id: 01_Information_Search_Organization_task_003_batch_normalization_claim_verification
name: BN研究的实验可比性与方法适用性核查
category: 01_Information_Search_Organization
timeout_seconds: 3600
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.04
  llm_judge: 0.96
judge_evidence:
  required:
    - path: evaluator_evidence/reference_answer.md
      role: evaluator_reference_not_agent_output
    - path: evaluator_evidence/candidate_answer.md
      role: evaluator_extracted_candidate_final
    - path: evaluator_evidence/rule_diagnostics.json
      role: grader_generated_rule_diagnostics
tags: [custom, academic, general_task_e2e]
---

## Prompt

请核查附件《待核查论断.md》中的综述，检索正式研究及相关补充材料，判断实验能否直接比较、解释表面冲突，并按给定条件提出方法建议。按A1—A6直接回答，附原文位置、链接及未核实范围；不限年份，无需生成文件。

## Expected Behavior

读取本次工作区的`/tmp_workspace/待核查论断.md`。附件是模拟综述与项目条件，不是事实来源。自行找到草稿提及的实际实验，取得支持具体设置和数字所需的正文、图表、脚注或补充材料。没有图表需求时不强制截图；结构化HTML、正式PDF、作者稿等能够提供所需内容的等价方式均可。

A1恢复机制研究的干预与对照；A2关联主文与补充材料；A3恢复不同批次、优化和预算口径并搜索更接近同条件的对照；A4查明相关样本实验及数字归属；A5区分分类/检测、冻结统计、head/骨干及预训练与微调；A6在三个项目约束下形成有依据的建议和最小验证方案。准确事实可以保留，草稿推论不能整体照抄。按A1—A6组织直接回答，可在同一回答末尾统一列引文；无需生成文件或执行模型训练。

不限制正式论文的发表年份、数量、工具名称、查询次数或固定操作顺序。草稿中点名或给出数字的历史实验须追溯其出处；A1未点名的两类干预允许确实匹配描述的其他正式研究。进一步解释、同条件证据和方案同样开放，不允许用另一实验改写已指明数字的归属。纯预印本可以中性补充，正式作品作者稿不视为未正式发表。关键版本差异影响定位/判断时明确说明。区分直接读取、推算和未核实范围，不把仅取得摘要或空正文回包表述为完成实验核验。

## Grading Criteria

题目/参考版本：2026-10-16.1。本版为29个检查点：2个确定性规则项共4分，27个LLM项共96分。规则只判公开要求的回答结构与引用目标结构，不判科学事实；工具调用项由LLM结合公开调用、实际契约和回执作语义归因。以下“LLM”是评分方式，不表示作者自检运行了Judge。难度为设计标注，需后续真实测评校准。

| 完整输出key | 类型 | 题目分值 | 检查对象 | 主能力 |
|---|---|---:|---|---|
| automated.answer_sections | 规则 | 2 | A1—A6独立回答部分的结构覆盖 | 不映射：格式覆盖 |
| automated.citation_targets | 规则 | 2 | 已给引用的目标结构可解析 | 不映射：结构合法性 |
| llm_judge.original_mechanism | LLM | 4 | 原始机制主张的证据程度 | 不映射：实质研究内容覆盖 |
| llm_judge.followup_interventions | LLM | 6 | 后续机制研究的干预与对照 | state_awareness#3 |
| llm_judge.efficiency_metric | LLM | 4 | 训练效率指标与比较对象 | state_awareness#3 |
| llm_judge.efficiency_configuration | LLM | 4 | 主文与补充材料的配置关联 | state_awareness#3 |
| llm_judge.small_batch_protocols | LLM | 6 | 归一化与梯度批次的实验关联 | state_awareness#3 |
| llm_judge.correlated_batch_protocols | LLM | 6 | 相关样本与数值的实验归属 | state_awareness#3 |
| llm_judge.transfer_protocols | LLM | 6 | 分类与检测的基线和训练阶段 | state_awareness#3 |
| llm_judge.source_identity | LLM | 2 | 正式来源身份 | state_awareness#8 |
| llm_judge.version_consistency | LLM | 3 | 载体及版本一致性 | state_awareness#8 |
| llm_judge.source_locators | LLM | 5 | 决定性证据的原文定位 | state_awareness#3 |
| llm_judge.mechanism_judgment | LLM | 4 | 机制解释的冲突判断 | reasoning_and_decision_making#1 |
| llm_judge.efficiency_judgment | LLM | 4 | 效率换算的因果判断 | reasoning_and_decision_making#1 |
| llm_judge.small_batch_judgment | LLM | 4 | 小批次结果的可比性判断 | reasoning_and_decision_making#1 |
| llm_judge.correlation_judgment | LLM | 4 | 相关性与跨实验拼接判断 | reasoning_and_decision_making#1 |
| llm_judge.transfer_judgment | LLM | 4 | 迁移结果与权重替换判断 | reasoning_and_decision_making#1 |
| llm_judge.recommendation_p1 | LLM | 4 | P1的约束满足与验证设计 | reasoning_and_decision_making#3 |
| llm_judge.recommendation_p2 | LLM | 4 | P2的配对约束与验证设计 | reasoning_and_decision_making#3 |
| llm_judge.recommendation_p3 | LLM | 4 | P3的预训练约束与验证设计 | reasoning_and_decision_making#3 |
| llm_judge.tool_call_contract | LLM | 8 | 全部参数错误事件的统一计分 | tool_invocation#1 |
| llm_judge.tool_data_handoff | LLM | 2 | 检索结果到原文接口的数据传递 | 不映射：条件性过程诊断 |
| llm_judge.tool_execution_context | LLM | 2 | 工作区与读取上下文落实 | tool_invocation#5 |
| llm_judge.verification_calibration_A1 | LLM | 1 | A1核验范围与声明校准 | result_evaluation#10 |
| llm_judge.verification_calibration_A2 | LLM | 1 | A2核验范围与声明校准 | result_evaluation#10 |
| llm_judge.verification_calibration_A3 | LLM | 1 | A3核验范围与声明校准 | result_evaluation#10 |
| llm_judge.verification_calibration_A4 | LLM | 1 | A4核验范围与声明校准 | result_evaluation#10 |
| llm_judge.verification_calibration_A5 | LLM | 1 | A5核验范围与声明校准 | result_evaluation#10 |
| llm_judge.verification_calibration_A6 | LLM | 1 | A6核验范围与声明校准 | result_evaluation#10 |

规则组分=`(2×answer_sections+2×citation_targets)/4`；LLM组分=`Σ(w_j×s_j)/96`；题目百分制=`4×规则组分+96×LLM组分`。分别报告两组和逐项结果，不将规则通过当成科学内容通过。缺GT/缺最终记录/评分异常不得把自动组丢弃后静默重归一。

映射依据`capabilities-2026-09-23-v1`，表内#编号是该能力的局部规范条目。映射预算W=90：状态感知42、推理与决策32、工具调用10、结果评估6。各维自身分=`100×该维Σ(w_i×s_i)/该维预算`；能力总分=`100×全部映射项Σ(w_i×s_i)/90`。意图理解未覆盖，不记0；未映射业务覆盖与能力分并列展示。全部满分时题目100、能力100。

能力映射保存在现有`checkpoint_capability_map7.yaml`；现有七维报告器不自动实现此五维加权公式，数据集更新不修改框架。任一必要映射项缺证据/未触发时不删除后重归一，也不把占位0当有效能力分；只在某维全部必要项有效时报告该维正式分。所有项有效才报告正式总分，否则列可确定明细及状态。条件性的`tool_data_handoff`对所有候选统一不映射，不随个别候选删改能力分母。完整轨迹证实未触发时，业务分按not_triggered_exempt记1并明确“未测得数据传递能力”；缺轨迹/不明是否触发仍为不可判定，不能豁免。工具维只测参数契约与执行上下文，不解释为全工具能力。

工具评分需要实际使用接口的可见定义或足以证实已解析的回执、上下游对象关系、工作区上下文及完整公开轨迹。完整记录证实没有执行本题检索/读取时，相关业务未完成按0记录，过程能力标not_observed；评分端缺记录则为evaluator_evidence_missing。分页#6、下载#8、错误修正#10没有独立必做分：仅在自然发生时作为相应操作证据说明，不以未发生判错或伪造满分。不要求内部思考、专用文件或特定Harness。

本版保留12分工具预算：参数契约8、数据传递2、执行上下文2。旧tool_call_contract、tool_parameter_stability、tool_retry_control合并为一个新的tool_call_contract；首次/其他/连续拒绝只保留诊断标签，不分别加扣分。每次参数错误仅记一次；顺序改变不改变同一错误集合的基础分。followup_interventions映射状态感知，评价干预、对象与训练条件的对应关系，不能把研究内容覆盖直接等同能力。各项目方案采用项目内可行性门槛，不跨项目封顶；推理与决策还包含A1—A5科学判断，不能把它解释成仅衡量方案可执行性。保留旧运行和旧分，离线重评不当作新模型运行。按未舍入检查点分数合分，最后显示两位。

## Automated Checks

规则取传入公开轨迹中的最后一轮最终交付，不读取工具正文作答、不拼接旧轮次。支持的记录形态及歧义处理见代码；不支持的形态报评测证据错误，不猜测候选没回答。`answer_sections`只验证六个编号下存在正文，语义空泛会在对应LLM项失分。`citation_targets`只验证已交付引用可解析为HTTP(S)/DOI目标或已定义的文献引用；不访问网络，不检查论文真伪。所有引用结构合法也不表示证据充分。

执行结束后，代码验证隐藏GT版本并导出参考、提取的最终回答和规则诊断到工作区内`evaluator_evidence/`，不使用系统共享临时证据文件。导出内容标明角色，不能当成候选检索轨迹。GT只在评分阶段注入。

```python
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit


EXPECTED_REFERENCE_SHA256 = "d5281eae706bafe1cf348f466150784ebd18fe7b497737164c4380806ebaabb7"


def _visible_text(message):
    if message.get("channel") in {"analysis", "reasoning"}:
        return ""
    content = message.get("content", message.get("text", ""))
    if isinstance(content, list):
        content = "\n".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in content
            if isinstance(block, str) or (
                isinstance(block, dict)
                and block.get("type") in {"text", "output_text", "assistant_text"}
                and isinstance(block.get("text", ""), str)
            )
        )
    if not isinstance(content, str):
        return ""
    content = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", content, flags=re.S | re.I)
    content = re.sub(r"<think(?:ing)?>.*\Z", "", content, flags=re.S | re.I)
    return content.strip()


def _final_answer(transcript):
    if not isinstance(transcript, list) or not transcript:
        raise ValueError("EVALUATOR_EVIDENCE_MISSING: nonempty transcript required")
    rows = []
    for index, outer in enumerate(transcript):
        if not isinstance(outer, dict):
            continue
        row = outer
        for key in ("payload", "message"):
            if isinstance(row.get(key), dict):
                row = row[key]
        rows.append((index, row))
    starts = [i for i, row in rows if row.get("type") == "task_started" or row.get("role") == "user"]
    start = max(starts, default=0)
    current = [(i, row) for i, row in rows if i >= start]
    complete = [(i, row) for i, row in current if row.get("type") == "task_complete"]
    if complete:
        end, terminal = complete[-1]
        current = [(i, row) for i, row in current if i <= end]
        if "last_agent_message" in terminal:
            answer = terminal["last_agent_message"]
            if answer is None or answer == "":
                return "", {"status": "completed_without_answer", "event_index": end}
            if not isinstance(answer, str):
                raise ValueError("EVALUATOR_EVIDENCE_MISSING: malformed final-answer receipt")
            return _visible_text({"content": answer}), {"status": "terminal_receipt", "event_index": end}
    messages = [(i, row) for i, row in current if row.get("role") == "assistant" and _visible_text(row)]
    explicit = [(i, row) for i, row in messages if row.get("channel") == "final" or row.get("finish_reason") in {"stop", "end_turn"} or row.get("end_turn") is True]
    if explicit:
        index, message = explicit[-1]
        return _visible_text(message), {"status": "explicit_final", "event_index": index}
    if complete and messages:
        index, message = messages[-1]
        if message.get("channel") not in {"commentary", "analysis", "reasoning"}:
            return _visible_text(message), {"status": "last_assistant_before_completion", "event_index": index}
    if complete and not messages:
        return "", {"status": "completed_without_answer", "event_index": complete[-1][0]}
    # A trailing plan or partial assistant message without a completion marker is not a final answer.
    raise ValueError("EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined")


def _prose(text):
    # Only visible prose is scored. Unmarked mathematical notation remains the author's responsibility.
    text = re.sub(r"```.*?(?:```|\Z)|~~~.*?(?:~~~|\Z)", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`|\$\$.*?\$\$|(?<!\\)\$[^$\n]*\$|\\\(.*?\\\)|\\\[.*?\\\]", "", text, flags=re.S)
    return unicodedata.normalize("NFKC", text)


def _sections(answer):
    text = _prose(answer)
    label = r"(?:\*\*|__)?[\[(【]?\s*A([1-6])\s*[\])】]?(?:\*\*|__)?"
    # A table row is an independent section; a heading's title is not answer body.
    text = re.sub(r"(?mi)^\s*\|\s*" + label + r"\s*\|([^\n]*)", lambda m: "A" + m.group(1) + ": " + m.group(2), text)
    text = re.sub(r"(?mi)^\s*\#{1,6}\s*" + label + r"(?=\s|[:：.、)）—-]|$)[^\n]*", lambda m: "A" + m.group(1), text)
    pattern = re.compile(r"(?mi)^\s*(?:[-*+]\s+|\(?[\d一二三四五六]+[.)、]\s*|>\s*)*" + label + r"(?=\s|[:：.、)）—-]|$)\s*[:：.、)）—-]*\s*")
    matches = list(pattern.finditer(text))
    present = set()
    for pos, match in enumerate(matches):
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(text)
        body = text[match.end():end]
        if re.search(r"[\w\u3400-\u9fff]", body):
            present.add("A" + match.group(1))
    return sorted(present)


def _target(value):
    value = value.strip().strip("<>").rstrip(".,;:!?，。；：！？")
    while value.endswith(")") and value.count(")") > value.count("("):
        value = value[:-1]
    doi = re.sub(r"(?i)^doi\s*:\s*", "", value)
    if re.fullmatch(r"10\.\d{4,9}/[^\s<>]+", doi):
        return "https://doi.org/" + doi, True
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname) and not any(c.isspace() for c in value)
        _ = parsed.port
    except ValueError:
        valid = False
    return value, valid


def _citations(answer):
    text = _prose(answer)
    definitions = {}
    pattern = re.compile(r"(?m)^\s*\[([^\]\n]+)\]:\s*<?([^\s>]+)>?")
    for match in pattern.finditer(text):
        definitions[match.group(1).strip().casefold()] = match.group(2)
    text = pattern.sub("", text)
    target_pattern = re.compile(r"https?://[^\s<>\]，。；]*|(?:doi\s*:\s*)?10\.\d{4,9}/[^\s<>\]，。；]*", re.I)
    # Numbered bibliography entries are shared targets, e.g. '[1] Paper title https://...'.
    for match in re.finditer(r"(?m)^\s*\[(\d+)\]\s+([^\n]+)", text):
        target = target_pattern.search(match.group(2))
        if target:
            definitions[match.group(1)] = target.group()
    records = {}
    def add(target, label=None):
        normalized, valid = _target(target)
        key = normalized or "undefined:" + str(label)
        records[key] = {"target": normalized or None, "label": label, "valid": valid}
    def reference(label):
        label = label.strip().casefold()
        if label in definitions:
            add(definitions[label], label)
        else:
            records["undefined:" + label] = {"target": None, "label": label, "valid": False}
    # Inline Markdown links; balanced parentheses in URLs are retained.
    spans = []
    for match in re.finditer(r"\[([^\]\n]+)\]\(", text):
        index, depth = match.end(), 1
        end = index
        while end < len(text) and depth and text[end] != "\n":
            depth += (text[end] == "(") - (text[end] == ")")
            end += 1
        if depth == 0:
            value = text[index:end - 1].strip().split(' "', 1)[0].split(" '", 1)[0]
            add(value, match.group(1))
            spans.append((match.start(), end))
    for start, end in reversed(spans):
        text = text[:start] + " " * (end - start) + text[end:]
    for match in re.finditer(r"\[([^\]\n]+)\]\[([^\]\n]*)\]", text):
        reference(match.group(2) or match.group(1))
    text = re.sub(r"\[[^\]\n]+\]\[[^\]\n]*\]", "", text)
    for match in re.finditer(r"\[([^\]\n]+)\](?!\s*[:(])", text):
        if match.group(1).strip().casefold() in definitions:
            reference(match.group(1))
    for match in re.finditer(r"(?<![A-Za-z0-9_=\\])\[(\d+)\](?!\s*[:(])", text):
        reference(match.group(1))
    for match in target_pattern.finditer(text):
        add(match.group())
    return list(records.values())


def grade(transcript: list, workspace_path: str) -> dict:
    answer, extraction = _final_answer(transcript)
    sections = _sections(answer)
    citations = _citations(answer)
    section_score = len(sections) / 6
    citation_score = sum(item["valid"] for item in citations) / len(citations) if citations else 0.0
    diagnostics = {"answer_extraction": extraction, "section_ids": sections, "section_denominator": 6,
                   "citation_targets": citations, "citation_valid": sum(item["valid"] for item in citations),
                   "citation_total": len(citations), "scope": "syntactic_structure_only_not_scientific_correctness"}
    root = Path(workspace_path).resolve(strict=True)
    reference = root / "gt" / "reference_answer.md"
    for path in (reference, reference.parent, root / "evaluator_evidence"):
        if path.is_symlink():
            raise ValueError("EVALUATOR_ERROR: evidence paths must not be symlinks")
    payload = reference.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_REFERENCE_SHA256:
        raise ValueError("EVALUATOR_ERROR: reference version mismatch")
    evidence = root / "evaluator_evidence"
    evidence.mkdir(exist_ok=True)
    files = {
        "reference_answer.md": "ROLE: evaluator_reference_not_agent_output\nSHA256: " + digest + "\nTRUNCATED: false\n\n" + payload.decode("utf-8"),
        "candidate_answer.md": "ROLE: extracted_candidate_final_answer\nTRUNCATED: false\nEVENT_INDEX: " + str(extraction["event_index"]) + "\n\n" + answer,
        "rule_diagnostics.json": json.dumps({"role": "grader_generated_diagnostics", **diagnostics}, ensure_ascii=False, indent=2),
    }
    for filename, content in files.items():
        path = evidence / filename
        if path.is_symlink():
            raise ValueError("EVALUATOR_ERROR: evidence output must not be a symlink")
        path.write_text(content, encoding="utf-8")
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("EVALUATOR_ERROR: evidence export verification failed")
    return {"answer_sections": section_score, "citation_targets": citation_score,
            "overall_score": (section_score + citation_score) / 2, "diagnostics": diagnostics}
```

## LLM Judge Rubric

### 共同判分与证据边界

仅使用最终回答、公开工具调用/返回、实际工具契约和本题参考。`evaluator_evidence/reference_answer.md`是裁判参考，不是候选证据；`candidate_answer.md`是确定性提取结果，仍须可追溯原始消息。记录缺失、截断或任务未结束时先补证，不把未看到当未执行；参考导出不能弥补过程轨迹缺失。普通摘要、成功状态或capture元数据不能证明候选收到未返回的正文/图片。裁判为核对事实追加的来源不能追认为候选取得。

“事实/关联”项检查回答是否恢复实际研究内容与条件；“判断”项检查用这些事实得出的比较、因果或范围结论；“方案”项检查公开项目约束与验证设计；“来源”项检查身份、载体与可定位性；“工具”项检查调用落实；“校准”项检查核验声明。一次错误优先归最直接项，跨项扣分须列独立义务、回答位置和证据，不能把同一遗漏换名重复扣分。例如仅缺学习率条件扣事实项；已经交代设置但仍宣布同预算可直接排名，才另扣判断。正文事实正确但引用缺失，不取消事实分；模型确实读到原文却解释错误，不自动扣校准。已撤回并更正的陈述不再算最终错误。

各事实/推导项明确给出固定单元；每单元满足为1，否则0，再除以单元数。只评分必要语义，不要求参考措辞或穷尽所有参数；泛泛称“不可比”不能代替具体义务。新增错误若直接否定某单元必要内容，该单元不通过，不另外扣负分。固定公开单元不能通过少答缩小分母。原文近似数字、版本图号变化、不同正式研究与合理方案均按实质接受。

正式研究的作者公开稿可采用；补充材料需属于所引作品。纯预印本作为额外补充时标注中性，不加减分；如承担必需事实的唯一正式依据，来源身份单元未满足。误归、虚构或错误论文仍扣相应项。开放回答不限GT清单；新正式证据支持同一公开义务时接受。若新证据实质反驳GT，标reference_review_required，冻结受影响评分，独立复核后统一重评同批答案，不能先因不在GT判错。

状态至少区分pass/partial/fail、not_observed、not_applicable、blocked_external、evidence_insufficient、evaluator_evidence_missing、evaluator_error。数值接口不支持null，未决项以0作接口占位并在notes明确无效，不能据此发布正式排名。完整记录证明业务未交付时业务0；外部失败本身不直接推定工具能力0。参考损坏或规则异常是evaluator_error，不能计候选失败。

每项notes至少包含：评分单元台账、满足数/固定分母或工具单元比例、最终回答位置、必要原始事件ID/行号、主要扣分归因、状态、实际未覆盖范围。不得按模型身份、耗时、调用总数、篇数或篇幅加分；参数拒绝次数仅按下述固定扣分规则使用。科学核查与真实执行记录分别核对。

### 工具项共同计分

按完整公开轨迹核对实际接口定义或足以证明参数拒绝/已解析的回执，不从答案正确或外层shell成功倒推参数正确。实际契约按“接口＋操作＋schema/命令输入版本”区分；`exec_command`内的检索命令、JSONL检查器等各按内层契约评价。不同查询词、论文或URL不重置同一契约。连续会话未记录版本号时可用实际定义及一致回执确认同一契约，注明版本号未显式记录；若存在无法排除的契约变更，相关项标evidence_insufficient。

参数拒绝按独立调用/内层操作逐次记录，不能按目标或重试链合并。仅相同call_id、相同内容的重复投递可去重；新call_id是新尝试，冲突记录报evaluator_error。一次外层调用若含多个有独立输入和回执的内层操作，分别记账；外层参数已拒绝时不臆测内层也失败。无关调用排除，任务内自选的辅助检查一旦执行也须核对其真实契约。

全部可归因于候选的参数拒绝统一归tool_call_contract，逐次记录K。可以按首次外部检索、已知拒绝后的再次尝试和其他事件分类诊断，但分类互斥且不另计分。调用前是否已经收到同契约拒绝，仅用于解释重试行为；并发请求不能事后串成无效重试。契约明确接受参数进入业务处理即证明结构可解析，HTTP403或合法业务失败不能当参数错误；未知回执也不能假定正确。

合法但未获得新信息的检索、反爬、网络超时和业务检查失败不计参数错误。结构符合契约但所选对象的URL/ID/版本传递错误，归tool_data_handoff；对象正确而cwd/路径解析/工作区绑定错误，归tool_execution_context。同一根因只扣一个工具项。只有独立错误及证据才可跨项扣分，不以一个参数拒绝推定传递或上下文错误。

参数契约Score=max(0,1-K/4)。每个错误事件扣0.25，四次及以上为0，继续列出全部事件数。成功调用不扩大分母、不冲抵错误；更正后成功不再次扣分，也不恢复已发生事件的扣分。完整有效轨迹中已执行本题检索/读取且K=0时可得1，不要求人为触发错误，不据此声称测得错误恢复能力。若同一事件换到首次、后续或重试位置，基础扣分相同。

tool_data_handoff和tool_execution_context按完整触发对象台账计分：u∈{0,0.5,1}，同目标同目的重试合并，r=Σu/N，Score=floor(10×r)/10，r=1时为1。此业务对象合并规则不适用于参数事件。数据传递N=0且完整轨迹证明未触发时业务Score=1、状态not_triggered_exempt；所有候选该项均不映射能力。执行上下文由公开附件读取必然触发，不存在自然N=0满分；完整记录证明未读取附件时业务0、能力not_observed。

没有实质外部检索/读取时，参数契约项为not_observed。缺契约、回执、完整轨迹或任一必要事件不可判定时，保留evidence_insufficient或evaluator_evidence_missing，不把未知当正确，也不删除分母。台账至少含call_id、内层操作标识、调用/回执行号、实际契约、参数结论、调用前可见反馈、唯一错误事件ID和扣分归属；相同事件重复投递只能去重一次。无需内部思考、特定工具、固定操作序列或人为触发失败。

### Criterion 1: 原始机制主张的证据程度 (key: original_mechanism, weight: 4)

A1，两个等权事实单元：①准确恢复原始BN对ICS的设计动机及其含义；②交付原文讨论的其他实际训练作用及其证据程度，需有实质原文依据。这里恢复作者实际说了什么；其能否推出唯一机制另计mechanism_judgment。缺引用本身在来源项评价，不取消已经正确交付的事实。

**Score 1**: 2个固定单元中满足2个。
**Score 0.5**: 2个固定单元中满足1个。
**Score 0**: 2个固定单元中满足0个。

### Criterion 2: 后续机制研究的干预与对照 (key: followup_interventions, weight: 6)

A1，四个等权事实单元。附件未点名这两篇作品，接受确实匹配所述噪声干预或低学习率对照的其他正式研究；模型、设置和定位随所用研究核实，不能仅因不是GT示例而判错：①恢复草稿所指噪声干预的位置、变化方式及主要观察；②交代该观察的模型/数据及影响解释的训练设置，至少能区分其与另一研究的实验；③恢复另一研究匹配低学习率、延长训练与有BN对照的结果；④交代其模型/数据、学习率和训练时长口径，不能把按训练周期百分比对齐的图理解成相同绝对训练预算。只复述“平滑”“较大学习率”不给这些单元分。具体设置可以有等价表述，不要求参考答案所有超参数；但必须足以复原干预与对照。对两类解释是否冲突的推导另计。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 3: 训练效率指标与比较对象 (key: efficiency_metric, weight: 4)

A2，四个等权事实关联：①14倍关联到达到同等精度的训练步数；②指标为相应验证top-1准确率而非top-5/测试误差；③明确Inception、BN-Baseline、BN-x5各自的比较角色；④正确关联72.2%目标及相应步数关系，可以用原文约数，不强制重算14与31/2.1的差别。若主动给出精确数字，须归入正确对象。墙钟换算是否成立另计efficiency_judgment。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 4: 主文与补充材料的配置关联 (key: efficiency_configuration, weight: 4)

A2，四个等权关联：①补充材料约30%计算增量对应相对GoogLeNet的架构变动，不能说成BN层开销；②主文Inception基线已经使用该变体，BN-Baseline是在该基线上加BN；③BN-x5的学习率改变准确；④至少一项其他配套训练调整及其适用配置准确。①②检查主文与补充材料中架构对象的内容关系；URL/页码的形式存在或是否可定位另归source_locators，不重复扣同一缺引用。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 5: 归一化与梯度批次的实验关联 (key: small_batch_protocols, weight: 6)

A3，四个等权关联：①BR小组实验改变统计组32→4，而梯度每步仍汇总1600个样本；②GN分类实验按每GPU计算统计量，固定8GPU时每GPU批次改变会改变总训练批次；③交代GN的学习率随批次缩放、epoch口径；对BR准确说明已披露设置与未披露的具体学习率数值/日程，不把移动统计更新率当优化器学习率；④找到并正确转述更接近同条件的BR/GN对照，说明模型/数据、每GPU批次、BR参数和结果。GN原文ResNet-50/ImageNet批次4的对照是合格示例；其他正式研究若确实比较BR/GN且条件足以解释，也可替代④，不能凭方法名称相同视作可比。①—③是草稿具体实验的追溯，不能用另一篇改写其历史设置。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 6: 相关样本与数值的实验归属 (key: correlated_batch_protocols, weight: 6)

A4，四个等权关联：①74.2%对应小归一化组的BN、相应IID条件与训练步数；②77.4%对应相关批次分半后的BN、分组构造与训练步数，不是BR成绩；③恢复类别/标签成对批次的构成及BN/BR相关对照，区分全批梯度汇总与统计分组；④找到检测head每图512个RoI的原始设置，说明RoI共享同一图像这一相关性来源。图例78.6与正文78.5的差异可如实标注；没有用该数字时不强制发现此差异。错误数字归属在本项，不再以同一错误扣来源定位或判断分。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 7: 分类与检测的基线和训练阶段 (key: transfer_protocols, weight: 6)

A5，四个等权关联：①分类常规批次下BN/GN的相对结果与所用指标；②COCO对照BN*使用固定的预训练统计并作线性变换，非以每GPU1张图重新估计统计的训练模式BN；不把冻结统计等同整个骨干不训练；③区分FPN head加GN与骨干也用GN的独立设置、对应预训练条件和AP变化；④区分180k与long训练的270k预算，并把最佳成绩关联到其实际配置。接受准确表格/段落定位与合理数值近似；不能把box AP、mask AP或分类error混配。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 8: 正式来源身份 (key: source_identity, weight: 2)

以A1—A5及A6的P1/P2/P3为八个固定单元。方案允许明确继承前文证据，不强制新增论文或重复链接。每个单元只有在该部分承担主要论证的来源均可辨识为真实作品、作者/题名/正式发表身份与链接指向相符时通过；允许明确继承统一参考文献。未给可辨来源为业务0，并记not_observed；有来源但实际身份错为有效失败。作者公开稿属于同一正式作品可通过。纯预印本只能中性补充，不能充当必须正式证据的唯一来源。某一错误链接若同一关联还明确给出正确正式链接，记录错误但不强行拆成第二作品；若错误链接被实际当作另一证据使用则不得忽略。记通过数k/8，未交付部分保留在分母。

**Score 1**: 8个固定单元中满足8个。
**Score 0.875**: 8个固定单元中满足7个。
**Score 0.75**: 8个固定单元中满足6个。
**Score 0.625**: 8个固定单元中满足5个。
**Score 0.5**: 8个固定单元中满足4个。
**Score 0.375**: 8个固定单元中满足3个。
**Score 0.25**: 8个固定单元中满足2个。
**Score 0.125**: 8个固定单元中满足1个。
**Score 0**: 8个固定单元中满足0个。

### Criterion 9: 载体及版本一致性 (key: version_consistency, weight: 3)

A1—A5及A6的P1/P2/P3八个固定单元；方案可明确继承前文的来源、载体和定位。各部分注明实际采用的正式PDF、官方补充材料或作者稿（明确URL可承担载体说明），关键图表/结果对应所引版本，才通过。无需同时获取所有版本；没有实质版本差异时不强制制造差异。实际使用了不同版本图号、误植图注或正文/图例差异且影响判断时，须能准确对应或保留差异；不可把版本位置差异当作科学反证。正确作者稿定位不因与GT正式PDF图号不同而扣分。错误作品身份主要归source_identity；正确作品中跨版本错配归本项；纯粹没给定位归source_locators，不重复。记k/8。

**Score 1**: 8个固定单元中满足8个。
**Score 0.875**: 8个固定单元中满足7个。
**Score 0.75**: 8个固定单元中满足6个。
**Score 0.625**: 8个固定单元中满足5个。
**Score 0.5**: 8个固定单元中满足4个。
**Score 0.375**: 8个固定单元中满足3个。
**Score 0.25**: 8个固定单元中满足2个。
**Score 0.125**: 8个固定单元中满足1个。
**Score 0**: 8个固定单元中满足0个。

### Criterion 10: 决定性证据的原文定位 (key: source_locators, weight: 5)

A1—A5及A6的P1/P2/P3八个固定单元；方案可明确继承前文的来源、载体和定位。每部分所有承担其决定性论证的证据，均能沿候选提供的链接和原文位置找到，才通过；接受页、节、图表、算法、可唯一找到的短引文或段落描述，也接受明确的统一引文继承。仅入口/标题/泛指“研究表明”不够。缺失某项事实本身归对应事实项；本项只审该部分已交付的决定性证据，整部分没有任何证据时记0/not_observed。数值解释错误但确实位于该引用段落，不再以相同错误判定位失败；正确原文位置而逻辑推广过度只扣判断。不得用裁判后查到的引用替候选补写。记k/8。

**Score 1**: 8个固定单元中满足8个。
**Score 0.875**: 8个固定单元中满足7个。
**Score 0.75**: 8个固定单元中满足6个。
**Score 0.625**: 8个固定单元中满足5个。
**Score 0.5**: 8个固定单元中满足4个。
**Score 0.375**: 8个固定单元中满足3个。
**Score 0.25**: 8个固定单元中满足2个。
**Score 0.125**: 8个固定单元中满足1个。
**Score 0**: 8个固定单元中满足0个。

### Criterion 11: 机制解释的冲突判断 (key: mechanism_judgment, weight: 4)

A1，四个等权推导：①原始动机不推出唯一机制证明；②噪声实验不能推广为任意ICS定义/任意扰动都无关；③局部优化平滑与可用学习率、泛化结果属于有关联但不同的解释层次；④基于已恢复的干预和对照，说明现有两类结果不构成直接互斥，给出保留范围的修正。若候选发现正式反证，按共同参考复核规则处理。与事实项独立：正确恢复两个实验但宣布互相彻底推翻，本项可失败而事实项通过。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 12: 效率换算的因果判断 (key: efficiency_judgment, weight: 4)

A2，四个等权推导：①撤回把14倍步数直接当墙钟收益；②不能把架构增量归给BN层再计算1.3/14；③说明配套设置使“只加BN”的因果归因不成立；④修正为特定目标精度/配置的步数观察，并指出墙钟验证须匹配设备、实现及训练设置实际测量。只因遗漏某个参数而扣事实项时，不自动扣本项；须有可观察的错误换算/推论或未给出本项结论。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 13: 小批次结果的可比性判断 (key: small_batch_judgment, weight: 4)

A3，四个等权推导：①明确BR与GN两篇所述实验不是只改变同一个batch变量；②不能拼接不同模型、预算和统计范围的结果作方法排名；③区分更接近同条件比较的结论与跨任务普遍优劣；④说明将准确率换成错误率只统一指标方向，不能消除模型和训练设置的混杂。P1统计范围、推荐方法及验证设计仅计recommendation_p1；本项限A3历史实验比较。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 14: 相关性与跨实验拼接判断 (key: correlation_judgment, weight: 4)

A4，四个等权推导：①拒绝把74.2→77.4解释为同一BN→BR对照；②样本总数相同不保证样本独立或统计估计等价；③每图512 RoI不能直接等同512个独立图像；④修正后保持研究的采样条件，不扩展成“相关性越高性能必单调下降”或“所有非IID场景必须用某方法”。数值归属错误与由此作出的推论须分别给位置和独立原因，不能只复制同一理由重复扣分。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

### Criterion 15: 迁移结果与权重替换判断 (key: transfer_judgment, weight: 4)

A5，四个等权推导：①分类与检测结果的不同不构成直接矛盾；②冻结BN*不会在检测时按单图重估训练统计，所以不能把全部差异归给当前小批次估计噪声；③head、骨干、预训练和训练时长分别变化，不能将全部AP增益归给骨干替换；④原文不能保证现有BN权重直接换GN、不改预算即可复现最佳结果。其他正式研究可提供转换方案，但须说明验证与适用条件。

**Score 1**: 4个固定单元中满足4个。
**Score 0.75**: 4个固定单元中满足3个。
**Score 0.5**: 4个固定单元中满足2个。
**Score 0.25**: 4个固定单元中满足1个。
**Score 0**: 4个固定单元中满足0个。

项目方案可行性门槛（P1—P3分别计算）：先按本项四个固定单元得原始分b，再判断最终仍有效的实际建议是否独立违反该项目明确硬约束；若是，Score=min(b,0.25)，否则Score=b。门槛与原单元失分取较严结果，不额外相加；门槛降低只归对应项目，不重复扣A1—A5事实/判断或完成校准。仅历史事实错误而最终方案满足项目条件，不触发门槛。只描述条件外的论文结果、明确排除不可行选项，或明确要求先获得额外资源才作为未来方案，均不触发；“当前可执行/预算内”的互相矛盾建议未撤回时触发，即使同时列出另一可行备选，也不能隐藏不可行建议。

P1硬约束：4张GPU、每卡一次前向2图、累计8次；不能以梯度累计代替跨前向统计，或把一次同步8图声称为64图统计；允许有明确实现与资源依据的其他方法。P2硬约束：保留16身份×2增强视图的成对训练目标；只拆统计组且保留跨组损失配对不算违反。缺少拆分说明但没有明确删除配对，仅按原单元缺失计分，不推定已经违反。P3硬约束：只能微调现有BN预训练骨干，不新增ImageNet预训练；4conv1fc head、180k更新预算。建议在当前预算内训练270k属于违反；历史long结果作为背景不算。notes记录b、硬约束原文、最终建议位置、是否触发、门槛后的唯一贡献，无法确认则不能凭整体印象触发。

### Criterion 16: P1的约束满足与验证设计 (key: recommendation_p1, weight: 4)

A6，四个等权方案条件：①明确当前前向BN的统计范围仍以每GPU2图为批维度（卷积层还包括空间位置），梯度汇总64不等于统计64；②提出满足显存/从头训练条件的可行方案，可比较GN、BR、同步统计或保留BN对照，不强制唯一方法；③若提同步统计，4GPU一次前向最多合并8图而非64，并说明通信/相关性条件；未采用同步方案时，准确说明所选方法的统计范围及可行性可满足③；④验证计划控制模型、数据、优化预算及目标指标，记录精度与实际资源代价。 本项检查实际交付的方案，不要求执行训练；不因方法名称与GT不同扣分。

**Score 1**: 四单元原始分经项目内可行性门槛后为1。
**Score 0.75**: 四单元原始分经项目内可行性门槛后为0.75。
**Score 0.5**: 四单元原始分经项目内可行性门槛后为0.5。
**Score 0.25**: 四单元原始分经项目内可行性门槛后为0.25。
**Score 0**: 四单元原始分经项目内可行性门槛后为0。

### Criterion 17: P2的配对约束与验证设计 (key: recommendation_p2, weight: 4)

A6，四个等权方案条件：①保留成对监督，区分损失配对与统计分组；②提出可执行的分组、归一化或统计方案，不能仅说删掉相关样本；③结合原研究说明有效范围，身份增强样本不必等同论文标签对，不保证照搬收益；④给出保持训练目标及预算的对照，检查目标任务指标和统计/训练稳定性。 本项检查实际交付的方案，不要求执行训练；不因方法名称与GT不同扣分。

**Score 1**: 四单元原始分经项目内可行性门槛后为1。
**Score 0.75**: 四单元原始分经项目内可行性门槛后为0.75。
**Score 0.5**: 四单元原始分经项目内可行性门槛后为0.5。
**Score 0.25**: 四单元原始分经项目内可行性门槛后为0.25。
**Score 0**: 四单元原始分经项目内可行性门槛后为0。

### Criterion 18: P3的预训练约束与验证设计 (key: recommendation_p3, weight: 4)

A6，四个等权方案条件：①沿用现有BN预训练骨干，不把新增GN ImageNet预训练作为既定可行条件；②提出可实施微调方案，例如冻结BN统计的骨干加GN head，也接受有正式依据的其他适配路线；③按180k及4conv1fc head约束区分可直接比较的对照，不承诺论文long或GN预训练最佳AP；④提出同骨干初始化/预算的消融及box/mask指标核验，明确骨干转GN需要额外验证。 本项检查实际交付的方案，不要求执行训练；不因方法名称与GT不同扣分。

**Score 1**: 四单元原始分经项目内可行性门槛后为1。
**Score 0.75**: 四单元原始分经项目内可行性门槛后为0.75。
**Score 0.5**: 四单元原始分经项目内可行性门槛后为0.5。
**Score 0.25**: 四单元原始分经项目内可行性门槛后为0.25。
**Score 0**: 四单元原始分经项目内可行性门槛后为0。

### Criterion 19: 全部参数错误事件的统一计分 (key: tool_call_contract, weight: 8)

按共同规则统计本题公开执行中的参数错误事件K。字段、类型、枚举和嵌套结构按当时实际契约核对；任务内辅助命令的独立内层输入也核对。首次、后续、无效重试统一计数，成功次数不能稀释；不把网络错误当参数错误。Score=max(0,1-K/4)。notes保留总K、全部事件及可选互斥诊断标签，无效状态按共同规则处理。

**Score 1.0**: K=0，且有完整有效操作证据。
**Score 0.75**: K=1。
**Score 0.5**: K=2。
**Score 0.25**: K=3。
**Score 0.0**: K≥4；仍报告全部错误，不合并反复拒绝；无效状态另记。

### Criterion 20: 检索结果到原文接口的数据传递 (key: tool_data_handoff, weight: 2)

触发于从检索/目录/上游工具的记录中提取URL、文档ID、页面引用或本地下载结果，再传给读取/定位接口。每个“源记录＋目的对象＋转换目的”一单元；同一对象镜像重试合并。在满足已知接口结构的前提下，核对上游字段、所需转换、下游实际参数和解析结果。u=1：正确提取/保留所选对象的字段、版本、片段标识及类型；u=0.5：传错后纠正且没有保留错误引用；u=0：遗漏/误传整段回执/破坏标识等未纠正。选错论文但按接口正确传递不在此扣；收到正确URL但外部抓取失败也不扣。浏览器点击选定结果、API、命令均可作为等价实现，但必须有对象传递证据；不能只从最后答案正确倒推。

**Score 1.0**: r=1；数据传递N=0时仅按共同规则记not_triggered_exempt业务豁免，不能把缺证当未触发。
**Score 0.9**: 0.9≤r<1；无效状态依共同规则另记。
**Score 0.8**: 0.8≤r<0.9；无效状态依共同规则另记。
**Score 0.7**: 0.7≤r<0.8；无效状态依共同规则另记。
**Score 0.6**: 0.6≤r<0.7；无效状态依共同规则另记。
**Score 0.5**: 0.5≤r<0.6；无效状态依共同规则另记。
**Score 0.4**: 0.4≤r<0.5；无效状态依共同规则另记。
**Score 0.3**: 0.3≤r<0.4；无效状态依共同规则另记。
**Score 0.2**: 0.2≤r<0.3；无效状态依共同规则另记。
**Score 0.1**: 0.1≤r<0.2；无效状态依共同规则另记。
**Score 0.0**: 0≤r<0.1；无效状态依共同规则另记。

### Criterion 21: 工作区与读取上下文落实 (key: tool_execution_context, weight: 2)

触发于公开附件读取，及实际发生的本地资料解析/临时文件操作；不要求下载论文或运行Python。每个“本次工作区对象＋操作目的”为单元，合并重试。核对路径解析、cwd/应用工作区绑定及实际工具回执；解释器和配置仅在操作确有要求时评价。u=1：实际操作指向本次对象并使用可用上下文；u=0.5：可归因上下文错误后正确重做并消除错误引用；u=0：仍在错误目录/环境处理或遗留错误引用。绝对路径、显式workdir、应用等价绑定均接受。外部环境没有安装依赖不直接扣；上下文正确但选错研究对象另归身份项。

**Score 1.0**: r=1；无效状态依共同规则另记。
**Score 0.9**: 0.9≤r<1；无效状态依共同规则另记。
**Score 0.8**: 0.8≤r<0.9；无效状态依共同规则另记。
**Score 0.7**: 0.7≤r<0.8；无效状态依共同规则另记。
**Score 0.6**: 0.6≤r<0.7；无效状态依共同规则另记。
**Score 0.5**: 0.5≤r<0.6；无效状态依共同规则另记。
**Score 0.4**: 0.4≤r<0.5；无效状态依共同规则另记。
**Score 0.3**: 0.3≤r<0.4；无效状态依共同规则另记。
**Score 0.2**: 0.2≤r<0.3；无效状态依共同规则另记。
**Score 0.1**: 0.1≤r<0.2；无效状态依共同规则另记。
**Score 0.0**: 0≤r<0.1；无效状态依共同规则另记。

### Criterion 22: A1核验范围与声明校准 (key: verification_calibration_A1, weight: 1)

只检查A1范围内最终有效的核验/完成声明，含明确覆盖该部分的总体声明。通过须有可辨核验范围；声称直接核实的实质事实有本次实际取得的相应原文；推算注明推算及依据；未取得的关键范围准确保留。A6是项目方案的文献依据及尚未执行的验证，不能虚报已运行项目。内容真实、HTTP200、capture_complete、PDF文件存在、模型记忆都不能替代候选实际收到的内容。正文中正确数字若只在裁判后查材料出现，仍不能认定候选已核验；粗略推算仅当已读前提足以支持且标明为推算才可接受。不强制数字逐字匹配：单位换算、算术差值和有明确精度界的近似有完整前提即可。

同一原文数字读到但误拼实验条件，主要扣相应事实关联；本项只有独立的虚报核验范围才扣，不因结论错误自动重复扣。仅作者稿而声称读过正式PDF/补充图表等具体载体，若实际没有该载体证据，应撤回或限定；只说核实某事实且等价作者稿已经支持，不强制正式PDF路径。真实限制说明可以通过，不恢复其他业务分。完整记录下没有可辨核验范围为0/not_observed；缺评测轨迹为evaluator_evidence_missing，占位0不得解释为能力失败。

**Score 1.0**: 该范围的全部有效核验声明及保留条件与实际证据一致。
**Score 0.0**: 存在未撤回的超范围声明，或没有可辨核验范围；缺证据时按共同状态规则。

### Criterion 23: A2核验范围与声明校准 (key: verification_calibration_A2, weight: 1)

只检查A2范围内最终有效的核验/完成声明，含明确覆盖该部分的总体声明。通过须有可辨核验范围；声称直接核实的实质事实有本次实际取得的相应原文；推算注明推算及依据；未取得的关键范围准确保留。A6是项目方案的文献依据及尚未执行的验证，不能虚报已运行项目。内容真实、HTTP200、capture_complete、PDF文件存在、模型记忆都不能替代候选实际收到的内容。正文中正确数字若只在裁判后查材料出现，仍不能认定候选已核验；粗略推算仅当已读前提足以支持且标明为推算才可接受。不强制数字逐字匹配：单位换算、算术差值和有明确精度界的近似有完整前提即可。

同一原文数字读到但误拼实验条件，主要扣相应事实关联；本项只有独立的虚报核验范围才扣，不因结论错误自动重复扣。仅作者稿而声称读过正式PDF/补充图表等具体载体，若实际没有该载体证据，应撤回或限定；只说核实某事实且等价作者稿已经支持，不强制正式PDF路径。真实限制说明可以通过，不恢复其他业务分。完整记录下没有可辨核验范围为0/not_observed；缺评测轨迹为evaluator_evidence_missing，占位0不得解释为能力失败。

**Score 1.0**: 该范围的全部有效核验声明及保留条件与实际证据一致。
**Score 0.0**: 存在未撤回的超范围声明，或没有可辨核验范围；缺证据时按共同状态规则。

### Criterion 24: A3核验范围与声明校准 (key: verification_calibration_A3, weight: 1)

只检查A3范围内最终有效的核验/完成声明，含明确覆盖该部分的总体声明。通过须有可辨核验范围；声称直接核实的实质事实有本次实际取得的相应原文；推算注明推算及依据；未取得的关键范围准确保留。A6是项目方案的文献依据及尚未执行的验证，不能虚报已运行项目。内容真实、HTTP200、capture_complete、PDF文件存在、模型记忆都不能替代候选实际收到的内容。正文中正确数字若只在裁判后查材料出现，仍不能认定候选已核验；粗略推算仅当已读前提足以支持且标明为推算才可接受。不强制数字逐字匹配：单位换算、算术差值和有明确精度界的近似有完整前提即可。

同一原文数字读到但误拼实验条件，主要扣相应事实关联；本项只有独立的虚报核验范围才扣，不因结论错误自动重复扣。仅作者稿而声称读过正式PDF/补充图表等具体载体，若实际没有该载体证据，应撤回或限定；只说核实某事实且等价作者稿已经支持，不强制正式PDF路径。真实限制说明可以通过，不恢复其他业务分。完整记录下没有可辨核验范围为0/not_observed；缺评测轨迹为evaluator_evidence_missing，占位0不得解释为能力失败。

**Score 1.0**: 该范围的全部有效核验声明及保留条件与实际证据一致。
**Score 0.0**: 存在未撤回的超范围声明，或没有可辨核验范围；缺证据时按共同状态规则。

### Criterion 25: A4核验范围与声明校准 (key: verification_calibration_A4, weight: 1)

只检查A4范围内最终有效的核验/完成声明，含明确覆盖该部分的总体声明。通过须有可辨核验范围；声称直接核实的实质事实有本次实际取得的相应原文；推算注明推算及依据；未取得的关键范围准确保留。A6是项目方案的文献依据及尚未执行的验证，不能虚报已运行项目。内容真实、HTTP200、capture_complete、PDF文件存在、模型记忆都不能替代候选实际收到的内容。正文中正确数字若只在裁判后查材料出现，仍不能认定候选已核验；粗略推算仅当已读前提足以支持且标明为推算才可接受。不强制数字逐字匹配：单位换算、算术差值和有明确精度界的近似有完整前提即可。

同一原文数字读到但误拼实验条件，主要扣相应事实关联；本项只有独立的虚报核验范围才扣，不因结论错误自动重复扣。仅作者稿而声称读过正式PDF/补充图表等具体载体，若实际没有该载体证据，应撤回或限定；只说核实某事实且等价作者稿已经支持，不强制正式PDF路径。真实限制说明可以通过，不恢复其他业务分。完整记录下没有可辨核验范围为0/not_observed；缺评测轨迹为evaluator_evidence_missing，占位0不得解释为能力失败。

**Score 1.0**: 该范围的全部有效核验声明及保留条件与实际证据一致。
**Score 0.0**: 存在未撤回的超范围声明，或没有可辨核验范围；缺证据时按共同状态规则。

### Criterion 26: A5核验范围与声明校准 (key: verification_calibration_A5, weight: 1)

只检查A5范围内最终有效的核验/完成声明，含明确覆盖该部分的总体声明。通过须有可辨核验范围；声称直接核实的实质事实有本次实际取得的相应原文；推算注明推算及依据；未取得的关键范围准确保留。A6是项目方案的文献依据及尚未执行的验证，不能虚报已运行项目。内容真实、HTTP200、capture_complete、PDF文件存在、模型记忆都不能替代候选实际收到的内容。正文中正确数字若只在裁判后查材料出现，仍不能认定候选已核验；粗略推算仅当已读前提足以支持且标明为推算才可接受。不强制数字逐字匹配：单位换算、算术差值和有明确精度界的近似有完整前提即可。

同一原文数字读到但误拼实验条件，主要扣相应事实关联；本项只有独立的虚报核验范围才扣，不因结论错误自动重复扣。仅作者稿而声称读过正式PDF/补充图表等具体载体，若实际没有该载体证据，应撤回或限定；只说核实某事实且等价作者稿已经支持，不强制正式PDF路径。真实限制说明可以通过，不恢复其他业务分。完整记录下没有可辨核验范围为0/not_observed；缺评测轨迹为evaluator_evidence_missing，占位0不得解释为能力失败。

**Score 1.0**: 该范围的全部有效核验声明及保留条件与实际证据一致。
**Score 0.0**: 存在未撤回的超范围声明，或没有可辨核验范围；缺证据时按共同状态规则。

### Criterion 27: A6核验范围与声明校准 (key: verification_calibration_A6, weight: 1)

只检查A6范围内最终有效的核验/完成声明，含明确覆盖该部分的总体声明。通过须有可辨核验范围；声称直接核实的实质事实有本次实际取得的相应原文；推算注明推算及依据；未取得的关键范围准确保留。A6是项目方案的文献依据及尚未执行的验证，不能虚报已运行项目。内容真实、HTTP200、capture_complete、PDF文件存在、模型记忆都不能替代候选实际收到的内容。正文中正确数字若只在裁判后查材料出现，仍不能认定候选已核验；粗略推算仅当已读前提足以支持且标明为推算才可接受。不强制数字逐字匹配：单位换算、算术差值和有明确精度界的近似有完整前提即可。

同一原文数字读到但误拼实验条件，主要扣相应事实关联；本项只有独立的虚报核验范围才扣，不因结论错误自动重复扣。仅作者稿而声称读过正式PDF/补充图表等具体载体，若实际没有该载体证据，应撤回或限定；只说核实某事实且等价作者稿已经支持，不强制正式PDF路径。真实限制说明可以通过，不恢复其他业务分。完整记录下没有可辨核验范围为0/not_observed；缺评测轨迹为evaluator_evidence_missing，占位0不得解释为能力失败。

**Score 1.0**: 该范围的全部有效核验声明及保留条件与实际证据一致。
**Score 0.0**: 存在未撤回的超范围声明，或没有可辨核验范围；缺证据时按共同状态规则。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_003_batch_normalization_claim_verification

## Skills

## Env

## Warmup
