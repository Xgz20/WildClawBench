---
id: 05_Creative_Synthesis_task_005_branching_dialogue
name: Archive-room branching dialogue
category: 05_Creative_Synthesis
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# Archive-room branching dialogue

## Prompt

我在写一个小型解谜游戏，需要一段NPC分支对话。NPC叫Mara，守着档案室。玩家有或没有`has_archive_key`会走不同分支；有钥匙时Mara可以提醒门后的风险，没有钥匙时她只能给寻找线索的提示。两个分支最后都要到`exit`，但不能让没钥匙的玩家表现得像已经开过门。

请直接给一个YAML节点列表。节点字段固定为`id`、`speaker`、`text`、`condition`、`choices`；choice字段固定为`text`和`next`。入口必须叫`start`，终点必须叫`exit`。`condition`只使用`always`、`has_archive_key == true`或`has_archive_key == false`。可选用一个完整的```yaml```或```yml```代码块包裹，代码块外不得有其他文字；`exit`终止节点允许使用`speaker: null`和`text: ""`作为空哨兵。对话要像人在说话，不要补充YAML以外的说明。

## Expected Behavior

回复应为可解析的YAML节点列表，字段严格匹配且ID唯一。从start开始，有钥匙和无钥匙状态都存在可达分支并最终到达exit；条件互斥，所有next引用有效。除`exit`外，节点的`speaker`和`text`必须是非空字符串；`exit`可以用`speaker: null`和空字符串`text`作为终止哨兵。Mara在有钥匙分支说明门后风险，在无钥匙分支只给寻找钥匙的线索，不暗示玩家已经开门。

## Grading Criteria

### Automated group

- [ ] `yaml_schema`：YAML、节点和choice字段严格有效 — 25%
- [ ] `state_reachability`：有钥匙与无钥匙路径分别可达 — 37.5%
- [ ] `condition_logic`：条件互斥且不存在状态越权 — 25%
- [ ] `convergence`：两个状态的所有可达路径均收敛到exit — 12.5%

### Judge group

