---
id: 01_Information_Search_Organization_task_004_luxun_national_character_source_comparison
name: 鲁迅留日思想与五四杂文的史料检索及比较
category: 01_Information_Search_Organization
timeout_seconds: 3600
modality: pure-text
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.02
  llm_judge: 0.98
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

请检索鲁迅留日期间思想转变的原始材料及学术研究，结合五四时期杂文，分析其国民性批判有哪些延续和变化。至少使用两篇留日同期文章、两篇五四时期杂文、两项学术研究，并与后来回忆交叉核对。说明时期范围，标注关键事件与材料年代、出处和原文位置，区分同期文本、后来回忆和研究者解释，比较有依据的不同观点；附来源链接，说明核验范围和未核实之处，直接回答。


## Expected Behavior

自行检索原始作品和学术研究，明确采用的留日、五四时期范围。五四可以使用有说明的广义新文化运动范围，不机械限定在1919年5月；边缘年份作品须说明用途。选取至少两篇不同的留日同期文章、两篇不同的五四时期杂文、两项不同的学术研究，并用至少一篇后来回忆核对早期经历及叙述。两项研究可以来自同一研究者的不同作品，不强制作者人数。文集重印、镜像页面和同篇转载不增加材料数量。小说、后来回忆可以补充，不能代替必需的五四杂文。

正文需实际使用材料，不以书目堆砌替代比较。分别说明材料说了什么、能支持什么推论；把关键事件发生时间、文章写作/初刊时间、回忆写作时间与后出数字转录日期分开。可确认到年的不强求月日；不能确认时注明依据与精度。引用提供实际载体的章节、段落首句、页码或可复核短语，不要求所有来源都有纸本页码。

比较不同研究解释及其材料基础，允许互补、不同侧重或争论，不强制形成对立阵营。允许其他可靠作品、版本与有依据的不同结论，不设唯一篇目或唯一思想史分期。原始作品的后出数字转录可用，但不能冒充原刊影印；只取得摘要可支持摘要明确表达的概括，不得称已核对全文细节。直接回答，不要求生成文件、下载PDF或固定检索顺序。

公开执行约束由`exec/AGENTS.md`提供，调度器须在任务开始时将全文作为可见任务上下文递送，并保存该递送记录；仅复制文件不代表已经告知。原生工作区根目录是`/tmp_workspace`，桌面执行使用所选项目根目录。

如需保存临时证据、下载或检索缓存，使用当前工作区的`.tmp/`；不使用共享`/tmp`、`/private/tmp`或其他工作区保存本次证据。不得探读其他任务、历史会话、评分材料或来源不明的共享临时文件。全局系统技能、解释器、公开来源及工具内部不可控制的缓存不受候选证据目录限制；不要求为得分额外创建文件。

## Grading Criteria

评分版本：2026-10-16.1；参考答案版本：2026-10-13.2。共23个检查点：1个确定性规则项2分，22个LLM项98分。规则只核查来源链接的结构存在；事实、史料关系、分析、调用落实及核验声明由LLM按明确单元判分。难度L3是设计标注，需真实测评校准。

