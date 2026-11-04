---
id: 01_Information_Search_Organization_task_004_luxun_national_character_source_comparison
name: 鲁迅国民性批判的材料对照分析（稳定材料版）
category: 01_Information_Search_Organization
timeout_seconds: 3600
modality: pure-text
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.02
  llm_judge: 0.98
judge_evidence:
  semantic_status_profile: evidence-aware-v1
  preserve_native_channels: true
  claim_review_keys:
  - scholar_claim_binding
  required:
  - path: evaluator_evidence/reference_sources.json
    role: evaluator_reference_not_agent_output
  - path: evaluator_evidence/reference_answer.md
    role: evaluator_reference_not_agent_output
  - path: evaluator_evidence/criterion_evidence.json
    role: evaluator_reference_not_agent_output
  - path: evaluator_evidence/public_materials/
    role: evaluator_provided_public_input_not_candidate_output
  - path: evaluator_evidence/candidate_answer.md
    role: evaluator_extracted_candidate_final
  - path: evaluator_evidence/rule_diagnostics.json
    role: grader_generated_rule_diagnostics
tags:
- custom
- academic
- general_task_e2e
- stable-materials
---

## Prompt

请实际读取当前工作区materials/README.md及M1—M5、R1—R2七份给定材料，分析鲁迅国民性批判从留日同期文章到新文化/广义五四杂文有哪些延续与变化，并用给定的后来回忆交叉核对。

只以本包作为必评依据：两篇留日文章M1/M2、两篇杂文或随感M3/M4、回忆M5、两项研究短摘录R1/R2都需实际使用。说明本题采用的时期范围、材料年代与角色；区分鲁迅原文、后来回忆、研究者解释和你自己的比较推论；比较R1/R2给定观点的侧重、互补关系及证据限度。

本题不要求联网、下载PDF、取得论文全文或核对原刊影印。引用可用M1#p1等材料ID/段号，或作品名称与可定位短语，排版不限。日期按卡片给定精度，不能反推未给事件的具体年/月。只取得本包节选时如实说明，不冒称读过全文或网站。外部材料可作附注，但不能替代必评材料或扩大本题必须核验的研究范围。

直接回答，不要求创建交付文件。勿改写materials/原件；如需整理，使用本题工作区.tmp/。不得读取GT、其他任务、历史答案或来源不明共享文件。

## Expected Behavior

完成可完全离线复核的固定材料对照，而非自由检索书目。至少实质使用M1/M2、M3/M4、M5及R1/R2；允许有材料依据的不同分析，不能把材料名称清单或任务计划当交付。七份材料的作者、载体、段落与年代卡均已提供，不要求补齐未给全文。

采用公开的留日1902—1909及新文化/广义五四1918—1925取材窗口，承认这是本题范围而非唯一史学分期。区分M1/M2的写作与初刊、M3/M4的文类、M5的后出回忆与所述事件。研究网页发布日期不是原刊年份，研究原刊日期不作必评事实；M5事件的具体年/月未给，不强求反推。

以至少一个共同维度比较延续与变化，明确各结论的跨期证据和限度。研究比较仅限R1/R2的短摘录，允许互补而非对立，不要求证明全文未给的论证。材料身份与数量、观点准确、比较关系、核验声明分别计分，同一具体错误不重复归因。

评分需要完整公开轨迹和执行前已递送的exec/AGENTS.md约束。只有文件存在不等于递送。原生逻辑根目录为/tmp_workspace，桌面使用本题项目根。工具名不固定，但需要有可核验的题内材料读取；无需额外写文件。系统工具不可控制的缓存不算候选临时证据写入。

## Grading Criteria


评分版本：2026-11-04.1（稳定材料版）；参考答案版本：2026-11-04.1。共23个检查点：1个确定性规则项2分，22个LLM项98分。规则只核查材料ID、题名或链接引用入口的结构存在；事实、史料关系、分析、调用落实及核验声明由LLM按明确单元判分。难度L3是设计标注，需真实测评校准。

