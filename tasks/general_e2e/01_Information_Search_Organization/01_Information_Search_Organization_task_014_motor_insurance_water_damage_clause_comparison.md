---
id: 01_Information_Search_Organization_task_014_motor_insurance_water_damage_clause_comparison
name: 车险发动机进水保障与免赔条款版本检索
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
    - path: evaluator_evidence/candidate_answer.md
      role: evaluator_extracted_candidate_final
    - path: evaluator_evidence/task_context.md
      role: public_task_context
    - path: evaluator_evidence/rule_diagnostics.json
      role: grader_generated_diagnostics
tags: [custom, finance, insurance, general_task_e2e]
---

## Prompt

家庭自用燃油车的发动机进水损坏，2014版和2020版车险条款分别怎么保？请比较主险、发动机相关附加条款及不计免赔、绝对免赔规定，标出中保协正式条款依据。

## Expected Behavior

自行检索中国保险行业协会2014版、2020版正式机动车商业车险示范条款，比较发动机进水损坏的主险责任、附加险作用及免赔机制。关联相同版本中的承保、免责、附加条款和免赔规则，给出分组直接回答与可定位正式依据。区分示范条款事实与具体保单或真实事故的赔付结论，不要求文件交付，也不要求判断二次启动的实际赔付。

执行前将exec/AGENTS.md全文作为工作区指令或公开上下文送达Agent并保留送达记录。标准运行路径为/tmp_workspace/AGENTS.md。仅将文件放入目录不替代送达证据。执行时不提供GT；执行结束后才注入GT。运行配置、网络外部阻断和评分日志缺失不能直接记为模型失败。

## Grading Criteria

业务总分100：core_accuracy为85分，source_binding为15分；tool_call_contract、verification_calibration、rule_application均为业务weight=0的独立能力项。所有语义结论由LLM/人工判分；Automated Checks为0业务分，仅执行可信证据准备、评分合法性、算术及运行有效性诊断，不能用关键词命中证明条款理解正确。

| 完整输出key | 检查点 | 业务weight | 能力m及映射 |
|---|---|---:|---|
| llm_judge.core_accuracy | 保障结构与免赔机制 | 85 | 不映射；事实正确不直接证明推理正确 |
| llm_judge.source_binding | 正式版本、条款对象与依据关联 | 15 | 10；state_awareness#3 |
| llm_judge.rule_application | 候选实际采用前提下的规则组合 | 0 | 20；reasoning_and_decision_making#1 |
| llm_judge.tool_call_contract | 按实际调用计数的参数契约 | 0 | 10；tool_invocation#1 |
| llm_judge.verification_calibration | 交付前实际核验及声明校准 | 0 | 5；result_evaluation#1、#10 |

core_accuracy内部固定四组，不新增独立rubric key：旧版保障20、新版保障20、旧版免赔25、新版免赔20。每组四个二值原子单元，内部组分=通过数/4，记录分子、分母、候选位置及扣分依据。raw_core=20×旧版保障组分+20×新版保障组分+25×旧版免赔组分+20×新版免赔组分。将raw_core/85向下取到{0,.25,.5,.75,1}档位；该量化规则必须在看见候选前固定，不临时插值。

关键逆转只使用core_accuracy本项封顶：存在最终回答未撤回的任一重大责任/免赔逆转时core_accuracy=min(常规档位,.5)。题目分=85×core_accuracy+15×source_binding，因此重大逆转时原生业务总分最高57.5。此机制直接写入原生rubric，不依赖原生Runner不会调用的外部helper；不再追加全题减分或第二次封顶。仅遗漏细节不是重大逆转。更正且明确撤回的旧陈述不触发。

| 关键逆转ID | 触发事实 | 主要归因单元 |
|---|---|---|
| K1 | 认定2014版主险无须相关附加险即可承担被专门排除的发动机进水损坏 | O1/O2，优先实际错误规则对应者 |
| K2 | 认定2020版必须另买旧版涉水险才有该责任，或将新版除外特约解释为增加进水保障 | N1/N3，按实际逆转 |
| K3 | 认定2014版无论是否对应投保不计免赔率险都必然自付15%，或将不对应投保也说成无条件免除15% | D3/D4 |
| K4 | 认定2020版所有保险组合一律零免赔，或将金额与比例混同到改变免赔结论 | E1/E3/E4，按实际错误 |