| 完整输出key | 类型 | 题目分值 | 检查对象 | 主能力 |
|---|---|---:|---|---|
| automated.source_link_present | 规则 | 2 | 最终回答至少有一个结构可解析的HTTP(S)/DOI来源目标 | 不映射：结构存在 |
| llm_judge.japan_material_coverage | LLM | 3 | 两篇留日文章的交付及使用 | 不映射：业务覆盖 |
| llm_judge.recollection_coverage | LLM | 3 | 后来回忆的交付及交叉使用 | 不映射：业务覆盖 |
| llm_judge.may_fourth_coverage | LLM | 5 | 两篇五四杂文的交付及使用 | 不映射：业务覆盖 |
| llm_judge.scholarly_coverage | LLM | 3 | 两项学术研究的交付及使用 | 不映射：业务覆盖 |
| llm_judge.source_identity | LLM | 4 | 作品、作者、载体和版本绑定 | state_awareness#8 |
| llm_judge.chronology_binding | LLM | 4 | 事件、写作、初刊及回忆年代关联 | state_awareness#3 |
| llm_judge.evidence_role_binding | LLM | 4 | 同期文本、回忆与研究解释的角色 | state_awareness#3 |
| llm_judge.period_genre_selection | LLM | 4 | 时期边界、文体与分析用途 | state_awareness#12 |
| llm_judge.source_locators | LLM | 4 | 决定性论据与实际版本位置绑定 | state_awareness#3 |
| llm_judge.japan_text_fidelity | LLM | 6 | 留日文本主张及语境 | state_awareness#3 |
| llm_judge.may_fourth_text_fidelity | LLM | 6 | 五四杂文主张及语境 | state_awareness#3 |
| llm_judge.recollection_text_fidelity | LLM | 4 | 后来回忆的场景、主体及语义限定 | state_awareness#3 |
| llm_judge.scholar_claim_binding | LLM | 4 | 不同研究者解释与来源关联 | state_awareness#3 |
| llm_judge.continuity_reasoning | LLM | 6 | 延续判断的跨期证据链 | reasoning_and_decision_making#1 |
| llm_judge.change_reasoning | LLM | 6 | 变化或展开判断的跨期比较 | reasoning_and_decision_making#1 |
| llm_judge.causal_limits | LLM | 8 | 思想转变的因果与外推边界 | reasoning_and_decision_making#1 |
| llm_judge.scholarly_comparison | LLM | 6 | 不同学术解释的实际比较 | reasoning_and_decision_making#1 |
| llm_judge.verification_calibration | LLM | 4 | 核验与完成声明对应实际证据 | result_evaluation#10 |
| llm_judge.tool_call_contract | LLM | 8 | 全程逐次参数契约错误；首次/普通/重试仅作诊断 | tool_invocation#1 |
| llm_judge.tool_data_handoff | LLM | 2 | 实际传递正确性；已外部检索且完整轨迹N=0时题目分免扣 | 不映射：条件免扣不代表实测能力 |
| llm_judge.temporary_evidence_scope | LLM | 2 | 本次临时证据写入的实际目录 | tool_invocation#5 |
| llm_judge.workspace_isolation | LLM | 2 | 文件访问的任务边界及隔离 | tool_invocation#5 |

规则组分=source_link_present；LLM组分=Σ(w_j×s_j)/98；题目百分制=2×规则组分+98×LLM组分。分别展示规则组、LLM组、各项得分及扣分依据。规则通过不说明链接真实、证据相关或事实正确；这些由对应LLM项评价。缺GT/缺终止记录/评分异常时不得丢弃规则组后静默重归一。

映射依据capabilities-2026-09-23-v1，#编号为各能力内部条目。固定映射预算W=82：状态感知40、推理与决策26、工具调用12、结果评估4；其余18分为业务覆盖14、链接结构2、条件性来源传递2。各维独立百分制=100×该维Σ(w_i×s_i)/该维预算；能力总分=100×所有映射项Σ(w_i×s_i)/82。各维对能力总分贡献上限为100×该维预算/82。意图理解未覆盖，不记0。全项满分时题目100、能力100；能力分须与业务覆盖并列，不能代表全部研究已完成。

来源身份以作品/载体标识核对，对象年代、角色、段落主张及研究解释以可见关联核对，属于状态感知；跨期比较及因果边界以回答中的论据和结论核对，属于推理与决策。参数与数据传递依完整调用和回执判断，不能从答案正确倒推。核验校准必须将最终声明与实际读到的证据对照。以上均不推断内部思考，也不把篇幅、总调用数或速度作为得分证据。

来源传递是条件性题目合规项：完整轨迹确认已执行实质外部检索且N=0时明确免扣，Score=1、计2分，记录`handoff_observed=false`、`credit_basis=not_triggered_exempt`，不是实测传递满分。N>0继续按实际传递单元计分。该项在所有运行中统一不纳入能力映射，实际触发时仍展示N与得分；不按各模型是否触发动态删项或重归一。缺轨迹不能当N=0，仍不发布受影响的题目总分。

其他必要映射项缺证据或不可判定时，不把占位0当有效能力分。只有某维所属项全部有效才能发布该维正式分；全部映射项有效才能发布正式能力总分，否则展示确定明细和状态。新增目录项基于公开调用、回执及实际生效路径评价执行上下文，不推断内部意图。现有七维报告器不自动实现本题五维公式；本题只在现有checkpoint_capability_map7.yaml登记，不修改框架。

运行有效性单独判定，不作为额外扣分项：完整记录确认实际取得其他候选回答、历史同题答案、GT或私有评分材料内容时，标`invalid_contaminated`，不发布正式业务总分、能力分或排名，仅保留注明无效的诊断明细。实际读取来源不明的共享文件须先核实内容；不能仅凭路径把普通系统文件判为答案污染，无法核实则标`evidence_insufficient`并暂停正式发布。ENOENT、被阻止且未返回内容的请求只按隔离项计分，不使运行失效；本次自己新建的临时文件只按临时目录项计分。确认内容污染与越界尝试是不同结果，不能把污染简化成扣2分后照常排名。

