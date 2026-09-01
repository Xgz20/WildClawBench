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

    def browser_probe(result_path, expected):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("EVALUATOR_PLAYWRIGHT_UNAVAILABLE") from exc

        network_urls = []
        page_errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        viewport={
                            "width": expected["mobile_width_px"],
                            "height": 900,
                        },
                        reduced_motion="reduce",
                    )
                    page = context.new_page()
                    page.on(
                        "request",
                        lambda request: network_urls.append(request.url)
                        if re.match(r"^(?:https?|wss?):", request.url, re.I)
                        else None,
                    )
                    page.on("pageerror", lambda error: page_errors.append(str(error)))
                    page.on(
                        "console",
                        lambda message: page_errors.append(message.text)
                        if message.type == "error" else None,
                    )
                    page.goto(result_path.resolve().as_uri(), wait_until="load", timeout=10_000)
                    page.wait_for_timeout(100)

                    setup = page.evaluate(
                        r"""
                        events => {
                          const visible = element => {
                            if (!element || element.hidden || element.getAttribute('aria-hidden') === 'true') return false;
                            const style = getComputedStyle(element);
                            const rect = element.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden'
                              && rect.width > 0 && rect.height > 0;
                          };
                          const focusable = element => {
                            if (!visible(element) || element.matches(':disabled,[disabled]')) return false;
                            return element.tabIndex >= 0;
                          };
                          const candidates = Array.from(document.querySelectorAll(
                            'button, summary, [role="button"], [aria-expanded], [aria-controls]'
                          )).filter(focusable);
                          const used = new Set();
                          const controls = [];

                          for (const event of events) {
                            let best = null;
                            let bestSize = Infinity;
                            for (const candidate of candidates) {
                              if (used.has(candidate)) continue;
                              let node = candidate;
                              while (node && node !== document.body && node !== document.documentElement) {
                                const text = node.innerText || node.textContent || '';
                                if (text.includes(event.id) && text.includes(event.date)
                                    && text.includes(event.title)) {
                                  if (text.length < bestSize) {
                                    best = candidate;
                                    bestSize = text.length;
                                  }
                                  break;
                                }
                                node = node.parentElement;
                              }
                            }
                            if (!best) {
                              best = candidates.find(candidate => {
                                if (used.has(candidate)) return false;
                                const text = `${candidate.innerText || candidate.textContent || ''} ${candidate.getAttribute('aria-label') || ''}`;
                                return text.includes(event.id) || text.includes(event.title);
                              }) || null;
                            }
                            if (best) used.add(best);
                            controls.push(best);
                          }

                          const targetFor = control => {
                            if (!control) return {kind: 'missing', target: null};
                            if (control.tagName.toLowerCase() === 'summary') {
                              return {kind: 'details', target: control.closest('details')};
                            }
                            const ids = (control.getAttribute('aria-controls') || '').trim().split(/\s+/).filter(Boolean);
                            return {kind: 'aria', target: ids.length === 1 ? document.getElementById(ids[0]) : null};
                          };
                          const visual = element => {
                            const style = getComputedStyle(element);
                            return {
                              outlineStyle: style.outlineStyle,
                              outlineWidth: style.outlineWidth,
                              boxShadow: style.boxShadow,
                              borderTopWidth: style.borderTopWidth,
                              borderRightWidth: style.borderRightWidth,
                              borderBottomWidth: style.borderBottomWidth,
                              borderLeftWidth: style.borderLeftWidth,
                            };
                          };

                          window.__wcbBaseFocus = {};
                          window.__wcbEventCount = controls.length;
                          const semantics = [];
                          controls.forEach((control, index) => {
                            if (!control) {
                              semantics.push(false);
                              return;
                            }
                            control.setAttribute('data-wcb-probe-index', String(index));
                            control.blur();
                            window.__wcbBaseFocus[String(index)] = visual(control);
                            const association = targetFor(control);
                            if (association.kind === 'details') {
                              semantics.push(Boolean(association.target));
                            } else {
                              semantics.push(
                                Boolean(association.target)
                                && ['true', 'false'].includes(control.getAttribute('aria-expanded'))
                              );
                            }
                          });

                          const contentRoot = document.body.cloneNode(true);
                          contentRoot.querySelectorAll('script, style, noscript, template')
                            .forEach(element => element.remove());
                          const bodyText = contentRoot.textContent || '';
                          return {
                            mapped: controls.map(Boolean),
                            semantics,
                            eventFlags: events.map(event =>
                              [event.id, event.date, event.title, event.description]
                                .every(value => bodyText.includes(value))
                            ),
                            positions: events.map(event => bodyText.indexOf(event.id)),
                            eventCounts: events.map(event => bodyText.split(event.id).length - 1),
                            semanticOutline: Boolean(document.querySelector('main'))
                              && document.querySelectorAll('h1').length === 1,
                          };
                        }
                        """,
                        expected["events"],
                    )

                    def states():
                        return page.evaluate(
                            r"""
                            () => Array.from({length: window.__wcbEventCount || 0}, (_, index) => {
                              const control = document.querySelector(`[data-wcb-probe-index="${index}"]`);
                              if (!control) return {expanded: null, visible: null};
                              if (control.tagName.toLowerCase() === 'summary') {
                                const details = control.closest('details');
                                return {
                                  expanded: details ? details.open : null,
                                  visible: details ? details.open : null,
                                };
                              }
                              const ids = (control.getAttribute('aria-controls') || '').trim().split(/\s+/).filter(Boolean);
                              const target = ids.length === 1 ? document.getElementById(ids[0]) : null;
                              const style = target ? getComputedStyle(target) : null;
                              const rect = target ? target.getBoundingClientRect() : null;
                              return {
                                expanded: control.getAttribute('aria-expanded') === 'true',
                                visible: Boolean(target && !target.hidden
                                  && target.getAttribute('aria-hidden') !== 'true'
                                  && style.display !== 'none' && style.visibility !== 'hidden'
                                  && rect.width > 0 && rect.height > 0),
                              };
                            })
                            """
                        )

                    initial_states = states()
                    initial_collapsed = all(
                        state["expanded"] is False and state["visible"] is False
                        for state in initial_states
                    )

                    page.evaluate(
                        """
                        () => {
                          if (document.activeElement && document.activeElement.blur) {
                            document.activeElement.blur();
                          }
                        }
                        """
                    )
                    tab_sequence = []
                    focus_visible = [False] * len(expected["events"])
                    for _ in range(40):
                        page.keyboard.press("Tab")
                        focused = page.evaluate(
                            """
                            () => {
                              const element = document.activeElement;
                              const rawIndex = element && element.getAttribute('data-wcb-probe-index');
                              if (rawIndex === null || rawIndex === undefined) return null;
                              const base = window.__wcbBaseFocus[rawIndex] || {};
                              const style = getComputedStyle(element);
                              const px = value => Number.parseFloat(value || '0') || 0;
                              const outline = style.outlineStyle !== 'none' && px(style.outlineWidth) > 0;
                              const shadow = style.boxShadow !== 'none' && style.boxShadow !== base.boxShadow;
                              const border = ['Top', 'Right', 'Bottom', 'Left'].some(side =>
                                style[`border${side}Width`] !== base[`border${side}Width`]
                              );
                              return {index: Number(rawIndex), visible: outline || shadow || border};
                            }
                            """
                        )
                        if isinstance(focused, dict):
                            index = focused["index"]
                            if index not in tab_sequence:
                                tab_sequence.append(index)
                            focus_visible[index] = focus_visible[index] or bool(focused["visible"])
                        if len(tab_sequence) == len(expected["events"]):
                            break

                    def key_results(key):
                        results = []
                        for index in range(len(expected["events"])):
                            locator = page.locator(f'[data-wcb-probe-index="{index}"]')
                            if locator.count() != 1:
                                results.append(False)
                                continue
                            before = states()
                            locator.focus()
                            locator.press(key)
                            page.wait_for_timeout(20)
                            opened = states()
                            other_unchanged = all(
                                opened[other] == before[other]
                                for other in range(len(before))
                                if other != index
                            )
                            opened_target = (
                                opened[index]["expanded"] is True
                                and opened[index]["visible"] is True
                            )
                            locator.press(key)
                            page.wait_for_timeout(20)
                            closed = states()
                            returned = closed == before
                            results.append(opened_target and other_unchanged and returned)
                        return results

                    enter_results = key_results("Enter")
                    space_results = key_results("Space")
                    motion_ok = page.evaluate(
                        """
                        () => {
                          const milliseconds = value => value.split(',').map(part => {
                            const item = part.trim();
                            if (item.endsWith('ms')) return Number.parseFloat(item) || 0;
                            if (item.endsWith('s')) return (Number.parseFloat(item) || 0) * 1000;
                            return 0;
                          });
                          let maximum = 0;
                          for (const element of document.querySelectorAll('body, body *')) {
                            for (const pseudo of [null, '::before', '::after']) {
                              let styles;
                              try {
                                styles = getComputedStyle(element, pseudo);
                              } catch (_) {
                                continue;
                              }
                              maximum = Math.max(
                                maximum,
                                ...milliseconds(styles.transitionDuration),
                                ...milliseconds(styles.animationDuration),
                              );
                            }
                          }
                          return maximum <= 100;
                        }
                        """
                    )
                    mobile_fits = page.evaluate(
                        """
                        () => document.documentElement.scrollWidth <= window.innerWidth + 1
                          && document.body.scrollWidth <= window.innerWidth + 1
                        """
                    )
                    context.close()
                finally:
                    browser.close()
        except Exception as exc:
            raise RuntimeError(f"EVALUATOR_BROWSER_PROBE_FAILED: {exc}") from exc

        return {
            **setup,
            "networkUrls": network_urls,
            "pageErrors": page_errors,
            "initialCollapsed": initial_collapsed,
            "tabOrder": tab_sequence == list(range(len(expected["events"]))),
            "focusVisible": focus_visible,
            "enterResults": enter_results,
            "spaceResults": space_results,
            "reducedMotion": bool(motion_ok),
            "mobileFits": bool(mobile_fits),
        }

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
    probe = kwargs.get("_browser_probe")
    observation = (
        probe(result_path, expected)
        if callable(probe)
        else browser_probe(result_path, expected)
    )
    scores["single_file_offline"] = round(mean([
        result_files == expected["result_files"],
        regular(result_path) and result_path.stat().st_size <= 500_000,
        external_attr is None and external_css is None,
        network_api is None and "<iframe" not in lower and "<object" not in lower
        and not observation.get("networkUrls"),
    ]), 6)

    scores["event_fidelity_order"] = round(mean([
        all(observation.get("eventFlags", []))
        and len(observation.get("eventFlags", [])) == len(expected["events"]),
        len(observation.get("eventCounts", [])) == len(expected["events"])
        and all(count >= 1 for count in observation.get("eventCounts", [])),
        all(position >= 0 for position in observation.get("positions", []))
        and observation.get("positions") == sorted(observation.get("positions", []))
        and len(observation.get("positions", [])) == len(expected["events"]),
        all(expected["events"][index]["date"] <= expected["events"][index + 1]["date"] for index in range(len(expected["events"]) - 1)),
    ]), 6)

    scores["keyboard_behavior"] = round(mean([
        all(observation.get("mapped", []))
        and len(observation.get("mapped", [])) == len(expected["events"]),
        observation.get("tabOrder") is True,
        all(observation.get("enterResults", []))
        and len(observation.get("enterResults", [])) == len(expected["events"]),
        all(observation.get("spaceResults", []))
        and len(observation.get("spaceResults", [])) == len(expected["events"]),
    ]), 6)

    scores["semantic_accessibility"] = round(mean([
        observation.get("semanticOutline") is True,
        all(observation.get("mapped", []))
        and len(observation.get("mapped", [])) == len(expected["events"]),
        all(observation.get("semantics", []))
        and len(observation.get("semantics", [])) == len(expected["events"]),
        all(observation.get("focusVisible", []))
        and len(observation.get("focusVisible", [])) == len(expected["events"]),
        observation.get("reducedMotion") is True,
    ]), 6)

    document_shape = (
        "<!doctype html" in lower
        and "<html" in lower and "</html>" in lower
        and "<head" in lower and "</head>" in lower
        and "<body" in lower and "</body>" in lower
        and "<style" in lower and "</style>" in lower
    )
    no_dangerous_markup = not re.search(
        r"<base\b|<meta[^>]+http-equiv\s*=\s*['\"]?refresh|document\.write\s*\(",
        lower,
    )
    scores["runtime_integrity"] = round(mean([
        inputs_ok and result_files == expected["result_files"],
        document_shape,
        observation.get("initialCollapsed") is True,
        observation.get("mobileFits") is True,
        not observation.get("pageErrors"),
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
