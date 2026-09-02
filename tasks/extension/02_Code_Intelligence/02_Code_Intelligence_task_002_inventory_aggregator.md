---
id: 02_Code_Intelligence_task_002_inventory_aggregator
name: 实现库存聚合函数
category: 02_Code_Intelligence
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - custom
---
## Prompt

请实现 `/tmp_workspace/project/inventory.py` 中缺失的 `aggregate_inventory(rows)` 函数。

每条输入记录都是字典，其中包含非空`sku`和以文本表示的整数`quantity`。请按SKU合并重复记录的数量，保留零值和负数调整，并以SKU升序返回对象列表：

```json
[
  {"sku": "A100", "quantity": 5}
]
```

保持函数名和命令行参数不变。只修改 `/tmp_workspace/project/inventory.py`，不要修改测试。运行测试后，使用 `/tmp_workspace/inventory.csv` 运行命令行程序，并将结果保存到 `/tmp_workspace/results/inventory_summary.json`。不要访问网络。

## Expected Behavior

Agent应实现一个确定性的基础聚合函数，保留现有命令行接口，通过公开与隐藏用例，并为给定CSV生成要求的JSON结果。

## Grading Criteria

- [ ] 公开聚合用例正确 — 40%
- [ ] 隐藏聚合用例正确 — 30%
- [ ] 要求的源码和未修改的公开测试均正确交付 — 10%
- [ ] 示例命令行结果合法且完全正确 — 20%