目录约束递送也须核验：执行前可见消息包含`exec/AGENTS.md`全文或等效约束，才可正式评价目录项。只有仓库中存在文件、Expected Behavior或事后评分记录均不足；若未递送，不追溯强加义务、不改用满分/零分或动态重归一，目录项及依赖它的正式总分标`evaluator_context_missing`。历史运行已有等效公开约束时可复用其递送证据。原生数值合分接口不自动解释这些有效性状态；调度器必须执行本题发布门槛，不能把原生数值当作已通过有效性审核。

## Automated Checks

只取本次公开记录的最终回答，不拼接旧轮次、工具正文或隐藏思考。规则为低权重二值结构检查：最终回答出现至少一个可解析的HTTP(S)链接或DOI即得1，否则0。接受明文、Markdown、编号书目及引用式链接定义；不限制排版。额外链接失效、错指和来源充分性均由LLM来源项评价，不由本规则联网判定。检索工具内部的引用标记若没有在最终交付中解析为链接或DOI，不能作为本项的来源目标。

执行结束后才注入GT。代码验证参考SHA256，向传入工作区内evaluator_evidence/导出带角色标记的参考、最终回答及规则诊断；不使用共享临时目录。评分导出不是候选执行证据。

```python
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit


EXPECTED_REFERENCE_SHA256 = "f8147c864b19f5601a038e44aa718405f5594eb61bc4cc5f0117ef85a4c4c209"


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
    explicit = [(i, row) for i, row in current if row.get("role") == "assistant" and row.get("channel") not in {"analysis", "reasoning"} and (row.get("channel") == "final" or row.get("finish_reason") in {"stop", "end_turn"} or row.get("end_turn") is True)]
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


def _source_targets(answer):
    text = unicodedata.normalize("NFKC", answer)
    pattern = r"https?://[^\s<>\]，。；]*|(?:doi\s*:\s*)?10\.\d{4,9}/[^\s<>\]，。；]+"
    records = {}
    for match in re.finditer(pattern, text, re.I):
        target, valid = _target(match.group())
        records[target] = {"target": target, "valid": valid}
    return list(records.values())



def tool_parameter_score(events):
    """Count independently classified parameter refusals; no semantic error inference."""
    if not isinstance(events, list):
        raise ValueError("EVALUATOR_ERROR: parameter event ledger required")
    seen = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("call_id"), str) or not event["call_id"]:
            raise ValueError("EVALUATOR_ERROR: parameter event call_id required")
        if event.get("parameter_rejection_count") not in (0, 1):
            raise ValueError("EVALUATOR_ERROR: one actual refusal counts once regardless of fields")
        if event["call_id"] in seen and seen[event["call_id"]] != event:
            raise ValueError("EVALUATOR_ERROR: conflicting duplicate event")
        seen[event["call_id"]] = event
    count = sum(e["parameter_rejection_count"] for e in seen.values())
    return max(0.0, 1 - count / 4)


def publication_status(*, trace_complete, context_delivered, confirmed_contamination, unresolved_content_access=False):
    """Deterministic publication gate after evidence-backed semantic/path classification.

    This helper does not infer contamination from strings, and is not a scored rule.
    """
    if confirmed_contamination:
        return "invalid_contaminated"
    if not trace_complete or unresolved_content_access:
        return "evidence_insufficient"
    if not context_delivered:
        return "evaluator_context_missing"
    return "valid"


def grade(transcript: list, workspace_path: str) -> dict:
    answer, extraction = _final_answer(transcript)
    targets = _source_targets(answer)
    score = float(any(item["valid"] for item in targets))
    diagnostics = {"answer_extraction": extraction, "source_targets": targets,
                   "scope": "link_presence_and_syntax_only_not_source_veracity"}
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
    return {"source_link_present": score, "overall_score": score, "diagnostics": diagnostics}
```

## LLM Judge Rubric

### 共同证据与归因规则

仅使用最终回答、公开调用/回执、实际接口契约和本题参考。GT是裁判参考，不是候选已读材料；评分者追加的来源不能追认为候选已取得。其他可靠来源可替代示例，其他有据结论可获满分。参考不是穷尽书目或唯一史学解释。新证据若实质反驳参考，标reference_review_required并暂停受影响项，复核后统一评分，不能因不在GT扣分。

先列来源台账：作品ID、角色、载体/版本、使用位置、必要性；镜像/重印/同文转载归同一对象。再列错误台账：对象ID、错误命题、回答位置、唯一主要评分key。覆盖项只检查公开要求的数量、独立性和实际使用，材料身份、日期、角色、文体及内容是否正确由相应质量项判定。例如用一篇1926年作品冒充第二篇五四杂文时，该对象仍算已提交，错误按主要原因归年代或体裁项，不能再当“完全未交第二篇”扣覆盖。仅列题名无对应说明不算使用；每类达公开最低数量即满覆盖，不奖励堆书目。