| 完整输出key | 类型 | 题目分值 | 检查对象 | 主能力 |
|---|---|---:|---|---|
| automated.source_link_present | 规则 | 2 | 最终回答至少有一个给定材料ID/题名或结构可解析来源目标 | 不映射：结构存在 |
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
| llm_judge.scholar_claim_binding | LLM | 4 | R1/R2两个固定研究单元，各2分；每项明确核对作者作品与观点范围 | state_awareness#3 |
| llm_judge.continuity_reasoning | LLM | 6 | 延续判断的跨期证据链 | reasoning_and_decision_making#1 |
| llm_judge.change_reasoning | LLM | 6 | 变化或展开判断的跨期比较 | reasoning_and_decision_making#1 |
| llm_judge.causal_limits | LLM | 8 | 思想转变的因果与外推边界 | reasoning_and_decision_making#1 |
| llm_judge.scholarly_comparison | LLM | 6 | 不同学术解释的实际比较 | reasoning_and_decision_making#1 |
| llm_judge.verification_calibration | LLM | 4 | 核验与完成声明对应实际证据 | result_evaluation#10 |
| llm_judge.tool_call_contract | LLM | 8 | 实际题内材料访问及逐次参数契约错误 | tool_invocation#1 |
| llm_judge.tool_data_handoff | LLM | 2 | 实际传递正确性；已材料读取或检索且完整轨迹N=0时题目分免扣 | 不映射：条件免扣不代表实测能力 |
| llm_judge.temporary_evidence_scope | LLM | 2 | 本次临时证据写入的实际目录 | tool_invocation#5 |
| llm_judge.workspace_isolation | LLM | 2 | 文件访问的任务边界及隔离 | tool_invocation#5 |

规则组分=source_link_present；LLM组分=Σ(w_j×s_j)/98；题目百分制=2×规则组分+98×LLM组分。分别展示规则组、LLM组、各项得分及扣分依据。规则通过不说明链接真实、证据相关或事实正确；这些由对应LLM项评价。缺GT/缺终止记录/评分异常时不得丢弃规则组后静默重归一。

映射依据capabilities-2026-09-23-v1，#编号为各能力内部条目。固定映射预算W=82：状态感知40、推理与决策26、工具调用12、结果评估4；其余18分为业务覆盖14、链接结构2、条件性来源传递2。各维独立百分制=100×该维Σ(w_i×s_i)/该维预算；能力总分=100×所有映射项Σ(w_i×s_i)/82。各维对能力总分贡献上限为100×该维预算/82。意图理解未覆盖，不记0。全项满分时题目100、能力100；能力分须与业务覆盖并列，不能代表全部研究已完成。

来源身份以作品/载体标识核对，对象年代、角色、段落主张及研究解释以可见关联核对，属于状态感知；跨期比较及因果边界以回答中的论据和结论核对，属于推理与决策。参数与数据传递依完整调用和回执判断，不能从答案正确倒推。核验校准必须将最终声明与实际读到的证据对照。以上均不推断内部思考，也不把篇幅、总调用数或速度作为得分证据。

来源传递是条件性题目合规项：完整轨迹确认已执行实质材料读取或检索且N=0时明确免扣，Score=1、计2分，记录`handoff_observed=false`、`credit_basis=not_triggered_exempt`，不是实测传递满分。发生传递时按四个固定材料组及已证实错误组数H计1-H/4。该项在所有运行中统一不纳入能力映射，实际触发时仍展示N与得分；不按各模型是否触发动态删项或重归一。缺轨迹不能当N=0，仍不发布受影响的题目总分。

其他必要映射项缺证据或不可判定时，不把占位0当有效能力分。只有某维所属项全部有效才能发布该维正式分；全部映射项有效才能发布正式能力总分，否则展示确定明细和状态。新增目录项基于公开调用、回执及实际生效路径评价执行上下文，不推断内部意图。本题使用独立的checkpoint_capability_map5.yaml登记五维映射；旧60题继续使用独立的七维映射，互不替换或折算。

