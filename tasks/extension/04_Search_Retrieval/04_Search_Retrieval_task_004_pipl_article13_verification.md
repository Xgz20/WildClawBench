---
id: 04_Search_Retrieval_task_004_pipl_article13_verification
name: 个人信息保护法第十三条依据核验
category: 04_Search_Retrieval
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

# 个人信息保护法第十三条依据核验

## Prompt

同事在评审里写：“《个人信息保护法》第十三条规定，处理个人信息只能以个人同意为依据。”请帮我核对这句话。只使用以下两份固定官方文本：

- https://flk.npc.gov.cn/detail?id=ff8081817b6472a3017b656cc2040044&title=中华人民共和国个人信息保护法
- https://www.gov.cn/xinwen/2021-08/20/content_5632404.htm

将核对结果保存到`/tmp_workspace/results/pipl_article13.json`，顶层字段严格为`law_name,presidential_order,adopted_date,effective_date,legal_bases,source_urls`。`legal_bases`按第一项至第七项排序，每项字段严格为`item_number,basis,requires_consent`；`item_number`规范写为JSON整数`1`至`7`，`basis`使用条款的核心原文，`requires_consent`使用JSON布尔值。日期使用`YYYY-MM-DD`，`source_urls`按上面的顺序保存两个地址。

再写一份`/tmp_workspace/results/review_note.md`，直接说明原说法哪里不准确并引用第十三条和上述来源。不要保存网页副本，不要使用其他来源，也不要扩展为个案法律意见或实际发送评审回复。

## Expected Behavior

Agent应确认法律名称、主席令第九十一号、2021-08-20通过及2021-11-01施行，按顺序列出第十三条七项依据，并准确区分第一项的个人同意与第二至第七项在法定条件成立时不需另行取得同意。说明应限制在条文核验范围，不作具体业务法律判断。

## Grading Criteria

### Automated group

- [ ] `document_identity_and_dates`：法律、主席令、通过日期和施行日期正确 — 25%
- [ ] `seven_legal_bases`：第十三条第一至第七项顺序和核心含义完整 — 35%
- [ ] `consent_flags`：第一项为同意，第二至第七项不以另行取得同意为前提 — 25%
- [ ] `structured_delivery`：JSON结构、两个固定URL、两个输出及网页副本边界正确 — 15%

### Judge group

