---
id: 04_Search_Retrieval_task_010_node_statfs_release_trace
name: Node.js statfs feature release trace
category: 04_Search_Retrieval
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3
tags:
  - custom
---

# Node.js statfs feature release trace

## Prompt

I’m documenting how Node.js added `statfs`. Trace the feature from the original stalled pull request through the merged replacement and the first Current and LTS releases. Use only these fixed records:

- https://api.github.com/repos/nodejs/node/pulls/31351
- https://api.github.com/repos/nodejs/node/pulls/46358
- https://api.github.com/repos/nodejs/node/commits/f145766011a9b600ff7c4fea043f435f70f6d0bf
- https://nodejs.org/en/blog/release/v19.6.0
- https://nodejs.org/en/blog/release/v18.15.0

Save `/tmp_workspace/results/statfs_timeline.csv` with exactly `date,event,identifier,evidence_url`. Use these event codes in order: `original_pr_opened,replacement_pr_merged,merge_commit,current_release,lts_release`. Normalize GitHub event timestamps to calendar dates in `Asia/Shanghai`, and use release dates printed in the fixed Node.js release pages.

Then write `/tmp_workspace/results/statfs_trace.md` listing `fs.statfs()`, `fs.statfsSync()`, and `fsPromises.statfs()` and explaining the relationship among both PRs, the merge commit, the Current release, and the LTS backport. Do not save webpage copies, infer dates from a mutable branch, use other sources, or create other result files.

## Expected Behavior

Agent should trace PR #31351 from its 2020-01-14 opening and stalled closure to replacement PR #46358, merged on 2023-01-30 in the requested timezone; identify merge commit `f145766011a9b600ff7c4fea043f435f70f6d0bf`; and record v19.6.0 on 2023-02-02 and v18.15.0 on 2023-03-07. The explanation should list all three public APIs and distinguish the Current release from the LTS backport.

## Grading Criteria

### Automated group

- [ ] `source_chain_identity`：two PRs, merge commit, and two fixed-tag changelogs are complete — 20%
- [ ] `pull_request_timeline`：original PR opening/stalled closure and replacement merge are correct — 25%
- [ ] `api_names`：all three public API names are present — 20%
- [ ] `release_versions_and_dates`：Current and LTS release versions and dates are correct — 25%
- [ ] `structured_delivery`：CSV columns/order, two outputs, and snapshot boundary are correct — 10%

### Judge group

- [ ] `trace_explanation`：the original PR, replacement, merge commit, and two release lines form a supported trace — 100%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import csv
    import json
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = [
        "source_chain_identity", "pull_request_timeline", "api_names",
        "release_versions_and_dates", "structured_delivery",
    ]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        csv_path = root / "results" / "statfs_timeline.csv"
        trace_path = root / "results" / "statfs_trace.md"
        if not regular(csv_path) or not regular(trace_path):
            raise ValueError("regular result files required")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames
            rows = list(reader)
        trace = trace_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError, TypeError, csv.Error):
        return {**scores, "overall_score": 0.0}

    columns = ["date", "event", "identifier", "evidence_url"]
    expected_by_event = {row["event"]: row for row in expected["rows"]}
    actual_by_event = {row.get("event"): row for row in rows if isinstance(row, dict)}
    scores["source_chain_identity"] = mean([
        set(row.get("evidence_url") for row in rows) == set(expected["source_urls"]),
        actual_by_event.get("original_pr_opened", {}).get("identifier") == "PR #31351",
        actual_by_event.get("replacement_pr_merged", {}).get("identifier") == "PR #46358",
        actual_by_event.get("merge_commit", {}).get("identifier") == "f145766011a9b600ff7c4fea043f435f70f6d0bf",
        actual_by_event.get("current_release", {}).get("identifier") == "v19.6.0",
        actual_by_event.get("lts_release", {}).get("identifier") == "v18.15.0",
    ])
    trace_lower = trace.lower()
    scores["pull_request_timeline"] = mean([
        actual_by_event.get("original_pr_opened", {}).get("date") == "2020-01-14",
        actual_by_event.get("replacement_pr_merged", {}).get("date") == "2023-01-30",
        "#31351" in trace and ("stalled" in trace_lower or "stale" in trace_lower),
        "#31351" in trace and "closed" in trace_lower,
        "#46358" in trace and ("replacement" in trace_lower or "revival" in trace_lower),
    ])
    scores["api_names"] = mean([name in trace for name in expected["api_names"]])
    scores["release_versions_and_dates"] = mean([
        actual_by_event.get("current_release", {}).get("date") == expected_by_event["current_release"]["date"],
        actual_by_event.get("current_release", {}).get("identifier") == expected_by_event["current_release"]["identifier"],
        actual_by_event.get("lts_release", {}).get("date") == expected_by_event["lts_release"]["date"],
        actual_by_event.get("lts_release", {}).get("identifier") == expected_by_event["lts_release"]["identifier"],
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
        fieldnames == columns,
        [row.get("event") for row in rows] == [row["event"] for row in expected["rows"]],
        len(rows) == 5,
        all(row.get(key) == wanted[key] for row, wanted in zip(rows, expected["rows"]) for key in columns),
        files == expected["result_files"],
        regular(csv_path) and regular(trace_path),
        not forbidden,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.20 * scores["source_chain_identity"]
        + 0.25 * scores["pull_request_timeline"]
        + 0.20 * scores["api_names"]
        + 0.25 * scores["release_versions_and_dates"]
        + 0.10 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/statfs_trace.md` against the five fixed records and `statfs_timeline.csv`. Do not add an overall-impression criterion. Equivalent precise technical wording is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Trace explanation (key: trace_explanation, weight: 1.00)

Evaluate whether the narrative forms a complete, source-bounded feature trace.

**Score 1.0**: Explains that #31351 was the original stalled and closed proposal, #46358 revived and replaced it, the fixed full commit merged the implementation, v19.6.0 first shipped it on Current, and v18.15.0 carried the LTS backport; all three APIs and date roles are accurate.

**Score 0.75**: The full chain and API set are correct, but one secondary date, status detail, or Current/LTS explanation is incomplete.

**Score 0.5**: Connects the replacement PR, commit, and releases but omits or materially underexplains one stage such as the original PR or LTS backport.

**Score 0.25**: Lists several records without a reliable relationship, confuses Current and LTS, or treats the original PR as the merged implementation.

**Score 0.0**: Gives a materially false trace, uses a mutable or unapproved source as authority, invents an API or release, or omits the narrative.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_010_node_statfs_release_trace
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

- Auto group weights are 20%, 25%, 20%, 25%, and 10%; the group is 70% of the task.
- Judge has one checkpoint and is 30% of the task.
- GitHub timestamps are normalized to `Asia/Shanghai` so the expected calendar date is backend-independent.