能力预算W=45，state10、reasoning20、tool10、result5，意图理解未覆盖。各维=100×Σ本维(m×Score)/Σ本维m；能力总分=100×Σ(m×Score)/45。能力分与业务分分别报告，不相加。依据capabilities-2026-09-23-v1及上述局部编号。reasoning仅有规则组合一项，内部关键组合占100%；不能将检索事实错直接作为推理错。YAML登记映射关系，旧七维报告器不自动实施该m加权，评分调度须明确复核。

每个原子错误记录唯一error_id和主owner。事实、条款解释及遗漏在core_accuracy内部对应单元处理；同一错误的改写和重复出现不增加分母。同一个错误跨两个内部单元时，只扣直接主owner，不把结果后果再扣第二单元。source_binding只检查独立的正式版本身份、条款定位和事实对象关联缺陷；正确正式来源被误读只扣core，不再扣source。若用错来源导致同一内容错误，选择core或source作为主owner并记录另项不重复扣，不能再增加“覆盖”“真实性”“推理”第三份扣分。规则组合项在候选自己的事实前提下判断推导；正确沿用错误事实不扣推理。确有另一个独立错误推导才扣rule_application。交付前核验只接受独立的过程证据；额外夸大核验声明须有声明与记录两侧证据，不能由答案事实错误推导出未核验或虚假完成。

分数状态pass/partial/fail代表有效得分；evidence_insufficient、blocked_external、not_observed、evaluator_error不是0分或1分。数值接口仅以0占位，不发布受影响正式分，不删项后重新归一。业务可由最终回答评分，不代表过程轨迹也充分。单独可判维度可展示；全部映射项有效才发布正式能力总分。完整记录显示确实未履行公开要求可记有效0，缺记录不能据此推断。

运行隔离是有效性前提：有证据确认读取本题GT或另一模型本题答案，run_status=contaminated_run，正式业务及能力分均不发布。必要隔离记录缺失为evidence_insufficient。仅路径名称、工具内部缓存或失败读取不能证明内容污染。违反公开临时目录约定但未证实内容污染时记录违规，不临时追加业务扣分，也不混入参数合法性。

规则执行与发布协议：grade()只在候选执行结束且GT注入后运行；规则输出为0业务分的诊断，不与语义得分平均。score_core接收裁判去重后的固定组比例及关键逆转布尔值，执行同一rubric的向下分档和本项上限；score_tool只对裁判逐次核实的参数错误次数计算分数。代码不能自行判断金融事实、关键逆转或工具错误类型，这些仍属大模型/人工判分。

裁判notes须保留各内部单元的候选位置、实际值/行为、通过或失分、唯一业务owner/能力owner、继承错误豁免、来源位置、证据状态及关键逆转证据。子点原始分用于展示，不与原生core重复相加。aggregate_review输入已判定scores、statuses、ability_statuses、run_status及core_groups、critical_error、parameter_errors，只校验与合分；不是第二轮语义裁判。所有语义key须返回；不可评分项以0占位并在notes注明状态。过程证据只用公开调用、回执及显式操作，不索取隐藏思考。

发布前须执行aggregate_review或人工等价复核。原生Runner不会自动调用该helper，也不会自动识别notes里的不可评分/污染状态；因此其原始数值不能覆盖本题的有效性门槛。日志适配须提供可信的final频道、end_turn结束标志或task_complete终止事件；单独finish_reason=stop及commentary进度消息不足以证明任务结束。日志缺失不得当作完整日志；仅本函数导出成功不证明工具轨迹完整或运行隔离。正常有效记录的业务分与原生weight合分一致。能力m加权及无效运行禁发由评分调度显式执行，不宣称旧七维报告器已实现。

## Automated Checks

