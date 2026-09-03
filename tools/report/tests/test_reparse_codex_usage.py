from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "reparse_codex_usage_script",
    Path(__file__).resolve().parents[1] / "scripts/reparse_codex_usage.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _write_run(
    root: Path,
    name: str,
    *,
    harness: str | None,
    request_count: int,
    status_text: str | None = None,
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    (run_dir / "usage.json").write_text(
        json.dumps({
            "request_count": request_count,
            "input_tokens": 7,
            "output_tokens": 3,
            "total_tokens": 10,
        }),
        encoding="utf-8",
    )
    (run_dir / "chat.jsonl").write_text("{}\n", encoding="utf-8")
    if status_text is not None:
        (run_dir / "execution_status.json").write_text(
            status_text, encoding="utf-8"
        )
    elif harness is not None:
        (run_dir / "execution_status.json").write_text(
            json.dumps({"harness": harness}), encoding="utf-8"
        )
    return run_dir


def _usage(run_dir: Path) -> dict:
    return json.loads((run_dir / "usage.json").read_text(encoding="utf-8"))


def _parsed(request_count: int, *, ttft: int | None = None) -> dict:
    return {
        "request_count": request_count,
        "input_tokens": 7,
        "output_tokens": 3,
        "total_tokens": 10,
        "time_to_first_token_ms": ttft,
    }


def test_apply_mixed_root_only_updates_astroncode_and_codex(tmp_path):
    astroncode = _write_run(
        tmp_path, "astroncode-run", harness="AstronCode", request_count=1
    )
    codex = _write_run(tmp_path, "codex-run", harness="codex", request_count=2)
    deepseek = _write_run(
        tmp_path, "deepseek-run", harness="deepseek-harness", request_count=6
    )
    claudecode = _write_run(
        tmp_path, "claudecode-run", harness="claudecode", request_count=109
    )
    calls: list[tuple[Path, str]] = []
    original = _MODULE.reparse_one

    def fake_reparse(run_dir: Path, harness: str):
        calls.append((run_dir, harness))
        if harness == "astroncode":
            return _parsed(8, ttft=1234), True
        return _parsed(9, ttft=5678), False

    _MODULE.reparse_one = fake_reparse
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            result = _MODULE.main([str(tmp_path), "--apply"])
    finally:
        _MODULE.reparse_one = original

    assert result == 0
    assert calls == [(astroncode, "astroncode"), (codex, "codex")]
    assert _usage(astroncode)["request_count"] == 8
    assert _usage(astroncode)["time_to_first_token_ms"] == 1234
    assert _usage(codex)["request_count"] == 9
    assert "time_to_first_token_ms" not in _usage(codex)
    assert _usage(deepseek)["request_count"] == 6
    assert _usage(claudecode)["request_count"] == 109
    assert (astroncode / "usage.json.bak").is_file()
    assert (codex / "usage.json.bak").is_file()
    assert not (deepseek / "usage.json.bak").exists()
    assert not (claudecode / "usage.json.bak").exists()
    assert "支持并扫描 2 个" in output.getvalue()
    assert "claudecode=1, deepseek-harness=1" in output.getvalue()


def test_apply_unsupported_root_fails_without_writing(tmp_path):
    run_dir = _write_run(
        tmp_path, "deepseek-run", harness="deepseek-harness", request_count=6
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = _MODULE.main([str(tmp_path), "--apply"])

    assert result == 2
    assert _usage(run_dir)["request_count"] == 6
    assert not (run_dir / "usage.json.bak").exists()
    assert "deepseek-harness=1" in stdout.getvalue()
    assert "没有发现可安全重解析" in stderr.getvalue()


def test_missing_or_invalid_execution_status_is_skipped(tmp_path):
    missing = _write_run(
        tmp_path, "missing-status", harness=None, request_count=3
    )
    invalid = _write_run(
        tmp_path,
        "invalid-status",
        harness=None,
        request_count=4,
        status_text="not-json",
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = _MODULE.main([str(tmp_path), "--apply"])

    assert result == 2
    assert _usage(missing)["request_count"] == 3
    assert _usage(invalid)["request_count"] == 4
    assert not list(tmp_path.rglob("usage.json.bak"))
    assert "execution_status=2" in stdout.getvalue()


def test_apply_skips_supported_run_when_token_totals_drift(tmp_path):
    run_dir = _write_run(
        tmp_path, "astroncode-run", harness="astroncode", request_count=6
    )
    original = _MODULE.reparse_one

    def fake_reparse(_run_dir: Path, _harness: str):
        parsed = _parsed(0)
        parsed["input_tokens"] = 0
        parsed["output_tokens"] = 0
        parsed["total_tokens"] = 0
        return parsed, True

    _MODULE.reparse_one = fake_reparse
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = _MODULE.main([str(tmp_path), "--apply"])
    finally:
        _MODULE.reparse_one = original

    assert result == 1
    assert _usage(run_dir)["request_count"] == 6
    assert not (run_dir / "usage.json.bak").exists()
    assert "token 漂移 10 -> 0" in stdout.getvalue()
    assert "因 token 漂移未写回" in stderr.getvalue()


def test_dry_run_unsupported_root_is_read_only_and_successful(tmp_path):
    run_dir = _write_run(
        tmp_path, "claudecode-run", harness="claudecode", request_count=11
    )

    assert _MODULE.main([str(tmp_path)]) == 0

    assert _usage(run_dir)["request_count"] == 11
    assert not (run_dir / "usage.json.bak").exists()


def test_reparse_one_uses_explicit_harness_in_astroncode_named_path(tmp_path):
    run_dir = tmp_path / "astroncode-copy" / "codex-run"
    run_dir.mkdir(parents=True)
    (run_dir / "chat.jsonl").write_text("{}\n", encoding="utf-8")

    _parsed_usage, supports_ttft = _MODULE.reparse_one(run_dir, "codex")

    assert supports_ttft is False


def test_reparse_one_rejects_other_harnesses(tmp_path):
    try:
        _MODULE.reparse_one(tmp_path, "deepseek-harness")
    except ValueError as exc:
        assert "不支持重解析 Harness" in str(exc)
    else:
        raise AssertionError("非 Codex/AstronCode Harness 应被拒绝")
