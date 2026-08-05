---
id: 05_Creative_Synthesis_task_008_accessible_timeline_microsite
name: Accessible offline timeline microsite
category: 05_Creative_Synthesis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3
tags:
  - custom
---

# Accessible offline timeline microsite

## Prompt

Please build the interactive timeline described in `/tmp_workspace/accessibility_brief.md` using all records in `/tmp_workspace/events.yaml`.

Deliver a single `/tmp_workspace/results/index.html`. It must work offline with no external scripts, fonts, images, or network requests. Keep every event ID, date, title, and description unchanged and in chronological order. Users must be able to reach every event with Tab, open or close details with Enter or Space, see a visible focus state, and use the page with reduced motion enabled. Make it usable on a narrow mobile viewport as well. Don’t modify the inputs or create extra files.

## Expected Behavior

The delivered HTML should be a self-contained, offline page containing all six events in source order. Each event should expose a keyboard-focusable toggle with accurate expanded state and a linked details region. Enter and Space should independently toggle the focused event, focus must be visible, reduced-motion settings must be honored, and a 420-pixel viewport must not require horizontal scrolling.

## Grading Criteria

### Automated group

- [ ] `single_file_offline`: one regular HTML file with no external dependency or request — 14.2857%
- [ ] `event_fidelity_order`: all event fields are unchanged, complete, and chronological — 28.5714%
- [ ] `keyboard_behavior`: every event is focusable and Enter/Space toggle only its details — 21.4286%
- [ ] `semantic_accessibility`: headings, state, controlled regions, focus, and reduced motion are represented — 21.4286%
- [ ] `runtime_integrity`: inputs, output range, inline runtime, and mobile rules are internally valid — 14.2857%

### Judge group