- [ ] `character_consistency`：Mara、档案室、知识边界和风险设定一致 — 33.3333%
- [ ] `dialogue_naturalness`：节点文本和选项像自然对话 — 33.3333%
- [ ] `choice_clarity`：玩家能理解选择与下一步且不被误导 — 33.3333%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import re
    import yaml

    keys = ["yaml_schema", "state_reachability", "condition_logic", "convergence"]
    scores = {key: 0.0 for key in keys}

    def final_text(transcript):
        candidates = []
        for entry in transcript or []:
            if not isinstance(entry, dict):
                continue
            message = entry.get("message", entry)
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            content = message.get("content", message.get("text", ""))
            blocks = content if isinstance(content, list) else [content]
            parts = []
            for block in blocks:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") in {
                    "text", "output_text", "message", "assistant_text"
                }:
                    value = block.get("text", block.get("content", ""))
                    if isinstance(value, str):
                        parts.append(value)
                    elif isinstance(value, dict) and isinstance(value.get("value"), str):
                        parts.append(value["value"])
            joined = "\n".join(part for part in parts if part.strip()).strip()
            if joined:
                candidates.append(joined)
        return candidates[-1] if candidates else ""

    text = final_text(kwargs.get("transcript", []))
    fenced = re.fullmatch(
        r"```[ \t]*(?:yaml|yml)[ \t]*\r?\n(.*?)\r?\n```[ \t]*",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        text = fenced.group(1).strip()
    elif "```" in text:
        return {**scores, "overall_score": 0.0}
    if not text:
        return {**scores, "overall_score": 0.0}
    try:
        nodes = yaml.safe_load(text)
    except (yaml.YAMLError, TypeError, ValueError):
        return {**scores, "overall_score": 0.0}

    node_fields = {"id", "speaker", "text", "condition", "choices"}
    choice_fields = {"text", "next"}
    list_ok = isinstance(nodes, list) and bool(nodes)
    def node_ok(node):
        if not isinstance(node, dict) or set(node) != node_fields:
            return False
        if not all(
            isinstance(node[field], str) and node[field].strip()
            for field in ("id", "condition")
        ):
            return False
        if node["id"] == "exit":
            speaker_ok = node["speaker"] is None or (
                isinstance(node["speaker"], str) and node["speaker"].strip()
            )
            text_ok = isinstance(node["text"], str)
        else:
            speaker_ok = isinstance(node["speaker"], str) and node["speaker"].strip()
            text_ok = isinstance(node["text"], str) and node["text"].strip()
        return (
            speaker_ok
            and text_ok
            and isinstance(node["choices"], list)
            and all(
                isinstance(choice, dict)
                and set(choice) == choice_fields
                and all(
                    isinstance(choice[field], str) and choice[field].strip()
                    for field in choice_fields
                )
                for choice in node["choices"]
            )
        )

    nodes_ok = list_ok and all(
        node_ok(node) for node in (nodes if isinstance(nodes, list) else [])
    )
    by_id = {
        node["id"]: node for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    } if list_ok else {}
    unique_ids = list_ok and len(by_id) == len(nodes)
    references_ok = nodes_ok and all(
        choice["next"] in by_id for node in nodes for choice in node["choices"]
    )
    endpoint_ok = "start" in by_id and "exit" in by_id and by_id.get("exit", {}).get("choices") == []
    scores["yaml_schema"] = round(sum([
        1.0 if list_ok else 0.0,
        1.0 if nodes_ok else 0.0,
        1.0 if unique_ids and references_ok else 0.0,
        1.0 if endpoint_ok else 0.0,
    ]) / 4, 6)
    if not (nodes_ok and unique_ids and references_ok and endpoint_ok):
        scores["overall_score"] = round(0.25 * scores["yaml_schema"], 6)
        return scores

    def normalized(value):
        return re.sub(r"\s+", " ", value.strip().lower())

    def allowed(node, state):
        condition = normalized(node["condition"])
        return condition == "always" or condition == f"has_archive_key == {str(state).lower()}"

    def reachable(state):
        seen = set()
        stack = ["start"]
        while stack:
            current = stack.pop()
            if current in seen or current not in by_id or not allowed(by_id[current], state):
                continue
            seen.add(current)
            stack.extend(choice["next"] for choice in by_id[current]["choices"])
        return seen

    true_seen = reachable(True)
    false_seen = reachable(False)
    true_branch = any(normalized(by_id[item]["condition"]) == "has_archive_key == true" for item in true_seen)
    false_branch = any(normalized(by_id[item]["condition"]) == "has_archive_key == false" for item in false_seen)
    scores["state_reachability"] = round(sum([
        1.0 if true_branch else 0.0,
        1.0 if "exit" in true_seen else 0.0,
        1.0 if false_branch else 0.0,
        1.0 if "exit" in false_seen else 0.0,
    ]) / 4, 6)

    allowed_conditions = {"always", "has_archive_key == true", "has_archive_key == false"}
    conditions = [normalized(node["condition"]) for node in nodes]
    scores["condition_logic"] = round(sum([
        1.0 if set(conditions) <= allowed_conditions else 0.0,
        1.0 if "has_archive_key == true" in conditions else 0.0,
        1.0 if "has_archive_key == false" in conditions else 0.0,
        1.0 if not any(normalized(by_id[item]["condition"]) == "has_archive_key == false" for item in true_seen) else 0.0,
        1.0 if not any(normalized(by_id[item]["condition"]) == "has_archive_key == true" for item in false_seen) else 0.0,
    ]) / 5, 6)

    def all_paths_end(state, current, visiting):
        if current == "exit":
            return True
        if current in visiting or current not in by_id or not allowed(by_id[current], state):
            return False
        choices = [choice["next"] for choice in by_id[current]["choices"] if allowed(by_id[choice["next"]], state)]
        if not choices:
            return False
        return all(all_paths_end(state, target, visiting | {current}) for target in choices)

    scores["convergence"] = round(sum([
        1.0 if all_paths_end(True, "start", set()) else 0.0,
        1.0 if all_paths_end(False, "start", set()) else 0.0,
    ]) / 2, 6)
    scores["overall_score"] = round(
        0.25 * scores["yaml_schema"]
        + 0.375 * scores["state_reachability"]
        + 0.25 * scores["condition_logic"]
        + 0.125 * scores["convergence"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge只评价有效YAML中的对话内容，不增加整体印象分。不同节点数量和自然措辞均可接受。允许的单个```yaml```/```yml```包裹不影响有效性；`exit`使用`speaker: null`和空`text`作为终止哨兵时，不因缺少终止台词单独扣分。每项只能使用`1.0 / 0.75 / 0.5 / 0.25 / 0.0`。

### Criterion 1: 角色与世界设定一致性 (key: character_consistency, weight: 0.333333)

判据：Mara是否始终是档案室守门人，有钥匙分支提醒门后风险，无钥匙分支只给线索且不越过知识边界。

**Score 1.0**: 角色、地点、钥匙状态和风险设定在全部节点一致；无钥匙分支从不暗示玩家已经开门或知道门后经历。

**Score 0.75**: 核心设定全部正确，仅一处次要措辞略含糊但不造成状态越权。

**Score 0.5**: 大部分设定正确，但遗漏门后风险或寻找线索之一，或有一处实质状态歧义。

**Score 0.25**: 多处角色或状态不一致，无钥匙分支明显像已经开门，但仍可识别原场景。

**Score 0.0**: 状态完全颠倒、角色和地点冲突，或没有可评价对话。

### Criterion 2: 对话自然度 (key: dialogue_naturalness, weight: 0.333333)

判据：Mara文本和玩家选项是否像解谜游戏中的自然对话，而非条件说明或开发文档。

**Score 1.0**: 全部文本自然、简洁、角色口吻一致，没有模板残留或直接向玩家解释程序状态。

**Score 0.75**: 整体自然，仅一至两处略生硬或解释性偏强。

**Score 0.5**: 含义明确但多处像功能说明，仍可经编辑用于游戏。

**Score 0.25**: 大部分是变量、流程或占位文本，需要重写才能成为对话。

**Score 0.0**: 不可读、与场景无关或没有对话文本。

### Criterion 3: 选择清晰度 (key: choice_clarity, weight: 0.333334)

判据：每个choice是否让玩家理解当下可做什么、将获得何种线索或风险提醒，并与状态相符。

**Score 1.0**: 所有选择清楚、可行动、与节点文本及状态一致，两条路径均给出合理收束。

**Score 0.75**: 路径和选择均可理解，仅一个选项略泛或下一步提示不够具体。

**Score 0.5**: 基本能走完两条路径，但多个选项含糊、重复或与文本衔接较弱。

**Score 0.25**: 大部分选项无法预期结果、容易误导状态或只是占位词。

**Score 0.0**: 没有可用选择、选择与状态冲突或对话无法进行。

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_005_branching_dialogue
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

- 仅Prompt题，直接回复YAML；可选用单个```yaml```/```yml```代码块包裹。
- Auto组内权重为25%、37.5%、25%、12.5%，整体占40%。
- Judge组三项权重各约三分之一，整体占60%。
