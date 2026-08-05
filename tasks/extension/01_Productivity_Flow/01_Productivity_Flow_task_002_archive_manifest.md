---
id: 01_Productivity_Flow_task_002_archive_manifest
name: 票据归档与校验清单
category: 01_Productivity_Flow
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - custom
---
## Prompt

`/tmp_workspace/inbox.zip.b64`是一个经过Base64编码的ZIP，其中包含3个票据文本文件。`/tmp_workspace/rename_map.csv`给出了每个源文件的归档文件名。

请解码并解压ZIP，在不改变文件字节的前提下完成重命名，并将文件直接保存到 `/tmp_workspace/results/archive/`。同时将 `/tmp_workspace/results/manifest.json` 保存为以下格式：

```json
{
  "file_count": 3,
  "files": [
    {
      "source_name": "scan_001.txt",
      "archive_name": "重命名后的文件",
      "sha256": "小写SHA-256",
      "size_bytes": 0
    }
  ]
}
```

`files`的顺序必须与`rename_map.csv`一致。`sha256`和`size_bytes`必须描述最终归档文件。不要访问网络，不要修改两个输入文件。

## Expected Behavior

Agent应解码和解压给定归档，应用3项重命名映射并保持文件内容不变，计算校验值和大小，最后生成指定目录结构与清单。

## Grading Criteria

- [ ] 所有归档文件保持预期字节 — 25%
- [ ] 清单中的SHA-256正确 — 18%
- [ ] 输出目录仅包含要求的文件 — 30%
- [ ] 清单结构、顺序、名称、大小和数量正确 — 27%

前两个检查点映射到`tool_use`，后两个映射到`verification_delivery`。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path

    keys = [
        "archive_contents_correct",
        "manifest_hashes_correct",
        "output_layout_correct",
        "manifest_delivery_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    workspace = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    results = workspace / "results"
    archive_dir = results / "archive"
    manifest_path = results / "manifest.json"
    expected_path = workspace / "gt" / "expected_manifest.json"

    if (
        results.is_symlink()
        or archive_dir.is_symlink()
        or manifest_path.is_symlink()
        or not expected_path.is_file()
    ):
        return scores
    try:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores
    expected_files = expected.get("files")
    if not isinstance(expected_files, list) or not expected_files:
        return scores

    for relative, expected_hash in expected.get("exec_file_sha256", {}).items():
        input_path = workspace / relative
        try:
            if (
                input_path.is_symlink()
                or not input_path.is_file()
                or hashlib.sha256(input_path.read_bytes()).hexdigest() != expected_hash
            ):
                return scores
        except OSError:
            return scores

    def sha256(path):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    content_hits = 0
    for item in expected_files:
        path = archive_dir / str(item.get("archive_name", ""))
        try:
            content_hits += int(
                path.is_file()
                and not path.is_symlink()
                and sha256(path) == item["sha256"]
            )
        except (OSError, KeyError):
            pass
    scores["archive_contents_correct"] = content_hits / len(expected_files)

    manifest = None
    if manifest_path.is_file():
        try:
            parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                manifest = parsed
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass

    manifest_files = manifest.get("files") if isinstance(manifest, dict) else None
    if isinstance(manifest_files, list):
        by_name = {
            item.get("archive_name"): item
            for item in manifest_files
            if isinstance(item, dict) and isinstance(item.get("archive_name"), str)
        }
        hash_hits = sum(
            1
            for exp in expected_files
            if by_name.get(exp["archive_name"], {}).get("sha256") == exp["sha256"]
        )
        scores["manifest_hashes_correct"] = hash_hits / len(expected_files)

    expected_layout = {"manifest.json"} | {
        f"archive/{item['archive_name']}" for item in expected_files
    }
    try:
        actual_layout = {
            path.relative_to(results).as_posix()
            for path in results.rglob("*")
            if path.is_file()
        }
    except OSError:
        actual_layout = set()
    scores["output_layout_correct"] = float(actual_layout == expected_layout)
    if any(path.is_symlink() for path in results.rglob("*")):
        scores["output_layout_correct"] = 0.0

    if isinstance(manifest, dict) and isinstance(manifest_files, list):
        checks = [manifest.get("file_count") == expected.get("file_count")]
        checks.append(len(manifest_files) == len(expected_files))
        for index, exp in enumerate(expected_files):
            got = manifest_files[index] if index < len(manifest_files) else {}
            checks.extend(
                [
                    isinstance(got, dict) and got.get("source_name") == exp["source_name"],
                    isinstance(got, dict) and got.get("archive_name") == exp["archive_name"],
                    isinstance(got, dict) and got.get("size_bytes") == exp["size_bytes"],
                ]
            )
        scores["manifest_delivery_correct"] = sum(checks) / len(checks)

    scores["overall_score"] = round(
        0.25 * scores["archive_contents_correct"]
        + 0.18 * scores["manifest_hashes_correct"]
        + 0.30 * scores["output_layout_correct"]
        + 0.27 * scores["manifest_delivery_correct"],
        6,
    )
    return scores
```

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_002_archive_manifest
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
