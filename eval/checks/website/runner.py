from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def build_start_command() -> list[str]:
    return ["npm", "run", "start", "--", "--host", "127.0.0.1", "--port", "4173"]


def browser_context_options() -> dict:
    return {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}


def canvas_text_capture_script() -> str:
    return """(() => {
        if (window.__wildclawbenchCanvasCaptureInstalled) return;
        window.__wildclawbenchCanvasCaptureInstalled = true;
        const proto = CanvasRenderingContext2D.prototype;
        const originalFillText = proto.fillText;
        const originalStrokeText = proto.strokeText;
        const originalClearRect = proto.clearRect;
        const remember = (context, value) => {
            const canvas = context.canvas;
            if (!Array.isArray(canvas.__wildclawbenchRenderedTexts)) {
                canvas.__wildclawbenchRenderedTexts = [];
            }
            canvas.__wildclawbenchRenderedTexts.push(String(value));
        };
        proto.fillText = function(value, ...args) {
            remember(this, value);
            return originalFillText.call(this, value, ...args);
        };
        proto.strokeText = function(value, ...args) {
            remember(this, value);
            return originalStrokeText.call(this, value, ...args);
        };
        proto.clearRect = function(...args) {
            this.canvas.__wildclawbenchRenderedTexts = [];
            return originalClearRect.apply(this, args);
        };
    })();"""


def evaluator_errors(checks: dict) -> list[dict[str, str]]:
    return [
        {"key": key, "error": str(value.get("error", ""))}
        for key, value in checks.items()
        if isinstance(value, dict) and value.get("status") == "evaluator_error"
    ]


async def capture_visual_evidence(module, page, screenshot_dir: Path) -> tuple[list[dict], list[dict[str, str]]]:
    capture_visual = getattr(module, "capture_visual", None)
    if not callable(capture_visual):
        return [], []
    try:
        return await capture_visual(page, screenshot_dir), []
    except Exception as exc:
        return [], [{
            "key": "__visual_capture__",
            "error": f"{type(exc).__name__}: {exc}",
        }]


def _run_command(command: list[str], cwd: Path, log_path: Path, timeout: float) -> None:
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")


def _wait_for_server(process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited with code {process.returncode}")
        try:
            with urllib.request.urlopen("http://127.0.0.1:4173", timeout=1) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError("server did not become ready within 30 seconds")


async def _run_browser(module, output_dir: Path) -> dict:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise RuntimeError(f"PLAYWRIGHT_UNAVAILABLE: {exc}") from exc

    screenshots = output_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    console_events: list[dict] = []
    network_events: list[dict] = []
    page_errors: list[str] = []
    visual_manifest: list[dict] = []
    visual_errors: list[dict[str, str]] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(**browser_context_options())
        await context.add_init_script(script=canvas_text_capture_script())
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)

        async def route_handler(route):
            url = route.request.url
            allowed = url.startswith((
                "http://127.0.0.1:4173",
                "http://localhost:4173",
                "data:", "blob:", "about:",
            ))
            if allowed:
                await route.continue_()
            else:
                network_events.append({"url": url, "method": route.request.method, "blocked": True})
                await route.abort("blockedbyclient")

        await context.route("**/*", route_handler)
        page = await context.new_page()
        page.on("console", lambda message: console_events.append({"type": message.type, "text": message.text}))
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        try:
            checks = await module.run(page, screenshots)
            visual_manifest, visual_errors = await capture_visual_evidence(
                module, page, screenshots
            )
        finally:
            await context.tracing.stop(path=str(output_dir / "trace.zip"))
            await context.close()
            await browser.close()

    (output_dir / "console.json").write_text(json.dumps(console_events, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "network.json").write_text(json.dumps(network_events, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "page-errors.json").write_text(json.dumps(page_errors, ensure_ascii=False, indent=2), encoding="utf-8")
    check_errors = evaluator_errors(checks) + visual_errors
    return {
        "checks": checks,
        "screenshots": visual_manifest,
        "evaluator_errors": check_errors,
        "console_error_count": sum(item["type"] == "error" for item in console_events),
        "page_error_count": len(page_errors),
        "blocked_network_count": len(network_events),
    }


def _write_summary(output_dir: Path, payload: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-module", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"task_id": args.task_id, "status": "evaluator_failed", "checks": {}, "screenshots": []}
    server = None
    try:
        package_json = workspace / "package.json"
        if not package_json.is_file():
            raise RuntimeError("WEB_BUILD_FAILED: package.json is missing")
        if not (workspace / "node_modules").is_dir():
            try:
                _run_command(["npm", "install"], workspace, output_dir / "npm-install.log", 180)
            except Exception as exc:
                raise RuntimeError(f"WEB_BUILD_FAILED: npm install failed: {exc}") from exc
        try:
            _run_command(["npm", "run", "build"], workspace, output_dir / "build.log", 180)
        except Exception as exc:
            raise RuntimeError(f"WEB_BUILD_FAILED: {exc}") from exc

        server_log = (output_dir / "server.log").open("w", encoding="utf-8")
        server = subprocess.Popen(
            build_start_command(),
            cwd=workspace,
            stdout=server_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            _wait_for_server(server)
        except Exception as exc:
            raise RuntimeError(f"WEB_START_FAILED: {exc}") from exc

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        module = importlib.import_module(f"tasks.{args.task_module}")
        result = asyncio.run(_run_browser(module, output_dir))
        payload.update(result)
        if result.get("evaluator_errors"):
            payload["status"] = "evaluator_failed"
            keys = ", ".join(item["key"] for item in result["evaluator_errors"])
            payload["error"] = f"EVALUATOR_CHECK_FAILED: {keys}"
        else:
            payload["status"] = "success"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        payload["error"] = error
        if "WEB_BUILD_FAILED:" in error or "WEB_START_FAILED:" in error:
            payload["status"] = "candidate_failed"
    finally:
        if server is not None:
            try:
                os.killpg(server.pid, 15)
                server.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(server.pid, 9)
                except Exception:
                    pass
        _write_summary(output_dir, payload)
        print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["status"] in {"success", "candidate_failed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