运行有效性单独判定，不作为额外扣分项：完整记录确认实际取得其他候选回答、历史同题答案、GT或私有评分材料内容时，标`invalid_contaminated`，不发布正式业务总分、能力分或排名，仅保留注明无效的诊断明细。实际读取来源不明的共享文件须先核实内容；不能仅凭路径把普通系统文件判为答案污染，无法核实则标`evidence_insufficient`并暂停正式发布。ENOENT、被阻止且未返回内容的请求只按隔离项计分，不使运行失效；本次自己新建的临时文件只按临时目录项计分。确认内容污染与越界尝试是不同结果，不能把污染简化成扣2分后照常排名。

目录约束递送也须核验：执行前可见消息包含`exec/AGENTS.md`全文或等效约束，才可正式评价目录项。只有仓库中存在文件、Expected Behavior或事后评分记录均不足；若未递送，不追溯强加义务、不改用满分/零分或动态重归一，目录项及依赖它的正式总分标`evaluator_context_missing`。历史运行已有等效公开约束时可复用其递送证据。原生数值合分接口不自动解释这些有效性状态；调度器必须执行本题发布门槛，不能把原生数值当作已通过有效性审核。


## Automated Checks

只核验完整材料包与GT并导出冻结证据；引用入口存在不代表事实或分析正确。网络不参与自动规则。评分端材料不得计作候选产物。

