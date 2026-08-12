---
id: 01_Productivity_Flow_task_014_delivery_qa
name: 做一轮PPT办公交付验收
category: 01_Productivity_Flow
timeout_seconds: 900
modality: multimodal
attachment_size_limit_mb: 10
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.55
  llm_judge: 0.45
tags:
  - custom
  - ppt
  - office
---

# 做一轮PPT办公交付验收

## Prompt

请检查并修正 /tmp_workspace/candidate.pptx，让它能直接给客户播放和继续修改。重点看页面比例、文字是否被截断、是否还有占位符、备注里有没有来源说明。把 final_delivery.pptx、final_delivery.pdf、delivery_checklist.json 和 delivery_notes.md 都放到 /tmp_workspace/results/；仍未通过的项目要在清单里写明原因。

## Expected Behavior

输出PPTX、对应PDF和两份验收记录；清单应覆盖可打开、16:9、无占位符、无明显溢出、可编辑文本、备注来源；结论与检查结果一致。

## Grading Criteria

### Automated group

- pptx_openable
- slide_count_and_order
- editable_objects_preserved
- output_package_complete
- pdf_correspondence
- input_files_unchanged

### Judge group

- 评审只看最终PPTX及题目允许的伴随文件；视觉判断只覆盖版式、层次、信息密度、图表与文字关系和受众可读性，不判断精确数字、XML关系、备注字段或对象是否可编辑。

## Automated Checks

