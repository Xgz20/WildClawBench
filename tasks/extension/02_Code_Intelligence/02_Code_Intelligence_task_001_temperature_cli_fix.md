---
id: 02_Code_Intelligence_task_001_temperature_cli_fix
name: 修复温度换算命令行程序
category: 02_代码智能
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - custom
---
## Prompt

`/tmp_workspace/project/converter.py`中的小型Python命令行程序应将摄氏度换算为华氏度，但当前结果错误。

请检查实现和测试，修复缺陷，并验证单元测试和命令行接口。保留公开API `celsius_to_fahrenheit(value)`和现有命令行输出格式。只修改 `/tmp_workspace/project/converter.py`，不要修改测试，不要访问网络。

可以使用以下命令验证：

```bash
python3 -m unittest discover -s /tmp_workspace/project -p 'test_*.py'
python3 /tmp_workspace/project/converter.py 100
```

## Expected Behavior

Agent应运行或检查测试，定位错误的运算符号，进行最小源码修改，并确认函数调用和命令行输出均正确。

## Grading Criteria

- [ ] 指定换算用例正确 — 50%
- [ ] 额外隐藏换算用例正确 — 20%
- [ ] 未修改的公开测试通过 — 15%
- [ ] 命令行输出与预期完全一致 — 15%

前两个检查点映射到`code_generation`，后两个映射到`tool_use`。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import ast
    import hashlib
    import json
    import math
    from pathlib import Path

    keys = [
        "function_cases_correct",
        "hidden_cases_correct",
        "public_tests_passed",
        "cli_output_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    workspace = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    source = workspace / "project" / "converter.py"
    test_file = workspace / "project" / "test_converter.py"
    expected_path = workspace / "gt" / "expected.json"

    def is_regular_delivery(path):
        try:
            root = workspace.resolve(strict=True)
            resolved = path.resolve(strict=True)
            relative = path.relative_to(workspace)
            if resolved != root and root not in resolved.parents:
                return False
            cursor = workspace
            for part in relative.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    return False
            return path.is_file()
        except (OSError, RuntimeError, ValueError):
            return False

    if not is_regular_delivery(source) or not expected_path.is_file():
        return scores
    try:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        if source.stat().st_size > 16384:
            return scores
        source_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores
    if not isinstance(expected, dict):
        return scores

    try:
        tree = ast.parse(source_text, filename=str(source))
        nodes = list(ast.walk(tree))
        if len(nodes) > 256:
            return scores
        stack = [(tree, 1)]
        while stack:
            node, depth = stack.pop()
            if depth > 32:
                return scores
            stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
        targets = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "celsius_to_fahrenheit"
        ]
        if len(targets) != 1:
            return scores
        target = targets[0]
    except (MemoryError, RecursionError, SyntaxError, TypeError, ValueError):
        return scores

    def canonical_ast(value):
        ignored = {"type_comment", "type_ignores", "type_params"}
        if isinstance(value, ast.AST):
            return (
                type(value).__name__,
                tuple(
                    (name, canonical_ast(child))
                    for name, child in ast.iter_fields(value)
                    if name not in ignored
                ),
            )
        if isinstance(value, list):
            return tuple(canonical_ast(child) for child in value)
        return value

    original_body = target.body
    try:
        target.body = [ast.Pass()]
        skeleton_hash = hashlib.sha256(
            repr(canonical_ast(tree)).encode("utf-8")
        ).hexdigest()
    except (MemoryError, RecursionError, TypeError, ValueError):
        return scores
    finally:
        target.body = original_body
    skeleton_ok = skeleton_hash == expected.get("module_skeleton_sha256")

    body = list(target.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        if len(body[0].value.value) > 512:
            return scores
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return scores
    expression = body[0].value

    def valid_expression(node):
        if isinstance(node, ast.Name):
            return node.id == "value" and isinstance(node.ctx, ast.Load)
        if isinstance(node, ast.Constant):
            if type(node.value) not in (int, float):
                return False
            try:
                return math.isfinite(float(node.value)) and abs(node.value) <= 1000000
            except (OverflowError, TypeError, ValueError):
                return False
        if isinstance(node, ast.UnaryOp):
            return isinstance(node.op, (ast.UAdd, ast.USub)) and valid_expression(
                node.operand
            )
        if isinstance(node, ast.BinOp):
            return (
                isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div))
                and valid_expression(node.left)
                and valid_expression(node.right)
            )
        return False

    if expression is None or not valid_expression(expression):
        return scores

    def evaluate_expression(node, value, budget):
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("expression limit exceeded")
        if isinstance(node, ast.Name):
            result = value
        elif isinstance(node, ast.Constant):
            result = node.value
        elif isinstance(node, ast.UnaryOp):
            operand = evaluate_expression(node.operand, value, budget)
            result = +operand if isinstance(node.op, ast.UAdd) else -operand
        elif isinstance(node, ast.BinOp):
            left = evaluate_expression(node.left, value, budget)
            right = evaluate_expression(node.right, value, budget)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            else:
                result = left / right
        else:
            raise ValueError("unsupported expression")
        if type(result) not in (int, float):
            raise ValueError("non-numeric result")
        number = float(result)
        if not math.isfinite(number) or abs(number) > 1000000000000:
            raise ValueError("numeric limit exceeded")
        return result

    def evaluate_cases(cases):
        if not isinstance(cases, list) or not cases:
            return 0.0
        hits = 0
        for case in cases:
            try:
                if not isinstance(case, list) or len(case) != 2:
                    continue
                output = evaluate_expression(expression, case[0], [128])
                wanted = float(case[1])
                actual = float(output)
                hits += int(
                    math.isfinite(wanted)
                    and math.isfinite(actual)
                    and abs(actual - wanted) <= 1e-6
                )
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                pass
        return hits / len(cases)

    scores["function_cases_correct"] = evaluate_cases(expected.get("public_cases"))
    scores["hidden_cases_correct"] = evaluate_cases(expected.get("hidden_cases"))

    test_hash_ok = False
    if is_regular_delivery(test_file):
        try:
            if test_file.stat().st_size <= 65536:
                test_hash_ok = (
                    hashlib.sha256(test_file.read_bytes()).hexdigest()
                    == expected.get("public_test_sha256")
                )
        except OSError:
            pass
    if test_hash_ok and skeleton_ok:
        scores["public_tests_passed"] = float(
            evaluate_cases(expected.get("public_test_cases")) == 1.0
        )

    cli_cases = expected.get("cli_cases")
    if skeleton_ok and isinstance(cli_cases, list) and cli_cases:
        hits = 0
        for case in cli_cases:
            try:
                if not isinstance(case, list) or len(case) != 2:
                    continue
                value, wanted = case
                output = evaluate_expression(expression, value, [128])
                hits += int(
                    isinstance(wanted, str) and f"{float(output):.1f}" == wanted
                )
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                pass
        scores["cli_output_correct"] = hits / len(cli_cases)

    scores["overall_score"] = round(
        0.50 * scores["function_cases_correct"]
        + 0.20 * scores["hidden_cases_correct"]
        + 0.15 * scores["public_tests_passed"]
        + 0.15 * scores["cli_output_correct"],
        6,
    )
    return scores
```

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_001_temperature_cli_fix
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