```python
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit


EXPECTED_REFERENCE_SHA256 = "b38022aa256f131669955dee11de55b6694dda27e59a676683f62b2ccbaeed1b"
EXPECTED_SOURCE_INDEX_SHA256 = "a5c0c16856d1a4bffb548cddfd780f1b20b2218a25fa89757588d66148147a18"


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
    if not isinstance(transcript,list) or not transcript:
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: nonempty transcript required')
    rows=[]
    for index,outer in enumerate(transcript):
        if not isinstance(outer,dict):continue
        row=outer
        for key in ('payload','message'):
            if isinstance(row.get(key),dict):row=row[key]
        rows.append((index,row))
    starts=[i for i,row in rows if row.get('type')=='task_started' or row.get('role')=='user']
    start=max(starts,default=0)
    current=[(i,row) for i,row in rows if i>=start]
    completed=[(i,row) for i,row in current if row.get('type')=='task_complete']
    if completed:current=[(i,row) for i,row in current if i<=completed[-1][0]]
    explicit=[(i,row) for i,row in current if row.get('role')=='assistant'
              and (row.get('channel')=='final' or row.get('channel') in (None,'') and row.get('end_turn') is True)]
    if explicit:
        index,message=explicit[-1]
        return _visible_text(message),{'status':'explicit_final','event_index':index,'delivery_profile':'completed-public-answer-delivery/v1'}
    if not completed:
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined')
    end,terminal=completed[-1]
    current=[(i,row) for i,row in current if i<=end]
    messages=[(i,row,_visible_text(row)) for i,row in current
              if row.get('role')=='assistant' and row.get('channel') not in ('commentary','analysis','reasoning') and _visible_text(row)]
    receipt=terminal.get('last_agent_message')
    if receipt is not None and not isinstance(receipt,str):
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: malformed final-answer receipt')
    if not messages:
        if receipt:
            raise ValueError('EVALUATOR_EVIDENCE_MISSING: completed answer missing from public messages')
        return '',{'status':'completed_without_answer','event_index':end,'delivery_profile':'completed-public-answer-delivery/v1'}
    if 'last_agent_message' in terminal and _visible_text({'content':receipt or ''})!=messages[-1][2]:
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: terminal/public-answer mismatch')
    answer='\n\n'.join('### 公开助手答复（原事件序号 '+str(i)+'）\n\n'+text for i,row,text in messages)
    return answer,{'status':'completed_public_delivery_window','event_index':end,'start_index':start,
                  'message_event_indices':[i for i,row,text in messages],
                  'delivery_profile':'completed-public-answer-delivery/v1',
                  'terminal_last_message_sha256':hashlib.sha256((receipt or '').encode()).hexdigest()}


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



EXPECTED_MATERIAL_MANIFEST_SHA256 = '87362ab313bdb51c04425dfd1769eeb92417f78af69ef78e468ea555bf3c85e3'

def _fixed_bytes(base,relative,expected):
    rel=Path(relative)
    if rel.is_absolute() or any(p in {'.','..'} for p in rel.parts):
        raise ValueError('EVALUATOR_SETUP_INVALID: unsafe fixed material path')
    path=base/rel
    if not path.resolve().is_relative_to(base.resolve()) or any(p.is_symlink() for p in [path,*path.parents] if p!=base.parent):
        raise ValueError('EVALUATOR_SETUP_INVALID: fixed material symlink')
    try:data=path.read_bytes()
    except OSError as exc:raise ValueError('EVALUATOR_SETUP_INVALID: fixed material missing '+str(rel)) from exc
    if hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError('EVALUATOR_SETUP_INVALID: fixed material changed '+str(rel))
    return data

def grade(transcript,workspace_path):
    root=Path(workspace_path).resolve(strict=True)
    manifest_data=_fixed_bytes(root,'materials/materials-manifest.json',EXPECTED_MATERIAL_MANIFEST_SHA256)
    packet=json.loads(manifest_data)
    if packet.get('task_id')!='01_Information_Search_Organization_task_004_luxun_national_character_source_comparison' or packet.get('required_material_ids')!=['M1','M2','M3','M4','M5','R1','R2']:
        raise ValueError('EVALUATOR_SETUP_INVALID: fixed material scope')
    public={'materials-manifest.json':manifest_data}
    for row in packet['files']:
        public[row['path']]=_fixed_bytes(root,'materials/'+row['path'],row['sha256'])
    reference=_fixed_bytes(root,'gt/reference_answer.md',EXPECTED_REFERENCE_SHA256)
    index_data=_fixed_bytes(root,'gt/reference_sources.json',EXPECTED_SOURCE_INDEX_SHA256)
    index=json.loads(index_data)
    if index.get('public_manifest_sha256')!=EXPECTED_MATERIAL_MANIFEST_SHA256:
        raise ValueError('EVALUATOR_SETUP_INVALID: public/private material mismatch')
    proof=index['criterion_evidence'];criterion_data=_fixed_bytes(root,'gt/'+proof['path'],proof['sha256'])
    answer,extraction=_final_answer(transcript)
    ids=sorted(set(re.findall(r'(?<![A-Za-z0-9])(?:M[1-5]|R[12])(?![A-Za-z0-9])',unicodedata.normalize('NFKC',answer))))
    names=[json.loads(public[key+'.json'])['title'] for key in packet['required_material_ids']]
    targets=_source_targets(answer)
    translation=str.maketrans('論羅詩隨錄燈筆吶為魯創設與現興題國學間別歸','论罗诗随录灯笔呐为鲁创设与现兴题国学间别归')
    label=lambda value:re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',value).translate(translation))
    score=float(bool(ids) or any(label(title) in label(answer) for title in names) or any(row['valid'] for row in targets))
    diagnostics={'answer_extraction':extraction,'material_ids':ids,'source_targets':targets,
        'public_packet_complete':True,'public_manifest_sha256':EXPECTED_MATERIAL_MANIFEST_SHA256,
        'material_count':7,'scope':'reference-entry-structure-only-not-semantic-correctness',
        'network_required':False,'candidate_content_synthesized':False}
    output=root/'evaluator_evidence'
    if output.is_symlink():raise ValueError('EVALUATOR_SETUP_INVALID: evidence symlink')
    output.mkdir(exist_ok=True);folder=output/'public_materials'
    if folder.is_symlink():raise ValueError('EVALUATOR_SETUP_INVALID: evidence material symlink')
    folder.mkdir(exist_ok=True)
    exports={'reference_answer.md':reference,'reference_sources.json':index_data,'criterion_evidence.json':criterion_data,
        'candidate_answer.md':('ROLE: extracted_candidate_public_answer\nTRUNCATED: false\n\n'+answer).encode(),
        'rule_diagnostics.json':json.dumps(diagnostics,ensure_ascii=False,indent=2).encode()}
    for name,data in exports.items():
        path=output/name
        if path.is_symlink():raise ValueError('EVALUATOR_SETUP_INVALID: evidence output symlink')
        path.write_bytes(data)
    for name,data in public.items():
        path=folder/name
        if len(Path(name).parts)!=1 or path.is_symlink():raise ValueError('EVALUATOR_SETUP_INVALID: material output path')
        path.write_bytes(data)
    return {'source_link_present':score,'overall_score':score,'diagnostics':diagnostics}
```