```python
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
import re

EXPECTED_REFERENCE_SHA256 = '66a79e7a0ba4d9af6e9a3929f8621fff8cce66425f598f21afcccf63cf28f805'
EXPECTED_CONTEXT_SHA256 = '0532c3944e2704129dccd2dc9f33414f381e417a8c5db496f019c66c22fc7499'
RESULT_WEIGHTS = {'core_accuracy': 85, 'source_binding': 15}
ABILITY_MAP = {'source_binding': ('state_awareness', 10), 'rule_application': ('reasoning_and_decision_making', 20), 'tool_call_contract': ('tool_invocation', 10), 'verification_calibration': ('result_evaluation', 5)}
ALLOWED_SCORES = {'tool_call_contract': [0.0, 0.25, 0.5, 0.75, 1.0], 'rule_application': [0.0, 0.25, 0.5, 0.75, 1.0], 'source_binding': [0.0, 0.25, 0.5, 0.75, 1.0], 'core_accuracy': [0.0, 0.25, 0.5, 0.75, 1.0], 'verification_calibration': [0.0, 0.25, 0.5, 0.75, 1.0]}
CORE_GROUPS = {'old_coverage': (20, 4), 'new_coverage': (20, 4), 'old_deductibles': (25, 4), 'new_deductibles': (20, 4)}

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
                and block.get("type") in {"text", "input_text", "output_text", "assistant_text"}
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
    explicit = [(i, row) for i, row in current
                if row.get("role") == "assistant"
                and (row.get("channel") == "final"
                     or (row.get("channel") in {None, ""} and row.get("end_turn") is True))]
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



def _safe_read(root, relative):
    path = root / relative
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink():
            raise ValueError("EVALUATOR_ERROR: symlink evidence path")
    return path.read_bytes()


def grade(transcript: list, workspace_path: str) -> dict:
    """Deterministic evidence preparation only; no candidate quality points."""
    if not isinstance(transcript, list) or not transcript:
        raise ValueError("EVALUATOR_EVIDENCE_MISSING: nonempty transcript required")
    root = Path(workspace_path).resolve(strict=True)
    reference = _safe_read(root, "gt/reference_answer.md")
    context = _safe_read(root, "AGENTS.md")
    if hashlib.sha256(reference).hexdigest() != EXPECTED_REFERENCE_SHA256:
        raise ValueError("EVALUATOR_ERROR: reference version mismatch")
    if hashlib.sha256(context).hexdigest() != EXPECTED_CONTEXT_SHA256:
        raise ValueError("EVALUATOR_SETUP_INVALID: public context changed or wrong version")
    context_text = context.decode("utf-8").strip().replace("\r\n", "\n")
    delivered = False
    for outer in transcript:
        if not isinstance(outer, dict):
            continue
        row = outer
        for field in ("payload", "message"):
            if isinstance(row.get(field), dict):
                row = row[field]
        if row.get("role") in {"user", "system", "developer"}:
            delivered |= context_text in _visible_text(row).replace("\r\n", "\n")
    if not delivered:
        raise ValueError("EVALUATOR_SETUP_INVALID: public task context delivery not evidenced")
    answer, receipt = _final_answer(transcript)
    diagnostics = {"status": "evidence_prepared", "scored_automated_points": 0,
                   "context_delivery_verified": True, "answer_extraction": receipt,
                   "note": "Does not verify financial facts or prove candidate self-checking"}
    target = root / "evaluator_evidence"
    if target.is_symlink():
        raise ValueError("EVALUATOR_ERROR: symlink output directory")
    target.mkdir(exist_ok=True)
    exports = {
        "reference_answer.md": "ROLE: evaluator_reference_not_agent_output\nTRUNCATED: false\n\n" + reference.decode("utf-8"),
        "candidate_answer.md": "ROLE: extracted_candidate_final_answer\nTRUNCATED: false\n\n" + answer,
        "task_context.md": "ROLE: public_input_not_candidate_answer\nTRUNCATED: false\n\n" + context_text,
        "rule_diagnostics.json": json.dumps(diagnostics, ensure_ascii=False, indent=2),
    }
    for name, content in exports.items():
        output = target / name
        if output.is_symlink():
            raise ValueError("EVALUATOR_ERROR: symlink output file")
        output.write_text(content, encoding="utf-8")
        if output.read_text(encoding="utf-8") != content:
            raise ValueError("EVALUATOR_ERROR: export readback mismatch")
    return {"diagnostics": diagnostics}


def score_core(group_scores: dict, critical_error: bool = False) -> dict:
    """Arithmetic on semantically reviewed, deduplicated group scores."""
    if not isinstance(group_scores, dict) or set(group_scores) != set(CORE_GROUPS):
        raise ValueError('EVALUATOR_ERROR: exact core group keys required')
    if not isinstance(critical_error, bool):
        raise ValueError('EVALUATOR_ERROR: critical_error must be a reviewed boolean')
    raw = Decimal(0)
    for key, (weight, units) in CORE_GROUPS.items():
        value = group_scores[key]
        allowed = [i / units for i in range(units + 1)]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in allowed:
            raise ValueError('EVALUATOR_ERROR: illegal group fraction ' + key)
        raw += Decimal(weight) * Decimal(str(value))
    band = float((raw * 4 // 85) / 4)
    return {'raw_core': float(raw), 'ordinary_band': band,
            'core_accuracy': min(band, .5) if critical_error else band}


def score_tool(parameter_errors: int) -> float:
    """Each independently issued erroneous call counts; successes do not dilute."""
    if isinstance(parameter_errors, bool) or not isinstance(parameter_errors, int) or parameter_errors < 0:
        raise ValueError('EVALUATOR_ERROR: nonnegative reviewed error count required')
    return max(0.0, 1.0 - parameter_errors / 4)


def aggregate_review(scores: dict, statuses: dict, ability_statuses: dict, run_status: str,
                     *, core_groups=None, critical_error=False, parameter_errors=None) -> dict:
    """Arithmetic after semantic review; does not classify financial facts."""
    keys = set(RESULT_WEIGHTS) | set(ABILITY_MAP)
    if set(scores) != keys or set(statuses) != keys or set(ability_statuses) != set(ABILITY_MAP):
        raise ValueError('EVALUATOR_ERROR: exact score/status keys required')
    if run_status not in {'valid', 'contaminated_run', 'evidence_insufficient'}:
        raise ValueError('EVALUATOR_ERROR: explicit run validity required')
    valid = {'pass', 'partial', 'fail'}
    unavailable = {'evidence_insufficient', 'blocked_external', 'not_observed', 'evaluator_error'}
    if any(s not in valid | unavailable for s in list(statuses.values()) + list(ability_statuses.values())):
        raise ValueError('EVALUATOR_ERROR: unsupported evidence status')
    for key, number in scores.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number not in ALLOWED_SCORES[key]:
            raise ValueError('EVALUATOR_ERROR: invalid score '+key)
        expected_status = 'pass' if number == 1 else 'fail' if number == 0 else 'partial'
        if statuses[key] in valid and statuses[key] != expected_status:
            raise ValueError('EVALUATOR_ERROR: score/status mismatch '+key)
        if key in ability_statuses and ability_statuses[key] in valid and ability_statuses[key] != expected_status:
            raise ValueError('EVALUATOR_ERROR: ability score/status mismatch '+key)
        if statuses[key] in unavailable and number != 0:
            raise ValueError('EVALUATOR_ERROR: unavailable evidence requires zero placeholder')
    if statuses['core_accuracy'] in valid:
        check = score_core(core_groups, critical_error)
        if scores['core_accuracy'] != check['core_accuracy']:
            raise ValueError('EVALUATOR_ERROR: core score disagrees with reviewed ledger')
    if statuses['tool_call_contract'] in valid:
        if scores['tool_call_contract'] != score_tool(parameter_errors):
            raise ValueError('EVALUATOR_ERROR: tool score disagrees with reviewed call count')
    d = lambda k: Decimal(str(scores[k]))
    def ability_score(weights):
        if run_status != 'valid' or any(statuses[k] not in valid or ability_statuses[k] not in valid for k in weights):
            return None
        return float(100*sum(Decimal(w)*d(k) for k,w in weights.items())/sum(weights.values()))
    result_valid = run_status == 'valid' and all(statuses[k] in valid for k in RESULT_WEIGHTS)
    raw = sum(Decimal(w)*d(k) for k,w in RESULT_WEIGHTS.items())
    return {'run_status': run_status,
            'automated_quality_score': None,
            'llm_result_score': float(raw) if result_valid else None,
            'capabilities': {a: ability_score({k:w for k,(label,w) in ABILITY_MAP.items() if label==a})
                            for a in sorted({label for label,_ in ABILITY_MAP.values()})},
            'capability_total': ability_score({k:w for k,(_,w) in ABILITY_MAP.items()}),
            'note': 'Automated checks have 0 quality points; semantic result and capability scores are separate.'}
```

