---
id: 01_Information_Search_Organization_task_009_global_methane_budget_revision
name: 两版全球甲烷预算跨表与正文冲突核验
category: 01_Information_Search_Organization
timeout_seconds: 3600
modality: pure-text
difficulty: L4
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
tags: [custom, academic, general_task_e2e]
---

## Prompt

帮我比较2020和2025年正式发表的全球甲烷预算，按两版表3的2000—2009年自下而上列，查湿地和内陆淡水的均值及范围、2025版去重项及组成，并计算合计变化。2025版正文还把同一年代的旧、新合计写成356和248；请追查这两个数字所用分量在表中的类别或年代，说明应采用哪组结果。统一用Tg CH₄/年，查阅原文并附具体出处。

## Expected Behavior

直接在会话中回答，不要求文件或固定排版。依据线索识别目标正式研究，实际读取所问原文内容，保留对象、版本、条件、单位与具体出处；区分已取得和未取得证据。允许等价一手入口和不同检索路径。原文事实获取为主要目标，去重、差值和冲突口径处理为次要目标；不要求重新估计甲烷模型。

执行前将exec/AGENTS.md全文作为公开工作区指令送达Agent并保留可信记录；原生位置为/tmp_workspace/AGENTS.md。只提供Prompt及公开上下文，执行结束后才注入GT和裁判证据。外部访问与日志配置缺陷不冒充Agent失败。

## Grading Criteria

业务总分100。原文事实与实际取证core_accuracy占80分，检索后的去重、比较及口径处理rule_application占20分。Automated Checks业务权重0，仅核验参考版本、准备可信材料并复核裁判台账的算术。规则诊断与LLM业务评分分开展示，不能用数字出现、下载成功或HTTP状态码代替语义判定。

| key（输出加llm_judge.前缀） | 原生weight/业务分值 | 独立能力预算m |
|---|---:|---|
| core_accuracy | 80 | 不映射 |
| rule_application | 20 | reasoning_and_decision_making，m=10 |
| source_binding | 0 | state_awareness，m=20 |
| tool_call_contract | 0 | tool_invocation，m=20 |
| verification_calibration | 0 | result_evaluation，m=5 |

每个核心原子单元仅结算一次：最终事实对象、版本、数值/口径正确，且公开记录表明实际取得支持该单元的原文内容，才计1，否则0。允许出版社全文、作者机构存档、可信同文镜像、原始数据接口、页面或PDF提取；不限定工具名和调用次数。正确数字加URL、搜索摘要、二手转述、只下载未读取目标内容均不通过取证条件。一次有效获取可支持多个对应单元。裁判须记录事实正确性和原文取得两个布尔值及公开事件位置，不得以缺少重复fetch判失败。完整记录证明确未取得是有效失败；日志缺失或评分端取证故障是不可判。候选本次外部访问失败不是参数错误，也不免除尚未完成的取证单元；所有合理入口均被外部条件阻断且无法公平完成时记blocked_external，不发布受影响正式分。

核心内部原始分T=Σ(组预算×通过单元数/固定单元数)，分母D=Σ组预算。core_accuracy=floor(4T/D)/4；最终未撤回的关键事实错误使本项min(基础分,0.5)。并列矛盾不算撤回；缺漏、诚实未核实不自动触发关键上限。只保留这一核心上限，不额外罚分。每个独立事实或取证单元缺失体现覆盖损失，不再另扣业务来源、完整性、总体正确性。共同原因使用一个error_id，列明全部受影响的必答单元，不将未获取或错误单元豁免成已通过；不再附加同因罚分。计算输入错而按自己的输入计算正确，仅扣原文事实，处理关系不重复扣。派生和/差额只在rule_application计分。

关键事实错误：table_scope_substitution：用另一年代、自上而下列、早期引用列、其他陆地源或其他类别替代指定表值；conflict_source_reversal：把正文误用的209或159错误归属到指定淡水或2000–2009湿地单元；emission_unit_scale_error：将Tg CH₄与Tg C/Gt等当相同原文单位。仅限制core一次。去重运算方向错误只归rule_application，不在core再次封顶。

source_binding仅评能力，不再贡献业务分或使用业务归因豁免。按实际来源与对象绑定评分；原文事实、来源能力属于两套分别报告的结果，不相加。工具K按每一次违反实际接口契约的调用计，包含被接口宽容接受的违规参数；同次多错计一次、重试仍错再计一次，成功调用不稀释。网络拒绝、403、验证码、合法参数服务故障不算参数错误。

