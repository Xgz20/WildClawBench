---
id: 02_Code_Intelligence_task_008_config_migrator
name: 多版本配置安全迁移
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

# 多版本配置安全迁移

## Prompt

客户目录里同时有v1和v2配置，`/tmp_workspace/project/`中给了v3 schema、三个示例、迁移骨架和测试。请补完迁移CLI：支持v1逐级迁移到v3、v2迁移到v3，以及v3重复运行不变化；未知的顶层字段和`service`扩展字段都要保留。

写回前必须完成解析、迁移和完整验证。任何错误或写入中断都不能覆盖原文件或留下半写入的临时文件。保持现有CLI参数和公开函数，只修改`/tmp_workspace/project/migrate.py`，不要修改schema、示例或测试，不联网，也不要创建结果文件。

运行测试：

```bash
cd /tmp_workspace/project
python3 -m unittest -v
```

## Expected Behavior

实现应把v1字段转换为v2结构后再转换为v3，把v2的服务、超时和功能字段转换为v3结构，并让有效v3文档保持语义幂等。未知字段需要深拷贝保留。无效JSON、未知版本或不符合v3要求的结果不得改写源文件。成功写回采用同目录临时文件和原子替换，并清理失败残留。

## Grading Criteria

- [ ] `v1_to_v3_correct`: v1按两级迁移规则生成完整有效的v3配置
- [ ] `v2_idempotence_correct`: v2迁移正确且v3重复运行保持不变
- [ ] `unknown_fields_preserved`: 顶层及嵌套扩展字段完整保留
- [ ] `validation_errors_correct`: 无效输入、未知版本和无效结果被拒绝且不覆盖原文件
- [ ] `atomic_failure_behavior`: 成功写回原子发布，异常时原文件和目录保持完整
- [ ] `tests_scope_delivery`: 公开测试、受保护文件、接口和修改范围保持有效

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import ast
    import hashlib
    import json
    from pathlib import Path
    import subprocess
    import sys

    keys = [
        "v1_to_v3_correct",
        "v2_idempotence_correct",
        "unknown_fields_preserved",
        "validation_errors_correct",
        "atomic_failure_behavior",
        "tests_scope_delivery",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    project = root / "project"
    source = project / "migrate.py"

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
import copy, importlib.util, inspect, json, os, pathlib, sys, tempfile
from unittest import mock
project = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("candidate_migrate", project / "migrate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = {}

v1 = {
    "version": 1,
    "service_name": "billing-api",
    "endpoint": "https://billing.internal",
    "timeout_seconds": 12,
    "features": ["audit", "retry"],
    "customer_extension": {"region": "ap-east"},
}
wanted_v1 = {
    "version": 3,
    "service": {"name": "billing-api", "endpoint": "https://billing.internal"},
    "timeouts": {"request_seconds": 12},
    "features": {"enabled": ["audit", "retry"]},
    "customer_extension": {"region": "ap-east"},
}
v1_before = copy.deepcopy(v1)
try:
    migrated_v1 = module.migrate_document(v1)
    result["v1"] = migrated_v1 == wanted_v1
    result["v1_input"] = v1 == v1_before
except Exception:
    result["v1"] = result["v1_input"] = False

v2 = {
    "version": 2,
    "service": {"name": "search-api", "endpoint": "https://search.internal", "owner": "platform"},
    "request_timeout_seconds": 8,
    "features": ["suggestions"],
    "deployment_hint": "blue",
}
try:
    migrated_v2 = module.migrate_document(v2)
    result["v2"] = (
        migrated_v2.get("version") == 3
        and migrated_v2.get("timeouts") == {"request_seconds": 8}
        and migrated_v2.get("features") == {"enabled": ["suggestions"]}
    )
    result["unknown"] = (
        migrated_v2.get("deployment_hint") == "blue"
        and migrated_v2.get("service", {}).get("owner") == "platform"
    )
    result["idempotent"] = module.migrate_document(migrated_v2) == migrated_v2
except Exception:
    result["v2"] = result["unknown"] = result["idempotent"] = False

invalid_documents = [
    {"version": 99},
    {"version": 1, "service_name": "", "endpoint": "x", "timeout_seconds": 1, "features": []},
    {"version": 3, "service": {"name": "x", "endpoint": "y"}, "timeouts": {"request_seconds": 0}, "features": {"enabled": []}},
]
rejected = []
for document in invalid_documents:
    try:
        module.migrate_document(document)
    except Exception:
        rejected.append(True)
    else:
        rejected.append(False)
result["validation"] = all(rejected)
result["signatures"] = (
    list(inspect.signature(module.migrate_document).parameters) == ["document"]
    and list(inspect.signature(module.migrate_file).parameters) == ["config_path", "schema_path"]
)

with tempfile.TemporaryDirectory() as temporary:
    directory = pathlib.Path(temporary)
    config = directory / "config.json"
    config.write_text(json.dumps(v1), encoding="utf-8")
    try:
        module.migrate_file(config, project / "schema_v3.json")
        result["file_success"] = json.loads(config.read_text(encoding="utf-8")) == wanted_v1
        result["success_clean"] = sorted(path.name for path in directory.iterdir()) == ["config.json"]
    except Exception:
        result["file_success"] = result["success_clean"] = False

with tempfile.TemporaryDirectory() as temporary:
    directory = pathlib.Path(temporary)
    config = directory / "config.json"
    config.write_text(json.dumps(v1), encoding="utf-8")
    before = config.read_bytes()
    try:
        with mock.patch("os.replace", side_effect=OSError("simulated interruption")):
            module.migrate_file(config, project / "schema_v3.json")
    except OSError:
        result["crash_raised"] = True
    except Exception:
        result["crash_raised"] = False
    else:
        result["crash_raised"] = False
    result["crash_preserved"] = config.read_bytes() == before
    result["crash_clean"] = sorted(path.name for path in directory.iterdir()) == ["config.json"]

print("__RESULT__" + json.dumps(result, sort_keys=True))
'''
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", driver, str(project)],
            text=True,
            capture_output=True,
            timeout=15,
        )
        marker = next(
            line[len("__RESULT__") :]
            for line in reversed(completed.stdout.splitlines())
            if line.startswith("__RESULT__")
        )
        hidden = json.loads(marker) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError):
        hidden = {}

    scores["v1_to_v3_correct"] = sum(
        bool(hidden.get(name)) for name in ("v1", "v1_input")
    ) / 2.0
    scores["v2_idempotence_correct"] = sum(
        bool(hidden.get(name)) for name in ("v2", "idempotent")
    ) / 2.0
    scores["unknown_fields_preserved"] = float(bool(hidden.get("unknown")))
    scores["validation_errors_correct"] = sum(
        bool(hidden.get(name)) for name in ("validation", "crash_preserved")
    ) / 2.0

    try:
        source_text = source.read_text(encoding="utf-8")
        atomic_static = (
            ("replace" in source_text)
            and any(token in source_text for token in ("mkstemp", "NamedTemporaryFile", "TemporaryFile"))
        )
    except (OSError, UnicodeError):
        atomic_static = False
    atomic_flags = [
        hidden.get("file_success"),
        hidden.get("success_clean"),
        hidden.get("crash_raised"),
        hidden.get("crash_preserved"),
        hidden.get("crash_clean"),
        atomic_static,
    ]
    scores["atomic_failure_behavior"] = sum(bool(flag) for flag in atomic_flags) / len(atomic_flags)

    try:
        public = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=project,
            text=True,
            capture_output=True,
            timeout=20,
        )
        files = sorted(
            path.relative_to(project).as_posix()
            for path in project.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
        delivery_flags = [
            public.returncode == 0,
            protected_ok,
            files == sorted(expected["allowed_project_files"]),
            bool(hidden.get("signatures")),
        ]
        scores["tests_scope_delivery"] = sum(delivery_flags) / len(delivery_flags)
    except (OSError, subprocess.SubprocessError):
        pass
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_008_config_migrator
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

- v3 schema只作为固定本地输入，不需要第三方JSON Schema库。
- 无结果附件要求，修改后的源码即交付内容。