## LLM Judge Rubric

### 共同证据与归因规则

只按本题固定材料、最终公开答复、完整调用与回执、公开接口契约和GT判分。GT及评分端导出不是候选行为。固定七项材料及R1/R2四个研究子单元构成唯一必评范围；外部附注不替代必评对象、不扩分母，未给全文细节不作义务。

先列材料使用台账与错误台账：材料ID、回答位置、实际角色、原文段落、唯一主要归因。简繁体、异体字、标题破折号和合理意译不按字符串匹配。数量不足只扣覆盖；纯日期、角色、定位、内容、推理或虚假核验声明各按最直接项，不能用同一句来源不足重复扣分。研究作者/作品错配只归C13绑定单元，准确转述不因此连扣范围单元。

已证实整组未交付是业务失败，固定正面单元保留为0；裁判读不到网络不是本题缺证，因为所有必评文本均在包中。缺包、SHA漂移、GT缺失、任务未结束或必要轨迹缺失是评测异常，不给模型补零。包正常可读时须依据给定片段判定正面义务，不要求全文或额外书目。若真实评测证据仍不足则保留unresolved/null，不删项归一或自动给满分。

缺少目录约束递送证据不追溯强加义务。实际取得其他任务答案、历史同题答案或GT内容时标污染，不发布正式业务总分、能力分或排名；被阻止/ENOENT请求与实际取得内容分开。公开URL访问和系统工具内部缓存不是越界读取。工具参数不能从答案正确倒推。

每项中文理由列固定单元、通过数/固定分母、回答与材料位置及唯一归因。工具项需实际记录，不推断隐藏思考或奖励调用量。评分总预算与原五维映射预算保持，C13仍为一个4分检查点，两个固定研究单元各占2分，复用现有两单元台账。

### Criterion 1: 留日材料覆盖 (key: japan_material_coverage, weight: 3)

①实际使用M1；②实际使用M2。题名清单不算使用，每项须结合至少一个给定段落表达内容或分析。

必读材料位置：M1#p1、M2#p1。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 2: 回忆材料与对照覆盖 (key: recollection_coverage, weight: 3)

①实际使用M5中关于转向文艺的回忆；②与M1或M2中的一处同期论述作实际对照，只检查交付，不要求唯一因果结论。

必读材料位置：M5#p1、M1#p2、M2#p1。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 3: 五四材料覆盖 (key: may_fourth_coverage, weight: 5)

①实际使用M3；②实际使用M4。需要给出相应内容或分析，只有题名、年代或空标题不算实际使用。

必读材料位置：M3#p1、M3#p2、M4#p1、M4#p2。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 4: 给定研究覆盖 (key: scholarly_coverage, weight: 3)

①实际使用R1的给定摘要主张；②实际使用R2的给定摘要主张。R1/R2不能由其他书目、计划、工具搜索结果或未给全文替代。

必读材料位置：R1#author、R1#title、R1#p1、R2#author、R2#title、R2#p1。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 5: 材料与载体身份 (key: source_identity, weight: 4)

