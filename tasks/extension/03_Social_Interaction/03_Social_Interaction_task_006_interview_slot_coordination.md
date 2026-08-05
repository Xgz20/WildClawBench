---
id: 03_Social_Interaction_task_006_interview_slot_coordination
name: 候选人面试时段协调
category: 03_Social_Interaction
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3
tags:
  - custom
---

# 候选人面试时段协调

## Prompt

候选人的可面试时间在`/tmp_workspace/interview_request.json`，面试官的空闲时间和当前分配量在`/tmp_workspace/interviewer_availability.csv`，轮值规则在`/tmp_workspace/scheduling_rules.json`。请按候选时段顺序选择最早可行的45分钟，并在该时段全程可用的人中分配不超过`max_hosts`的人数；并列时先选本月已分配次数少的，再按`roster_order`排序。

把计划保存到`/tmp_workspace/results/interview_plan.json`，字段严格为`request_id,proposed_start,proposed_end,timezone,duration_minutes,interviewer_ids,host_count,status,selection_reason`；状态使用`draft_pending_candidate_confirmation`。再写一封`/tmp_workspace/results/candidate_reply.md`，请候选人确认所选时间，不要透露内部轮值次数。

不要发送邮件、创建日历事件、修改输入或创建其他结果文件。

## Expected Behavior

应选择候选人的第一个时段，即2026年9月8日09:00至09:45（Asia/Shanghai），并在四位全程可用面试官中按负载和轮值顺序选出`H04,H02,H03`。JSON应保持指定字段和待候选人确认状态。回复面向候选人，准确说明建议时间和待确认状态，但不披露内部负载或轮值信息。

## Grading Criteria

### Automated group

- [ ] `earliest_slot_selected`：请求ID及最早可行起止时间正确 — 30%
- [ ] `host_assignment`：人数上限、负载和轮值并列规则正确 — 30%
- [ ] `duration_timezone_constraints`：45分钟和时区表示正确 — 20%
- [ ] `structured_delivery`：JSON结构、两个输出及输入完整性正确 — 20%

### Judge group

- [ ] `candidate_message_fidelity`：日期、起止时间、时区和待确认状态准确 — 40%
- [ ] `candidate_message_readiness`：面向候选人、简洁、无内部负载信息且可直接发送 — 60%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path

    keys = [
        "earliest_slot_selected",
        "host_assignment",
        "duration_timezone_constraints",
        "structured_delivery",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        try:
            return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        except OSError:
            return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        inputs_ok = all(
            regular(root / relative)
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in expected["exec_file_sha256"].items()
        )
        plan_path = root / "results" / "interview_plan.json"
        message_path = root / "results" / "candidate_reply.md"
        if not regular(plan_path):
            return scores
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores

    scores["earliest_slot_selected"] = mean([
        plan.get("request_id") == expected["request_id"],
        plan.get("proposed_start") == expected["proposed_start"],
        plan.get("proposed_end") == expected["proposed_end"],
    ])
    interviewer_ids = plan.get("interviewer_ids")
    scores["host_assignment"] = mean([
        interviewer_ids == expected["interviewer_ids"],
        plan.get("host_count") == expected["host_count"],
        isinstance(interviewer_ids, list) and plan.get("host_count") == len(interviewer_ids),
        isinstance(interviewer_ids, list) and 1 <= len(interviewer_ids) <= 3,
    ])
    scores["duration_timezone_constraints"] = mean([
        plan.get("duration_minutes") == expected["duration_minutes"],
        plan.get("timezone") == expected["timezone"],
        plan.get("status") == expected["status"],
    ])
    required_types = {
        "request_id": str,
        "proposed_start": str,
        "proposed_end": str,
        "timezone": str,
        "duration_minutes": int,
        "interviewer_ids": list,
        "host_count": int,
        "status": str,
        "selection_reason": str,
    }
    exact_schema = set(plan) == set(expected["plan_fields"]) and all(
        type(plan.get(field)) is wanted for field, wanted in required_types.items()
    )
    results = root / "results"
    try:
        files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink())
    except OSError:
        files = []
    scores["structured_delivery"] = mean([
        exact_schema,
        files == expected["result_files"],
        regular(plan_path),
        regular(message_path),
        inputs_ok,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.30 * scores["earliest_slot_selected"]
        + 0.30 * scores["host_assignment"]
        + 0.20 * scores["duration_timezone_constraints"]
        + 0.20 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/candidate_reply.md` against the supplied request and computed plan. Do not add an overall-impression criterion. Different natural formulations are acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: 候选人消息事实准确性 (key: candidate_message_fidelity, weight: 0.4)

判据：消息是否准确包含2026年9月8日、09:00至09:45、Asia/Shanghai或明确北京时间，以及等待候选人确认的状态。

**Score 1.0**: 四项事实全部清楚准确，没有把建议时间写成已确认安排。

**Score 0.75**: 核心时间准确，仅遗漏时区标签或待确认措辞中的一个次要要素。

**Score 0.5**: 日期和大致时段正确，但缺少结束时间、时区或确认状态中的两项，仍可识别建议安排。

**Score 0.25**: 只说“周二上午”等模糊时间，或有一处实质性时间错误。

**Score 0.0**: 日期或时段错误，宣称候选人已经确认，或没有提供建议时间。

### Criterion 2: 候选人消息可用性 (key: candidate_message_readiness, weight: 0.6)

判据：消息是否面向周岚，简洁礼貌地请求确认，不披露面试官负载、轮值顺序或其他内部决策信息。

**Score 1.0**: 称呼和语气适合候选人，确认请求明确，内容简洁可直接发送，且完全不含内部负载或轮值信息。

**Score 0.75**: 可直接发送且边界正确，仅有一处轻微冗余、格式或称呼问题。

**Score 0.5**: 基本可用，但确认动作不够明确、措辞明显生硬，或包含面试官名单等不必要内部信息但未披露负载。

**Score 0.25**: 披露分配次数、轮值依据或内部评价，或需要大幅改写才能面向候选人。

**Score 0.0**: 包含歧视性或不当内容、擅自通知面试已确认，或没有可用候选人消息。

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_006_interview_slot_coordination
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

## Additional Notes

- Auto组内权重为30%、30%、20%、20%，整体占70%。
- Judge组内权重为40%、60%，整体占30%。