## LLM Judge Rubric

### Criterion 1: 保障结构与免赔机制 (key: core_accuracy, weight: 85)

证据为最终回答及正式条款，不要求展示内部思考。四个固定内部组如下；每组四单元，各单元二值，通过须表达相应实质含义，允许合并表述。漏答的业务单元为0；外部来源暂时无法访问但候选保留未核实不被视为事实已正确。

- 旧版保障：O1，第六条列有暴雨/洪水等原因仍不能覆盖第十条（八）的专门发动机进水免责；O2，明确该责任通过旧版《发动机涉水损失险》补充，而非仅凭主险；O3，附加险适用于家庭自用汽车且先投保车损险；O4，第一条保障使用过程中的发动机进水直接损毁，不把仅行驶涉水或发生暴雨当作唯一条件。
- 新版保障：N1，第六条的一般自然灾害/意外事故责任与第九至十一条免责结构纳入该类责任；N2，仍受保险责任和其他免责条件限制，不等于所有进水无条件赔；N3，除外特约是排除发动机进水直接损毁而非增保；N4，该特约须基于已投保车损险且以实际附加为条件，不对未附加保单自动排除责任。
- 旧版免赔：D1，发动机涉水附加险基础绝对免赔率为15%；D2，该附加险不适用主险各项免赔率和免赔额约定；D3，对应投保不计免赔率险可以承担按该15%计算的免赔金额，未对应附加不能无条件免除；D4，不计免赔率险第二条（四）排除主险约定的每次事故绝对免赔额，不能据此推出所有绝对免赔率均不受该险保障。
- 新版免赔：E1，主险第十二条保留投保时协商的每次事故绝对免赔额；E2，不将旧涉水险统一15%作为新版主险默认规则，新版没有旧《不计免赔率险》不等于全部零免赔；E3，附加绝对免赔率特约允许协商5%、10%、15%、20%四档，以保单载明为准；E4，免赔额是金额、免赔率是比例，特约按主险计算赔款再乘（1－约定比例），不把两者混同或断言无条件叠用/免除。

