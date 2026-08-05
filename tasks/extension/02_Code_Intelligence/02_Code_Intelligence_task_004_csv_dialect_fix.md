---
id: 02_Code_Intelligence_task_004_csv_dialect_fix
name: 修复Windows CSV边界解析
category: 02_Code_Intelligence
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
grading_weights:
  automated: 1.0
  llm_judge: 0.0
tags:
  - custom
---

# 修复Windows CSV边界解析

## Prompt

`/tmp_workspace/project/csv_parser.py`解析Windows导出的CSV时，会在带逗号、转义双引号和字段内CRLF的记录上错行，也会丢掉全空行或末尾空字段。请修复解析器，保持`parse_csv(text)`的输入输出接口；未加引号的字段中间出现引号时不得错误进入quoted模式。

只修改`/tmp_workspace/project/csv_parser.py`，不要修改测试，不联网，也不要创建结果文件。完成后运行：

```bash
cd /tmp_workspace/project
python3 -m unittest -v
```

## Expected Behavior

解析器应按CSV记录边界处理CRLF，保留引号字段内部的原始CRLF，正确解析逗号、转义双引号、空记录和末尾空字段。位于未加引号字段中间的双引号应作为普通字符，不得改变后续逗号的分隔语义。函数签名、返回类型、测试和修改范围保持不变。

## Grading Criteria

- [ ] `quoted_escaped_fields`: 带逗号的引号字段和双引号转义解析正确
- [ ] `crlf_multiline_fields`: Windows CRLF记录边界和字段内CRLF均正确
- [ ] `empty_trailing_fields`: 空记录、连续空字段和末尾空字段不丢失
- [ ] `invalid_quote_behavior`: 未加引号字段中间的双引号按普通字符处理
- [ ] `public_tests_passed`: 原有单元测试保持不变并通过
- [ ] `scope_api_preserved`: 只修改允许的源码并保留公开函数接口

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path
    import subprocess
    import sys

    keys = [
        "quoted_escaped_fields",
        "crlf_multiline_fields",
        "empty_trailing_fields",
        "invalid_quote_behavior",
        "public_tests_passed",
        "scope_api_preserved",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    project = root / "project"
    source = project / "csv_parser.py"

    def regular(path):
        try:
            return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        except OSError:
            return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        protected_ok = all(
            regular(root / relative)
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in expected["protected_file_sha256"].items()
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores
    if not regular(source):
        return scores

    driver = r'''
import importlib.util, inspect, json, pathlib, sys
project = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("candidate_csv", project / "csv_parser.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
cases = {
    "quoted": (
        'name,note\r\nA,"hello, world"\r\nB,"He said ""hi"""\r\n',
        [["name", "note"], ["A", "hello, world"], ["B", 'He said "hi"']],
    ),
    "quoted_empty": ('"",plain,"a,b"\r\n', [["", "plain", "a,b"]]),
    "multiline": (
        'id,note\r\n1,"line one\r\nline two"\r\n2,end\r\n',
        [["id", "note"], ["1", "line one\r\nline two"], ["2", "end"]],
    ),
    "empty": ("a,b,\r\n\r\nc,,\r\n", [["a", "b", ""], [], ["c", "", ""]]),
    "trailing": (",,\r\nlast,value,", [["", "", ""], ["last", "value", ""]]),
    "literal_quote": ('ab"cd",x\r\n', [['ab"cd"', "x"]]),
    "literal_quote_comma": ('left"quote,right\r\n', [['left"quote', "right"]]),
}
result = {}
for name, (text, wanted) in cases.items():
    try:
        result[name] = module.parse_csv(text) == wanted
    except Exception:
        result[name] = False
result["signature"] = list(inspect.signature(module.parse_csv).parameters) == ["text"]
print("__RESULT__" + json.dumps(result, sort_keys=True))
'''
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", driver, str(project)],
            text=True,
            capture_output=True,
            timeout=10,
        )
        marker = next(
            line[len("__RESULT__") :]
            for line in reversed(completed.stdout.splitlines())
            if line.startswith("__RESULT__")
        )
        hidden = json.loads(marker) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError):
        hidden = {}

    scores["quoted_escaped_fields"] = sum(
        bool(hidden.get(name)) for name in ("quoted", "quoted_empty")
    ) / 2.0
    scores["crlf_multiline_fields"] = float(bool(hidden.get("multiline")))
    scores["empty_trailing_fields"] = sum(
        bool(hidden.get(name)) for name in ("empty", "trailing")
    ) / 2.0
    scores["invalid_quote_behavior"] = sum(
        bool(hidden.get(name)) for name in ("literal_quote", "literal_quote_comma")
    ) / 2.0

    try:
        public = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=project,
            text=True,
            capture_output=True,
            timeout=15,
        )
        scores["public_tests_passed"] = float(public.returncode == 0)
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        files = sorted(
            path.relative_to(project).as_posix()
            for path in project.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
        scope_flags = [
            protected_ok,
            files == sorted(expected["allowed_project_files"]),
            bool(hidden.get("signature")),
        ]
        scores["scope_api_preserved"] = sum(scope_flags) / len(scope_flags)
    except OSError:
        pass
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_004_csv_dialect_fix
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

- 输入项目仅使用Python标准库。
- 无结果附件要求，修改后的源码即交付内容。
