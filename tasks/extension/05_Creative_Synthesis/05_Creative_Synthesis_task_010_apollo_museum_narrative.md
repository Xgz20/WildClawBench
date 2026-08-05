---
id: 05_Creative_Synthesis_task_010_apollo_museum_narrative
name: Apollo 11 family museum narration
category: 05_Creative_Synthesis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# Apollo 11 family museum narration

## Prompt

Use NASA’s fixed Apollo 11 report record and its official PDF:

- https://ntrs.nasa.gov/citations/19710015566
- https://ntrs.nasa.gov/api/citations/19710015566/downloads/19710015566.pdf

Draft a 600–750 word, five-minute museum narration for families with children aged 10–14. Use the headings `# Opening`, `## Act 1`, `## Act 2`, `## Act 3`, and `## Closing Question` in that order. Add one short source note immediately after each act in the form `[Source note: NASA-SP-238, p. X]`, using the report’s printed page number. Label every sentence that is your own connective narration as `[Narrative transition: ...]`. Do not invent dialogue or present a reconstruction as a quotation. Use only this NASA record and include both fixed URLs plus Document ID 19710015566 in a final source line. Reply with the narration only; do not save the PDF or a webpage copy.

## Expected Behavior

The narration should accurately follow launch and lunar approach, landing and surface activity, then ascent and Pacific recovery. It should preserve six ground-truth facts from printed report pages 1–2, distinguish report facts from clearly labeled narrative transitions, provide a source note after each act, address families without invented dialogue, and include the NASA-SP-238 identity, Document ID, and both fixed URLs.

## Grading Criteria

### Automated group

- [ ] `official_id_url`: two fixed URLs, Document ID and NASA-SP-238 are present without other sources — 37.5%
- [ ] `required_sections`: opening, three chronological acts, closing question, and three source notes are structurally present — 25%
- [ ] `length_and_labels`: 600–750 English words and narrative-transition labels are used — 37.5%

### Judge group