- [ ] `consent_rule_explanation`：第一项同意依据和第二至第七项法定情形分别对应第十三条 — 60%
- [ ] `review_note_usability`：结论明确、规范强度准确且不扩展为个案法律结论 — 40%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = [
        "document_identity_and_dates",
        "seven_legal_bases",
        "consent_flags",
        "structured_delivery",
    ]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def norm(value):
        return re.sub(r"\s+", "", str(value or ""))

    def item_number(value):
        if type(value) is int:
            return value if 1 <= value <= 7 else None
        text = norm(value).strip("（）()[]")
        text = re.sub(r"^第", "", text)
        text = re.sub(r"项$", "", text)
        numbers = {
            "1": 1, "一": 1,
            "2": 2, "二": 2,
            "3": 3, "三": 3,
            "4": 4, "四": 4,
            "5": 5, "五": 5,
            "6": 6, "六": 6,
            "7": 7, "七": 7,
        }
        return numbers.get(text)

    def norm_basis(value):
        text = norm(value)
        text = re.sub(
            r"^(?:第?[一二三四五六七1-7]项?|[（(\[][一二三四五六七1-7][）)\]])[、，,:：.．]?",
            "",
            text,
        )
        text = text.replace("在合理的范围内", "在合理范围内")
        return re.sub(r"[；;。.]$", "", text)

    def basis_matches(actual, wanted, fragments):
        actual_text = norm_basis(actual)
        if not actual_text:
            return False
        if actual_text == norm_basis(wanted):
            return True
        return all(norm_basis(fragment) in actual_text for fragment in fragments)

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        answer_path = root / "results" / "pipl_article13.json"
        note_path = root / "results" / "review_note.md"
        if not regular(answer_path) or not regular(note_path):
            raise ValueError("regular result files required")
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        note = note_path.read_text(encoding="utf-8")
        if not isinstance(answer, dict):
            raise ValueError("JSON object required")
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    top_fields = {
        "law_name", "presidential_order", "adopted_date", "effective_date",
        "legal_bases", "source_urls",
    }
    bases = answer.get("legal_bases")
    basis_items = bases if isinstance(bases, list) else []
    canonical_schema = (
        set(answer) == top_fields
        and all(type(answer.get(k)) is str for k in top_fields - {"legal_bases", "source_urls"})
        and type(bases) is list
        and type(answer.get("source_urls")) is list
        and len(basis_items) == 7
        and all(
            type(item) is dict
            and set(item) == {"item_number", "basis", "requires_consent"}
            and type(item.get("item_number")) is int
            and type(item.get("basis")) is str
            and type(item.get("requires_consent")) is bool
            for item in basis_items
        )
    )

    scores["document_identity_and_dates"] = mean([
        answer.get("law_name") == expected["law_name"],
        norm(answer.get("presidential_order")).endswith("第九十一号"),
        answer.get("adopted_date") == expected["adopted_date"],
        answer.get("effective_date") == expected["effective_date"],
    ])
    fragments = expected["basis_required_fragments"]
    ordered_basis_flags = []
    for index, wanted in enumerate(expected["legal_bases"]):
        item = basis_items[index] if index < len(basis_items) else None
        ordered_basis_flags.append(
            isinstance(item, dict)
            and item_number(item.get("item_number")) == wanted["item_number"]
            and basis_matches(
                item.get("basis"),
                wanted["basis"],
                fragments[str(wanted["item_number"])],
            )
        )
    scores["seven_legal_bases"] = mean(ordered_basis_flags)
    by_number = {
        item_number(item.get("item_number")): item
        for item in basis_items
        if isinstance(item, dict) and item_number(item.get("item_number")) is not None
    }
    scores["consent_flags"] = mean([
        by_number.get(wanted["item_number"], {}).get("requires_consent")
        is wanted["requires_consent"]
        for wanted in expected["legal_bases"]
    ])

    try:
        files = sorted(p.name for p in (root / "results").iterdir() if p.is_file() or p.is_symlink())
    except OSError:
        files = []
    forbidden = [
        p for p in root.rglob("*")
        if p.is_file()
        and "gt" not in p.parts
        and "exec" not in p.parts
        and p.suffix.lower() in {".html", ".htm", ".mhtml", ".pdf", ".warc"}
    ]
    urls_in_outputs = set(re.findall(r"https://[^\s)>\]}'\",,]+", json.dumps(answer, ensure_ascii=False) + "\n" + note))
    scores["structured_delivery"] = mean([
        canonical_schema,
        answer.get("source_urls") == expected["source_urls"],
        files == expected["result_files"],
        regular(answer_path) and regular(note_path),
        not forbidden,
        urls_in_outputs.issubset(set(expected["source_urls"])),
    ])

    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.25 * scores["document_identity_and_dates"]
        + 0.35 * scores["seven_legal_bases"]
        + 0.25 * scores["consent_flags"]
        + 0.15 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/review_note.md` against the two fixed official texts and `pipl_article13.json`. Do not add an overall-impression criterion. Accurate natural formulations are acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Consent rule explanation (key: consent_rule_explanation, weight: 0.60)

Evaluate whether the note accurately explains the relationship between consent and all seven Article 13 legal bases.

**Score 1.0**: Clearly states that consent is the first basis and that items 2 through 7 are separate statutory bases that do not require additional consent when their respective conditions are met; ties both parts to Article 13 without inventing exceptions.

**Score 0.75**: The core distinction is correct, but one secondary condition or one group of statutory bases is summarized too generally.

**Score 0.5**: Correctly rejects “consent only” but does not clearly limit items 2 through 7 to their stated statutory conditions, or contains one material ambiguity.

**Score 0.25**: Mostly reproduces the claim or the list without explaining the rule, or implies a broad consent exemption unsupported by Article 13.

**Score 0.0**: Says consent is always the sole basis, says consent is generally unnecessary, invents a legal basis, or provides no usable explanation.

### Criterion 2: Review-note usability (key: review_note_usability, weight: 0.40)

Evaluate whether the note gives a concise internal-review conclusion with accurate authority and scope boundaries.

**Score 1.0**: Directly identifies the inaccurate wording, cites Article 13 and the fixed official sources, uses appropriately qualified language, and expressly avoids deciding a particular business case.

**Score 0.75**: The conclusion and sources are usable, with only one minor omission in citation, qualification, or scope wording.

**Score 0.5**: The conclusion is understandable but requires editing because the authority, scope boundary, or recommended correction is incomplete.

**Score 0.25**: Gives a vague legal summary, overstates the effect of the provision, or drifts into case-specific advice.

**Score 0.0**: Gives an unsupported legal conclusion, relies on an unapproved source, provides individual legal advice, or omits the review note.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_004_pipl_article13_verification
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

- Auto组内权重为25%、35%、25%、15%，整体占70%。
- Judge组内权重为60%、40%，整体占30%。
