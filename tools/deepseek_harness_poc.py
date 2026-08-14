#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Sequence

from src.agents.deepseek_harness.transcript import DshSessionFormatError, write_conversion


CREDENTIAL_ENV_NAMES = ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY")
OPTIONAL_ENV_NAMES = ("OPENROUTER_BASE_URL",)


def build_docker_command(
    *,
    image: str,
    workspace: Path,
    sessions_dir: Path,
    model: str,
    prompt: str,
    container_name: str,
    reasoning: str = "",
) -> list[str]:
    command = [
        "docker",
        "run",
        "--name",
        container_name,
        "--workdir",
        "/tmp_workspace",
        "--volume",
        f"{workspace}:/tmp_workspace",
        "--volume",
        f"{sessions_dir}:/root/.dsh/sessions",
        "--env",
        f"DSH_MODEL_ID={model}",
    ]
    if reasoning:
        command.extend(["--env", f"DSH_REASONING={reasoning}"])
    for env_name in (*CREDENTIAL_ENV_NAMES, *OPTIONAL_ENV_NAMES):
        command.extend(["--env", env_name])
    command.extend([image, prompt])
    return command


def build_run_manifest(
    *,
    image: str,
    workspace: Path,
    sessions_dir: Path,
    model: str,
    prompt: str,
    container_name: str,
    timeout_seconds: float,
    exit_code: int,
    timed_out: bool,
) -> dict[str, Any]:
    return {
        "format": "wildclawbench-deepseek-harness-poc-run-v1",
        "image": image,
        "workspace": str(workspace),
        "sessions_dir": str(sessions_dir),
        "model": model,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "container_name": container_name,
        "timeout_seconds": timeout_seconds,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "credential_env_names": list(CREDENTIAL_ENV_NAMES),
    }


def _redact_secrets(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    secrets = sorted(
        {os.environ.get(name, "") for name in CREDENTIAL_ENV_NAMES} - {""},
        key=len,
        reverse=True,
    )
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    return text


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_docker(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    output_dir = Path(args.output).expanduser().resolve()
    sessions_dir = output_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    container_name = args.container_name or f"wcb-dsh-poc-{uuid.uuid4().hex[:12]}"
    command = build_docker_command(
        image=args.image,
        workspace=workspace,
        sessions_dir=sessions_dir,
        model=args.model,
        prompt=args.prompt,
        container_name=container_name,
        reasoning=args.reasoning,
    )

    exit_code = 127
    timed_out = False
    stdout = ""
    stderr = ""
    cleanup_error = ""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        timed_out = True
        stdout = exc.stdout or exc.output or ""
        stderr = exc.stderr or ""
    except OSError as exc:
        stderr = str(exc)
    finally:
        try:
            cleanup = subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            if cleanup.returncode != 0:
                cleanup_error = cleanup.stderr or cleanup.stdout
        except OSError as exc:
            cleanup_error = str(exc)

    (output_dir / "dsh.stdout.log").write_text(
        _redact_secrets(stdout), encoding="utf-8"
    )
    (output_dir / "dsh.stderr.log").write_text(
        _redact_secrets(stderr), encoding="utf-8"
    )

    manifest = build_run_manifest(
        image=args.image,
        workspace=workspace,
        sessions_dir=sessions_dir,
        model=args.model,
        prompt=args.prompt,
        container_name=container_name,
        timeout_seconds=args.timeout,
        exit_code=exit_code,
        timed_out=timed_out,
    )
    if cleanup_error:
        manifest["cleanup_error"] = _redact_secrets(cleanup_error)

    if any(sessions_dir.rglob("session.jsonl")):
        try:
            conversion = write_conversion(sessions_dir, output_dir)
            manifest["converted_session_count"] = len(conversion.sessions)
            manifest["converted_message_count"] = len(conversion.messages)
        except DshSessionFormatError as exc:
            manifest["conversion_error"] = _redact_secrets(str(exc))
    else:
        manifest["converted_session_count"] = 0
        manifest["converted_message_count"] = 0

    _write_json(output_dir / "run_manifest.json", manifest)
    return exit_code


def _positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or convert a standalone DeepSeek Harness PoC task."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert_parser = subparsers.add_parser("convert", help="convert DSH session JSONL")
    convert_parser.add_argument("--sessions", type=Path, required=True)
    convert_parser.add_argument("--output", type=Path, required=True)

    run_parser = subparsers.add_parser("run", help="run one DSH Docker task")
    run_parser.add_argument("--image", required=True)
    run_parser.add_argument("--workspace", type=Path, required=True)
    run_parser.add_argument("--model", required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--prompt", required=True)
    run_parser.add_argument("--reasoning", default="")
    run_parser.add_argument("--timeout", type=_positive_float, default=1800.0)
    run_parser.add_argument("--container-name", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "convert":
        write_conversion(args.sessions, args.output)
        return 0
    return _run_docker(args)


if __name__ == "__main__":
    raise SystemExit(main())