```python
def grade(**kwargs):
    import hashlib, html, json, re, zipfile
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    results = root / "results"
    expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
    scores = {key: 0.0 for key in expected["keys"]}

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def file_text(path):
        if not regular(path):
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def ppt_info(path):
        info = {"valid": False, "slides": 0, "text": "", "notes": "", "slide_xml": "",
                "charts": 0, "relationships": 0, "theme": False, "master": False}
        if not regular(path) or not zipfile.is_zipfile(path):
            return info
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                slide_names = sorted(
                    name for name in names
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                )
                slide_xml = "\\n".join(
                    archive.read(name).decode("utf-8", "ignore") for name in slide_names
                )
                notes_xml = "\\n".join(
                    archive.read(name).decode("utf-8", "ignore")
                    for name in names
                    if name.startswith("ppt/notesSlides/") and name.endswith(".xml")
                )
                text_nodes = re.findall(r"<a:t[^>]*>(.*?)</a:t>", slide_xml, re.S)
                notes_nodes = re.findall(r"<a:t[^>]*>(.*?)</a:t>", notes_xml, re.S)
                info.update({
                    "valid": bool(slide_names),
                    "slides": len(slide_names),
                    "text": html.unescape("\\n".join(text_nodes)),
                    "notes": html.unescape("\\n".join(notes_nodes)),
                    "slide_xml": slide_xml,
                    "charts": len([name for name in names if re.fullmatch(r"ppt/charts/chart\d+\.xml", name)]),
                    "relationships": len([name for name in names if name.endswith(".rels") and name.startswith("ppt/")]),
                    "theme": any(name.startswith("ppt/theme/") for name in names),
                    "master": any(name.startswith("ppt/slideMasters/") for name in names),
                })
        except (OSError, zipfile.BadZipFile, KeyError):
            return info
        return info

    output = results / expected.get("output", "")
    if output.is_dir():
        deck_infos = [ppt_info(path) for path in sorted(output.glob("*.pptx"))]
        info = {
            "valid": bool(deck_infos) and all(item["valid"] for item in deck_infos),
            "slides": sum(item["slides"] for item in deck_infos),
            "text": "\\n".join(item["text"] for item in deck_infos),
            "notes": "\\n".join(item["notes"] for item in deck_infos),
            "slide_xml": "\\n".join(item["slide_xml"] for item in deck_infos),
            "charts": sum(item["charts"] for item in deck_infos),
            "relationships": sum(item["relationships"] for item in deck_infos),
            "theme": all(item["theme"] for item in deck_infos),
            "master": all(item["master"] for item in deck_infos),
        }
    else:
        info = ppt_info(output) if output.suffix.lower() == ".pptx" else {"valid": False, "slides": 0, "text": "", "notes": "", "slide_xml": "", "charts": 0, "relationships": 0, "theme": False, "master": False}
    visible = info["text"]
    evidence_file = results / expected.get("source_file", "sources.md")
    evidence = visible + "\\n" + info["notes"] + "\\n" + file_text(evidence_file)

    if "pptx_openable" in scores:
        scores["pptx_openable"] = float(info["valid"] and info["theme"] and info["master"] and info["relationships"] > 0)
    if "slide_count_and_order" in scores:
        min_slides = int(expected.get("min_slides", 1))
        count_ok = info["slides"] >= min_slides
        ordered_terms = expected.get("ordered_terms", [])
        positions = [visible.find(term) for term in ordered_terms]
        order_ok = not ordered_terms or all(pos >= 0 for pos in positions) and positions == sorted(positions)
        scores["slide_count_and_order"] = (float(count_ok) + float(order_ok)) / 2
    if "editable_objects_preserved" in scores:
        text_nodes = len(re.findall(r"<a:t[^>]*>", info["slide_xml"]))
        image_nodes = len(re.findall(r"<p:pic\b", info["slide_xml"]))
        scores["editable_objects_preserved"] = float(
            text_nodes >= int(expected.get("min_text_nodes", 3)) and
            (text_nodes > 0 or image_nodes == 0)
        )
    if "source_identity" in scores:
        domains = expected.get("official_domains", [])
        markers = expected.get("source_markers", [])
        scores["source_identity"] = (
            float(any(domain in evidence for domain in domains)) +
            float(all(marker in evidence for marker in markers))
        ) / 2
    if "source_fidelity" in scores:
        required = expected.get("required", [])
        scores["source_fidelity"] = sum(term in visible for term in required) / max(1, len(required))
    if "claim_evidence_alignment" in scores:
        source_markers = expected.get("source_markers", [])
        has_source_block = "[Sources]" in evidence or "来源" in evidence
        has_marker = all(marker in evidence for marker in source_markers)
        scores["claim_evidence_alignment"] = (float(has_source_block) + float(has_marker)) / 2
    if "chart_data_correct" in scores:
        chart_terms = expected.get("chart_terms", expected.get("required", []))
        chart_exists = info["charts"] >= int(expected.get("min_charts", 1))
        scores["chart_data_correct"] = (
            float(chart_exists) + sum(term in visible for term in chart_terms) / max(1, len(chart_terms))
        ) / 2
    if "output_package_complete" in scores:
        output_ok = regular(output) or (
            output.is_dir() and len(list(output.glob("*.pptx"))) >= int(expected.get("generated_decks", 1))
        )
        companion_ok = all(regular(results / name) for name in expected.get("companions", []))
        scores["output_package_complete"] = (float(output_ok) + float(companion_ok)) / 2
    if "pdf_correspondence" in scores:
        pdf = results / expected.get("pdf_output", "")
        try:
            import fitz
            pdf_pages = fitz.open(pdf).page_count if regular(pdf) else 0
            scores["pdf_correspondence"] = float(regular(output) and regular(pdf) and pdf_pages == info["slides"])
        except (ImportError, OSError, RuntimeError):
            scores["pdf_correspondence"] = float(regular(output) and regular(pdf) and pdf.stat().st_size > 0)
    if "input_files_unchanged" in scores:
        checks = []
        for name, digest in expected.get("input_hashes", {}).items():
            path = root / name
            if not regular(path):
                path = root / "exec" / name
            if not regular(path):
                checks.append(False)
                continue
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            checks.append(h == digest)
        scores["input_files_unchanged"] = sum(checks) / max(1, len(checks))
    if "generator_tests_pass" in scores:
        checks = [regular(results / name) for name in expected.get("generator_files", [])]
        report_name = expected.get("report_file")
        if report_name:
            report_path = results / report_name
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                checks.append(isinstance(report, dict) and isinstance(report.get("summary"), dict) and isinstance(report.get("slides"), list))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                checks.append(False)
        if expected.get("generated_decks"):
            deck_dir = results / expected.get("output", "")
            decks = list(deck_dir.glob("*.pptx")) if deck_dir.is_dir() else []
            checks.append(len(decks) >= int(expected["generated_decks"]) and all(zipfile.is_zipfile(p) for p in decks))
        scores["generator_tests_pass"] = sum(checks) / max(1, len(checks))
    if "pii_absent" in scores:
        banned = expected.get("banned", [])
        scores["pii_absent"] = float(not any(value in (visible + "\\n" + info["notes"]) for value in banned))

    scores = {key: round(float(value), 6) for key, value in scores.items()}
    scores["overall_score"] = round(sum(scores.values()) / max(1, len(scores)), 6)
    return scores
```