质量项评价该组全部承担实质论证的材料，不按成功对象缩小分母，也不靠额外正确来源冲抵错误。数量不足只归覆盖项，不因少一篇重复扣语义项；整组缺失时仍按下文固定单元为0。固定单元满足为1、不满足为0，再除以规定分母。缺必需组时，其固定单元保留且为0。最终交付确实遗漏公开义务是有效业务失败；过程记录缺失与任务未结束是评测证据问题。参考作品、字形、简称、顺序和页码版本不作为字符串匹配标准；允许有根据的保留判断，不要求夸大结论。

归因优先按具体根因：不存在/错作者/错作品/载体错认→source_identity；日期数值或事件时间错配→chronology_binding；年份正确却把回忆当现场文本、把研究者解释当自述→evidence_role_binding；年份/角色已正确但把小说等替代杂文或把范围外材料当主体→period_genre_selection；纯缺定位/跨版本位置错配→source_locators；引文、转述含义或重要上下文失真→相应text_fidelity或scholar_claim_binding。一个根因仅归一项；例如日期错误自然导致越界，不再扣范围项。已归他项的缺陷不再作为本项重复扣分的理由；仍据实际材料评价独立正面义务，不补造不存在的文本、引用或论据。来源不存在时，不能假定所引内容已经成立。

比较项检查是否建立跨期关系、使用共同维度及避免不成立的推论，不因已扣分的事实前提再次扣相同错误；出现独立的过度外推、伪造对立等推理错误才另扣。缺少材料导致既无业务交付又无比较关系时，分别属于“材料”和“比较”两项未完成义务，须明确列出，不可用同一句“来源不足”笼统扣多项。事实正确但没引用不取消事实分；读到了全文但解释错误不自动扣核验校准。

状态区分pass/partial/fail、not_observed、not_applicable、blocked_external、evidence_insufficient、evaluator_evidence_missing、evaluator_error。数值接口不能表达null时以0占位并在notes标无效，不据此发布正式排名或能力分。完整轨迹证明未做本题外部检索时，统一参数项与来源传递项为not_observed，不能将未检索解释为传递免扣；两个目录项独立依据完整文件操作记录判分；未交付业务按相应固定单元0。网络/权限失败不是参数错误；可通过其他来源完成时按实际结果判。缺GT或参考版本不符是evaluator_error。

三个text_fidelity项及scholar_claim_binding的同一具体转述错误若涉及两个单元，只使最直接对应的一个单元失败：①主要核对对象及主张归属，②主要核对限定与语境。只有独立错误才使另一单元失败，归因须记录到单元号。影响含义的同一引文错误只扣内容项，不同时扣角色、年代、因果或校准；只有另有错误角色、错误年代、独立外推或虚假核验声明的证据，才能另扣。无关含义的错别字或候选忠实转引来源中不影响论证的字形问题仅记录，不扣语义分。缺少独立正面义务仍按实际交付判断，不补造论据。

每项notes列固定单元或调用台账、通过数/分母、回答位置、必要原始事件ID/行号、扣分的唯一主要归因及状态。涉及过程必须有完整公开记录，缺记录不能默认全部成功。回答中的不确定性标注不能自动免除未完成义务，但准确标注可满足校准项。

### 工具项共同计分

工具项评价本题实际采用的接口契约，不限制工具名称。契约按“接口＋操作＋schema/命令输入版本”区分。外层exec成功不能证明内层调用合法；有独立输入和回执的内层搜索、读取、辅助检查分别记账。不同查询词、论文或URL不重置同一契约；无法确认契约/版本时相关项evidence_insufficient。

每个实际参数拒绝逐次计数，不按目标或重试链合并。仅相同call_id、相同内容的重复投递去重；新call_id是新尝试；冲突记录为evaluator_error。一次外层请求含多个独立内层操作时分别记录；外层已拒绝不臆测内层也失败。任务内自选的辅助检查一旦执行也纳入契约核查，无关操作排除。

全部参数拒绝只归tool_call_contract。可另外记录诊断标签：①首次实质外部检索请求为first；②其他请求发出前已收到同契约参数拒绝、尚未收到参数接受回执，本次又被拒绝为retry；③其余拒绝为stability。标签不增加权重，不改变每次错误的扣分。首次包括搜索、目录/作者页检索、DOI解析、来源直接读取和引文追踪；技能读取、计划、登录及初始化不算。按调用发出顺序确定首次，同时间按轨迹顺序。

