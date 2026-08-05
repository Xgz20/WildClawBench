---
id: 02_Code_Intelligence_task_009_safe_archive_extract
name: Harden plugin ZIP extraction
category: 02_Code_Intelligence
timeout_seconds: 600
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

# Harden plugin ZIP extraction

## Prompt

Please harden `/tmp_workspace/project/extractor.py`, which installs plugin ZIP bundles. Reject POSIX and Windows path traversal, absolute paths, archive symlinks, pre-existing symlink path components, normalized-name collisions, and bundles that exceed the provided entry-count or uncompressed-size limits. Extraction must be staged so a malformed bundle leaves no partial installation.

Preserve valid bundle behavior, `ExtractionError`, and the existing `extract_plugin()` signature. The destination is a new installation directory and must remain absent after any rejection. Modify only `/tmp_workspace/project/extractor.py`; do not modify the tests. Run the tests, then add `/tmp_workspace/results/SECURITY_NOTES.md` explaining the rejection policy and any remaining assumptions. Do not execute anything from the test archives or use the network.

You can run the public tests with:

```bash
cd /tmp_workspace/project
python3 -m unittest discover -s . -p 'test_*.py'
```

## Expected Behavior

The Agent should inspect the vulnerable implementation and public tests, preserve the documented API, and implement validation before extraction. The implementation should normalize both slash styles, reject unsafe or ambiguous members and symbolic links, enforce both resource limits, extract only into a sibling staging directory, and publish the destination only after all members are written successfully. It should leave the destination absent and remove staging data after any failure. Only `extractor.py` and the requested result note may change.

## Grading Criteria

### Automated criteria

- [ ] `path_traversal_blocked`: POSIX, backslash, absolute, drive-qualified, and UNC paths are rejected
- [ ] `symlink_collision_blocked`: archive symlinks, existing symlink components, and normalized-name collisions are rejected
- [ ] `limits_malformed_archives`: entry count, expanded-size limits, invalid limits, and malformed ZIP input are rejected
- [ ] `atomic_no_partial_delivery`: mixed-validity and over-limit bundles leave no destination or staging residue
- [ ] `valid_bundles_api_preserved`: valid nested bundles, bytes, return values, exception type, signature, tests, and source scope are preserved

### LLM criterion

