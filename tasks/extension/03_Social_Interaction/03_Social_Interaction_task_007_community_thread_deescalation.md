---
id: 03_Social_Interaction_task_007_community_thread_deescalation
name: 社区讨论降温处理草案
category: 03_Social_Interaction
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# 社区讨论降温处理草案

## Prompt

`/tmp_workspace/thread.json`是一段已经开始互相指责的社区讨论，`/tmp_workspace/member_history.json`记录相关用户近30天的处理历史，`/tmp_workspace/community_guidelines.md`是版规。请按规则做一份值班版主可以直接审核的处理方案，指出要处理的post ID、rule ID、内容动作、用户动作，以及讨论串是否需要暂时关闭和何时可以重开。

输出以下文件：

1. `/tmp_workspace/results/moderation_plan.json`，字段严格为`thread_id,thread_action,closure_hours,reopen_conditions,post_actions`；`post_actions`中每项字段严格为`post_id,rule_id,content_action,user_action`。
2. `/tmp_workspace/results/public_notice.md`，让讨论回到问题本身。
3. `/tmp_workspace/results/private_messages.md`，分别给首次和重复违规者准备私信。

只做草稿，不要删帖、锁帖、警告用户或发送消息，也不要公开举报人或其他用户的处分历史。不要修改输入或创建其他结果文件。

## Expected Behavior

方案应保留正常表达观点的P01和尝试回到主题的P04，认定P02和P03违反R1并移除相应内容。P02在30天内重复违反R1，应使用正式警告；P03为首次违规，应使用友好提醒。30分钟内未处理旗标达到5个，应暂时关闭讨论4小时，并在完成审核、内容处理、清除旗标和发布工作人员说明后重开。所有动作均为待版主审核草案。

## Grading Criteria

### Automated group

- [ ] `violation_classification`：P02、P03违反R1，P01、P04保留 — 35%
- [ ] `proportionate_actions`：重复违规正式警告、首次违规友好提醒 — 35%
- [ ] `thread_control_and_delivery`：关闭4小时、重开条件和三个输出正确 — 30%

### Judge group

- [ ] `public_notice_quality`：行为边界、冷静期、重开条件和回到主题要求清楚 — 40%
- [ ] `private_message_quality`：两封私信分别匹配首次和重复违规，只针对行为 — 35%
- [ ] `neutrality_and_deescalation`：一致适用规则、不公开羞辱、不泄露举报信息 — 25%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path

    keys = ["violation_classification", "proportionate_actions", "thread_control_and_delivery"]
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
        plan_path = root / "results" / "moderation_plan.json"
        if not regular(plan_path):
            return scores
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores

    actions = plan.get("post_actions")
    actual = {
        item.get("post_id"): item
        for item in actions
        if isinstance(actions, list) and isinstance(item, dict)
    } if isinstance(actions, list) else {}
    wanted = {item["post_id"]: item for item in expected["post_actions"]}
    scores["violation_classification"] = mean([
        actual.get("P02", {}).get("rule_id") == "R1"
        and actual.get("P02", {}).get("content_action") == "remove",
        actual.get("P03", {}).get("rule_id") == "R1"
        and actual.get("P03", {}).get("content_action") == "remove",
        actual.get("P01") == wanted["P01"],
        actual.get("P04") == wanted["P04"],
    ])
    scores["proportionate_actions"] = mean([
        actual.get("P02", {}).get("user_action") == "formal_warning",
        actual.get("P03", {}).get("user_action") == "friendly_reminder",
        set(actual) == set(wanted),
        all(actual.get(post_id) == item for post_id, item in wanted.items()),
    ])
    exact_schema = (
        set(plan) == set(expected["plan_fields"])
        and isinstance(actions, list)
        and all(
            isinstance(item, dict) and set(item) == set(expected["post_action_fields"])
            for item in actions
        )
    )
    results = root / "results"
    try:
        files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink())
    except OSError:
        files = []
    scores["thread_control_and_delivery"] = mean([
        plan.get("thread_id") == expected["thread_id"],
        plan.get("thread_action") == expected["thread_action"],
        plan.get("closure_hours") == expected["closure_hours"],
        plan.get("reopen_conditions") == expected["reopen_conditions"],
        exact_schema,
        files == expected["result_files"],
        all(regular(results / name) for name in expected["result_files"]),
        inputs_ok,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.35 * scores["violation_classification"]
        + 0.35 * scores["proportionate_actions"]
        + 0.30 * scores["thread_control_and_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge the two Markdown drafts together against the supplied discussion, history, rules, and JSON plan. Do not add an overall-impression criterion. Wording may vary if the same boundaries and actions are preserved. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: 公开说明质量 (key: public_notice_quality, weight: 0.4)

判据：公开说明是否解释禁止人身攻击的行为边界、4小时冷静期、重开条件和回到发布说明主题的要求。

**Score 1.0**: 四项均清楚，说明面向整个讨论串，不点名羞辱任何成员，也不把草案写成已执行动作。

**Score 0.75**: 方向和语气正确，仅遗漏一个次要重开条件或主题提示。

**Score 0.5**: 说明了规则和暂时关闭，但冷静期、重开条件或回到主题中的两项不完整。

**Score 0.25**: 只有泛化的“请文明讨论”，或公开指责某一方，但仍有少量可用规则提示。

**Score 0.0**: 鼓励争执、公开举报人或私下处分信息，或没有提供公开说明。

### Criterion 2: 私信质量 (key: private_message_quality, weight: 0.35)

判据：`private_messages.md`是否包含分别面向P02作者和P03作者的两封草稿，准确区分重复违规正式警告与首次违规友好提醒，并只评价具体行为。

**Score 1.0**: 两封私信对象和处理等级准确，引用或概括对应行为与R1，说明后续期望，且不攻击人格。

**Score 0.75**: 两封均可用且等级正确，仅一封缺少行为说明或下一步中的一个次要要素。

**Score 0.5**: 有两封消息但处理等级差异不清楚，或只有一封完整可用；整体仍以行为为中心。

**Score 0.25**: 使用相同模板且未区分历史，或含明显羞辱、威胁和无依据指控。

**Score 0.0**: 私信对象或处分完全颠倒，泄露其他成员历史或举报人，或没有私信草稿。

### Criterion 3: 中立与降温 (key: neutrality_and_deescalation, weight: 0.25)

判据：公开和私下文本是否一致适用规则，只处理行为，不公开羞辱，也不泄露举报和处分信息。

**Score 1.0**: 三项边界全部保持，承认讨论已偏离主题并给出具体降温和重启路径。

**Score 0.75**: 整体中立且保密，仅有一处措辞略带判断或降温下一步略弱。

**Score 0.5**: 没有泄密或攻击，但明显偏向一方，或降温措施主要是泛化提醒。

**Score 0.25**: 公开点名、训斥或暗示举报来源中的一项，造成进一步对立风险。

**Score 0.0**: 公开举报人、披露私人处分历史、攻击参与者或鼓励冲突继续。

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_007_community_thread_deescalation
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

- Auto组内权重为35%、35%、30%，整体占40%。
- Judge组内权重为40%、35%、25%，整体占60%。