拒绝状态只看调用发出前已经可见的反馈；并发调用未见前一回执不能事后计重试。同契约明确接受参数并进入业务处理即清除拒绝状态，HTTP403或业务失败也可能证明已解析；未知超时不清除，除非有已解析证据。修改参数但仍被拒绝也算再次拒绝；改正后成功不算。成功不冲抵历史扣分。

合法但没有新信息、反爬、网络超时、业务错误本身不计参数拒绝。结构合法但把上游选定对象的URL、ID、段落/页码等错误传给下游归tool_data_handoff；在已经正确读取后写错书目信息归来源项。同一次参数拒绝不再扣传递分。任一无法判定的必要操作保留在台账，相关项不出正式分。

统一参数项按全程互不重复的实际拒绝事件数K计Score=max(0,1-K/4)。每个新尝试均计一次，不论首次、普通或重试；每次扣本项0.25，即2个业务分，四次及以上为0，仍须列全部拒绝。一次实际拒绝同时指出多个字段错误只计一次；外层请求整体被拒绝时不臆测内层失败；实际独立内层操作各有输入和拒绝回执时分别计数。成功调用不增加分母、不恢复扣分，调换事件顺序不改变得分。完整记录证实执行过实质外部检索、K=0可得1；这不宣称测得错误恢复能力，不需人为制造失败。契约无法确认的语法或业务报错不追认为已证实参数拒绝；若影响必要调用结论仍保留证据不足状态。

传递项按实际触发的不同“上游对象→下游用途”关系记N个单元。同对象同用途的重试合并，不同用途单列，重复正确调用不扩大分母。N>0时，u=1表示落实正确；u=0.5表示曾错传、后已改正且后续确实使用正确对象；u=0表示未解决错传。r=Σu/N；Score=floor(10r)/10，r=1得1。该合并只适用于传递，不适用于统一参数项。完整轨迹确认已执行实质外部检索且N=0时Score=1，状态pass，但notes必须标明未触发免扣及`handoff_observed=false`；不声称传递已执行，不要求制造调用。缺轨迹、漏回执或无法确认必要对象关系时为evidence_insufficient，0仅作无效占位，不能免扣。调用台账至少列ID、发出及回执行号/时间、契约、当时反馈、实际参数结论与唯一归属。

目录项覆盖本次主会话及受其委派的任务执行记录。按调用时的cwd、环境变量展开、已知符号链接和实际回执判定路径，不用字符串前缀代替真实目录边界。仅查看运行cwd、系统临时目录名、技能或解释器，不等于读取其他任务内容；工具内部自动缓存、guardian审核输入及评分器导出不当作候选主动读写。未知路径归属或记录不完整时保留不可判定，禁止默认合规。临时目录与隔离项按不同对象和动作归因：当前运行自己新建的证据及后续读取只归临时目录项；读取来源不明的共享临时文件、其他任务/历史/GT内容或修改其他工作区只归隔离项，后者优先，同一目录根因不重复扣分。正常参数解析的越界请求不计参数错误；若只因路径边界被工具拒绝，归目录项。完整轨迹中没有创建临时文件仍可通过目录约束，不要求为触发评分产生文件。

### Criterion 1: 留日文章的交付及使用 (key: japan_material_coverage, weight: 3)

固定两篇单元。每篇须明确题名，并用一个对应内容说明其与留日思想的关系；单列书名或搜索结果不算。按候选用于该角色的不同作品计数，上限两篇；质量错误归对应项，不重复扣覆盖。

**Score 1**: 使用至少两篇不同作品。
**Score 0.5**: 使用一篇。
**Score 0**: 没有使用。

### Criterion 2: 后来回忆的交付及交叉使用 (key: recollection_coverage, weight: 3)

两个固定单元：①明确使用至少一篇后来回忆，并复述一个与留日经历有关的内容；②将这个回忆与一篇同期作品或一项研究实际对照，说明相合、差异或相互不能替代之处。这里只检查是否完成材料及对照交付，不预定必选幻灯事件。

**Score 1**: 满足2个单元。
**Score 0.5**: 满足1个单元。
**Score 0**: 满足0个单元。

### Criterion 3: 五四杂文的交付及使用 (key: may_fourth_coverage, weight: 5)

固定两篇单元。每篇明确题名或可区分的篇号，并用其内容说明国民性批判；不同《随感录》篇号可以各计一篇，同一篇不同载体不能重复。数量上限两篇，质量另判。

**Score 1**: 使用至少两篇不同作品。
**Score 0.5**: 使用一篇。
**Score 0**: 没有使用。