- [ ] `security_notes_quality`: `SECURITY_NOTES.md` accurately documents the implemented rejection policy, atomic behavior, and remaining assumptions

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import sys
    import tempfile
    import textwrap

    keys = [
        "path_traversal_blocked",
        "symlink_collision_blocked",
        "limits_malformed_archives",
        "atomic_no_partial_delivery",
        "valid_bundles_api_preserved",
    ]
    scores = {key: 0.0 for key in keys}
    workspace = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    project = workspace / "project"
    source = project / "extractor.py"
    public_test = project / "test_extractor.py"
    expected_path = workspace / "gt" / "expected.json"

    def is_regular_delivery(path):
        try:
            root = workspace.resolve(strict=True)
            resolved = path.resolve(strict=True)
            relative = path.relative_to(workspace)
            cursor = workspace
            for part in relative.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    return False
            return root in resolved.parents and path.is_file()
        except (OSError, RuntimeError, ValueError):
            return False

    if not is_regular_delivery(source) or not expected_path.is_file():
        return scores
    try:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        hashes = expected.get("exec_file_sha256")
        if (
            not isinstance(hashes, dict)
            or set(hashes) != {"project/extractor.py", "project/test_extractor.py"}
            or any(
                not isinstance(value, str) or len(value) != 64
                for value in hashes.values()
            )
            or source.stat().st_size > 131072
        ):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores

    test_hash_ok = False
    if is_regular_delivery(public_test):
        try:
            test_hash_ok = (
                hashlib.sha256(public_test.read_bytes()).hexdigest()
                == hashes["project/test_extractor.py"]
            )
        except OSError:
            pass

    allowed_files = {source.resolve(), public_test.resolve() if public_test.exists() else public_test}
    unexpected_files = []
    if project.is_dir():
        for path in project.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            try:
                if path.resolve() not in allowed_files:
                    unexpected_files.append(path)
            except OSError:
                unexpected_files.append(path)
    scope_ok = test_hash_ok and not unexpected_files

    driver = textwrap.dedent(r'''
        import importlib.util
        import inspect
        import json
        import os
        from pathlib import Path
        import stat
        import tempfile
        import zipfile

        def blank_result():
            return {
                "path": [False] * 7,
                "symlink_collision": [False] * 5,
                "limits": [False] * 5,
                "atomic": [False] * 3,
                "valid": [False] * 3,
                "api": False,
            }

        result = blank_result()
        try:
            module_path = Path(__file__).with_name("extractor.py")
            spec = importlib.util.spec_from_file_location("candidate_extractor", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            extract_plugin = module.extract_plugin
            extraction_error = module.ExtractionError
        except BaseException:
            print(json.dumps(result))
            raise SystemExit(0)

        def snapshot(root):
            state = []
            for current, directories, files in os.walk(root, followlinks=False):
                current_path = Path(current)
                for name in sorted(directories + files):
                    path = current_path / name
                    relative = path.relative_to(root).as_posix()
                    if path.is_symlink():
                        state.append((relative, "link", os.readlink(path)))
                    elif path.is_file():
                        state.append((relative, "file", path.read_bytes().hex()))
                    else:
                        state.append((relative, "dir", ""))
            return state

        def make_bundle(path, entries):
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
                for entry in entries:
                    name, data, kind = entry
                    if kind == "symlink":
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        bundle.writestr(info, data)
                    elif kind == "directory":
                        info = zipfile.ZipInfo(name.rstrip("/") + "/")
                        info.external_attr = (stat.S_IFDIR | 0o755) << 16
                        bundle.writestr(info, b"")
                    else:
                        bundle.writestr(name, data)

        def invoke(bundle, destination, **limits):
            try:
                value = extract_plugin(bundle, destination, **limits)
                return True, value, None
            except BaseException as exc:
                return False, None, exc

        def rejected_unchanged(entries, **limits):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                bundle = root / "bundle.zip"
                make_bundle(bundle, entries)
                destination = root / "installed"
                before = snapshot(root)
                ok, _, error = invoke(bundle, destination, **limits)
                after = snapshot(root)
                return (
                    not ok
                    and isinstance(error, extraction_error)
                    and before == after
                    and not destination.exists()
                    and not destination.is_symlink()
                )

        path_names = [
            "../escaped.txt",
            "safe/../../escaped.txt",
            "/absolute.txt",
            "C:/temp/evil.txt",
            r"C:\temp\evil.txt",
            r"\\server\share\evil.txt",
            r"safe\..\evil.txt",
        ]
        result["path"] = [
            rejected_unchanged([(name, b"unsafe", "file")])
            for name in path_names
        ]

        result["symlink_collision"][0] = rejected_unchanged(
            [("plugin-link", b"target.txt", "symlink")]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            link = root / "linked"
            link.symlink_to(real, target_is_directory=True)
            bundle = root / "bundle.zip"
            make_bundle(bundle, [("plugin.txt", b"ok", "file")])
            destination = link / "installed"
            before = snapshot(root)
            ok, _, error = invoke(bundle, destination)
            result["symlink_collision"][1] = (
                not ok
                and isinstance(error, extraction_error)
                and before == snapshot(root)
                and not (real / "installed").exists()
            )
        collision_sets = [
            [("pkg/a.txt", b"1", "file"), ("pkg/./a.txt", b"2", "file")],
            [(r"pkg\b.txt", b"1", "file"), ("pkg/b.txt", b"2", "file")],
            [("Readme.txt", b"1", "file"), ("README.txt", b"2", "file")],
        ]
        for index, entries in enumerate(collision_sets, start=2):
            result["symlink_collision"][index] = rejected_unchanged(entries)

        result["limits"][0] = rejected_unchanged(
            [("a", b"a", "file"), ("b", b"b", "file")],
            max_entries=1,
        )
        result["limits"][1] = rejected_unchanged(
            [("large.bin", b"x" * 32, "file")],
            max_uncompressed_bytes=16,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "broken.zip"
            bundle.write_bytes(b"not a zip file")
            destination = root / "installed"
            before = snapshot(root)
            ok, _, error = invoke(bundle, destination)
            result["limits"][2] = (
                not ok
                and isinstance(error, extraction_error)
                and before == snapshot(root)
            )
        result["limits"][3] = rejected_unchanged(
            [("a", b"a", "file")], max_entries=0
        )
        result["limits"][4] = rejected_unchanged(
            [("a", b"a", "file")], max_uncompressed_bytes=0
        )

        result["atomic"][0] = rejected_unchanged(
            [("good.txt", b"good", "file"), ("../bad.txt", b"bad", "file")]
        )
        result["atomic"][1] = rejected_unchanged(
            [("good.txt", b"good", "file"), ("bad-link", b"good.txt", "symlink")]
        )
        result["atomic"][2] = rejected_unchanged(
            [("first.txt", b"1234", "file"), ("second.txt", b"5678", "file")],
            max_uncompressed_bytes=7,
        )

        valid_cases = [
            [
                ("plugin.json", b'{"name":"demo"}\n', "file"),
                ("src/main.py", b"VALUE = 7\n", "file"),
            ],
            [
                ("assets", b"", "directory"),
                ("assets/read me.txt", b"hello", "file"),
                ("文档/说明.txt", "安全".encode("utf-8"), "file"),
            ],
            [],
        ]
        for index, entries in enumerate(valid_cases):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                bundle = root / "bundle.zip"
                make_bundle(bundle, entries)
                destination = root / "installed"
                ok, value, error = invoke(bundle, destination)
                expected_files = sorted(
                    name.replace("\\", "/")
                    for name, _, kind in entries
                    if kind == "file"
                )
                bytes_ok = all(
                    (destination / Path(name.replace("\\", "/"))).read_bytes() == data
                    for name, data, kind in entries
                    if kind == "file"
                ) if destination.is_dir() else False
                result["valid"][index] = (
                    ok
                    and error is None
                    and value == expected_files
                    and destination.is_dir()
                    and bytes_ok
                )

        try:
            signature = inspect.signature(extract_plugin)
            parameters = list(signature.parameters.values())
            result["api"] = (
                isinstance(extraction_error, type)
                and issubclass(extraction_error, ValueError)
                and [parameter.name for parameter in parameters]
                == [
                    "archive_path",
                    "install_dir",
                    "max_entries",
                    "max_uncompressed_bytes",
                ]
                and parameters[2].kind is inspect.Parameter.KEYWORD_ONLY
                and parameters[3].kind is inspect.Parameter.KEYWORD_ONLY
            )
        except BaseException:
            result["api"] = False

        print(json.dumps(result))
    ''')

    try:
        with tempfile.TemporaryDirectory(prefix="safe-extract-grade-") as tmp:
            sandbox = Path(tmp)
            shutil.copy2(source, sandbox / "extractor.py")
            driver_path = sandbox / "driver.py"
            driver_path.write_text(driver, encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                [sys.executable, "-I", str(driver_path)],
                cwd=sandbox,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = None
            for line in reversed(completed.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    payload = candidate
                    break
    except (OSError, subprocess.SubprocessError):
        payload = None

    if not isinstance(payload, dict):
        return scores

    def fraction(name, expected_count):
        values = payload.get(name)
        if not isinstance(values, list) or len(values) != expected_count:
            return 0.0
        return sum(value is True for value in values) / expected_count

    scores["path_traversal_blocked"] = fraction("path", 7)
    scores["symlink_collision_blocked"] = fraction("symlink_collision", 5)
    scores["limits_malformed_archives"] = fraction("limits", 5)
    scores["atomic_no_partial_delivery"] = fraction("atomic", 3)
    valid_components = payload.get("valid")
    if isinstance(valid_components, list) and len(valid_components) == 3:
        scores["valid_bundles_api_preserved"] = sum(
            [value is True for value in valid_components]
            + [payload.get("api") is True, scope_ok]
        ) / 5.0
    return scores
```

## LLM Judge Rubric

### Criterion 1: Security notes quality (key: security_notes_quality, weight: 1.0)

Judge `/tmp_workspace/results/SECURITY_NOTES.md` against the implementation and task requirements. Do not award credit for claims contradicted by `extractor.py` or for generic security advice without a stated rejection rule.

**Score 1.0**: The note accurately covers POSIX and Windows traversal and absolute paths, archive and pre-existing symlinks, normalized-name collisions, both resource limits, staged atomic failure, and at least one concrete remaining assumption or boundary. It does not claim that archive content is executed.

**Score 0.75**: The note is technically consistent with the implementation and covers all major controls, but omits exactly one secondary threat class or gives an incomplete remaining-assumption statement.

**Score 0.5**: The note correctly covers at least three threat classes and states a basic rejection policy, but omits atomic failure behavior or one of the two resource limits, or leaves multiple required controls undocumented.

**Score 0.25**: The note only gives a generic path-sanitization description, documents fewer than three required controls, or makes one material claim that is not supported by the implementation.

**Score 0.0**: The note is missing, recommends extracting before validation, contradicts the implemented behavior on a central control, or suggests executing archive content.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_009_safe_archive_extract
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

- The public tests cover valid behavior, one traversal case, and one resource limit. Automated grading adds fixed hidden cases for the remaining required controls.
- The grader executes a copied candidate module in an isolated subprocess with a fixed timeout and does not execute any archive member.
- Ground truth records SHA-256 hashes for every regular file initially present under `exec/`; only `extractor.py` is allowed to change.
