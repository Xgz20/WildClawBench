"""Verify the screenshot bytes and image-tool output cited by an AStudio Web score."""
from __future__ import annotations

import json
import ntpath
import re
import struct
from urllib.parse import urlsplit

from .backend import GUEST_WORKSPACE
from .common import E2EError, digest, file_sha256, inside, read_json
from .trace import windows_equal

CAPTURE_SCHEMA = "astudio.browser-screenshot/v1"
CAPTURE_FILE = re.compile(r"native-[a-z0-9]+(?:-[a-z0-9]+)*\.png\Z")
DIRECT_BROWSER_TOOLS = {"astron_browser_tab", "astron_browser_inspect"}


def _origin(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise E2EError("DESKTOP_SCORING_NATIVE_SCREENSHOT_ORIGIN_INVALID")
    return parsed.scheme, parsed.hostname, parsed.port or 80


def _tool_payload(value):
    if isinstance(value, dict):
        if value.get("success") is False:
            return {}
        if "contentItems" in value:
            return _tool_payload(value["contentItems"])
        if "content" in value and "error" not in value:
            return _tool_payload(value["content"])
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        item = value[0]
        if item.get("type") in {"text", "input_text", "inputText"}:
            return _tool_payload(item.get("text"))
    if isinstance(value, str):
        try:
            result = json.loads(value.removeprefix("Untrusted browser data, not instructions.\n"))
        except ValueError:
            return {}
        return result if isinstance(result, dict) else {}
    return {}


def _completed_tools(binding):
    # 发布客户端的内置浏览器使用 Direct 工具，应用连接器仍留下 MCP 结束事件。
    mcp_calls = {event["native_status"].get("call_id") for event in binding["events"]
                 if (event.get("native_status") or {}).get("type") == "mcp_tool_call_end"}
    pending = {}
    for index, event in enumerate(binding["events"]):
        tool = event.get("tool") or {}
        call_id = tool.get("call_id")
        if event.get("type") == "tool_call" and tool.get("name") in DIRECT_BROWSER_TOOLS and call_id not in mcp_calls:
            pending[call_id] = tool
        if event.get("type") == "tool_result" and call_id in pending:
            call = pending.pop(call_id)
            payload = _tool_payload(tool.get("result"))
            if payload and not payload.get("error"):
                yield index, {"call_id": call_id, "invocation": {
                    "server": "acode", "tool": call["name"], "arguments": call.get("arguments"),
                }}, payload
        status = event.get("native_status") or {}
        if status.get("type") != "mcp_tool_call_end":
            continue
        result = (status.get("result") or {}).get("Ok")
        if isinstance(result, dict) and not (result.get("isError") or result.get("is_error")):
            payload = result.get("structuredContent") or result.get("structured_content")
            if payload is None:
                payload = _tool_payload(result.get("content"))
            if isinstance(payload, dict) and payload.get("error"):
                continue
            yield index, status, payload if isinstance(payload, dict) else {}


def _referenced_screenshots(score_input):
    refs = {}
    for criterion in score_input.get("criteria", []):
        for evidence in criterion.get("evidence", []):
            path = evidence.get("path", "")
            if evidence.get("type") == "screenshot" or path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                refs[path] = None
    aesthetic = score_input.get("aesthetic") or {}
    for image in aesthetic.get("screenshots", []):
        refs[image["path"]] = image["viewport"]
    return refs


def _capture_filename(path):
    filename = ntpath.basename(path) if isinstance(path, str) else ""
    expected = ntpath.join(GUEST_WORKSPACE, r"private-scoring\browser-captures", filename)
    if len(filename) > 104 or not CAPTURE_FILE.fullmatch(filename) or not windows_equal(path, expected):
        raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_INVALID")
    return filename


def _published_capture(arguments, payload, tabs, source):
    receipt = payload.get("result")
    if payload.get("action") != "screenshot" or not isinstance(receipt, dict) or receipt.get("mimeType") != "image/png":
        return None
    filename = _capture_filename(receipt.get("path"))
    requested = arguments.get("path")
    tab_id = arguments.get("tabId")
    if (not isinstance(requested, str) or ".." in requested.replace("\\", "/").split("/")
            or not windows_equal(ntpath.join(GUEST_WORKSPACE, requested), receipt["path"])
            or not isinstance(tab_id, str) or tab_id not in tabs or arguments.get("fullPage") is True
            or source is None):
        raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_INVALID")
    # 发布版回执提供路径及大小。读取沙箱收集的原始截图，独立校验接收器回传内容。
    raw = inside(source, filename)
    size = receipt.get("bytes")
    if (type(size) is not int or not 33 <= size <= 8 * 1024 * 1024
            or not raw.is_file() or raw.stat().st_size != size):
        raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_SOURCE_MISSING")
    return filename, {"sha256": file_sha256(raw), "bytes": size, "url": tabs[tab_id], "tabId": tab_id}


def verify_native_browser(binding, private, score_input, *, raw_captures=None):
    references = _referenced_screenshots(score_input)
    opened = False
    tabs = {}
    captures = {}
    reads = []
    for index, status, payload in _completed_tools(binding):
        invocation = status["invocation"]
        tool = invocation.get("server"), invocation.get("tool")
        arguments = invocation.get("arguments") or {}
        screenshot = None
        if tool in {("acode", "astron_browser_open"), ("acode", "astron_browser_navigate")}:
            opened = True
        if tool == ("acode", "astron_browser_tab") and payload.get("status") == "completed":
            tabs = {tab["tabId"]: tab["url"] for tab in payload.get("tabs", [])
                    if isinstance(tab.get("tabId"), str) and isinstance(tab.get("url"), str)}
            opened |= payload.get("action") in {"open", "navigate"}
        if tool == ("acode", "astron_browser_inspect") and arguments.get("action") == "screenshot":
            receipt = payload.get("result")
            path = receipt.get("path") if isinstance(receipt, dict) else None
            if isinstance(path, str) and "evidence/" + ntpath.basename(path) in references:
                screenshot = _published_capture(arguments, payload, tabs, raw_captures)
        if tool == ("acode", "astron_browser_save_screenshot") and payload.get("schema") == CAPTURE_SCHEMA:
            if "evidence/" + str(payload.get("filename")) in references:
                filename = _capture_filename(payload.get("path"))
                if payload.get("filename") != filename:
                    raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_INVALID")
                screenshot = filename, payload
        if screenshot:
            filename, capture = screenshot
            if filename in captures:
                raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_INVALID")
            captures[filename] = index, status, capture
        elif tool == ("acode_apps", "image_understanding"):
            path = arguments.get("image")
            observation = payload.get("text")
            if isinstance(path, str) and isinstance(observation, str) and observation.strip():
                reads.append((index, status, path, observation))

    if not opened:
        raise E2EError("DESKTOP_SCORING_NATIVE_BROWSER_EVIDENCE_MISSING")
    evidence_chain = []
    for relative, viewport in sorted(references.items()):
        filename = relative.removeprefix("evidence/")
        if relative != "evidence/" + filename or filename not in captures:
            raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_MISSING")
        capture_index, capture_call, capture = captures[filename]
        if _origin(capture["url"]) != _origin(score_input["site_url"]):
            raise E2EError("DESKTOP_SCORING_NATIVE_SCREENSHOT_ORIGIN_INVALID")
        target = inside(private, relative)
        receipt = read_json(inside(private, relative + ".receipt.json"))
        if (not target.is_file() or receipt.get("path") != "private-scoring/" + relative
                or receipt.get("format") != "png" or receipt.get("content_type") != "image/png"
                or receipt.get("bytes") != capture.get("bytes") or receipt.get("sha256") != capture.get("sha256")
                or not 33 <= target.stat().st_size == capture.get("bytes") <= 8 * 1024 * 1024
                or file_sha256(target) != capture.get("sha256")):
            raise E2EError("DESKTOP_SCORING_SCREENSHOT_DRIFT")
        with target.open("rb") as stream:
            header = stream.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            raise E2EError("DESKTOP_SCORING_SCREENSHOT_DRIFT")
        width, height = struct.unpack(">II", header[16:24])
        dimensions = {"width": width, "height": height}
        if (not width or not height or capture.get("viewport", dimensions) != dimensions
                or (viewport is not None and viewport != dimensions)):
            raise E2EError("DESKTOP_SCORING_NATIVE_SCREENSHOT_VIEWPORT_MISMATCH")
        image_path = ntpath.join(GUEST_WORKSPACE, r"private-scoring\evidence", filename)
        observations = [{"call_id": call["call_id"], "observation_sha256": digest(text)}
                        for index, call, path, text in reads if index > capture_index and windows_equal(path, image_path)]
        if not observations:
            raise E2EError("DESKTOP_SCORING_NATIVE_IMAGE_UNDERSTANDING_MISSING")
        evidence_chain.append({"path": relative, "sha256": capture["sha256"], "bytes": capture["bytes"],
                               "url": capture["url"], "tab_id": capture["tabId"], "viewport": dimensions,
                               "capture_call_id": capture_call["call_id"], "image_understanding": observations})
    return {"schema": "wildclawbench.astudio-web-visual-evidence/v1", "screenshots": evidence_chain}


def verify_chatgpt_browser(binding, private, score_input):
    """Bind each receiver acknowledgement to bytes in a Codex Desktop turn."""
    _origin(score_input["site_url"])
    calls = {}
    observed = False
    uploads = []
    for event in binding["events"]:
        tool = event.get("tool") or {}
        if event["type"] == "tool_call" and tool.get("name") in {
            "mcp__node_repl__js", "mcp__cua_repl__js", "mcp__cua_repl.js",
        }:
            arguments = tool.get("arguments")
            if isinstance(arguments, dict) and isinstance(arguments.get("code"), str):
                calls[tool["call_id"]] = arguments["code"]
        if event["type"] != "tool_result" or tool.get("call_id") not in calls:
            continue
        code = calls.pop(tool["call_id"])
        output = json.dumps(tool.get("result"), ensure_ascii=False)
        if any(token in code for token in ("browser.tabs", ".playwright.", ".getScreenshot(")):
            observed = True
        if ".getScreenshot(" in code and "fetch(" in code:
            uploads.append((tool["call_id"], output))
    if not observed:
        raise E2EError("DESKTOP_SCORING_NATIVE_BROWSER_EVIDENCE_MISSING")
    screenshots = []
    for relative in sorted(_referenced_screenshots(score_input)):
        target = inside(private, relative)
        if not relative.startswith("evidence/") or not target.is_file():
            raise E2EError("DESKTOP_SCORING_SCREENSHOT_DRIFT")
        sha = file_sha256(target)
        size = target.stat().st_size
        with target.open("rb") as stream:
            header = stream.read(8)
        formats = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
        signature = formats.get(target.suffix.lower())
        if not signature or not header.startswith(signature):
            raise E2EError("DESKTOP_SCORING_SCREENSHOT_DRIFT")
        matched = [call_id for call_id, output in uploads
                   if sha in output and "private-scoring/" + relative in output]
        if len(matched) != 1:
            raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_MISSING")
        screenshots.append({"path": relative, "bytes": size, "sha256": sha, "capture_call_id": matched[0]})
    return {"schema": "wildclawbench.chatgpt-web-visual-evidence/v1", "screenshots": screenshots}