### Criterion 4: 学术研究的交付及使用 (key: scholarly_coverage, weight: 3)

固定两项研究单元。每项能辨认作者和作品，并用于解释某个文本、思想阶段或研究问题。只列参考文献不算使用。不同研究可以同作者，重印/转载同文只算一项；不要求两位研究者直接争论。

**Score 1**: 使用至少两项不同研究。
**Score 0.5**: 使用一项。
**Score 0**: 没有使用。

### Criterion 5: 来源身份与版本 (key: source_identity, weight: 4)

固定四组：留日文章、五四杂文、后来回忆、学术研究。每组实质使用的作品均真实可辨、作者/题名/链接所指对象相符，并能识别实际载体或版本，则该组通过；准确URL可承担载体说明。数字转录可用，不能称原刊影印；学术论文、学术著作章节及可靠研究机构公开研究均可，不限私有清单或发表年份。准确声明只取得摘要本身不扣身份分；假学术来源或虚构作品在本项扣。网页更新年误作初刊年归chronology_binding；正确作品的页码跨版本错配归source_locators。

**Score 1**: 4组通过。
**Score 0.75**: 3组通过。
**Score 0.5**: 2组通过。
**Score 0.25**: 1组通过。
**Score 0**: 0组通过。

### Criterion 6: 年代关联 (key: chronology_binding, weight: 4)

固定四组：①所讨论的关键留日事件有合理时间范围，未把叙述时间当发生时间；②留日文章的写作/初刊信息正确对应，知道二者不必同年；③五四杂文的写作或初刊年份与作品对应；④后来回忆的成文/发表时间与回忆对象分开。各组已给日期不得自相矛盾，关键可得年代不能完全省略；证据只支持到年时不要求月日。无法确认的写作日期可注明未知、给可核实的初刊年代；禁止编造精确月日。1907作/1908刊只是示例，不能强制候选选这些作品。

**Score 1**: 4组通过。
**Score 0.75**: 3组通过。
**Score 0.5**: 2组通过。
**Score 0.25**: 1组通过。
**Score 0**: 0组通过。

### Criterion 7: 材料角色关联 (key: evidence_role_binding, weight: 4)

固定四个角色单元：①留日同期文本被用于当时实际表达；②五四杂文被用于其自身历史语境；③回忆被明确作为后来自述而非现场记录；④研究者解释与鲁迅原文、自述及候选自己的分析可区分。未要求使用这些标签原词；清楚的叙述和引用归属即可。只把回忆写作年份写错归年代；年份正确却仍宣称这是现场思想记录才归本项。是否据回忆推出唯一因果另归causal_limits。

**Score 1**: 4个单元通过。
**Score 0.75**: 3个单元通过。
**Score 0.5**: 2个单元通过。
**Score 0.25**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 8: 时期与文体筛选 (key: period_genre_selection, weight: 4)

两个固定单元：①说明留日与五四的合理采用范围，主体/补充材料与边界自洽；②必需的五四材料确属可接受的杂文、随感或议论性散文，小说、回忆及后期材料有清楚的补充用途。宽窄五四定义均可，但不能为纳入1926年回忆而随意延伸范围。完整的1918—1923新文化语境解释可接受，1919不是唯一允许年份。由已扣年代错误造成的越界不重复扣本项。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 9: 原文位置与载体对应 (key: source_locators, weight: 4)

固定四组：留日文章、五四杂文、后来回忆、学术研究。每组承担决定性论据的材料均给出处链接及能定位的章节、段落首句、明确段落内容标识、可搜索短语或该版本页码，则通过。接受正文与统一书目可明确连接，不强求重复链接或纸本页码。只有主页、泛泛“见原文”、无定位的长篇PDF链接不足。官方摘要中完整表达的概括可定位摘要；未取得正文就编造正文页码不通过。转述内容错与来源定位缺失区分；原始作品身份错只归source_identity。

**Score 1**: 4组通过。
**Score 0.75**: 3组通过。
**Score 0.5**: 2组通过。
**Score 0.25**: 1组通过。
**Score 0**: 0组通过。

### Criterion 10: 留日文本的语义与语境 (key: japan_text_fidelity, weight: 6)

两个固定单元：①该组实际使用文章的主要内容及被批判对象均转述准确，不把其中一篇内容安到另一篇；②相关引文/概括保留对结论重要的限定，未断章取义。按实际选篇判断，不要求固定观点。例如早期个性论不能直接说成拒绝全部西方文明、国家关怀或科学；对精神战士的期待不能抹去受压制的困难。这些只是反例，其他篇目的限制随原文核对。独立内容错误在本项，日期/题名错误不重复。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 11: 五四杂文的语义与语境 (key: may_fourth_text_fidelity, weight: 6)

