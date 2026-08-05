---
id: 05_Creative_Synthesis_task_004_feedback_to_launch_script
name: 内测反馈发布会讲稿
category: 05_Creative_Synthesis
timeout_seconds: 300
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

# 内测反馈发布会讲稿

## Prompt

这5条内测反馈有点散，帮我整理成一段220～300字的新品介绍，我要在小型发布会上直接念。好评和顾虑都要提到，不要自己补数据。引用某条反馈的意思时，在句末标`[F1]`这种编号。

- F1：第一次建共享行程很快
- F2：家庭成员之间的权限还不够直观
- F3：地铁里没网时也能看到之前同步的路线
- F4：默认通知有点频繁
- F5：把完整路线导出来要点好几步

不用逐条念反馈，要把它们组织成一段自然的讲稿。只回复讲稿正文。

## Expected Behavior

回复应为一段220～300个中文字符的可朗读讲稿，将快速创建、离线查看两项价值和权限、通知、导出三项顾虑组织为平衡的新品介绍。五项含义均应在对应句末保留来源ID，不新增数据、效果或未给出的产品事实。

## Grading Criteria

### Automated group

- [ ] `feedback_references`：F1至F5均在讲稿中使用 — 62.5%
- [ ] `length_range`：中文字符数为220至300 — 25%
- [ ] `single_script_format`：只有一段讲稿正文 — 12.5%

### Judge group

- [ ] `faithful_synthesis`：五项反馈含义准确且无虚构 — 33.3333%
- [ ] `balanced_message`：价值与顾虑均有实质内容 — 25%
- [ ] `spoken_flow`：内容可自然朗读并有清楚推进 — 25%
- [ ] `stage_readiness`：适合小型发布会直接使用 — 16.6667%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import re

    keys = ["feedback_references", "length_range", "single_script_format"]
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
    if not text:
        return {**scores, "overall_score": 0.0}

    references = [f"F{number}" for number in range(1, 6)]
    scores["feedback_references"] = round(
        sum(1.0 if re.search(rf"\[{item}\]", text, flags=re.I) else 0.0 for item in references) / 5,
        6,
    )
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    scores["length_range"] = 1.0 if 220 <= len(chinese_chars) <= 300 else 0.0

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    no_markup = not re.search(r"(?:^|\n)\s*(?:#{1,6}|[-*]\s|\d+[.、]\s)", text)
    scores["single_script_format"] = 1.0 if (
        len(paragraphs) == 1 and no_markup and "```" not in text
    ) else 0.0

    scores["overall_score"] = round(
        0.625 * scores["feedback_references"]
        + 0.25 * scores["length_range"]
        + 0.125 * scores["single_script_format"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge只评价最终讲稿和给定五条反馈，不增加整体印象分。允许不同组织方式，不要求唯一措辞。每项只能使用`1.0 / 0.75 / 0.5 / 0.25 / 0.0`。

### Criterion 1: 反馈忠实综合 (key: faithful_synthesis, weight: 0.333333)

判据：讲稿是否准确保留F1至F5的五项含义，并在组织内容时不新增数据、功能或效果。

**Score 1.0**: 五项反馈均准确进入讲稿并与正确ID对应，没有夸大、因果推断或材料外事实。

**Score 0.75**: 五项均出现且总体准确，仅一项有轻微概括偏差，不改变原意。

**Score 0.5**: 至少三项准确，另有一项实质遗漏、误读或一个材料外次要主张。

**Score 0.25**: 少于三项准确，多项ID与含义错配，或新增多项未经支持的效果。

**Score 0.0**: 核心内容与反馈冲突、伪造数据或功能，或没有可评价讲稿。

### Criterion 2: 价值与顾虑平衡 (key: balanced_message, weight: 0.25)

判据：是否既说明创建和离线查看的价值，也诚实呈现权限、通知和导出方面的顾虑。

**Score 1.0**: 两类价值和三类顾虑均有实质内容，定位清楚且不掩饰问题，也不把顾虑写成已解决。

**Score 0.75**: 正反内容均清楚，仅一项顾虑或价值处理略简略。

**Score 0.5**: 同时提到价值与顾虑，但明显偏向一侧，或遗漏两项相关内容。

**Score 0.25**: 主要是单向宣传或问题清单，另一侧只有一句泛化带过。

**Score 0.0**: 完全忽略价值或顾虑，否认反馈，或把所有问题说成已经解决。

### Criterion 3: 口语流畅度 (key: spoken_flow, weight: 0.25)

判据：内容是否把零散反馈组织为有开头、推进和收束的一段自然讲稿，而非逐条念清单。

**Score 1.0**: 结构连贯、过渡自然、句子适合现场朗读，五项反馈被综合而非机械排列。

**Score 0.75**: 整体顺畅，仅一至两处转折或句子略生硬。

**Score 0.5**: 主线可理解，但多处像反馈清单、句式重复或存在明显跳转。

**Score 0.25**: 大部分是逐项复述、模板残留或难以自然朗读，需要大幅重组。

**Score 0.0**: 不可读、逻辑混乱或没有形成讲稿。

### Criterion 4: 现场可用性 (key: stage_readiness, weight: 0.166667)

判据：讲稿是否适合小型发布会直接朗读，表达克制且能合理设定听众预期。

**Score 1.0**: 语气适合发布现场，信息完整、克制、可直接使用，无需实质修改。

**Score 0.75**: 基本可直接使用，仅需一处轻微措辞或节奏调整。

**Score 0.5**: 内容完整但有多处内部表述、过度宣传或收束不足，需要编辑后使用。

**Score 0.25**: 更像内部纪要或草稿，需要重写才适合现场。

**Score 0.0**: 无法用于发布场景或内容与请求无关。

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_004_feedback_to_launch_script
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

- 仅Prompt题，直接回复讲稿正文。
- Auto组内权重为62.5%、25%、12.5%，整体占40%。
- Judge组内权重为33.3333%、25%、25%、16.6667%，整体占60%。
