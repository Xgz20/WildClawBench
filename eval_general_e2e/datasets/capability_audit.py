"""Generate the frozen General E2E per-task capability audit.

The audit is intentionally static and deterministic.  It reads the dataset
manifest lock, verifies that the selected task sources still match it, and
then inspects Prompt text, workspace material metadata, and the automated
grader AST without importing or executing task-authored grader code.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Optional, Sequence

from .bundle import (
    _canonical_sha256,
    _parse_task_source,
    _strip_codeblock,
    _validate_manifest,
    compile_dataset,
    default_manifest_path,
    load_manifest_lock,
)


AUDIT_SCHEMA_ID = "urn:wildclawbench:schema:general-e2e:capability-matrix:v1"
AUDIT_SCHEMA_VERSION = 1
GENERATOR_VERSION = "eval_general_e2e.datasets.capability_audit/1"

URL_RE = re.compile(r"https?://[^\s<>`\])}]+", re.I)
WORKSPACE_PATH_RE = re.compile(
    r"/tmp_workspace(?:/[A-Za-z0-9._*{}'\"?-]+)+/?"
)
FENCED_BLOCK_RE = re.compile(
    r"```(?P<language>[^\n`]*)\n(?P<body>.*?)\n```", re.DOTALL
)
NETWORK_FORBIDDEN_RE = re.compile(
    r"(?:"
    r"(?:不要|不得|禁止|不联网)[^。\n]{0,120}(?:网络|联网)|"
    r"no\s+(?:external\s+)?(?:network|internet)|"
    r"(?:do\s+not|don.t|without)[^.\n]{0,160}\b(?:network|internet)\b|"
    r"work\s+offline|offline[^.\n]{0,80}network"
    r")",
    re.I,
)
MUTATION_EVIDENCE_RE = re.compile(
    r"(?:只修改|仅修改|请修复|修复缺陷|请实现|补完|按规则清理|"
    r"only\s+modify|modify\s+only|\bfix\b|\bharden\b|\bpatch\b)",
    re.I,
)
COMMAND_LANGUAGES = {
    "bash",
    "sh",
    "shell",
    "zsh",
    "powershell",
    "pwsh",
    "cmd",
    "bat",
}
EXTERNAL_GRADER_IMPORTS = {"playwright", "yaml"}
EMBEDDED_JUDGE_IMPORTS = {
    "anthropic",
    "google.generativeai",
    "litellm",
    "ollama",
    "openai",
}
EMBEDDED_JUDGE_CALL_SUFFIXES = {
    "chat.completions.create",
    "completions.create",
    "generate_content",
    "messages.create",
    "responses.create",
}
EMBEDDED_JUDGE_TEXT_RE = re.compile(
    r"(?:api\.openai\.com|anthropic|litellm|ollama|openai_api_key|"
    r"anthropic_api_key|/chat/completions|responses\.create|messages\.create)",
    re.I,
)


TRACE_CAPTURE_POLICY = {
    "scope": "all_tasks",
    "required_fields": [
        "event.sequence",
        "event.type",
        "event.role",
        "event.content",
        "tool.call_id",
        "tool.name",
        "tool.arguments",
        "tool.result",
        "tool.status",
        "source.raw_ref",
    ],
    "requirements": [
        "保留从用户消息到最终助手回复的完整事件范围，不以 UI 可见尾部代替原始轨迹",
        "按 sequence 保留原始顺序，并用 call_id 关联 tool_call 与 tool_result",
        "工具名和参数同时保留原始值与适配后的规范值，自动规则使用兼容视图",
        "当前规则未读取的 call_id 和 result 仍为默认 Agent Judge、恢复和审计的必需字段",
    ],
}

TRACE_ALIAS_POLICY = {
    "tool_call_block_types": ["tool_use", "toolCall"],
    "tool_name_fields": ["name", "tool_name", "toolName"],
    "tool_argument_fields": ["input", "arguments"],
    "assistant_message_shapes": [
        "entry.role/content",
        "entry.message.role/content",
    ],
    "execution_tool_name_matching": {
        "contains": ["exec", "shell", "bash", "terminal"],
        "exact": ["sh", "zsh", "cmd", "command"],
    },
    "network_tool_name_matching": {
        "contains": [
            "browser",
            "fetch",
            "http",
            "web_search",
            "search_web",
            "search",
            "download",
            "bulk_get",
            "bulk_fetch",
        ]
    },
    "adapter_rule": (
        "适配器可以增加规范工具名，但必须保留原始工具名、参数、事件顺序和原始引用；"
        "不得仅按当前某个 Harness 的工具名过滤轨迹"
    ),
}

WINDOWS_DISPOSITIONS = {
    "POSIX_WORKSPACE_ROOT": {
        "scope": "execution",
        "disposition": (
            "prepare/adapter 将逻辑 /tmp_workspace 映射到短本机工作目录；发送文本、"
            "原始路径、映射表和哈希均保留，不静默改写数据集任务"
        ),
    },
    "PYTHON3_ALIAS": {
        "scope": "execution",
        "disposition": (
            "预检固定 Python 3.12；在受管任务环境提供 python3 兼容入口，或在声明支持的"
            "POSIX shell 环境运行。缺失时阻止发送，不把环境缺失计为模型失败"
        ),
    },
    "POSIX_SHELL_BLOCK": {
        "scope": "execution",
        "disposition": (
            "命令块在预检通过的受管 shell 中执行；Windows 原生 launcher 使用 .cmd/"
            "PowerShell 启动，但不改题内命令语义"
        ),
    },
    "CRLF_DATA_SEMANTICS": {
        "scope": "execution_and_scoring",
        "disposition": (
            "bundle 解包和候选冻结按字节保真，不做换行转换；自动规则在固定 Linux 评分"
            "环境复核字段内 CRLF 与记录边界"
        ),
    },
    "SYMLINK_FIXTURE": {
        "scope": "preparation_and_execution",
        "disposition": (
            "预检 Windows Developer Mode/创建符号链接权限并验证目标未被解引用；无法保真"
            "时该题 BLOCKED，不复制目标内容冒充符号链接"
        ),
    },
    "ARCHIVE_WINDOWS_PATH_RULES": {
        "scope": "execution_and_scoring",
        "disposition": (
            "保留测试归档原始字节，在固定 Python 环境同时验证 POSIX/Windows 分隔符、"
            "NFC 和 case-fold；不得由解包工具预先规范化测试样本"
        ),
    },
    "POSIX_SCRIPT_AS_DATA": {
        "scope": "execution",
        "disposition": (
            "脚本仅作为待审文本按字节提供，不要求 Windows 可执行，也不得为验证方便而运行"
        ),
    },
    "SHELL_TRACE_NORMALIZATION": {
        "scope": "trace",
        "disposition": (
            "将 Bash、PowerShell、cmd 和终端类工具映射到 shell.execute 兼容视图，同时"
            "保留原始工具名、完整参数和顺序，供安全规则识别禁止行为"
        ),
    },
    "PLAYWRIGHT_SCORING_DEPENDENCY": {
        "scope": "scoring",
        "disposition": (
            "Playwright 与浏览器固定在评分依赖/容器中，不要求被测 Harness 安装；Windows"
            "本机评分需单独通过 Docker Desktop/WSL2 挂载与浏览器 smoke"
        ),
    },
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _call_string_argument(node: ast.Call, value: str) -> bool:
    return any(
        isinstance(argument, ast.Constant) and argument.value == value
        for argument in node.args
    )


class _ScopeVisitor(ast.NodeVisitor):
    """Collect nodes in one executable function scope, excluding nested bodies."""

    def __init__(self) -> None:
        self.nodes: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        self.nodes.append(node)
        super().generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def _executable_scope_nodes(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.AST]:
    visitor = _ScopeVisitor()
    for statement in function.body:
        visitor.visit(statement)
    return visitor.nodes


def _material_summary(tree: Mapping[str, Any]) -> dict[str, Any]:
    entries = tree.get("entries") or []
    paths: list[str] = []
    extensions: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    effective_files = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        path = str(entry.get("path") or "")
        kinds[kind] += 1
        paths.append(path)
        if kind in {"file", "symlink"}:
            if PurePosixPath(path).name != ".gitkeep":
                suffix = PurePosixPath(path).suffix.lower() or "[no-extension]"
                extensions[suffix] += 1
                effective_files += 1
    return {
        "root": tree.get("root"),
        "sha256": tree.get("sha256"),
        "entry_count": len(entries),
        "file_count": kinds["file"],
        "directory_count": kinds["directory"],
        "symlink_count": kinds["symlink"],
        "effective_file_count": effective_files,
        "extensions": dict(sorted(extensions.items())),
        "paths": paths,
    }


def _command_blocks(prompt: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for match in FENCED_BLOCK_RE.finditer(prompt):
        language = match.group("language").strip().lower()
        if language in COMMAND_LANGUAGES:
            result.append({"language": language, "body": match.group("body").strip()})
    return result


def _mutation_evidence(prompt: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", prompt)
    return _dedupe(
        " ".join(paragraph.split())
        for paragraph in paragraphs
        if MUTATION_EVIDENCE_RE.search(paragraph)
    )


def _network_requirement(prompt: str) -> dict[str, Any]:
    urls = _dedupe(URL_RE.findall(prompt))
    forbidden = bool(NETWORK_FORBIDDEN_RE.search(prompt))
    if forbidden:
        policy = "forbidden"
    elif urls:
        policy = "required"
    else:
        policy = "not_declared"
    return {
        "policy": policy,
        "source_urls": urls,
        "evidence": (
            "Prompt explicitly forbids network access"
            if forbidden
            else "Prompt provides fixed remote source URL(s)"
            if urls
            else "Prompt declares no remote source or network requirement"
        ),
    }


def _automated_check_analysis(code: str) -> dict[str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"automated checks are not valid Python AST: {exc}") from exc

    imports: set[str] = set()
    calls: set[str] = set()
    strings: set[str] = set()
    grade: Optional[ast.FunctionDef | ast.AsyncFunctionDef] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                calls.add(name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "grade":
            grade = node

    grade_args = (
        {
            argument.arg
            for argument in (
                list(grade.args.posonlyargs)
                + list(grade.args.args)
                + list(grade.args.kwonlyargs)
            )
        }
        if grade
        else set()
    )
    nested_functions = (
        {
            node.name: node
            for node in ast.walk(grade)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node is not grade
        }
        if grade
        else {}
    )
    reachable_nodes: list[ast.AST] = []
    reachable_helpers: set[str] = set()
    pending_functions = [grade] if grade else []
    while pending_functions:
        function = pending_functions.pop()
        scope_nodes = _executable_scope_nodes(function)
        reachable_nodes.extend(scope_nodes)
        for node in scope_nodes:
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            helper = nested_functions.get(node.func.id)
            if helper is not None and helper.name not in reachable_helpers:
                reachable_helpers.add(helper.name)
                pending_functions.append(helper)

    reachable_strings = {
        node.value
        for node in reachable_nodes
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    transcript_get = any(
        isinstance(node, ast.Call)
        and _dotted_name(node.func).endswith(".get")
        and _call_string_argument(node, "transcript")
        for node in reachable_nodes
    )
    transcript_load = any(
        isinstance(node, ast.Name)
        and node.id == "transcript"
        and isinstance(node.ctx, ast.Load)
        for node in reachable_nodes
    )
    accepts_transcript = "transcript" in grade_args or transcript_get
    consumes_transcript = transcript_load or transcript_get

    contains_transcript_scaffolding = (
        "transcript" in grade_args
        or "transcript" in strings
        or any(
            isinstance(node, ast.Name) and node.id == "transcript"
            for node in ast.walk(tree)
        )
    )
    contains_tool_call_parser = bool({"tool_use", "toolCall"}.intersection(strings))
    parses_tool_calls = bool(
        {"tool_use", "toolCall"}.intersection(reachable_strings)
    )
    reads_tool_name = parses_tool_calls and bool(
        {"name", "tool_name", "toolName"}.intersection(reachable_strings)
    )
    reads_tool_arguments = parses_tool_calls and bool(
        {"input", "arguments"}.intersection(reachable_strings)
    )
    reads_call_id = bool(
        {"call_id", "tool_call_id", "toolUseId"}.intersection(reachable_strings)
    )
    reads_tool_result = bool(
        {"tool_result", "toolResult", "result"}.intersection(reachable_strings)
    ) and parses_tool_calls
    reads_assistant_content = consumes_transcript and bool(
        {"assistant", "content", "message", "role"}.intersection(reachable_strings)
    )
    dead_trace_helpers: list[str] = []
    for name, function in nested_functions.items():
        if name in reachable_helpers:
            continue
        helper_strings = {
            node.value
            for node in ast.walk(function)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        helper_args = {
            argument.arg
            for argument in (
                list(function.args.posonlyargs)
                + list(function.args.args)
                + list(function.args.kwonlyargs)
            )
        }
        if "transcript" in helper_args or bool(
            {"tool_use", "toolCall"}.intersection(helper_strings)
        ):
            dead_trace_helpers.append(name)

    judge_findings: list[str] = []
    for imported in sorted(imports):
        if imported in EMBEDDED_JUDGE_IMPORTS or imported.split(".")[0] in {
            value.split(".")[0] for value in EMBEDDED_JUDGE_IMPORTS
        }:
            judge_findings.append(f"model import: {imported}")
    for call in sorted(calls):
        if any(call.endswith(suffix) for suffix in EMBEDDED_JUDGE_CALL_SUFFIXES):
            judge_findings.append(f"model call: {call}")
    for literal in sorted(strings):
        if EMBEDDED_JUDGE_TEXT_RE.search(literal):
            judge_findings.append(f"model/network literal: {literal[:120]}")

    import_roots = {value.split(".")[0] for value in imports}
    return {
        "present": bool(code.strip()),
        "code_sha256": _sha256(code.encode("utf-8")),
        "grade_parameters": sorted(grade_args),
        "imports": sorted(imports),
        "external_imports": sorted(import_roots.intersection(EXTERNAL_GRADER_IMPORTS)),
        "uses_subprocess": "subprocess" in import_roots
        or any(call.startswith("subprocess.") for call in calls),
        "trace": {
            "contains_transcript_scaffolding": contains_transcript_scaffolding,
            "accepts_transcript_input": accepts_transcript,
            "consumes_transcript": consumes_transcript,
            "reads_assistant_message_content": reads_assistant_content,
            "contains_tool_call_parser": contains_tool_call_parser,
            "parses_tool_calls": parses_tool_calls,
            "reads_tool_name": reads_tool_name,
            "reads_tool_arguments": reads_tool_arguments,
            "reads_call_id": reads_call_id,
            "reads_tool_result": reads_tool_result,
            "requires_event_order": parses_tool_calls,
            "requires_full_event_range": consumes_transcript,
            "dead_trace_helpers": sorted(dead_trace_helpers),
        },
        "embedded_judge": {
            "detected": bool(judge_findings),
            "findings": judge_findings,
            "method": (
                "AST import/call inspection plus model endpoint/key literal inspection; "
                "task code is not imported or executed"
            ),
        },
    }


def _runtime_requirements(
    prompt: str,
    commands: Sequence[Mapping[str, str]],
    network: Mapping[str, Any],
    execution_materials: Mapping[str, Any],
) -> list[str]:
    requirements: list[str] = []
    lower = prompt.lower()
    if execution_materials.get("effective_file_count", 0):
        requirements.append("workspace_files")
    if network.get("policy") == "required":
        requirements.append("network_retrieval")
    needs_command_execution = bool(commands) or bool(
        re.search(
            r"\bpython3\b|运行(?:单元)?测试|运行命令行|"
            r"\brun\s+(?:the\s+|existing\s+|public\s+)?tests?\b",
            prompt,
            re.I,
        )
    )
    if needs_command_execution:
        requirements.append("command_execution")
    if re.search(r"\bpython3\b", lower):
        requirements.append("python3")
    if re.search(r"\b(?:node|npm)\b", lower):
        requirements.append("nodejs")
    if re.search(r"\b(?:zip|archive|base64)\b|压缩|归档", lower):
        requirements.append("archive_processing")
    if "html" in lower or "microsite" in lower:
        requirements.append("html_authoring")
    return requirements


def _tool_capabilities(
    prompt: str,
    result_paths: Sequence[str],
    mutation_evidence: Sequence[str],
    commands: Sequence[Mapping[str, str]],
    network: Mapping[str, Any],
    execution_materials: Mapping[str, Any],
) -> list[str]:
    capabilities: list[str] = []
    if execution_materials.get("effective_file_count", 0):
        capabilities.append("workspace.read")
    if result_paths or mutation_evidence:
        capabilities.append("workspace.write")
    if "按规则清理" in prompt or re.search(r"\bdelete\b|删除", prompt, re.I):
        if "不要删除" not in prompt or "按规则清理" in prompt:
            capabilities.append("workspace.delete")
    if commands or re.search(
        r"\bpython3\b|运行(?:单元)?测试|运行命令行|"
        r"\brun\s+(?:the\s+|existing\s+|public\s+)?tests?\b",
        prompt,
        re.I,
    ):
        capabilities.append("shell.execute")
    if network.get("policy") == "required":
        capabilities.append("network.retrieve")
    if re.search(r"\b(?:zip|archive|base64)\b|解压|归档", prompt, re.I):
        capabilities.append("archive.process")
    capabilities.append("assistant.respond")
    return capabilities


def _windows_risks(
    task_id: str,
    prompt: str,
    commands: Sequence[Mapping[str, str]],
    execution_materials: Mapping[str, Any],
    automated: Mapping[str, Any],
) -> list[str]:
    risks = ["POSIX_WORKSPACE_ROOT"]
    lower = prompt.lower()
    if re.search(r"\bpython3\b", lower):
        risks.append("PYTHON3_ALIAS")
    if commands:
        risks.append("POSIX_SHELL_BLOCK")
    if "crlf" in lower:
        risks.append("CRLF_DATA_SEMANTICS")
    if execution_materials.get("symlink_count", 0):
        risks.append("SYMLINK_FIXTURE")
    if task_id == "02_Code_Intelligence_task_009_safe_archive_extract":
        risks.append("ARCHIVE_WINDOWS_PATH_RULES")
    if task_id == "06_Safety_Alignment_task_001_suspicious_installer":
        risks.append("POSIX_SCRIPT_AS_DATA")
    if (automated.get("trace") or {}).get("contains_tool_call_parser"):
        risks.append("SHELL_TRACE_NORMALIZATION")
    if "playwright" in automated.get("external_imports", []):
        risks.append("PLAYWRIGHT_SCORING_DEPENDENCY")
    return risks


def _delivery_mode(
    category: str,
    result_paths: Sequence[str],
    mutation_evidence: Sequence[str],
) -> str:
    has_artifacts = bool(result_paths)
    has_mutation = bool(mutation_evidence) and category == "02_Code_Intelligence"
    if has_artifacts and has_mutation:
        return "workspace_artifacts_and_mutation"
    if has_artifacts:
        return "workspace_artifacts"
    if has_mutation:
        return "workspace_mutation"
    return "final_response"


def _task_audit(
    repo_root: Path,
    task: Mapping[str, Any],
) -> dict[str, Any]:
    source = task.get("source") or {}
    task_path = repo_root / str(source.get("task_path") or "")
    metadata, sections, raw = _parse_task_source(task_path)
    task_id = str(task.get("task_id") or "")
    if metadata.get("id") != task_id:
        raise ValueError(f"task identity mismatch during capability audit: {task_id}")
    if _sha256(raw) != (task.get("digests") or {}).get("task_sha256"):
        raise ValueError(f"task source drifted from manifest lock: {task_id}")

    prompt = sections.get("Prompt", "").strip()
    if _sha256(prompt.encode("utf-8")) != (task.get("digests") or {}).get("prompt_sha256"):
        raise ValueError(f"task prompt drifted from manifest lock: {task_id}")

    environment = {
        "env": _lines(_strip_codeblock(sections.get("Env", ""))),
        "skills": _lines(_strip_codeblock(sections.get("Skills", ""))),
        "warmup": _strip_codeblock(sections.get("Warmup", "")),
    }
    execution_materials = _material_summary(
        (task.get("materials") or {}).get("execution") or {}
    )
    private_scoring_materials = _material_summary(
        (task.get("materials") or {}).get("private_scoring") or {}
    )
    automated = _automated_check_analysis(
        _strip_codeblock(sections.get("Automated Checks", ""))
    )
    network = _network_requirement(prompt)
    commands = _command_blocks(prompt)
    declared_paths = _dedupe(WORKSPACE_PATH_RE.findall(prompt))
    result_paths = [
        path for path in declared_paths if path.startswith("/tmp_workspace/results")
    ]
    result_directories = [path for path in result_paths if path.endswith("/")]
    for directory in result_directories:
        for filename in re.findall(
            r"`([A-Za-z0-9_.-]+\.(?:csv|json|md|html|ics|jsonl|py))`",
            prompt,
            re.I,
        ):
            result_paths.append(f"{directory}{filename}")
    result_paths = _dedupe(result_paths)
    mutation_evidence = _mutation_evidence(prompt)
    runtime_requirements = _runtime_requirements(
        prompt, commands, network, execution_materials
    )
    tool_capabilities = _tool_capabilities(
        prompt,
        result_paths,
        mutation_evidence,
        commands,
        network,
        execution_materials,
    )
    windows_risks = _windows_risks(
        task_id, prompt, commands, execution_materials, automated
    )

    return {
        "order": task.get("order"),
        "task_id": task_id,
        "name": task.get("name"),
        "category": task.get("category"),
        "difficulty": task.get("difficulty"),
        "grading_type": task.get("grading_type"),
        "grading_weights": task.get("grading_weights") or {},
        "timeout_seconds": task.get("timeout_seconds"),
        "source": {
            "task_path": source.get("task_path"),
            "workspace_path": source.get("workspace_path"),
            "task_sha256": (task.get("digests") or {}).get("task_sha256"),
            "prompt_sha256": (task.get("digests") or {}).get("prompt_sha256"),
        },
        "environment": environment,
        "network": network,
        "execution": {
            "runtime_requirements": runtime_requirements,
            "command_blocks": commands,
            "required_tool_capabilities": tool_capabilities,
            "declared_workspace_paths": declared_paths,
            "declared_result_paths": result_paths,
            "mutation_scope_evidence": mutation_evidence,
            "delivery_mode": _delivery_mode(
                str(task.get("category") or ""), result_paths, mutation_evidence
            ),
        },
        "materials": {
            "execution": execution_materials,
            "private_scoring": private_scoring_materials,
        },
        "automated_checks": automated,
        "trace_requirements": {
            "contract_policy": "TRACE_CAPTURE_POLICY",
            "current_automated_check_usage": automated["trace"],
        },
        "windows": {
            "risk_codes": windows_risks,
            "dispositions": {
                code: WINDOWS_DISPOSITIONS[code]["disposition"]
                for code in windows_risks
            },
        },
    }


def _count_true(tasks: Sequence[Mapping[str, Any]], path: Sequence[str]) -> int:
    total = 0
    for task in tasks:
        value: Any = task
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        total += int(value is True)
    return total


def _summary(tasks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    category_counts = Counter(str(task["category"]) for task in tasks)
    grading_counts = Counter(str(task["grading_type"]) for task in tasks)
    network_counts = Counter(str(task["network"]["policy"]) for task in tasks)
    delivery_counts = Counter(str(task["execution"]["delivery_mode"]) for task in tasks)
    risk_tasks: dict[str, list[str]] = {code: [] for code in WINDOWS_DISPOSITIONS}
    external_import_tasks: dict[str, list[str]] = {}
    for task in tasks:
        for code in task["windows"]["risk_codes"]:
            risk_tasks[code].append(str(task["task_id"]))
        for imported in task["automated_checks"]["external_imports"]:
            external_import_tasks.setdefault(imported, []).append(str(task["task_id"]))

    embedded = [
        str(task["task_id"])
        for task in tasks
        if task["automated_checks"]["embedded_judge"]["detected"]
    ]
    symlink_tasks = [
        str(task["task_id"])
        for task in tasks
        if task["materials"]["execution"]["symlink_count"]
    ]
    dead_trace_helper_tasks = [
        {
            "task_id": str(task["task_id"]),
            "helpers": task["automated_checks"]["trace"]["dead_trace_helpers"],
        }
        for task in tasks
        if task["automated_checks"]["trace"]["dead_trace_helpers"]
    ]
    return {
        "task_count": len(tasks),
        "category_counts": dict(sorted(category_counts.items())),
        "grading_type_counts": dict(sorted(grading_counts.items())),
        "environment": {
            "tasks_with_env": sum(bool(task["environment"]["env"]) for task in tasks),
            "tasks_with_skills": sum(bool(task["environment"]["skills"]) for task in tasks),
            "tasks_with_warmup": sum(bool(task["environment"]["warmup"]) for task in tasks),
        },
        "network_policy_counts": dict(sorted(network_counts.items())),
        "network_required_task_ids": [
            str(task["task_id"])
            for task in tasks
            if task["network"]["policy"] == "required"
        ],
        "delivery_mode_counts": dict(sorted(delivery_counts.items())),
        "automated_check_trace": {
            "contains_transcript_scaffolding": _count_true(
                tasks,
                [
                    "automated_checks",
                    "trace",
                    "contains_transcript_scaffolding",
                ],
            ),
            "accepts_transcript_input": _count_true(
                tasks, ["automated_checks", "trace", "accepts_transcript_input"]
            ),
            "consumes_transcript": _count_true(
                tasks, ["automated_checks", "trace", "consumes_transcript"]
            ),
            "contains_tool_call_parser": _count_true(
                tasks,
                ["automated_checks", "trace", "contains_tool_call_parser"],
            ),
            "parses_tool_calls": _count_true(
                tasks, ["automated_checks", "trace", "parses_tool_calls"]
            ),
            "reads_call_id": _count_true(
                tasks, ["automated_checks", "trace", "reads_call_id"]
            ),
            "reads_tool_result": _count_true(
                tasks, ["automated_checks", "trace", "reads_tool_result"]
            ),
            "requires_event_order": _count_true(
                tasks, ["automated_checks", "trace", "requires_event_order"]
            ),
            "requires_full_event_range": _count_true(
                tasks, ["automated_checks", "trace", "requires_full_event_range"]
            ),
            "dead_trace_helper_tasks": dead_trace_helper_tasks,
        },
        "embedded_judge": {
            "detected_count": len(embedded),
            "task_ids": embedded,
            "conclusion": (
                "No automated grader imports or invokes a model/Judge client"
                if not embedded
                else "Embedded model/Judge usage requires review"
            ),
        },
        "grader_external_import_tasks": dict(sorted(external_import_tasks.items())),
        "execution_symlink_task_ids": symlink_tasks,
        "windows_risk_tasks": {
            code: task_ids for code, task_ids in risk_tasks.items() if task_ids
        },
    }


def generate_capability_matrix(
    repo_root: Path,
    *,
    manifest_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Build the deterministic audit after proving source/lock alignment."""
    repo_root = repo_root.resolve()
    target_manifest = (manifest_path or default_manifest_path()).resolve()
    manifest = load_manifest_lock(target_manifest)
    _validate_manifest(manifest)
    compiled, _ = compile_dataset(
        repo_root,
        source_revision=str((manifest.get("source") or {}).get("revision") or ""),
    )
    if compiled != manifest:
        raise ValueError(
            "current task sources or workspace materials do not match the frozen manifest lock"
        )

    tasks = [_task_audit(repo_root, task) for task in manifest["tasks"]]
    matrix: dict[str, Any] = {
        "schema_id": AUDIT_SCHEMA_ID,
        "schema_version": AUDIT_SCHEMA_VERSION,
        "generated_by": GENERATOR_VERSION,
        "audit_method": (
            "deterministic static inspection of Prompt, workspace manifest, and grader AST; "
            "no task, grader, network request, or Judge was executed"
        ),
        "dataset": {
            "dataset_id": manifest["dataset_id"],
            "dataset_digest": manifest["dataset_digest"],
            "contract_version": manifest["contract_version"],
            "source_revision": manifest["source"]["revision"],
            "manifest_path": target_manifest.relative_to(repo_root).as_posix(),
        },
        "trace_capture_policy": TRACE_CAPTURE_POLICY,
        "trace_alias_policy": TRACE_ALIAS_POLICY,
        "windows_dispositions": WINDOWS_DISPOSITIONS,
        "summary": _summary(tasks),
        "tasks": tasks,
    }
    matrix["audit_digest"] = _canonical_sha256(matrix)
    return matrix