## LLM Judge Rubric

评审只依据最终PPTX的渲染图和可见内容，必要时查看导出的PDF页面；不判断精确数字、XML关系、备注字段或对象是否可编辑。每项使用1.0 / 0.75 / 0.5 / 0.25 / 0.0五档，不设置整体印象分。

### Criterion 1: 验收摘要清晰度 (key: qa_summary_clarity, weight: 0.35)

判据：页面是否清楚呈现通过项、风险项和交付结论；不判断JSON、备注或XML字段。

**Score 1.0**：视觉结构完整，重点突出，页面之间衔接自然，且没有明显溢出、遮挡、裁切或无意义空白。

**Score 0.75**：整体可用，仅有一处轻微层次、密度、对齐或可读性问题。

**Score 0.5**：主要内容可读，但存在多处需要人工调整的版式或叙事问题。

**Score 0.25**：页面基本是内容堆叠，重点、顺序或受众适配明显不足。

**Score 0.0**：渲染结果不可用，或与题目要求的受众和交付场景无关。

### Criterion 2: 视觉层次 (key: visual_hierarchy, weight: 0.3)

判据：标题、检查结果、证据和行动项的层级是否清楚。

**Score 1.0**：视觉结构完整，重点突出，页面之间衔接自然，且没有明显溢出、遮挡、裁切或无意义空白。

**Score 0.75**：整体可用，仅有一处轻微层次、密度、对齐或可读性问题。

**Score 0.5**：主要内容可读，但存在多处需要人工调整的版式或叙事问题。

**Score 0.25**：页面基本是内容堆叠，重点、顺序或受众适配明显不足。

**Score 0.0**：渲染结果不可用，或与题目要求的受众和交付场景无关。

### Criterion 3: 交付可读性 (key: delivery_readability, weight: 0.35)

判据：投屏和打印时是否无拥挤、截断或遮挡，受众能否快速判断下一步。

**Score 1.0**：视觉结构完整，重点突出，页面之间衔接自然，且没有明显溢出、遮挡、裁切或无意义空白。

**Score 0.75**：整体可用，仅有一处轻微层次、密度、对齐或可读性问题。

**Score 0.5**：主要内容可读，但存在多处需要人工调整的版式或叙事问题。

**Score 0.25**：页面基本是内容堆叠，重点、顺序或受众适配明显不足。

**Score 0.0**：渲染结果不可用，或与题目要求的受众和交付场景无关。

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_014_delivery_qa
```

## Skills

```
presentations
```

## Env

```
```

## Warmup

```
```

## Additional Notes

- 规则组只验证文件存在性、PPTX ZIP/XML结构、关键字和题目边界；不运行真实评测、不调用VLM。
- Judge组负责渲染后的版式、叙事、可读性和交付质量。