相同原子误解的后果只扣一个主owner：例如只将除外特约误读成增保归N3，不同时扣N1；仅遗漏15%数字归D1，不再扣D3；正确引用却把绝对免赔额当免赔率归D4，不再扣source。分组台账须显示免重复扣分理由。常规档位按Grading Criteria中的raw_core/85向下量化。K1—K4任一关键逆转存在时本项上限0.5，不因其余细节正确绕过上限。

**Score 1.0**: raw_core/85=1，全部16单元通过，且没有关键逆转。
**Score 0.75**: 0.75≤raw_core/85<1，且没有关键逆转。
**Score 0.5**: 0.5≤raw_core/85<0.75；或常规档位高于0.5但触发关键逆转封顶。
**Score 0.25**: 0.25≤raw_core/85<0.5。
**Score 0.0**: 0≤raw_core/85<0.25，或完整终止记录确认未提供实质答案。

### Criterion 2: 正式版本与条款依据关联 (key: source_binding, weight: 15)

四个固定证据包：S1旧版主险/涉水附加险；S2新版主险/发动机除外特约；S3旧版涉水免赔/不计免赔率险；S4新版主险免赔额/附加绝对免赔率。每包1/4，须能确认正确正式版本，并将文件内可定位条款与回答相应比较项关联。可用条款名称和编号、PDF页码、可直接定位段落的引用；无需同时给编号与页码。允许共享正式原文链接，正文定位必须足以区别被比较的条款。DOCX页码渲染变化不扣分。协会正式发布页加附件名称/条款定位亦可，不强制直接下载URL。

不要求固定域名字符串，不用引用数量奖励多余来源。一般保险科普、媒体摘要、错误版本、征求意见稿不能替代指定正式条款。正确定位的原文被解释错归core，此处不重复扣。相同错误版本已作为core主owner时，相关S单元记去重豁免，不宣称引用正确；仅独立的缺链接、不可定位、虚构条款或不同对象混用才在本项扣。整组业务完全缺失已归core时，不因同一遗漏再次扣S；未交付任何实质答案则本项0，不借去重规则给空答案加分。台账固定四包，逐包记录通过、独立缺陷或去重豁免。业务去重豁免不等于证明来源关联正确；若某包只能豁免而无法确认实际关联状态，将source_binding的能力状态标为evidence_insufficient，不以业务豁免补造能力满分。

**Score 1.0**: 四包均通过或按明确error_id去重豁免，且至少一包有实质可核验来源。
**Score 0.75**: 恰有一包存在独立来源缺陷。
**Score 0.5**: 恰有两包存在独立来源缺陷。
**Score 0.25**: 恰有三包存在独立来源缺陷。
**Score 0.0**: 四包均存在独立来源缺陷，或完整记录确认没有实质回答/可核验正式依据。

### Criterion 3: 候选前提下的规则组合 (key: rule_application, weight: 0)

