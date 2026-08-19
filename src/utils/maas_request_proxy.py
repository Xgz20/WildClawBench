#!/usr/bin/env python3
"""Streaming HTTP proxy that injects MaaS candidate output limits.

This script runs inside Harness containers whose native client cannot express
the MaaS ``max_tokens`` request field.  It deliberately logs only limit/status
metadata; request headers, prompts, responses, and credentials are never
persisted.
"""

from __future__ import annotations

import argparse
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def inject_max_tokens(body: bytes, max_tokens: int) -> tuple[bytes, object]:
    """Return a JSON request body with the configured MaaS limit."""

    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("MaaS request body must be a JSON object")
    previous = payload.get("max_tokens")
    payload["max_tokens"] = max_tokens
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        previous,
    )


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def write(self, record: dict[str, Any]) -> None:
        record = {"timestamp": time.time(), **record}
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")


class MaasProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        upstream_base_url: str,
        max_tokens: int,
        audit_log: AuditLog,
    ) -> None:
        super().__init__(address, MaasProxyHandler)
        upstream = urlsplit(upstream_base_url.rstrip("/"))
        if upstream.scheme not in {"http", "https"} or not upstream.hostname:
            raise ValueError("upstream base URL must use http or https")
        self.upstream = upstream
        self.max_tokens = max_tokens
        self.audit_log = audit_log


class MaasProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: MaasProxyServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._forward()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._forward()

    def _forward(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length else b""
        previous_limit: object = None
        injected = False
        if self.command == "POST" and body:
            try:
                body, previous_limit = inject_max_tokens(body, self.server.max_tokens)
                injected = True
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self.server.audit_log.write(
                    {
                        "event": "request_rejected",
                        "method": self.command,
                        "path": self.path,
                        "error": type(exc).__name__,
                    }
                )
                self.send_error(400, "MaaS proxy requires a JSON object request body")
                return

        upstream_path = self.server.upstream.path.rstrip("/") + self.path
        upstream_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
            and key.lower() not in {"host", "content-length"}
        }
        connection_type = (
            http.client.HTTPSConnection
            if self.server.upstream.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_type(
            self.server.upstream.hostname,
            self.server.upstream.port,
            timeout=600,
        )
        response: http.client.HTTPResponse | None = None
        try:
            connection.request(self.command, upstream_path, body=body or None, headers=upstream_headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                lower_key = key.lower()
                if lower_key in HOP_BY_HOP_HEADERS or lower_key == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = response.read1(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            self.close_connection = True
            self.server.audit_log.write(
                {
                    "event": "request_completed",
                    "method": self.command,
                    "path": self.path,
                    "injected": injected,
                    "previous_max_tokens": previous_limit,
                    "effective_max_tokens": self.server.max_tokens if injected else None,
                    "status": response.status,
                }
            )
        except (BrokenPipeError, ConnectionError, OSError) as exc:
            self.server.audit_log.write(
                {
                    "event": "request_failed",
                    "method": self.command,
                    "path": self.path,
                    "injected": injected,
                    "previous_max_tokens": previous_limit,
                    "effective_max_tokens": self.server.max_tokens if injected else None,
                    "error": type(exc).__name__,
                }
            )
            if response is None:
                self.send_error(502, "MaaS upstream request failed")
        finally:
            connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--upstream-base-url", required=True)
    parser.add_argument("--max-tokens", type=int, required=True)
    parser.add_argument("--audit-log", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_tokens <= 0:
        raise ValueError("max tokens must be positive")
    server = MaasProxyServer(
        (args.host, args.port),
        args.upstream_base_url,
        args.max_tokens,
        AuditLog(args.audit_log),
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