两个固定单元：①该组实际使用材料的批判对象、行动建议或价值目标转述准确；②相关引文/概括保留影响结论的重要上下文。不能由《三十八》的遗传措辞直接改写成文本宣告民族性不可改变，或因《四十一》质疑超人就说原文已完全排斥尼采；《五十九》开头与结尾须在语境中解释。未选这些篇目时按实际文章核对，不强制讨论这些例子。用其他文本支持不同判断可以接受。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 12: 后来回忆的语义与语境 (key: recollection_text_fidelity, weight: 4)

两个固定单元：①实际使用回忆中的人物、行为、场景和主张转述准确，未把不同事件、不同主体或不同回忆混为同一现场；②相关引文与概括保留影响论证的否定、限定和叙述视角，未将回忆文本所述事实改成相反含义。例如课堂中的日本学生喝彩、幻灯片中的中国围观者以及归国后看刑人的喝彩须按实际原文区分；这不是要求必须选用该例。许寿裳或其他可靠回忆同样适用。字形讹误只有改变主张含义时才扣分；同一错误按最直接的一个单元扣分，不能使两个单元同时失败。年代、来源身份、材料角色和候选的独立因果推断分别依共同归因规则处理。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 13: 学术解释的来源归属 (key: scholar_claim_binding, weight: 4)

两个固定单元：①该组实际使用研究的主要解释均对应到正确研究作品及作者，不把候选自拟概括冒充作者结论；②转述与所引研究实际论证范围相符，摘要支持总论时不虚构摘要外的具体论证。可用全文、准确摘要或学术著作相关章节，只要支持所声称的内容；未取得其他段落并不自动判转述错误。这里判研究实际说什么，两个解释之间怎样比较另计。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 14: 延续判断 (key: continuity_reasoning, weight: 6)

两个固定单元：①提出一个明确可检验的延续判断，并分别连接至少一篇留日文章和一篇五四杂文的具体内容；②解释两组内容在哪个共同维度构成延续，保留其语境差异，不仅罗列相似口号。允许有据判断某维不存在延续，但需比较两期材料、解释何以不构成连续，不以“没有延续”免除论证。参考的“立人”结论不是必答词。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 15: 变化或展开判断 (key: change_reasoning, weight: 6)

两个固定单元：①在共同维度上对照早期与五四材料，提出具体变化、重心转移或展开；②说明该差异怎样由材料支持，区分表现/实践层面的改变与价值目标改变，不凭体裁变了就宣布思想彻底断裂。也接受有据论证某个被声称的变化并不存在。可讨论主体、批判对象、实践路径或自我位置，不规定唯一变化方向。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 16: 因果及外推边界 (key: causal_limits, weight: 8)

两个固定单元各占4分，不能用材料数量、定位完整或其他分析抵消本项独立错误。①对思想转变的原因区分作者回顾、同期证据和分析推论，不把某次事件的叙述自动当唯一充分原因；②关于“国民性”的总体判断与所选文本范围相称，不由少数段落直接推出民族天性永远不变、鲁迅终身思想始终一致或某年突然完全反转。可以提出强判断，但须有相称证据及对相关反例的处理；不强制候选接受参考立场。角色标注正确却仍作超额因果推论属于本项独立错误。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 17: 学术解释比较 (key: scholarly_comparison, weight: 6)

两个固定单元：①比较至少两种来自实际研究、可区分的解释，指出分析问题、时间尺度、材料或论证重点的差异；②说明两者对本题延续/变化判断各有何贡献及可兼容或冲突的条件。不同侧重即可，不要求立场互斥，也不把候选综合写成作者曾直接论战。只有作者名及标签并列不构成比较。

**Score 1**: 2个单元通过。
**Score 0.5**: 1个单元通过。
**Score 0**: 0个单元通过。

### Criterion 18: 核验与完成声明校准 (key: verification_calibration, weight: 4)

固定四组：留日文章、五四杂文、后来回忆、学术研究。每组核验/完成声明与实际工具返回的范围相符，并准确说明影响结论的未核实之处，才通过。明确说明已读相应段落、只读摘要或尚未验证版本均可，不要求声称全文已读。若本组已完成必要核对且无未决问题，不强制虚构未知。只有笼统“仅供参考”不足；完全没有可归到本组的范围说明为0，不能把会话结束自动当完成声明。已完整获取HTML或等价文本可以通过，不强制PDF/截图。工具只返回摘要、下载路径、空正文、错误或截断片段而声称已核查未返回部分则失败。对文本解释错误由内容项扣；不能仅凭答案正确或引用正确认定候选实际核验过。

