---
id: 05_Creative_Synthesis_task_002_release_note_rewrite
name: Existing-user release note rewrite
category: 05_Creative_Synthesis
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L1
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# Existing-user release note rewrite

## Prompt

Can you turn these release bullets into a short update for existing users?

- Focus Mode now keeps pinned tabs active
- CSV Export preserves local timestamps
- Sync can retry interrupted uploads

Use one short heading and one paragraph, no more than 90 words. Keep the three feature names exactly as written. Don’t add version numbers, performance metrics, or promises that aren’t in the notes. Reply with the update only.

## Expected Behavior

The response should contain one short heading followed by one readable paragraph of at most 90 English words. It should preserve the exact names Focus Mode, CSV Export, and Sync, accurately explain the three supplied changes, and add no unsupported version, metric, or promise.

## Grading Criteria

### Automated group

- [ ] `word_limit`: response contains 1–90 English words — 25%
- [ ] `feature_tokens`: all three feature names appear exactly as written — 50%
- [ ] `required_format`: one short heading and one body paragraph only — 25%

### Judge group

- [ ] `fact_fidelity`: the three changes retain their supplied meanings — 41.6667%
- [ ] `user_readability`: language suits existing non-specialist users — 33.3333%
- [ ] `publish_ready`: copy is concise, coherent, and ready to publish — 25%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import re

    keys = ["word_limit", "feature_tokens", "required_format"]
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

    words = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?", text)
    scores["word_limit"] = 1.0 if 1 <= len(words) <= 90 else 0.0

    feature_names = ["Focus Mode", "CSV Export", "Sync"]
    scores["feature_tokens"] = round(
        sum(1.0 if name in text else 0.0 for name in feature_names) / 3,
        6,
    )

    blocks = [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]
    heading_ok = (
        len(blocks) == 2
        and "\n" not in blocks[0]
        and 1 <= len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", blocks[0])) <= 12
    )
    paragraph_ok = len(blocks) == 2 and "\n" not in blocks[1]
    scores["required_format"] = 1.0 if (
        heading_ok and paragraph_ok and "```" not in text
    ) else 0.0

    scores["overall_score"] = round(
        0.25 * scores["word_limit"]
        + 0.50 * scores["feature_tokens"]
        + 0.25 * scores["required_format"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge evaluates only the final assistant reply against the supplied bullets. Do not add an overall-impression criterion. Natural wording is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Fact fidelity (key: fact_fidelity, weight: 0.416667)

Evaluate whether the update preserves the meaning of all three supplied changes without unsupported facts.

**Score 1.0**: Accurately conveys pinned tabs remaining active in Focus Mode, local timestamps being preserved by CSV Export, and interrupted uploads being retryable by Sync; adds no version, metric, guarantee, or invented behavior.

**Score 0.75**: All three changes remain accurate, with one minor imprecision that does not alter what users can expect.

**Score 0.5**: At least two changes are accurate, but one is materially omitted or blurred, or one unsupported secondary claim is added.

**Score 0.25**: Fewer than two changes retain their meaning, or the copy introduces multiple unsupported claims while remaining recognizably related.

**Score 0.0**: Contradicts the supplied notes, fabricates performance or availability promises, or provides no usable update.

### Criterion 2: User readability (key: user_readability, weight: 0.333333)

Evaluate whether existing non-specialist users can quickly understand what changed and why it matters.

**Score 1.0**: Clear, concise, plain-language copy explains all three changes without internal jargon or unnecessary technical detail.

**Score 0.75**: Generally clear, with one slightly awkward, dense, or technical phrase.

**Score 0.5**: Meaning is recoverable but several phrases read like internal release bullets or require editing for ordinary users.

**Score 0.25**: Mostly jargon, fragmented notes, or promotional wording that obscures the changes.

**Score 0.0**: Unreadable, aimed at the wrong audience, or not an update for users.

### Criterion 3: Publish readiness (key: publish_ready, weight: 0.25)

Evaluate whether the heading and paragraph form a coherent short update that can be published as written.

**Score 1.0**: Heading and paragraph work together, the three changes flow naturally, and no substantive edit is needed.

**Score 0.75**: Ready to publish after one minor wording or transition edit.

**Score 0.5**: Complete but needs several edits for flow, repetition, or emphasis before publication.

**Score 0.25**: Mostly a restated bullet list, draft notes, or promotional fragments requiring a rewrite.

**Score 0.0**: No publishable update is present or the response is unrelated.

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_002_release_note_rewrite
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

- Prompt-only task; grade reads the final assistant message from the backend-neutral transcript.
- Auto group weights are 25%, 50%, 25%; the group contributes 40% overall.
- Judge group weights are 41.6667%, 33.3333%, 25%; the group contributes 60% overall.