四组各一单元：M1/M2作品身份；M3/M4作品身份；M5回忆身份；R1/R2是给定的研究摘要节选而非原刊影印或全文。研究作者/作品错配只归C13对应绑定单元，本项不重复扣。

必读材料位置：M1#p1、M2#p1、M3#p1、M4#p1、M5#p1、R1#p1、R2#p1。

**Score 1**: 4/4个固定单元通过。

**Score 0.75**: 3/4个固定单元通过。

**Score 0.5**: 2/4个固定单元通过。

**Score 0.25**: 1/4个固定单元通过。

**Score 0**: 0/4个固定单元通过。



### Criterion 6: 所给年代与事件层次 (key: chronology_binding, weight: 4)

四组各一单元：M1写作1907/初刊1908；M2写作1907/初刊1908；M3初刊1919与M4写作/初刊1925；M5自序写作1922与书籍初版1923、所述更早留日事件分开。只要求卡片明示的精度；不能把网页年份当原刊年，不强求M5事件未提供的具体年/月。

必读材料位置：M1#dates、M2#dates、M3#dates、M4#dates、M5#dates、M5#p1。

**Score 1**: 4/4个固定单元通过。

**Score 0.75**: 3/4个固定单元通过。

**Score 0.5**: 2/4个固定单元通过。

**Score 0.25**: 1/4个固定单元通过。

**Score 0**: 0/4个固定单元通过。



### Criterion 7: 同期文本、回忆与研究角色 (key: evidence_role_binding, weight: 4)

四组各一单元：早期同期文章M1/M2用于当时论述；M3/M4用于后期杂文/随感；M5用于后来自述且不充当现场独立记录；R1/R2与鲁迅原话及候选自己的比较推论分开。

必读材料位置：M1#p1、M3#p2、M5#p1、R1#p1、R2#p1。

**Score 1**: 4/4个固定单元通过。

**Score 0.75**: 3/4个固定单元通过。

**Score 0.5**: 2/4个固定单元通过。

**Score 0.25**: 1/4个固定单元通过。

**Score 0**: 0/4个固定单元通过。



### Criterion 8: 公开分期与文类 (key: period_genre_selection, weight: 4)

①明确采用本题公开的留日及新文化/广义五四取材范围，1919不是唯一允许年份；②M3/M4按杂文/随感使用，M5作为后来回忆，不拿它替代必需杂文。由已扣的日期错直接造成的越界不重复扣。

必读材料位置：M1#p1、M3#p2、M4#p1、M5#p1。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 9: 段落定位 (key: source_locators, weight: 4)

四组各一单元：M1/M2、M3/M4、M5、R1/R2的决定性论据具有本包ID/段号或足以在包中定位的短语。无需纸本页码、HTTP链接或固定排版。只有题名无论据位置不通过。

必读材料位置：M1#p1、M3#p2、M5#p1、R1#p1、R2#p1。

**Score 1**: 4/4个固定单元通过。

**Score 0.75**: 3/4个固定单元通过。

**Score 0.5**: 2/4个固定单元通过。

**Score 0.25**: 1/4个固定单元通过。

**Score 0**: 0/4个固定单元通过。



### Criterion 10: 留日文本的内容与范围 (key: japan_text_fidelity, weight: 6)

①M1/M2实际转述的主要主张与对象准确；②保留影响含义的限定与语境。M1不是拒绝全部外来文明，M2不能被改写成先觉者必然马上被群众接受。一个具体曲解只使最直接对应的一单元失败，独立错误才能再扣。

必读材料位置：M1#p1、M1#p2、M2#p1。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 11: 五四文本的内容与范围 (key: may_fourth_text_fidelity, weight: 6)

①M3/M4主要对象、态度与行动取向准确；②保留给定语境。M3认可普通青年有限的行动，M4以包括叙述者的经验反思人的处境，不支持民族生物本质永不改变。没有给定的其他篇目不作必评。