只评四种组合推导：R1主险一般承保与专门免责/补充附加险的优先关系；R2主险已承保与可选除外特约的条件关系；R3附加险基础免赔率与对应不计免赔率险的条件关系；R4协商免赔额与可选免赔率的金额/比例关系。每种1/4，按候选在该处实际采用的条款前提判断结论是否遵循该前提；不能用GT真实前提直接替换候选前提后惩罚其推理。错误条款事实被一致地组合，业务core扣而本项不扣；事实正确但结论违背已明确采用的规则，是本项独立错误。需列“候选前提—所作结论—是否推出”的证据，不以知识量或事实召回代替。

最终回答保留独立关键逻辑反转时本项cap0.25，例如先正确指出除外特约排除责任却又断言附加后新增保障；先承认对应不计免赔率险承担该免赔金额却仍断言即使附加也永远自付15%；明确存在可选免赔后又断言所有组合均零免赔。事实错本身不触发此能力封顶。缺可观察前提或推导、无法区分事实缺口和逻辑错误时记evidence_insufficient/not_observed，不当作0或1；完整记录及明确回答足以证明相关组合错误时才记失败。

**Score 1.0**: 四种组合均有充分证据且推导一致，没有关键逻辑反转。
**Score 0.75**: 恰有一种独立非关键组合错误，其余三种成立。
**Score 0.5**: 恰有两种独立非关键组合错误，其余两种成立。
**Score 0.25**: 仅一种组合成立，或原始分更高但触发独立关键逻辑反转封顶。
**Score 0.0**: 四种组合均被充分证据证实错误。证据不可判时0仅接口占位。

### Criterion 4: 每次工具参数契约 (key: tool_call_contract, weight: 0)

根据完整公开调用、当时接口定义及回执逐次识别由Agent输入造成的必填项、类型、枚举、格式、越界引用ID等参数错误。每个实际发出的独立调用记一次；同一调用的多条报错只计一次，多个调用重犯相同错误逐次计入K，不按业务步骤、根因或工具类别合并，也不以成功调用数稀释。批量调用内可独立定位的每次子调用分别计数。内容分析错误、网络超时、站点拒绝、服务端故障不自动算参数错误；错误页面引用与正文解析等具体调用须根据当时契约判断。公式max(0,1-K/4)。仅统计调用契约，不重复设置参数错误恢复扣分项。

**Score 1.0**: 完整且可信轨迹确认K=0，并有实际相关工具调用。
**Score 0.75**: K=1。
**Score 0.5**: K=2。
**Score 0.25**: K=3。
**Score 0.0**: K≥4。完整记录没有实际工具调用记not_observed，缺轨迹或接口信息记evidence_insufficient，均非有效0分。

### Criterion 5: 交付前实际核验及声明校准 (key: verification_calibration, weight: 0)

exec/AGENTS.md公开要求交付前核对版本、核心结论与引用。四个固定验收对象为V1旧版主附险责任、V2新版主附险责任、V3旧版免赔组合、V4新版免赔组合，每个1/4。需要公开轨迹显示Agent把已有或拟交付的判断与相应正式条款和引用作实际对照；可在中途完成，不要求独立末尾步骤或特定工具。首次检索、仅取得摘要、页面能打开、文件下载成功均不自动证明对已有结论作了有效核验。重新读取关键条款后具体比较并据此保留、修订或标为未核实，可计对应对象通过；同一次实质对照可覆盖明确涉及的多个对象。正文结论正确不自动证明已核验，结论错误也不自动证明未核验。

base为有独立有效核验依据的验收对象数/4。完整轨迹足以确认未执行公开要求的核验时，相应对象为0；缺轨迹或记录被截断而不能判断时记evidence_insufficient，不用0或1填补。仅会话结束不是完成/核验声明；没有自检自述本身不扣分。若另有明确的超额核验声明，例如声称两版全部逐条核验但对应公开记录明确仍未取得必要正文，本项取min(base,0.25)，不再按该声明另扣第二份分；必须同时指出原始过程位置与明确声明。普通条款回答不是已通读的过程声明。已明确标注未核实可避免虚假声明，但不能替代实际完成对应核验。

**Score 1.0**: 四个验收对象均有充分的实际对照证据，且无独立超额核验声明。
**Score 0.75**: 恰有三个验收对象通过，且无独立超额核验声明。
**Score 0.5**: 恰有两个验收对象通过，且无独立超额核验声明。
**Score 0.25**: 恰有一个验收对象通过，或base更高但触发明确超额核验声明封顶。
**Score 0.0**: 完整轨迹确认四个对象均未完成有效核验。证据不足时0仅接口占位，不是有效得分。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_014_motor_insurance_water_damage_clause_comparison

## Skills

## Env

## Warmup
