---
id: 02_Code_Intelligence_task_012_pptx_audit_tool
name: 写一个能检查PPTX交付质量的小工具
category: 02_Code_Intelligence
timeout_seconds: 900
modality: multimodal
attachment_size_limit_mb: 10
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.55
  llm_judge: 0.45
tags:
  - custom
  - ppt
  - office
---

# 写一个能检查PPTX交付质量的小工具

## Prompt

请为 /tmp_workspace/audit_fixture.pptx 写一个简单的PPTX审计工具，同时生成一个 2 页的审计摘要PPT。把 pptx_audit.py、audit_report.json 和 pptx_audit_summary.pptx 都放到 /tmp_workspace/results/。工具至少检查页数、每页标题、备注是否存在、是否有可读的文本对象，每项结果标明 pass 或 fail，并在摘要PPT中展示总览、逐页结果和下一步。不要依赖VLM或联网。

## Expected Behavior

脚本可运行或结构完整；JSON含summary和slides，检查结果包含pass/fail状态；摘要PPT可打开且有2页；至少报告页数、标题、备注和可编辑文本四类检查。

## Grading Criteria

### Automated group

- pptx_openable
- slide_count_and_order
- generator_tests_pass
- output_package_complete
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
        import ast
        checks = []
        required_terms = expected.get("generator_required_terms", [])
        for name in expected.get("generator_files", []):
            script_path = results / name
            script_text = file_text(script_path)
            try:
                ast.parse(script_text)
                syntax_ok = True
            except (SyntaxError, ValueError, TypeError):
                syntax_ok = False
            checks.append(
                regular(script_path) and syntax_ok and
                all(term in script_text for term in required_terms)
            )
        report_name = expected.get("report_file")
        if report_name:
            report_path = results / report_name
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                report_shape_ok = (
                    isinstance(report, dict)
                    and isinstance(report.get("summary"), dict)
                    and isinstance(report.get("slides"), list)
                )
                report_terms = expected.get("report_required_terms", [])
                report_text = json.dumps(report, ensure_ascii=False).lower()
                report_content_ok = all(str(term).lower() in report_text for term in report_terms)
                checks.append(report_shape_ok and report_content_ok)
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

### Criterion 1: 审计摘要结构 (key: audit_summary_structure, weight: 0.4)

判据：审计摘要PPT是否按总览、逐页证据和结论组织，不判断报告字段的精确值。

**Score 1.0**：视觉结构完整，重点突出，页面之间衔接自然，且没有明显溢出、遮挡、裁切或无意义空白。

**Score 0.75**：整体可用，仅有一处轻微层次、密度、对齐或可读性问题。

**Score 0.5**：主要内容可读，但存在多处需要人工调整的版式或叙事问题。

**Score 0.25**：页面基本是内容堆叠，重点、顺序或受众适配明显不足。

**Score 0.0**：渲染结果不可用，或与题目要求的受众和交付场景无关。

### Criterion 2: 视觉层次 (key: visual_hierarchy, weight: 0.3)

判据：通过/风险/待处理等状态是否有清晰层级和阅读路径。

**Score 1.0**：视觉结构完整，重点突出，页面之间衔接自然，且没有明显溢出、遮挡、裁切或无意义空白。

**Score 0.75**：整体可用，仅有一处轻微层次、密度、对齐或可读性问题。

**Score 0.5**：主要内容可读，但存在多处需要人工调整的版式或叙事问题。

**Score 0.25**：页面基本是内容堆叠，重点、顺序或受众适配明显不足。

**Score 0.0**：渲染结果不可用，或与题目要求的受众和交付场景无关。

### Criterion 3: 报告可读性 (key: audit_report_readability, weight: 0.3)

判据：技术和办公受众是否能快速理解检查结果与下一步。

**Score 1.0**：视觉结构完整，重点突出，页面之间衔接自然，且没有明显溢出、遮挡、裁切或无意义空白。

**Score 0.75**：整体可用，仅有一处轻微层次、密度、对齐或可读性问题。

**Score 0.5**：主要内容可读，但存在多处需要人工调整的版式或叙事问题。

**Score 0.25**：页面基本是内容堆叠，重点、顺序或受众适配明显不足。

**Score 0.0**：渲染结果不可用，或与题目要求的受众和交付场景无关。

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_012_pptx_audit_tool
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