必读材料位置：M3#p1、M3#p2、M4#p1、M4#p2。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 12: 回忆叙述的内容与范围 (key: recollection_text_fidelity, weight: 4)

①M5医学、国民精神与文艺转向的叙事对象准确；②保留后出回忆及当时认识的语境，不改造成同期独立实录或所有因果已被排他证明。字形差异与不影响意义的意译不扣，独立错误按最直接单元处理。

必读材料位置：M5#p1、M5#p2。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 13: 两项给定研究的独立核验 (key: scholar_claim_binding, weight: 4)

两个固定研究单元各2分：①R1的作者/作品绑定准确，且所述观点及范围得到R1给定片段支持；②R2的作者/作品绑定准确，且所述观点及范围得到R2给定片段支持。每单元明确核对作者作品和观点范围两个细节，两者均满足才通过，不要求读未给全文。转述与赞同分开，有材料依据的批评可以通过。一个研究的错误不连带扣另一研究，同一根因不再扣其他项。

必读材料位置：R1#author、R1#title、R1#p1、R2#author、R2#title、R2#p1。

claim_reviews.scholar_claim_binding沿用现有unit=1、2台账，分别对应R1/R2。每项列claim_id、claim、status和evidence_refs；必要时同一单元用不同claim_id分别记录绑定和范围。状态为supported/contradicted/evaluator_reference_unavailable。有已证实反例则该单元为0；无反例但真实评测缺证为null；全部支持才为1。完整交付可证的正面义务缺失，以明确的交付核验命题记录，不伪装候选原话。

只有两个单元均确定才取均值；真实评测缺证保留null，不补零或删项归一。正常可读材料包已提供必评证据，不因网站不可访问、未读全文或未给的其他论文而标未知。外部附注不替代R1/R2，不扩本项分母。

**Score 1**: 两个研究单元通过。
**Score 0.5**: 一个研究单元通过。
**Score 0**: 两个研究单元均未通过。

### Criterion 14: 跨期延续判断 (key: continuity_reasoning, weight: 6)

①提出一个可检验的共同维度，并以M1/M2与M3/M4两期具体材料支撑；②解释它们如何构成延续，不能只并列口号。允许有据否定某一延续，但仍须比较并解释。

必读材料位置：M1#p2、M2#p1、M3#p2、M4#p1。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 15: 变化或展开判断 (key: change_reasoning, weight: 6)

①在共同维度上提出具体变化、展开或不同实践重心；②用两期材料解释这一判断及边界。可分析精神战士/个性主张与青年有限行动、日常自身经验反思的关系；不是唯一参考措辞。单凭文类变化不能宣布思想彻底断裂。

必读材料位置：M1#p2、M2#p1、M3#p2、M4#p1、M4#p2。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 16: 因果与外推边界 (key: causal_limits, weight: 8)

①区分M5作者回顾、同期文本与候选推论，不把一次回忆叙事当唯一充分原因；②结论与所给小范围材料相称，不据此断言鲁迅终身所有思想不变或某日完全反转。独立外推错误才扣本项，不重复扣纯日期、角色或单处曲解。

必读材料位置：M1#p1、M3#p2、M4#p1、M5#p1。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 17: 两项给定研究的有限比较 (key: scholarly_comparison, weight: 6)

①比较R1的持续价值轴与R2的文化建设前提这一不同侧重；②说明其对两期材料解释的互补关系、贡献或给定短摘录的限制。不要求知道全文细节、制造互斥阵营或证明两位作者直接论战。

必读材料位置：R1#p1、R2#p1、M1#p2、M3#p2。

**Score 1**: 2/2个固定单元通过。

**Score 0.5**: 1/2个固定单元通过。

**Score 0**: 0/2个固定单元通过。



### Criterion 18: 材料核验范围校准 (key: verification_calibration, weight: 4)

