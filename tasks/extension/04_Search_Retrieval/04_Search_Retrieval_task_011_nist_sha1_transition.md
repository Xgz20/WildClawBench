---
id: 04_Search_Retrieval_task_011_nist_sha1_transition
name: NIST SHA-1 archive transition check
category: 04_Search_Retrieval
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

# NIST SHA-1 archive transition check

## Prompt

A reviewer wrote, “NIST disallows SHA-1 everywhere, so our archive must reject every old SHA-1 signature.” Check that statement against the fixed NIST publications below. Use SP 800-131A Rev. 2 as the primary source; use FIPS 186-5 only for publication and transition context.

- https://csrc.nist.gov/pubs/sp/800/131/a/r2/final
- https://doi.org/10.6028/NIST.SP.800-131Ar2
- https://csrc.nist.gov/pubs/fips/186-5/final

Create `/tmp_workspace/results/sha1_use_matrix.csv` with exactly `use_case,nist_status,conditions,primary_source,section_or_table`. Use the case codes `digital_signature_generation,existing_digital_signature_verification,non_digital_signature_use` in that order. Write `primary_source` canonically as `NIST SP 800-131A Rev. 2`; preserve NIST’s status terms and state the limiting condition for each row.

Then write `/tmp_workspace/results/transition_memo.md` for the archive team. Identify the primary publication, DOI and publication month, mention FIPS 186-5 only as context, and separate what must stop from what may remain for controlled legacy verification. Do not generalize the fixed documents into claims about every product or protocol, save the publications, use other sources, or create other result files.

## Expected Behavior

Agent should identify SHA-1 digital-signature generation as Disallowed except where NIST protocol-specific guidance explicitly allows it, existing-signature verification as Legacy use, and non-digital-signature use as Acceptable only where collision resistance is not required. It should explain that Legacy use means processing already protected information, not recommending new SHA-1 signatures.

## Grading Criteria

### Automated group

- [ ] `publication_identity`：SP 800-131A Rev.2, DOI, 2019-03, and FIPS 186-5 identity are correct — 25%
- [ ] `signature_status_matrix`：signature generation is Disallowed and existing-signature verification is Legacy use — 35%
- [ ] `non_signature_condition`：non-signature use is Acceptable only without a collision-resistance requirement — 20%
- [ ] `structured_delivery`：three CSV rows, source locations, two outputs, and publication-copy boundary are correct — 20%

### Judge group