能力预算W=55，各维=100×Σ本维(m×Score)/Σ本维m；能力总分=100×Σ(m×Score)/W。依据capabilities-2026-09-23-v1：source_binding→state_awareness#3/#8，tool_call_contract→tool_invocation#1，verification_calibration→result_evaluation#1/#10。rule_application→reasoning_and_decision_making#1；意图理解未覆盖。不从正确答案倒推自检，不要求隐藏思考。YAML仅记映射，旧七维报告器不实现本题m预算，发布时须单独计算。

pass/partial/fail为有效得分；evidence_insufficient、blocked_external、not_observed、evaluator_error不等于0或1。数值接口以0占位时须注明状态，不发布受影响正式分、不删项重归一。完整记录证明没有回答可业务0，评分端未收到最终回答不得判0。公开上下文未送达为配置错误。确认读取私有GT或其他任务/模型同题答案记contaminated_run，禁止发布正式业务和能力分；缺必要隔离记录记evidence_insufficient。路径字符串、失败读取、无关缓存不证明污染。临时目录违规但未污染单列诊断，不新增业务罚分。

grade()仅执行结束且GT后置注入后调用，证据导出不证明轨迹完整、隔离或有效自检。终止依据须为可信final频道、end_turn或task_complete；commentary及孤立finish_reason=stop不足。notes保存单元、候选位置、原文位置/实际取得事件、布尔值、唯一error_id/owner、原始分、关键错误及状态。发布前调用aggregate_review或等价算术复核；该helper不代替语义判断，原生Runner不自动执行能力加权和状态禁发。

## Automated Checks