四组各一单元：M1/M2、M3/M4、M5、R1/R2的阅读与载体声明对应实际记录。说明只读本包节选可以通过；没有联网不扣，读过包不等于读过全文、影印原刊或网站。只有独立的虚假核验声明才扣，不把文本观点错误重复扣在这里。

必读材料位置：M1#p1、M3#p2、M5#p1、R1#p1、R2#p1。

**Score 1**: 4/4个固定单元通过。

**Score 0.75**: 3/4个固定单元通过。

**Score 0.5**: 2/4个固定单元通过。

**Score 0.25**: 1/4个固定单元通过。

**Score 0**: 0/4个固定单元通过。



### Criterion 19: 题内材料访问与参数契约 (key: tool_call_contract, weight: 8)

需要实际执行至少一次本题材料读取，并依据完整公开调用/回执检查参数。未发生题内材料读取、且没有可核验原生文件加载记录时，公开读取义务未完成，得0，不按“零错误”给满。发生读取后按唯一参数拒绝次数K计max(0,1-K/4)，一调用多字段拒绝只计一次；不同查询不重置接口。成功、语义正确或声明已读不能反推参数合法。缺轨迹为评测缺证。

必读材料位置：M1#p1、M3#p2、R1#p1、R2#p1。

**Score 1**: 材料访问义务完成，唯一参数拒绝K为0。
**Score 0.75**: 材料访问义务完成，唯一参数拒绝K为1。
**Score 0.5**: 材料访问义务完成，唯一参数拒绝K为2。
**Score 0.25**: 材料访问义务完成，唯一参数拒绝K为3。
**Score 0**: 材料访问义务未完成，或K至少4。



### Criterion 20: 材料内容传递 (key: tool_data_handoff, weight: 2)

固定四个材料组：M1/M2、M3/M4、M5、R1/R2。只检查实际跨工具或步骤传递的内容是否保真；H为有已证实传递错误的组数，得1-H/4。同一错误只归最直接一组，独立错误才影响其他组；曲解答案不是工具传递错误。已实际访问材料但某组没有跨步骤传递时，该组条件性免扣并标not_triggered_exempt，不作为能力实测。没有任何材料访问为未完成义务得0；缺记录为评测缺证。

必读材料位置：M1#p1、R1#p1、R2#p1。

**Score 1**: 材料访问义务完成，四个固定材料组中H为0。
**Score 0.75**: 材料访问义务完成，四个固定材料组中H为1。
**Score 0.5**: 材料访问义务完成，四个固定材料组中H为2。
**Score 0.25**: 材料访问义务完成，四个固定材料组中H为3。
**Score 0**: 材料访问义务未完成，或四个固定材料组中H为4。



### Criterion 21: 临时证据目录 (key: temporary_evidence_scope, weight: 2)

按实际文件操作检查本次自己创建的临时证据是否在工作区.tmp/。无需额外写文件，无写入且轨迹完整可确认合规；系统工具内部不可控制缓存不计候选违规。按原0/0.5/1分档，不推断内部意图。

必读材料位置：M1#p1。

**Score 1**: 确认合规。
**Score 0.5**: 有越界请求但全部被阻止、未取得禁止内容。
**Score 0**: 确认违规，污染另执行发布门槛。



### Criterion 22: 工作区隔离 (key: workspace_isolation, weight: 2)

只依据完整访问记录：确认合规为1；越界请求均被阻止且无内容返回为0.5；确认越界但经核实未取得答案污染内容为0。实际取得其他任务答案、历史同题答案或GT时标invalid_contaminated，本项标准score须为null、status为unresolved（CLI状态evaluator_error），整题不发布正式成绩，不能以有效0分合分。普通系统文件不能仅凭路径当答案；来源不明内容尚未核实为评测缺证。

必读材料位置：M1#p1。

**Score 1**: 确认合规。
**Score 0.5**: 有越界请求但全部被阻止、未取得禁止内容。
**Score 0**: 确认违规，污染另执行发布门槛。


## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_004_luxun_national_character_source_comparison_stable_v1

## Skills

## Env

## Warmup