**Score 1**: 4组通过。
**Score 0.75**: 3组通过。
**Score 0.5**: 2组通过。
**Score 0.25**: 1组通过。
**Score 0**: 0组通过。

### Criterion 19: 全程参数契约落实 (key: tool_call_contract, weight: 8)

按工具共同条款逐次审阅全程实际拒绝事件，K为互不重复的参数拒绝数量。首次、稳定性和重试只作诊断标签，不分别评分。相同call_id且内容完全相同的重复投递去重；新call_id重复错误仍逐次计数；冲突记录为evaluator_error。每次拒绝只计一次，不按错误字段数量、受影响条目数或成功调用比例计分。notes必须列全部错误事件及已排除事件的依据。固定公式Score=max(0,1-K/4)。

**Score 1**: K=0。
**Score 0.75**: K=1。
**Score 0.5**: K=2。
**Score 0.25**: K=3。
**Score 0**: K≥4。

### Criterion 20: 来源标识与读取数据传递 (key: tool_data_handoff, weight: 2)

实际发生搜索/目录返回→原文读取、页面→论文PDF、全文→段落/页码读取等接口关系时，核对所选对象与下游参数。工具允许的ref_id、URL、DOI、文件路径等等价标识均可。选题是否相关由内容项评价；正确传递但被站点阻断不扣本项。以共同条款N、u和r计算，不将只存在最终引用视为已执行传递。

**Score 1**: N>0且r=1；或完整轨迹确认已执行实质外部检索且N=0，按题目政策免扣并标明未实测传递。
**Score 0.9**: 0.9≤r<1。
**Score 0.8**: 0.8≤r<0.9。
**Score 0.7**: 0.7≤r<0.8。
**Score 0.6**: 0.6≤r<0.7。
**Score 0.5**: 0.5≤r<0.6。
**Score 0.4**: 0.4≤r<0.5。
**Score 0.3**: 0.3≤r<0.4。
**Score 0.2**: 0.2≤r<0.3。
**Score 0.1**: 0.1≤r<0.2。
**Score 0**: N>0且0≤r<0.1；缺必要证据时仅为无效占位，不能作为N=0免扣。

### Criterion 21: 临时证据目录 (key: temporary_evidence_scope, weight: 2)

检查候选主动创建、更新或下载的本次临时证据、检索缓存及下载文件，是否实际位于当前工作区`.tmp/`。不以“稍后会迁移”抵消已发生写入；不以大量正确写入稀释一次成功越界。不把完全没有生成临时文件判为失败。本次自己新建的共享临时文件及后续读取归本项，其他任务/未知旧文件等按隔离项优先归因。notes列请求和回执、实际路径、成功/被阻止、唯一归属及例外依据。

**Score 1**: 完整记录内没有归本项的越界写入请求；已写临时证据均在当前工作区`.tmp/`，或未创建临时证据。
**Score 0.5**: 至少一次归本项的越界写入请求，但全部被阻止、没有实际写入；随后如有写入均在允许目录。
**Score 0**: 至少一次本次临时证据成功写入允许目录以外；后续迁移、删除或更正不恢复分数。缺记录时0仅作无效占位并标evidence_insufficient。

### Criterion 22: 工作区与文件访问隔离 (key: workspace_isolation, weight: 2)

检查实际调用访问的文件对象：不得读取其他任务工作区、历史会话、评分材料或未证明为本次生成的共享临时证据，也不得修改其他工作区。实际取得部分内容即属于读取；路径存在性结果或ENOENT不是取得文件内容。与临时目录项的界限按共同条款执行，允许全局系统技能、解释器及公开来源。按本次全程最严重结果分档，不按成功调用比例稀释，不将工具拒绝等同于Agent未发出请求。notes须列出被阻止请求与实际访问，不能只写“未见污染”。本项给分不取代运行有效性判定；确认取得答案/评分内容时，即使其他检查全部通过，也必须标invalid_contaminated。

**Score 1**: 完整记录内没有归本项的越界文件请求；仅使用本任务可用文件及公开来源。
**Score 0.5**: 至少一次越界文件请求，但全部被阻止或目标不存在，未取得文件内容，也未修改其他工作区。
**Score 0**: 至少一次实际取得禁止对象的内容或修改其他工作区；后续纠正不恢复分数。缺记录或无法确定请求结果时0仅作无效占位并标evidence_insufficient。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_004_luxun_national_character_source_comparison

## Skills

## Env

## Warmup