前两个检查点映射到`code_generation`，后两个映射到`verification_delivery`。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import ast
    import copy
    import hashlib
    import json
    import math
    import sys
    from collections import Counter, defaultdict
    from pathlib import Path

    keys = [
        "public_cases_correct",
        "hidden_cases_correct",
        "source_delivery_valid",
        "result_delivery_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    workspace = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    source = workspace / "project" / "inventory.py"
    test_file = workspace / "project" / "test_inventory.py"
    inventory_file = workspace / "inventory.csv"
    result_path = workspace / "results" / "inventory_summary.json"
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
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores
    if not isinstance(expected, dict):
        return scores

    expected_input_hashes = expected.get("exec_file_sha256")
    if (
        not isinstance(expected_input_hashes, dict)
        or set(expected_input_hashes) != {"inventory.csv"}
        or not is_regular_delivery(inventory_file)
    ):
        return scores
    try:
        if (
            inventory_file.stat().st_size > 65536
            or hashlib.sha256(inventory_file.read_bytes()).hexdigest()
            != expected_input_hashes["inventory.csv"]
        ):
            return scores
    except OSError:
        return scores

    source_text = None
    try:
        if source.stat().st_size <= 32768:
            source_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        pass

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

    tree = None
    target = None
    skeleton_ok = False
    if source_text is not None:
        try:
            parsed = ast.parse(source_text, filename=str(source))
            nodes = list(ast.walk(parsed))
            if len(nodes) <= 512:
                stack = [(parsed, 1)]
                depth_ok = True
                while stack:
                    node, depth = stack.pop()
                    if depth > 40:
                        depth_ok = False
                        break
                    stack.extend(
                        (child, depth + 1) for child in ast.iter_child_nodes(node)
                    )
                targets = [
                    node
                    for node in parsed.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "aggregate_inventory"
                ]
                if depth_ok and len(targets) == 1:
                    tree = parsed
                    target = targets[0]
                    original_body = target.body
                    try:
                        target.body = [ast.Pass()]
                        skeleton_hash = hashlib.sha256(
                            repr(canonical_ast(tree)).encode("utf-8")
                        ).hexdigest()
                    finally:
                        target.body = original_body
                    skeleton_ok = (
                        skeleton_hash == expected.get("module_skeleton_sha256")
                    )
        except (
            MemoryError,
            RecursionError,
            SyntaxError,
            TypeError,
            ValueError,
        ):
            tree = None
            target = None

    builtin_calls = {
        "Counter": (0, 1),
        "dict": (0, 1),
        "defaultdict": (1, 1),
        "int": (1, 1),
        "len": (1, 1),
        "list": (0, 1),
        "sorted": (1, 1),
        "sum": (1, 1),
    }
    method_calls = {
        "append": (1, 1),
        "get": (1, 2),
        "items": (0, 0),
        "keys": (0, 0),
        "setdefault": (1, 2),
        "values": (0, 0),
    }
    reserved_names = {
        "_candidate_function",
        "_method_append",
        "_method_get",
        "_method_items",
        "_method_keys",
        "_method_setdefault",
        "_method_values",
        "_safe_add",
        "_safe_counter",
        "_safe_defaultdict",
        "_safe_dict",
        "_safe_int",
        "_safe_len",
        "_safe_list",
        "_safe_sorted",
        "_safe_sub",
        "_safe_sum",
    }

    def valid_identifier(name, storing=False):
        if not isinstance(name, str) or "__" in name or name in reserved_names:
            return False
        if storing and name in builtin_calls:
            return False
        return True

    def valid_target(node):
        if isinstance(node, ast.Name):
            return isinstance(node.ctx, (ast.Store, ast.Load)) and valid_identifier(
                node.id, storing=True
            )
        if isinstance(node, (ast.Tuple, ast.List)):
            return len(node.elts) <= 4 and all(valid_target(item) for item in node.elts)
        if isinstance(node, ast.Subscript):
            slice_ok = isinstance(node.slice, (ast.Name, ast.Constant)) or (
                isinstance(node.slice, ast.Subscript)
                and isinstance(node.slice.value, ast.Name)
                and valid_identifier(node.slice.value.id)
                and isinstance(node.slice.slice, (ast.Name, ast.Constant))
            )
            return (
                isinstance(node.value, ast.Name)
                and valid_identifier(node.value.id)
                and slice_ok
            )
        return False

    def valid_candidate_function(function):
        allowed_nodes = (
            ast.Add,
            ast.And,
            ast.Assign,
            ast.Attribute,
            ast.AugAssign,
            ast.BinOp,
            ast.BoolOp,
            ast.Call,
            ast.Compare,
            ast.Constant,
            ast.Dict,
            ast.DictComp,
            ast.Eq,
            ast.Expr,
            ast.For,
            ast.FunctionDef,
            ast.Gt,
            ast.GtE,
            ast.If,
            ast.IfExp,
            ast.ImportFrom,
            ast.In,
            ast.List,
            ast.ListComp,
            ast.Load,
            ast.Lt,
            ast.LtE,
            ast.Name,
            ast.Not,
            ast.NotEq,
            ast.NotIn,
            ast.Or,
            ast.Pass,
            ast.Return,
            ast.Store,
            ast.Sub,
            ast.Subscript,
            ast.Tuple,
            ast.UAdd,
            ast.USub,
            ast.UnaryOp,
            ast.alias,
            ast.arg,
            ast.arguments,
            ast.comprehension,
        )
        parents = {}
        for parent in ast.walk(function):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent

        for node in ast.walk(function):
            if not isinstance(node, allowed_nodes):
                return False
            if isinstance(node, ast.FunctionDef) and node is not function:
                return False
            if isinstance(node, ast.Name):
                if not valid_identifier(
                    node.id, storing=isinstance(node.ctx, ast.Store)
                ):
                    return False
            if isinstance(node, ast.arg) and not valid_identifier(node.arg):
                return False
            if isinstance(node, ast.ImportFrom):
                if (
                    node.level != 0
                    or node.module != "collections"
                    or not node.names
                    or any(
                        item.name not in {"Counter", "defaultdict"}
                        or item.asname is not None
                        for item in node.names
                    )
                ):
                    return False
            if isinstance(node, ast.alias):
                parent = parents.get(id(node))
                if (
                    not isinstance(parent, ast.ImportFrom)
                    or parent.module != "collections"
                    or node.name not in {"Counter", "defaultdict"}
                    or node.asname is not None
                ):
                    return False
            if isinstance(node, ast.Constant):
                value = node.value
                if isinstance(value, str):
                    if len(value) > 256:
                        return False
                elif type(value) in (int, float):
                    try:
                        if not math.isfinite(float(value)) or abs(value) > 1000000:
                            return False
                    except (OverflowError, TypeError, ValueError):
                        return False
                elif value is not None and type(value) is not bool:
                    return False
            if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) > 32:
                return False
            if isinstance(node, ast.Dict):
                if len(node.keys) > 32 or any(key is None for key in node.keys):
                    return False
            if isinstance(node, ast.Assign):
                if len(node.targets) > 2 or not all(
                    valid_target(item) for item in node.targets
                ):
                    return False
            if isinstance(node, ast.AugAssign):
                if (
                    not valid_target(node.target)
                    or not isinstance(node.op, (ast.Add, ast.Sub))
                ):
                    return False
            if isinstance(node, ast.For) and not valid_target(node.target):
                return False
            if isinstance(node, ast.comprehension):
                if node.is_async or not valid_target(node.target):
                    return False
            if isinstance(node, (ast.ListComp, ast.DictComp)):
                if len(node.generators) > 2:
                    return False
            if isinstance(node, ast.BinOp) and not isinstance(
                node.op, (ast.Add, ast.Sub)
            ):
                return False
            if isinstance(node, ast.UnaryOp) and not isinstance(
                node.op, (ast.UAdd, ast.USub, ast.Not)
            ):
                return False
            if isinstance(node, ast.BoolOp) and len(node.values) > 4:
                return False
            if isinstance(node, ast.Compare):
                if len(node.ops) > 2 or not all(
                    isinstance(
                        operator,
                        (
                            ast.Eq,
                            ast.Gt,
                            ast.GtE,
                            ast.In,
                            ast.Lt,
                            ast.LtE,
                            ast.NotEq,
                            ast.NotIn,
                        ),
                    )
                    for operator in node.ops
                ):
                    return False
            if isinstance(node, ast.Call):
                if node.keywords:
                    return False
                if isinstance(node.func, ast.Name):
                    limits = builtin_calls.get(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    limits = method_calls.get(node.func.attr)
                else:
                    return False
                if limits is None or not limits[0] <= len(node.args) <= limits[1]:
                    return False
            if isinstance(node, ast.Attribute):
                parent = parents.get(id(node))
                if (
                    not isinstance(parent, ast.Call)
                    or parent.func is not node
                    or node.attr not in method_calls
                ):
                    return False
        return True

    function_ok = target is not None and valid_candidate_function(target)

    def checked_number(value):
        if type(value) is int:
            if abs(value) > 1000000000000:
                raise ValueError("numeric limit exceeded")
            return value
        if type(value) is float:
            if not math.isfinite(value) or abs(value) > 1000000000000:
                raise ValueError("numeric limit exceeded")
            return value
        raise TypeError("number required")

    def safe_add(left, right):
        return checked_number(checked_number(left) + checked_number(right))

    def safe_sub(left, right):
        return checked_number(checked_number(left) - checked_number(right))

    def safe_int(value):
        if type(value) not in (str, int, float):
            raise TypeError("unsupported int input")
        if isinstance(value, str) and len(value) > 128:
            raise ValueError("string limit exceeded")
        return checked_number(int(value))

    def limited_sequence(value):
        if not isinstance(value, (list, tuple, dict, str)):
            raise TypeError("bounded collection required")
        if len(value) > 512:
            raise ValueError("collection limit exceeded")
        return value

    empty = object()

    def safe_list(value=empty):
        if value is empty:
            return []
        return list(limited_sequence(value))

    def safe_dict(value=empty):
        result = {} if value is empty else dict(limited_sequence(value))
        if len(result) > 512:
            raise ValueError("collection limit exceeded")
        return result

    def safe_defaultdict(factory):
        if factory is not int:
            raise TypeError("only defaultdict(int) is supported")
        return defaultdict(int)

    def safe_counter(value=empty):
        result = Counter() if value is empty else Counter(limited_sequence(value))
        if len(result) > 512:
            raise ValueError("collection limit exceeded")
        return result

    def safe_len(value):
        return len(limited_sequence(value))

    def safe_sorted(value):
        return sorted(limited_sequence(value))

    def safe_sum(value):
        if type(value) not in (list, tuple) or len(value) > 512:
            raise TypeError("bounded numeric collection required")
        result = 0
        for item in value:
            result = safe_add(result, item)
        return result

    def method_append(value, item):
        if type(value) is not list or len(value) >= 512:
            raise TypeError("bounded list required")
        value.append(item)
        return None

    def method_get(value, key, default=None):
        if not isinstance(value, dict) or len(value) > 512:
            raise TypeError("bounded dict required")
        return value.get(key, default)

    def method_setdefault(value, key, default=None):
        if not isinstance(value, dict) or (key not in value and len(value) >= 512):
            raise TypeError("bounded dict required")
        return value.setdefault(key, default)

    def method_items(value):
        if not isinstance(value, dict) or len(value) > 512:
            raise TypeError("bounded dict required")
        return list(value.items())

    def method_keys(value):
        if not isinstance(value, dict) or len(value) > 512:
            raise TypeError("bounded dict required")
        return list(value.keys())

    def method_values(value):
        if not isinstance(value, dict) or len(value) > 512:
            raise TypeError("bounded dict required")
        return list(value.values())

    class SafetyTransformer(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None

        def visit_BinOp(self, node):
            node = self.generic_visit(node)
            helper = "_safe_add" if isinstance(node.op, ast.Add) else "_safe_sub"
            replacement = ast.Call(
                func=ast.Name(id=helper, ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            )
            return ast.copy_location(replacement, node)

        def visit_AugAssign(self, node):
            node = self.generic_visit(node)
            read_target = copy.deepcopy(node.target)
            read_target.ctx = ast.Load()
            helper = "_safe_add" if isinstance(node.op, ast.Add) else "_safe_sub"
            replacement = ast.Assign(
                targets=[node.target],
                value=ast.Call(
                    func=ast.Name(id=helper, ctx=ast.Load()),
                    args=[read_target, node.value],
                    keywords=[],
                ),
            )
            return ast.copy_location(replacement, node)

        def visit_Call(self, node):
            node = self.generic_visit(node)
            if isinstance(node.func, ast.Name):
                helper = {
                    "Counter": "_safe_counter",
                    "dict": "_safe_dict",
                    "defaultdict": "_safe_defaultdict",
                    "int": "_safe_int",
                    "len": "_safe_len",
                    "list": "_safe_list",
                    "sorted": "_safe_sorted",
                    "sum": "_safe_sum",
                }[node.func.id]
                arguments = node.args
            else:
                helper = {
                    "append": "_method_append",
                    "get": "_method_get",
                    "items": "_method_items",
                    "keys": "_method_keys",
                    "setdefault": "_method_setdefault",
                    "values": "_method_values",
                }[node.func.attr]
                arguments = [node.func.value] + node.args
            replacement = ast.Call(
                func=ast.Name(id=helper, ctx=ast.Load()),
                args=arguments,
                keywords=[],
            )
            return ast.copy_location(replacement, node)

    candidate = None
    if function_ok:
        try:
            safe_module = ast.parse("def _candidate_function(rows):\n    pass\n")
            safe_module.body[0].body = target.body
            safe_module = SafetyTransformer().visit(safe_module)
            ast.fix_missing_locations(safe_module)
            safe_globals = {
                "__builtins__": {},
                "_method_append": method_append,
                "_method_get": method_get,
                "_method_items": method_items,
                "_method_keys": method_keys,
                "_method_setdefault": method_setdefault,
                "_method_values": method_values,
                "_safe_add": safe_add,
                "_safe_counter": safe_counter,
                "_safe_defaultdict": safe_defaultdict,
                "_safe_dict": safe_dict,
                "_safe_int": safe_int,
                "_safe_len": safe_len,
                "_safe_list": safe_list,
                "_safe_sorted": safe_sorted,
                "_safe_sub": safe_sub,
                "_safe_sum": safe_sum,
                "int": int,
            }
            exec(compile(safe_module, "<candidate>", "exec"), safe_globals)
            candidate = safe_globals["_candidate_function"]
        except BaseException:
            candidate = None
            function_ok = False

    def valid_json_value(value):
        stack = [(value, 0)]
        seen = set()
        count = 0
        while stack:
            item, depth = stack.pop()
            count += 1
            if count > 2048 or depth > 20:
                return False
            if item is None or type(item) is bool:
                continue
            if type(item) is int:
                if abs(item) > 1000000000000:
                    return False
                continue
            if type(item) is float:
                if not math.isfinite(item) or abs(item) > 1000000000000:
                    return False
                continue
            if type(item) is str:
                if len(item) > 1024:
                    return False
                continue
            if type(item) is list:
                if len(item) > 512 or id(item) in seen:
                    return False
                seen.add(id(item))
                stack.extend((child, depth + 1) for child in item)
                continue
            if type(item) is dict:
                if len(item) > 512 or id(item) in seen:
                    return False
                seen.add(id(item))
                for key, child in item.items():
                    if type(key) is not str or len(key) > 1024:
                        return False
                    stack.append((child, depth + 1))
                continue
            return False
        return True

    def run_candidate(rows):
        if candidate is None or not valid_json_value(rows):
            raise ValueError("invalid candidate or input")
        copied_rows = json.loads(json.dumps(rows))
        steps = [0]

        def tracer(frame, event, argument):
            steps[0] += 1
            if steps[0] > 5000:
                raise RuntimeError("execution step limit exceeded")
            return tracer

        previous_trace = sys.gettrace()
        sys.settrace(tracer)
        try:
            return candidate(copied_rows)
        finally:
            sys.settrace(previous_trace)

    def evaluate_cases(cases):
        if not isinstance(cases, list) or not cases or candidate is None:
            return 0.0
        hits = 0
        for case in cases:
            try:
                if not isinstance(case, dict):
                    continue
                output = run_candidate(case["rows"])
                wanted = case["expected"]
                hits += int(valid_json_value(output) and output == wanted)
            except BaseException:
                pass
        return hits / len(cases)

    scores["public_cases_correct"] = evaluate_cases(expected.get("public_cases"))
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
    scores["source_delivery_valid"] = float(
        function_ok
        and candidate is not None
        and skeleton_ok
        and test_hash_ok
        and scores["public_cases_correct"] == 1.0
    )

    if is_regular_delivery(result_path):
        try:
            if result_path.stat().st_size <= 131072:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                scores["result_delivery_correct"] = float(
                    valid_json_value(result)
                    and result == expected.get("sample_output")
                )
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass

    scores["overall_score"] = round(
        0.40 * scores["public_cases_correct"]
        + 0.30 * scores["hidden_cases_correct"]
        + 0.10 * scores["source_delivery_valid"]
        + 0.20 * scores["result_delivery_correct"],
        6,
    )
    return scores
```

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_002_inventory_aggregator
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