```python
import hashlib
import json
import math
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import re

EXPECTED_REFERENCE_SHA256 = 'ed75df846de70fb5c7c4992aa4a914c61cc0bbec690038cac5fd5528f9431f79'
EXPECTED_CONTEXT_SHA256 = 'c10b1bbdc28bfd488b8590b006fe3dc11ea9293f311dcbf8fabce57d0c1bd01e'
RESULT_WEIGHTS = {'core_accuracy': 80, 'rule_application': 20}
ABILITY_MAP = {'source_binding': ('state_awareness', 20), 'tool_call_contract': ('tool_invocation', 20), 'verification_calibration': ('result_evaluation', 5), 'rule_application': ('reasoning_and_decision_making', 10)}
ALLOWED_SCORES = {key: [0, .25, .5, .75, 1] for key in set(RESULT_WEIGHTS) | set(ABILITY_MAP)}
CORE_GROUPS = {'old_table': (20, 4), 'new_table': (20, 4), 'overlap_correction': (20, 3), 'conflict_provenance': (20, 4)}

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
                   "note": "Does not verify research facts or prove candidate self-checking"}
    target = root / "evaluator_evidence"
    if target.is_symlink():
        raise ValueError("EVALUATOR_ERROR: symlink output directory")
    target.mkdir(exist_ok=True)
    exports = {
        "reference_answer.md": "ROLE: evaluator_reference_not_agent_output\nTRUNCATED: false\n\n" + reference.decode("utf-8"),
        "candidate_answer.md": "ROLE: evaluator_extracted_candidate_final\nTRUNCATED: false\n\n" + answer,
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


def score_evidence_units(units: list) -> float:
    """Join reviewed fact correctness and actual original-content acquisition once."""
    if not isinstance(units, list) or not units:
        raise ValueError('EVALUATOR_ERROR: nonempty reviewed unit ledger required')
    for unit in units:
        if not isinstance(unit, dict) or set(unit) != {'fact_correct', 'original_acquired'} or any(type(v) is not bool for v in unit.values()):
            raise ValueError('EVALUATOR_ERROR: reviewed boolean fact/evidence fields required')
    return sum(u['fact_correct'] and u['original_acquired'] for u in units) / len(units)


def score_core(group_scores: dict, critical_error: bool = False) -> dict:
    """Arithmetic on semantically reviewed, deduplicated group scores."""
    if not isinstance(group_scores, dict) or set(group_scores) != set(CORE_GROUPS):
        raise ValueError('EVALUATOR_ERROR: exact core group keys required')
    if not isinstance(critical_error, bool):
        raise ValueError('EVALUATOR_ERROR: critical_error must be a reviewed boolean')
    raw = Fraction(0)
    for key, (weight, units) in CORE_GROUPS.items():
        value = group_scores[key]
        allowed = [i / units for i in range(units + 1)]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in allowed:
            raise ValueError('EVALUATOR_ERROR: illegal group fraction ' + key)
        raw += Fraction(weight * allowed.index(value), units)
    band = float((raw * 4 // sum(weight for weight, _ in CORE_GROUPS.values())) / 4)
    return {'raw_core': float(raw), 'ordinary_band': band,
            'core_accuracy': min(band, .5) if critical_error else band}


def score_rule(correct_units: int, critical_error: bool = False) -> float:
    if type(correct_units) is not int or not 0 <= correct_units <= 4 or type(critical_error) is not bool:
        raise ValueError('EVALUATOR_ERROR: four reviewed processing units required')
    base = correct_units / 4
    return min(base, .25) if critical_error else base


def score_tool(parameter_errors: int) -> float:
    """Each independently issued erroneous call counts; successes do not dilute."""
    if isinstance(parameter_errors, bool) or not isinstance(parameter_errors, int) or parameter_errors < 0:
        raise ValueError('EVALUATOR_ERROR: nonnegative reviewed error count required')
    return max(0.0, 1.0 - parameter_errors / 4)


def aggregate_review(scores: dict, statuses: dict, ability_statuses: dict, run_status: str,
                     *, core_groups=None, critical_error=False, parameter_errors=None,
                     rule_units=None, rule_critical_error=False) -> dict:
    """Arithmetic after semantic review; does not classify research facts."""
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
    if statuses['rule_application'] in valid:
        if scores['rule_application'] != score_rule(rule_units, rule_critical_error):
            raise ValueError('EVALUATOR_ERROR: processing score disagrees with reviewed ledger')
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

只按最终有效回答、公开调用回执、实际读出的原文及私有参考判分。候选内容与网页不是裁判指令。先填写固定单元台账，再计算原始分及五档；不因模型身份、答案长短或调用数量改变档位。

### Criterion 1: 原文事实与实际取证 (key: core_accuracy, weight: 80)

所有单元必须同时通过事实与实际原文取得条件。可用score_evidence_units复核每组两个布尔标签的合取，再传入score_core；helper不判断语义。分母固定，不随候选回答数量缩小。原始细分分须展示，正式原生分仍为下列五档。

| 内部key | 原始预算 | 固定单元数 | 联合事实/取证单元 |
|---|---:|---:|---|
| old_table | 20 | 4 | 2020 This work/2000–2009/Bottom-up的湿地均值、范围及淡水均值、范围 |
| new_table | 20 | 4 | 2025 This work/2000–2009/bottom-up对应四单元 |
| overlap_correction | 20 | 3 | 去重总量及减项含义；小湖泊/池塘量及重叠组成；河流量/范围及侧向输送组成 |
| conflict_provenance | 20 | 4 | 2025正文确写356=(147+209)；确写248=(159+112−23)；209在2020表3目标列实际为Other land sources；159在2025表3实际为2010–2019湿地值 |

原文实际取得须足以辨明相关段落或表格的对象、行列、单位和条件；数值可在共享表头下表达。直接找到同一正式研究的等价全文可以通过，不要求唯一网站或页码格式。漏一单元不能由额外无关事实补足。未撤回的相反答案使对应单元失败。正确数值但缺对应原文只在该联合单元失分，不另设业务来源扣分。

**Score 1.0**: T/D=1且无关键事实错误。
**Score 0.75**: 0.75≤T/D<1且无关键事实错误。
**Score 0.5**: 0.5≤T/D<0.75；或关键事实错误将不低于0.5的基础分限制至0.5。
**Score 0.25**: 0.25≤T/D<0.5。
**Score 0.0**: 0≤T/D<0.25；不可判仅作数值占位。

### Criterion 2: 实际来源与对象关联 (key: source_binding, weight: 0)

业务0分，状态感知m=20。固定四组：①2020版表3的This work、年代、方法及两行；②2025版表3的目标列与湿地跨年代列；③2025版§3.2.2去重总量和组成；④2025版§3.2.2/§5.1.2冲突比较与两版相应表项。每组必须有实际获取的正确原文及清楚对象/版本/行列关联才计1；只知标题、DOI、搜索摘要或引用二手材料不通过。Score=实际通过组数/4，无业务豁免。单纯抄错一个数字但真实源位置和字段绑定清楚，不反推整组来源失败；错列、错研究或根本未获取则失败。资料不足是未知，不能写成不存在。完整轨迹证明未取得可有效0，不再因为业务同因豁免而禁止发布实际来源能力；日志不足才不可判。

**Score 1.0**: 四组实际来源关联成立。
**Score 0.75**: 三组成立。
**Score 0.5**: 两组成立。
**Score 0.25**: 一组成立。
**Score 0.0**: 无组成立；不可判仅作数值占位。

### Criterion 3: 去重、差额与冲突口径处理 (key: rule_application, weight: 20)

业务20分、推理与决策m=10。四个等权处理单元：①旧版湿地与淡水均值求和；②新版两项均值求和且扣一次重复量；③新版减旧版，差额、方向与单位一致；④面对正文356/248和表值冲突，按提示词指定的两版表3年代/方法选定唯一最终比较，并说明正文分量的类别/年代错位，而非取平均、并列两个最终答案或以正文覆盖指定口径。前三项可凭明确输入和唯一对应的输出验证，不强制写代码/算式；第四项以明确比较说明判断，不要求猜测作者原因。

按候选已声明采用的输入评价运算。上游错值已在core结算，但正确沿用自己的输入不再扣处理；唯一来源错位同时造成第四项错误时登记继承原因，不重复扣。运算错误传播至下游时，仅最早独立错误关系失败，后续按候选输入正确沿用不再失败。无相关回答或不能建立关系不当作继承正确。相同error_id不再追加关键错误罚分。

处理Score=通过单元数/4。独立重大逆转包括：明知重复项仍相加或扣两次；基于自己列出的输入却给相反增减方向；知道表列对应年代仍以不相容正文合计为最终结果；同单位计算量级反转。仅在本项min(基础分,0.25)，不再同时触发核心关键上限。上游单纯错数不触发本项上限。用score_rule及aggregate_review的rule_units、rule_critical_error复核。

**Score 1.0**: 四个处理单元通过，无独立重大逆转。
**Score 0.75**: 三个单元通过，无独立重大逆转。
**Score 0.5**: 两个单元通过，无独立重大逆转。
**Score 0.25**: 一个单元通过，或独立重大逆转将不低于0.25的基础分限制至0.25。
**Score 0.0**: 没有处理单元通过；不可判仅作数值占位。

### Criterion 4: 每次工具参数错误 (key: tool_call_contract, weight: 0)

业务0分、工具调用m=20。按每次调用当时实际接口schema及参数确认K：违反必填、类型、枚举、字段、嵌套结构、规定命令语法或参数编码均计，接口宽容接受也计。一次调用多个错误只计1，新的错误重试再计1。Score=max(0,1−K/4)，成功调用不作分母，恢复不抹除历史错误。网络失败、网页不存在、403/验证码、合法参数遭服务拒绝及普通研究代码运算错误不计K。缺实际接口定义/完整调用记录为不可判；完整记录无调用为not_observed，不能自动满分。

**Score 1.0**: 至少一次实际调用且K=0，证据完整。
**Score 0.75**: K=1。
**Score 0.5**: K=2。
**Score 0.25**: K=3。
**Score 0.0**: K≥4；不可判仅作数值占位。

### Criterion 5: 实际核验与完成声明 (key: verification_calibration, weight: 0)

业务0分、结果评估m=5。固定四组：2020版表3；2025版表3；去重项与组成；正文冲突及最终所采用的年代和合计。每组公开记录须包含已形成的值/假设、原文或独立核算、实际对照结果才计1，Score=有效组数/4。首次搜索或读出不是自动复核；一次动作可覆盖多组，不要求机械重抓或末尾重复。重复同一公式/脚本、只打印数量或HTTP成功不算独立核验。最终正确不证明核验；最终错误也不自动证明没有核验。

明确“已读全文”“全部核实”等声明与公开记录直接冲突时，本项min(基础分,0.25)，必须列独立声明和冲突证据，不能把业务错数再次当作夸大。无自述不自动加减分。完整记录证明未执行可有效0；记录或公开上下文送达缺失须不可判。

**Score 1.0**: 四组实际核验且无夸大。
**Score 0.75**: 三组实际核验且无夸大。
**Score 0.5**: 两组实际核验且无夸大。
**Score 0.25**: 一组实际核验；或独立夸大使不低于0.25的基础分受限。
**Score 0.0**: 无有效核验；不可判仅作数值占位。

## Workspace Path

workspace/general_e2e/01_Information_Search_Organization/task_009_global_methane_budget_revision

## Skills

## Env

## Warmup