- [ ] `narrative_scanability`: the timeline is easy to scan and understand across six events — 50%
- [ ] `interaction_usability`: interaction cues and responsive presentation are practical for intended users — 50%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import html
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    keys = [
        "single_file_offline",
        "event_fidelity_order",
        "keyboard_behavior",
        "semantic_accessibility",
        "runtime_integrity",
    ]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    inputs_ok = True
    for relative, wanted_hash in expected["exec_file_sha256"].items():
        path = root / relative
        try:
            inputs_ok = inputs_ok and regular(path) and hashlib.sha256(path.read_bytes()).hexdigest() == wanted_hash
        except OSError:
            inputs_ok = False
    if not inputs_ok:
        return {**scores, "overall_score": 0.0}

    result_path = root / "results" / "index.html"
    try:
        if not regular(result_path):
            raise ValueError("regular index.html required")
        raw = result_path.read_text(encoding="utf-8")
        if not raw.strip():
            raise ValueError("nonempty HTML required")
        result_files = sorted(path.name for path in (root / "results").iterdir() if path.is_file() or path.is_symlink())
    except (OSError, UnicodeError, ValueError):
        return {**scores, "overall_score": 0.0}

    lower = raw.lower()
    external_attr = re.search(
        r"\b(?:src|href)\s*=\s*['\"]\s*(?://|https?:|data:|javascript:)",
        lower,
    )
    network_api = re.search(
        r"\b(?:fetch|xmlhttprequest|websocket|eventsource|sendbeacon)\s*\(",
        lower,
    )
    external_css = re.search(r"@import\b|url\s*\(\s*['\"]?(?!#)", lower)
    scores["single_file_offline"] = round(mean([
        result_files == expected["result_files"],
        regular(result_path) and result_path.stat().st_size <= 500_000,
        external_attr is None and external_css is None,
        network_api is None and "<iframe" not in lower and "<object" not in lower,
    ]), 6)

    visible = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    positions = []
    event_flags = []
    for event in expected["events"]:
        values = [event["id"], event["date"], event["title"], event["description"]]
        event_flags.append(all(value in visible for value in values))
        positions.append(visible.find(event["id"]))
    scores["event_fidelity_order"] = round(mean([
        all(event_flags),
        all(visible.count(event["id"]) >= 1 for event in expected["events"]),
        all(position >= 0 for position in positions) and positions == sorted(positions),
        all(expected["events"][index]["date"] <= expected["events"][index + 1]["date"] for index in range(len(expected["events"]) - 1)),
    ]), 6)

    toggle_flags = []
    region_flags = []
    for event in expected["events"]:
        event_id = re.escape(event["id"])
        toggle_flags.append(bool(re.search(
            rf"<button\b(?=[^>]*\bdata-event-id=['\"]{event_id}['\"])(?=[^>]*\baria-expanded=['\"]false['\"])(?=[^>]*\baria-controls=['\"]details-{event_id}['\"])[^>]*>",
            raw,
            flags=re.I,
        )))
        region_flags.append(bool(re.search(
            rf"<[^>]+\bid=['\"]details-{event_id}['\"][^>]*\bhidden\b[^>]*>",
            raw,
            flags=re.I,
        )))
    key_handler = (
        "addeventlistener" in lower
        and "keydown" in lower
        and re.search(r"(?:event|e)\.key\s*={2,3}\s*['\"]enter['\"]", lower)
        and re.search(r"(?:event|e)\.key\s*={2,3}\s*['\"](?: |space|spacebar)['\"]", lower)
        and "preventdefault" in lower
    )
    toggle_code = (
        "aria-expanded" in lower
        and re.search(r"\.hidden\s*=|toggleattribute\s*\(\s*['\"]hidden", lower)
    )
    scores["keyboard_behavior"] = round(mean([
        all(toggle_flags),
        all(region_flags),
        bool(key_handler),
        bool(toggle_code),
    ]), 6)

    semantic_outline = bool(re.search(r"<main\b", lower)) and len(re.findall(r"<h1\b", lower)) == 1
    list_semantics = bool(re.search(r"<(?:ol|ul)\b", lower)) and len(re.findall(r"<li\b", lower)) >= len(expected["events"])
    focus_visible = bool(re.search(r":focus-visible\b|:focus\b", lower)) and re.search(r"outline\s*:", lower)
    reduced_motion = "prefers-reduced-motion" in lower and "reduce" in lower
    scores["semantic_accessibility"] = round(mean([
        semantic_outline,
        list_semantics,
        all(toggle_flags) and all(region_flags),
        bool(focus_visible),
        reduced_motion,
    ]), 6)

    document_shape = (
        "<!doctype html" in lower
        and "<html" in lower and "</html>" in lower
        and "<head" in lower and "</head>" in lower
        and "<body" in lower and "</body>" in lower
        and "<script" in lower and "</script>" in lower
        and "<style" in lower and "</style>" in lower
    )
    mobile_rule = bool(re.search(r"@media[^\{]*max-width\s*:\s*420px", lower))
    overflow_protection = (
        "box-sizing" in lower
        and ("overflow-wrap" in lower or "word-break" in lower)
        and re.search(r"max-width\s*:\s*100%", lower)
    )
    no_dangerous_markup = not re.search(
        r"<base\b|<meta[^>]+http-equiv\s*=\s*['\"]?refresh|document\.write\s*\(",
        lower,
    )
    scores["runtime_integrity"] = round(mean([
        inputs_ok and result_files == expected["result_files"],
        document_shape,
        mobile_rule and bool(overflow_protection),
        no_dangerous_markup,
    ]), 6)

    scores["overall_score"] = round(
        (1 / 7) * scores["single_file_offline"]
        + (2 / 7) * scores["event_fidelity_order"]
        + (3 / 14) * scores["keyboard_behavior"]
        + (3 / 14) * scores["semantic_accessibility"]
        + (1 / 7) * scores["runtime_integrity"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge evaluates only the delivered offline page against the supplied brief and event data. Do not add an overall-impression criterion or require one visual style. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Narrative scanability (key: narrative_scanability, weight: 0.5)

Evaluate whether readers can understand the project history, chronology, and each event's relationship to the whole timeline.

**Score 1.0**: Heading and introduction establish context; dates, titles, and details have a clear hierarchy; all six events are easy to scan in order on desktop and narrow screens without visual or narrative confusion.

**Score 0.75**: The chronology and hierarchy are clear, with one minor density, spacing, or labeling issue.

**Score 0.5**: All events are understandable, but hierarchy is weak, multiple items feel dense or repetitive, or the narrow layout needs several edits.

**Score 0.25**: The page is mostly an unstructured data dump, chronology is hard to follow, or substantial layout work is required.

**Score 0.0**: The timeline is unusable, misleading, or lacks readable event content.

### Criterion 2: Interaction usability (key: interaction_usability, weight: 0.5)

Evaluate whether visual and textual cues make the focus and open/closed interactions understandable across keyboard, screen-reader, reduced-motion, and mobile use.

**Score 1.0**: Controls clearly communicate action and state, focus is easy to locate, expanded content remains associated with its event, motion and responsive behavior are restrained, and no substantive usability edit is needed.

**Score 0.75**: Interaction is usable across intended modes, with one minor cue, focus, spacing, or responsive issue.

**Score 0.5**: Core interaction works but several cues are ambiguous, focus or state presentation is weak, or mobile use needs multiple edits.

**Score 0.25**: Users must guess how to open events, state is confusing, or the interaction is impractical for one major intended access mode.

**Score 0.0**: Interaction prevents access to event details, contradicts the requested modes, or no usable page is delivered.

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_008_accessible_timeline_microsite
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

- Auto组内权重由整题10%、20%、15%、15%、10%归一化，整体占70%。
- Judge两项组内权重各50%，整体占30%。