- [ ] `standards_scope_reasoning`：generation, existing verification, and non-signature use are separately grounded in NIST scope — 40%
- [ ] `archive_transition_plan`：the memo stops new SHA-1 signatures while retaining controlled legacy verification with actions — 35%
- [ ] `uncertainty_and_claim_boundary`：Legacy use is not presented as a new-use recommendation or a product-support claim — 25%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import csv
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["publication_identity", "signature_status_matrix", "non_signature_condition", "structured_delivery"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def norm(value):
        return re.sub(r"\s+", " ", str(value or "")).strip().lower()

    def publication_id(value):
        text = norm(value).replace("revision", "rev")
        text = re.sub(r"^nist\s+", "", text)
        return re.sub(r"[^a-z0-9]+", "", text)

    def primary_publication_mentioned(value):
        return bool(re.search(
            r"\b(?:nist\s+)?sp\s*800[- ]131a\s+rev(?:ision)?\.?\s*2\b",
            str(value or ""),
            re.I,
        ))

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        csv_path = root / "results" / "sha1_use_matrix.csv"
        memo_path = root / "results" / "transition_memo.md"
        if not regular(csv_path) or not regular(memo_path):
            raise ValueError("regular result files required")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames
            rows = list(reader)
        memo = memo_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError, TypeError, csv.Error):
        return {**scores, "overall_score": 0.0}

    columns = ["use_case", "nist_status", "conditions", "primary_source", "section_or_table"]
    rows_are_well_formed = all(
        isinstance(row, dict)
        and set(row) == set(columns)
        and None not in row
        and all(value is not None for value in row.values())
        for row in rows
    )
    expected_by_case = {row["use_case"]: row for row in expected["rows"]}
    actual_by_case = {row.get("use_case"): row for row in rows if isinstance(row, dict)}
    memo_lower = memo.lower()
    scores["publication_identity"] = mean([
        primary_publication_mentioned(memo),
        expected["doi"].lower() in memo_lower,
        "2019-03" in memo or "march 2019" in memo_lower,
        "fips 186-5" in memo_lower,
    ])
    generation = actual_by_case.get("digital_signature_generation", {})
    verification = actual_by_case.get("existing_digital_signature_verification", {})
    scores["signature_status_matrix"] = mean([
        generation.get("nist_status") == "Disallowed",
        "protocol-specific guidance" in norm(generation.get("conditions")),
        verification.get("nist_status") == "Legacy use",
        "already" in norm(verification.get("conditions")) and "signature" in norm(verification.get("conditions")),
        publication_id(generation.get("primary_source")) == publication_id(expected["publication"]),
        publication_id(verification.get("primary_source")) == publication_id(expected["publication"]),
    ])
    non_signature = actual_by_case.get("non_digital_signature_use", {})
    scores["non_signature_condition"] = mean([
        non_signature.get("nist_status") == "Acceptable",
        "do not require collision resistance" in norm(non_signature.get("conditions")),
        publication_id(non_signature.get("primary_source")) == publication_id(expected["publication"]),
        "section 9" in norm(non_signature.get("section_or_table")) or "table 8" in norm(non_signature.get("section_or_table")),
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
    scores["structured_delivery"] = mean([
        fieldnames == columns and rows_are_well_formed,
        [row.get("use_case") for row in rows] == [row["use_case"] for row in expected["rows"]],
        len(rows) == 3,
        all(row.get("section_or_table") for row in rows),
        files == expected["result_files"],
        regular(csv_path) and regular(memo_path),
        not forbidden,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.25 * scores["publication_identity"]
        + 0.35 * scores["signature_status_matrix"]
        + 0.20 * scores["non_signature_condition"]
        + 0.20 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/transition_memo.md` against the three fixed NIST records and `sha1_use_matrix.csv`. Do not add an overall-impression criterion. Alternative precise standards language is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Standards-scope reasoning (key: standards_scope_reasoning, weight: 0.40)

Evaluate whether the memo separately reasons about the three SHA-1 use cases in SP 800-131A Rev. 2.

**Score 1.0**: Separately ties signature generation to Disallowed with its protocol-guidance exception, existing-signature verification to Legacy use, and non-signature use to Acceptable only where collision resistance is not required.

**Score 0.75**: All three conclusions are correct, but one secondary condition or source-location link is implicit.

**Score 0.5**: Correctly distinguishes generation from verification but incompletely handles the non-signature condition or one exception.

**Score 0.25**: Gives a broad “allowed” or “disallowed” conclusion while preserving only one or two correct use-case facts.

**Score 0.0**: Says every SHA-1 use has one status, reverses generation and verification status, relies on FIPS 186-5 for the matrix, or omits the analysis.

### Criterion 2: Archive transition plan (key: archive_transition_plan, weight: 0.35)

Evaluate whether the memo turns the standards distinction into bounded archive actions.

**Score 1.0**: Stops creation of new SHA-1 signatures, permits controlled verification of already-generated signatures, identifies migration and validation actions, and preserves records needed for verification without claiming universal product behavior.

**Score 0.75**: The stop/retain distinction and main actions are correct, but one secondary migration, logging, or validation step is missing.

**Score 0.5**: Gives the correct policy direction but lacks an actionable control for either new signing or legacy verification.

**Score 0.25**: Offers only a general recommendation, or would reject all old signatures without an evidence-based exception process.

**Score 0.0**: Recommends new SHA-1 signing, disables all archive verification contrary to the fixed guidance without qualification, or provides no plan.

### Criterion 3: Uncertainty and claim boundary (key: uncertainty_and_claim_boundary, weight: 0.25)

Evaluate whether the memo preserves the publication, protocol, product, and Legacy-use boundaries.

**Score 1.0**: Explains Legacy use as processing already protected information, does not call it approval for new use, preserves the protocol-specific exception wording, and makes no unsupported claim about product support or every protocol.

**Score 0.75**: All core boundaries are respected, with one minor qualification left implicit.

**Score 0.5**: Avoids a false universal claim but leaves Legacy use or the protocol-specific exception materially unclear.

**Score 0.25**: Uses language that could be read as recommending new SHA-1 use or inferring broad product behavior.

**Score 0.0**: Explicitly recommends new SHA-1 signatures, claims all products must behave identically, invents a NIST guarantee, or omits the boundary discussion.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_011_nist_sha1_transition
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

- Auto group weights are 25%, 35%, 20%, and 20%; the group is 40% of the task.
- Judge group weights are 40%, 35%, and 25%; the group is 60% of the task.
