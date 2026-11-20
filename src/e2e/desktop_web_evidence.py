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
CAPTURE_FILE = re.compile(r"native-[0-9a-f-]{36}-[a-z0-9]+(?:-[a-z0-9]+)*\.png\Z")


def _origin(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise E2EError("DESKTOP_SCORING_NATIVE_SCREENSHOT_ORIGIN_INVALID")
    return parsed.scheme, parsed.hostname, parsed.port or 80


def _completed_tools(binding):
    for index, event in enumerate(binding["events"]):
        status = event.get("native_status") or {}
        if status.get("type") != "mcp_tool_call_end":
            continue
        result = (status.get("result") or {}).get("Ok")
        if isinstance(result, dict) and not (result.get("isError") or result.get("is_error")):
            payload = result.get("structuredContent") or result.get("structured_content")
            if payload is None:
                content = result.get("content") or []
                if len(content) == 1 and content[0].get("type") == "text":
                    try:
                        payload = json.loads(content[0].get("text", ""))
                    except (TypeError, ValueError):
                        pass
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


def verify_native_browser(binding, private, score_input):
    tools = list(_completed_tools(binding))
    if not any(status["invocation"].get("server") == "acode"
               and status["invocation"].get("tool") in {"astron_browser_open", "astron_browser_navigate"}
               for _, status, _ in tools):
        raise E2EError("DESKTOP_SCORING_NATIVE_BROWSER_EVIDENCE_MISSING")

    captures = {}
    reads = []
    for index, status, payload in tools:
        invocation = status["invocation"]
        tool = invocation.get("server"), invocation.get("tool")
        if tool == ("acode", "astron_browser_save_screenshot") and payload.get("schema") == CAPTURE_SCHEMA:
            filename = payload.get("filename", "")
            if (not isinstance(filename, str) or not CAPTURE_FILE.fullmatch(filename) or filename in captures
                    or not isinstance(payload.get("path"), str) or not windows_equal(
                        payload["path"], ntpath.join(GUEST_WORKSPACE, r"private-scoring\browser-captures", filename))):
                raise E2EError("DESKTOP_SCORING_NATIVE_CAPTURE_INVALID")
            captures[filename] = index, status, payload
        elif tool == ("acode_apps", "image_understanding"):
            path = (invocation.get("arguments") or {}).get("image")
            observation = payload.get("text")
            if isinstance(path, str) and isinstance(observation, str) and observation.strip():
                reads.append((index, status, path, observation))

    evidence_chain = []
    for relative, viewport in sorted(_referenced_screenshots(score_input).items()):
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
        if not width or not height or capture.get("viewport") != dimensions or (viewport is not None and viewport != dimensions):
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