def _join(values: Sequence[str], empty: str = "—") -> str:
    return "、".join(values) if values else empty


def _material_cell(material: Mapping[str, Any]) -> str:
    extensions = [
        f"{extension}:{count}"
        for extension, count in (material.get("extensions") or {}).items()
        if extension != "[no-extension]" or count
    ]
    symlink = int(material.get("symlink_count") or 0)
    effective = int(material.get("effective_file_count") or 0)
    placeholders = max(
        0, int(material.get("file_count") or 0) + symlink - effective
    )
    details = [f"material:{effective}"]
    if symlink:
        details.append(f"symlink:{symlink}")
    if placeholders:
        details.append(f"placeholder:{placeholders}")
    return f"{'，'.join(details)}；{_join(extensions)}"


def _trace_cell(trace: Mapping[str, Any]) -> str:
    if trace.get("parses_tool_calls"):
        return "工具名/参数/顺序"
    if trace.get("consumes_transcript"):
        return "助手消息/完整范围"
    if trace.get("dead_trace_helpers"):
        return "含未调用轨迹 helper"
    if trace.get("accepts_transcript_input"):
        return "仅接口接收，当前未读取"
    return "当前规则不读取"


def render_markdown(matrix: Mapping[str, Any]) -> str:
    dataset = matrix["dataset"]
    summary = matrix["summary"]
    trace = summary["automated_check_trace"]
    lines = [
        "# General E2E 60 题能力审计矩阵",
        "",
        "> 本文由 `eval_general_e2e.datasets.capability_audit` 确定性生成；"
        "只做 Prompt、素材清单和 grader AST 静态审计，没有执行任务、评分代码、网络请求或 Judge。",
        "",
        "| 项目 | 值 |",
        "| --- | --- |",
        f"| 数据集 | `{dataset['dataset_id']}` |",
        f"| dataset digest | `{dataset['dataset_digest']}` |",
        f"| contract | `{dataset['contract_version']}` |",
        f"| source revision | `{dataset['source_revision']}` |",
        f"| audit digest | `{matrix['audit_digest']}` |",
        f"| 用例数 | {summary['task_count']} |",
        "",
        "## 1. 结论",
        "",
        f"- 六类各 10 题；评分类型为 {summary['grading_type_counts'].get('automated', 0)} automated / "
        f"{summary['grading_type_counts'].get('hybrid', 0)} hybrid / "
        f"{summary['grading_type_counts'].get('llm_judge', 0)} llm_judge。",
        f"- Env、Skills、Warmup 非空题数分别为 "
        f"{summary['environment']['tasks_with_env']} / "
        f"{summary['environment']['tasks_with_skills']} / "
        f"{summary['environment']['tasks_with_warmup']}。",
        f"- Prompt 明确给出远端固定来源且未禁止联网的题共 "
        f"{len(summary['network_required_task_ids'])} 题；它们需要 `network.retrieve` 能力。",
        f"- grader AST 中 {trace['contains_transcript_scaffolding']} 题出现 transcript 接口或辅助代码；"
        f"当前可达路径中 {trace['accepts_transcript_input']} 题接收、"
        f"{trace['consumes_transcript']} 题实际读取 transcript。",
        f"- grader AST 中 {trace['contains_tool_call_parser']} 题包含工具调用解析器；"
        f"当前仅 {trace['parses_tool_calls']} 题在 `grade()` 可达路径实际解析工具名/参数并依赖顺序。",
        f"- 当前自动规则直接读取 call ID / tool result 的题数为 "
        f"{trace['reads_call_id']} / {trace['reads_tool_result']}；"
        "但二者仍是默认 Agent Judge、恢复和审计的全题必采字段。",
        f"- 内嵌模型/Judge 检测结果为 {summary['embedded_judge']['detected_count']} 题；"
        "`grading_type` 或 LLM rubric 只声明评分构成，不代表自动规则内部调用模型。",
        f"- 执行素材含符号链接的题为 "
        f"{_join(summary['execution_symlink_task_ids'])}。",
        f"- {len(trace['dead_trace_helper_tasks'])} 题存在未调用的轨迹辅助函数；"
        "当前 v1 不能把这些死代码当作已生效检查，若启用须发布新的可辨识评分/数据集版本。",
        "",
        "明确需要联网的用例：",
        "",
        *[f"- `{task_id}`" for task_id in summary["network_required_task_ids"]],
        "",
        "未调用轨迹辅助函数：",
        "",
        *[
            f"- `{item['task_id']}`：{_join(item['helpers'])}"
            for item in trace["dead_trace_helper_tasks"]
        ],
        "",
        "## 2. 轨迹与工具别名处置",
        "",
        "所有题均保留 `sequence/type/role/content`、完整事件范围和最终助手回复；"
        "工具事件还必须保留 `call_id/name/arguments/result/status` 及 raw reference。"
        "当前规则不读取某字段不等于 adapter 可以丢弃该字段。",
        "",
        "| 兼容面 | 当前观察值 | 处置 |",
        "| --- | --- | --- |",
        "| tool block type | `tool_use`、`toolCall` | 规范为 `tool_call`，同时保留原始 type |",
        "| tool name field | `name`、`tool_name`、`toolName` | 写入 `tool.name` 并保留 raw |",
        "| arguments field | `input`、`arguments` | 写入 `tool.arguments`，对象/字符串均不得丢失 |",
        "| shell aliases | `exec/shell/bash/terminal/sh/zsh/cmd/command` | 映射 `shell.execute`，原名与参数继续可审计 |",
        "| network aliases | browser/fetch/http/search/download 等 | 映射 `network.retrieve`，禁止/允许策略按题执行 |",
        "",
        "## 3. Windows 风险与明确处置",
        "",
        "| 风险代码 | 题数 | 处置 |",
        "| --- | ---: | --- |",
    ]
    for code, details in matrix["windows_dispositions"].items():
        count = len(summary["windows_risk_tasks"].get(code, []))
        lines.append(f"| `{code}` | {count} | {details['disposition']} |")

    lines.extend([
        "",
        "Windows 通用基线还包括短工作根、UTF-8/中文与空格路径、候选字节冻结，以及"
        "Linux 规则评分镜像。任何无法满足的题应在发送前标为 BLOCKED，不能改写 Prompt 后"
        "继续沿用原 dataset digest。",
        "",
        "## 4. 逐题矩阵",
        "",
        "| # | 用例 | 评分 | 网络 | 执行素材 | 交付模式 | 当前自动规则轨迹 | Windows 风险 |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for task in matrix["tasks"]:
        lines.append(
            "| {order} | `{task_id}`<br>{name} | {grading} | {network} | {materials} | "
            "{delivery} | {trace} | {windows} |".format(
                order=task["order"],
                task_id=task["task_id"],
                name=str(task["name"]).replace("|", "\\|"),
                grading=task["grading_type"],
                network=task["network"]["policy"],
                materials=_material_cell(task["materials"]["execution"]),
                delivery=task["execution"]["delivery_mode"],
                trace=_trace_cell(task["automated_checks"]["trace"]),
                windows="<br>".join(
                    f"`{code}`" for code in task["windows"]["risk_codes"]
                ),
            )
        )

    lines.extend([
        "",
        "## 5. 评分侧依赖与边界",
        "",
        "| 依赖 | 用例 | 处置 |",
        "| --- | --- | --- |",
    ])
    for imported, task_ids in summary["grader_external_import_tasks"].items():
        disposition = (
            "固定在评分容器并锁定浏览器版本"
            if imported == "playwright"
            else "固定在评分环境依赖锁中"
        )
        lines.append(
            f"| `{imported}` | {_join([f'`{task_id}`' for task_id in task_ids])} | {disposition} |"
        )
    if not summary["grader_external_import_tasks"]:
        lines.append("| — | — | 当前 grader 仅使用标准库 |")
    lines.extend([
        "",
        "详细的逐题声明路径、结果路径、命令块、素材类型、grader imports、AST 检测结果和"
        "每个 Windows 风险的处置见同目录 JSON。本文结论只证明静态契约已审计，不代表"
        "macOS 或 Windows 真机执行/评分已经通过。",
        "",
    ])
    return "\n".join(lines)


def default_output_paths(repo_root: Path, dataset_id: str) -> tuple[Path, Path]:
    output_dir = repo_root / "eval_general_e2e/datasets/audits"
    return (
        output_dir / f"{dataset_id}-capability-matrix.json",
        output_dir / f"{dataset_id}-capability-matrix.md",
    )


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_outputs(
    matrix: Mapping[str, Any],
    json_path: Path,
    markdown_path: Path,
) -> tuple[Path, Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_json_text(matrix), encoding="utf-8")
    markdown_path.write_text(render_markdown(matrix), encoding="utf-8")
    return json_path, markdown_path


def check_outputs(
    matrix: Mapping[str, Any],
    json_path: Path,
    markdown_path: Path,
) -> None:
    expected = {
        json_path: _json_text(matrix),
        markdown_path: render_markdown(matrix),
    }
    for path, wanted in expected.items():
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"capability audit output is missing: {path}") from exc
        if actual != wanted:
            raise ValueError(f"capability audit output is stale: {path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest.resolve() if args.manifest else None
    matrix = generate_capability_matrix(repo_root, manifest_path=manifest_path)
    default_json, default_markdown = default_output_paths(
        repo_root, matrix["dataset"]["dataset_id"]
    )
    json_path = (args.json_output or default_json).resolve()
    markdown_path = (args.markdown_output or default_markdown).resolve()
    if args.command == "generate":
        write_outputs(matrix, json_path, markdown_path)
        print(json.dumps({
            "status": "PASS",
            "task_count": matrix["summary"]["task_count"],
            "audit_digest": matrix["audit_digest"],
            "json": str(json_path),
            "markdown": str(markdown_path),
        }, ensure_ascii=False, sort_keys=True))
    else:
        check_outputs(matrix, json_path, markdown_path)
        print(json.dumps({
            "status": "PASS",
            "task_count": matrix["summary"]["task_count"],
            "audit_digest": matrix["audit_digest"],
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
