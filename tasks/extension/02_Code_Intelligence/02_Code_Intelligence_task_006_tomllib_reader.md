---
id: 02_Code_Intelligence_task_006_tomllib_reader
name: Python项目元数据读取器
category: 02_Code_Intelligence
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
grading_weights:
  automated: 1.0
  llm_judge: 0.0
tags:
  - custom
---

# Python项目元数据读取器

## Prompt

我们需要一个只用Python 3.12标准库的`pyproject.toml`元数据读取器。请先核对Python 3.12官方文档里的`tomllib`页面：

<https://docs.python.org/3.12/library/tomllib.html>

然后创建`/tmp_workspace/results/pyproject_reader.py`，提供`read_project_metadata(path)`，返回字段`name`、可为空的`version`和按原顺序保留的`dependencies`。命令行运行方式为`python3 pyproject_reader.py PATH`，成功时向stdout输出UTF-8 JSON。

缺文件、无效TOML、缺失或无效的`project.name`分别使用退出码2、3、4，并把清晰的原因写入stderr。另生成`/tmp_workspace/results/source.json`，字段严格为`url,version`，记录上面的固定地址和Python文档版本。不要安装第三方包、保存网页或创建其他结果文件。

## Expected Behavior

读取器应使用标准库`tomllib`以二进制方式读取TOML，准确返回项目名、可缺省的版本和保持顺序的依赖列表。API与CLI应处理完整和可选元数据，并按约定区分三类错误。来源记录必须指向指定的Python 3.12官方文档页面，结果目录只包含两个请求文件。

## Grading Criteria

- [ ] `fixed_source_identity`: 固定URL和Python文档版本完全正确
- [ ] `valid_metadata_api`: 函数接口及完整、缺省元数据读取正确
- [ ] `error_contract_correct`: 三类错误使用规定退出码并输出原因
- [ ] `cli_json_correct`: CLI成功输出字段准确的UTF-8 JSON
- [ ] `stdlib_scope_only`: 实现仅导入Python标准库模块
- [ ] `source_delivery_correct`: 结果文件范围、结构和文件类型正确，未保存网页副本

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import ast
    import json
    from pathlib import Path
    import subprocess
    import sys
    import tempfile

    keys = [
        "fixed_source_identity",
        "valid_metadata_api",
        "error_contract_correct",
        "cli_json_correct",
        "stdlib_scope_only",
        "source_delivery_correct",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    results = root / "results"
    reader_path = results / "pyproject_reader.py"
    source_path = results / "source.json"

    def regular(path):
        try:
            return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        except OSError:
            return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores

    try:
        delivered_source = json.loads(source_path.read_text(encoding="utf-8"))
        source_flags = [
            isinstance(delivered_source, dict),
            set(delivered_source) == {"url", "version"},
            delivered_source.get("url") == expected["source"]["url"],
            delivered_source.get("version") == expected["source"]["version"],
        ]
        scores["fixed_source_identity"] = sum(source_flags) / len(source_flags)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        pass
    if not regular(reader_path):
        return scores

    driver = r'''
import importlib.util, inspect, json, pathlib, sys, tempfile
source = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("candidate_reader", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = {}
with tempfile.TemporaryDirectory() as temporary:
    directory = pathlib.Path(temporary)
    complete = directory / "complete.toml"
    complete.write_text("""[project]\nname = "sample-service"\nversion = "2.4.1"\ndependencies = ["httpx>=0.27", "orjson; python_version >= '3.12'"]\n""", encoding="utf-8")
    minimal = directory / "minimal.toml"
    minimal.write_text("""[project]\nname = "minimal-service"\n""", encoding="utf-8")
    try:
        result["complete"] = module.read_project_metadata(complete)
        result["minimal"] = module.read_project_metadata(minimal)
    except Exception as exc:
        result["api_error"] = type(exc).__name__
result["signature"] = list(inspect.signature(module.read_project_metadata).parameters) == ["path"]
print("__RESULT__" + json.dumps(result, sort_keys=True))
'''
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", driver, str(reader_path)],
            text=True,
            capture_output=True,
            timeout=10,
        )
        marker = next(
            line[len("__RESULT__") :]
            for line in reversed(completed.stdout.splitlines())
            if line.startswith("__RESULT__")
        )
        api = json.loads(marker) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError):
        api = {}
    api_flags = [
        api.get("complete") == expected.get("valid_metadata"),
        api.get("minimal")
        == {"name": "minimal-service", "version": None, "dependencies": []},
        bool(api.get("signature")),
    ]
    scores["valid_metadata_api"] = sum(api_flags) / len(api_flags)

    with tempfile.TemporaryDirectory(prefix="tomllib-grade-") as temporary:
        directory = Path(temporary)
        valid = directory / "valid.toml"
        invalid = directory / "invalid.toml"
        missing_name = directory / "missing-name.toml"
        valid.write_text(
            '[project]\nname = "sample-service"\nversion = "2.4.1"\n'
            'dependencies = ["httpx>=0.27", "orjson; python_version >= \'3.12\'"]\n',
            encoding="utf-8",
        )
        invalid.write_text("[project\nname = broken\n", encoding="utf-8")
        missing_name.write_text('[project]\nversion = "1.0"\n', encoding="utf-8")

        def run(path):
            try:
                return subprocess.run(
                    [sys.executable, str(reader_path), str(path)],
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                return None

        missing = run(directory / "absent.toml")
        malformed = run(invalid)
        no_name = run(missing_name)
        success = run(valid)
        error_flags = [
            missing is not None and missing.returncode == 2 and bool(missing.stderr.strip()),
            malformed is not None and malformed.returncode == 3 and bool(malformed.stderr.strip()),
            no_name is not None and no_name.returncode == 4 and bool(no_name.stderr.strip()),
        ]
        scores["error_contract_correct"] = sum(error_flags) / len(error_flags)
        try:
            stdout_data = json.loads(success.stdout) if success and success.returncode == 0 else None
        except json.JSONDecodeError:
            stdout_data = None
        cli_flags = [
            success is not None and success.returncode == 0,
            stdout_data == expected.get("valid_metadata"),
            success is not None and not success.stderr.strip(),
        ]
        scores["cli_json_correct"] = sum(cli_flags) / len(cli_flags)

    try:
        source_text = reader_path.read_text(encoding="utf-8")
        tree = ast.parse(source_text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        stdlib = set(getattr(sys, "stdlib_module_names", ())) | {
            "argparse", "json", "pathlib", "sys", "tomllib"
        }
        scope_flags = [
            imported <= stdlib,
            "tomllib" in imported,
            not ({"pip", "requests", "toml", "tomli"} & imported),
        ]
        scores["stdlib_scope_only"] = sum(scope_flags) / len(scope_flags)
    except (OSError, UnicodeError, SyntaxError):
        pass

    try:
        result_files = sorted(
            path.name for path in results.iterdir() if path.is_file() or path.is_symlink()
        )
        compile(reader_path.read_text(encoding="utf-8"), str(reader_path), "exec")
        delivery_flags = [
            result_files == expected["result_files"],
            regular(reader_path),
            regular(source_path),
            not any(path.suffix.lower() in {".html", ".htm", ".pdf"} for path in results.iterdir()),
        ]
        scores["source_delivery_correct"] = sum(delivery_flags) / len(delivery_flags)
    except (OSError, UnicodeError, SyntaxError, KeyError):
        pass
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_006_tomllib_reader
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

- 实时网络仅用于读取指定Python 3.12官方文档页面，不保存网页副本。
- 运行结果只允许写入`/tmp_workspace/results/`。