- [ ] `fact_fidelity`: six specified historical facts and report pages remain accurate — 41.6667%
- [ ] `source_transition_separation`: report facts are traceable and creative transitions are clearly separated — 25%
- [ ] `museum_arc`: the three acts form a coherent chronological museum narration — 16.6667%
- [ ] `family_audience_fit`: language and pacing suit families with children aged10–14 — 16.6666%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import re

    keys = ["official_id_url", "required_sections", "length_and_labels"]
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
    if not text or "```" in text:
        return {**scores, "overall_score": 0.0}

    record_url = "https://ntrs.nasa.gov/citations/19710015566"
    pdf_url = "https://ntrs.nasa.gov/api/citations/19710015566/downloads/19710015566.pdf"
    urls = set(re.findall(r"https://[^\s)>\]}\"']+", text))
    urls = {url.rstrip(".,;") for url in urls}
    scores["official_id_url"] = round(sum([
        1.0 if record_url in text else 0.0,
        1.0 if pdf_url in text else 0.0,
        1.0 if "Document ID 19710015566" in text else 0.0,
        1.0 if "NASA-SP-238" in text else 0.0,
        1.0 if urls <= {record_url, pdf_url} else 0.0,
    ]) / 5, 6)

    headings = ["# Opening", "## Act 1", "## Act 2", "## Act 3", "## Closing Question"]
    positions = [text.find(heading) for heading in headings]
    heading_order = all(position >= 0 for position in positions) and positions == sorted(positions)
    exact_headings = all(len(re.findall(rf"^{re.escape(heading)}\s*$", text, flags=re.M)) == 1 for heading in headings)
    source_notes = re.findall(r"\[Source note:\s*NASA-SP-238,\s*p\.\s*(\d+)\]", text, flags=re.I)
    note_pages_valid = len(source_notes) == 3 and all(int(page) in {1, 2, 3} for page in source_notes)
    acts = [
        text[positions[index]:positions[index + 1]] if heading_order else ""
        for index in range(1, 4)
    ]
    note_after_each = heading_order and all(
        len(re.findall(r"\[Source note:\s*NASA-SP-238,\s*p\.\s*\d+\]", act, flags=re.I)) == 1
        for act in acts
    )
    closing_question = heading_order and "?" in text[positions[4]:]
    scores["required_sections"] = round(sum([
        1.0 if heading_order and exact_headings else 0.0,
        1.0 if note_pages_valid else 0.0,
        1.0 if note_after_each else 0.0,
        1.0 if closing_question else 0.0,
    ]) / 4, 6)

    words = re.findall(r"[A-Za-z]+(?:[-’'][A-Za-z]+)*|\d+(?:\.\d+)?", text)
    transition_labels = re.findall(r"\[Narrative transition:\s*[^\]\n]+\]", text, flags=re.I)
    unmatched_label = "[Narrative transition:" in text and not transition_labels
    scores["length_and_labels"] = round(sum([
        1.0 if 600 <= len(words) <= 750 else 0.0,
        1.0 if len(transition_labels) >= 3 else 0.0,
        1.0 if not unmatched_label else 0.0,
    ]) / 3, 6)

    scores["overall_score"] = round(
        0.375 * scores["official_id_url"]
        + 0.25 * scores["required_sections"]
        + 0.375 * scores["length_and_labels"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge uses only the NASA record, NASA-SP-238 PDF, and the final narration. Do not add an overall-impression criterion or reward invented dramatic detail. Natural narration is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Historical fact fidelity (key: fact_fidelity, weight: 0.416667)

Evaluate these six report-grounded facts: the July 16 launch at 8:32 a.m. EST from Kennedy; lunar-orbit insertion near 76 hours; Sea of Tranquility landing at 102:45:40; Armstrong's first surface contact at 109:24:15, 9:56:15 p.m. EST July 20; ascent near 124.25 hours and docking at 128 hours; Pacific landing near 195.25 hours followed by recovery to USS Hornet. The first five are on printed page 1 and the recovery fact is on printed page 2.

**Score 1.0**: All six facts, their sequence, and cited printed pages are accurate; no invented dialogue, quotation, person, time, place, or event is presented as report fact.

**Score 0.75**: All six facts are substantively correct, with only one minor rounding, wording, or page-note imprecision that does not change the history.

**Score 0.5**: At least three facts are accurate, but one fact is materially wrong, two are omitted, or one unsupported secondary claim is presented as fact.

**Score 0.25**: Fewer than three facts are accurate, chronology is materially confused, or multiple reconstructions are presented as report facts.

**Score 0.0**: Core mission facts conflict with the report, sources or quotations are fabricated, or no usable narration is present.

### Criterion 2: Source and transition separation (key: source_transition_separation, weight: 0.25)

Evaluate whether report-based statements remain traceable to the act source notes and the writer's connective narration is visibly labeled without being passed off as quotation.

**Score 1.0**: Each act's factual content is supported by its note; all creative connective sentences are clearly labeled; no invented dialogue or reconstructed scene is presented as sourced fact.

**Score 0.75**: Separation is consistently clear, with one minor transition-label or page-note omission that creates no factual ambiguity.

**Score 0.5**: Most facts are traceable, but several transitions are unlabeled or one act's note is too broad, requiring editing to restore the boundary.

**Score 0.25**: Fact and creative narration are repeatedly mixed, source notes do not support major passages, or reconstruction is ambiguously presented.

**Score 0.0**: Invented material is presented as report quotation or fact, source identity is false, or separation is absent.

### Criterion 3: Museum narrative arc (key: museum_arc, weight: 0.166667)

Evaluate whether opening, three chronological acts, and closing question form a coherent five-minute museum experience.

**Score 1.0**: The opening establishes the visit; acts move clearly through approach, surface, and return; transitions preserve chronology; the closing question meaningfully reflects the story.

**Score 0.75**: The arc is clear, with one minor jump, repetition, or weak transition.

**Score 0.5**: The chronology is understandable but one act is thin or misplaced, or several transitions require editing.

**Score 0.25**: The piece is a fact list with little narrative progression or has multiple chronological breaks.

**Score 0.0**: The narration is incoherent, substantially out of order, or unrelated to Apollo 11.

### Criterion 4: Family audience fit (key: family_audience_fit, weight: 0.166666)

Evaluate whether vocabulary, explanation, pacing, and question suit families with children aged 10–14 without talking down to them.

**Score 1.0**: Language is vivid but accurate, technical terms are understandable in context, pacing supports listening, and the closing invites age-appropriate reflection.

**Score 0.75**: Overall well suited, with one dense, overly technical, or slightly patronizing passage.

**Score 0.5**: Meaning remains accessible but several passages are too technical, abstract, or adult-oriented for the target visit.

**Score 0.25**: Most of the narration reads like a technical report or, conversely, oversimplifies and talks down to the audience.

**Score 0.0**: Language is unusable for the intended audience or contains inappropriate material.

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_010_apollo_museum_narrative
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

- 联网直接回复题，只允许两个固定NASA URL，不保存网页或PDF副本。
- Auto组内权重为37.5%、25%、37.5%，整体占40%。
- Judge组内权重为41.6667%、25%、16.6667%、16.6666%，整体占60%。
