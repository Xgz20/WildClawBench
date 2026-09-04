from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

from src.utils.model_limits import (
    MODEL_LIMIT_RESOLUTION_FILENAME,
    clear_model_limit_caches,
    is_maas_model,
    prepare_maas_max_tokens_resolution,
    resolve_maas_max_tokens,
    resolve_maas_max_tokens_details,
)


class _Response:
    def __init__(self, payload: object) -> None:
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.raw


class ModelLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_model_limit_caches()
        self.environ = {
            "ASTRON_MODELS_BASE_URL": "https://catalog.example/model-manager",
            "ASTRON_MODELS_API_KEY": "catalog-test-token",
        }

    def tearDown(self) -> None:
        clear_model_limit_caches()

    @staticmethod
    def _payload(*models: dict[str, object]) -> dict[str, object]:
        return {"code": 0, "data": {"models": list(models)}}

    def test_catalog_value_replaces_fixed_default(self) -> None:
        payload = self._payload(
            {"slug": "xopglm52", "max_output_tokens": 128000}
        )
        with patch(
            "src.utils.model_limits.urlopen", return_value=_Response(payload)
        ) as open_url:
            details = resolve_maas_max_tokens_details(
                "openrouter/xopglm52",
                "https://maas-api.example/v1",
                environ=self.environ,
            )

        self.assertEqual(details["max_tokens"], 128000)
        self.assertEqual(details["source"], "astron_model_catalog")
        self.assertEqual(details["status"], "resolved")
        request = open_url.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://catalog.example/model-manager/models",
        )
        self.assertEqual(
            request.get_header("Authorization"),
            "Bearer catalog-test-token",
        )

    def test_switch_defaults_enabled_and_false_disables_injection(self) -> None:
        disabled = {**self.environ, "WILDCLAW_MAAS_MAX_TOKENS_ENABLED": "false"}
        with patch("src.utils.model_limits.urlopen") as open_url:
            details = resolve_maas_max_tokens_details(
                "xopglm52",
                "https://maas-api.example/v1",
                environ=disabled,
            )

        self.assertFalse(details["enabled"])
        self.assertEqual(details["status"], "disabled")
        self.assertIsNone(details["max_tokens"])
        open_url.assert_not_called()

    def test_explicit_value_has_priority_and_invalid_value_uses_catalog(self) -> None:
        explicit = {**self.environ, "MAAS_MAX_TOKENS": "8192"}
        with patch("src.utils.model_limits.urlopen") as open_url:
            details = resolve_maas_max_tokens_details(
                "xopglm52",
                "https://maas-api.example/v1",
                environ=explicit,
            )
        self.assertEqual(details["max_tokens"], 8192)
        self.assertEqual(details["source"], "explicit_env")
        open_url.assert_not_called()

        payload = self._payload(
            {"slug": "xopglm52", "max_output_tokens": 128000}
        )
        clear_model_limit_caches()
        invalid = {**self.environ, "MAAS_MAX_TOKENS": "invalid"}
        with patch(
            "src.utils.model_limits.urlopen", return_value=_Response(payload)
        ):
            details = resolve_maas_max_tokens_details(
                "xopglm52",
                "https://maas-api.example/v1",
                environ=invalid,
            )
        self.assertEqual(details["max_tokens"], 128000)
        self.assertEqual(details["override_status"], "invalid")

    def test_missing_model_or_limit_does_not_inject(self) -> None:
        cases = (
            (self._payload({"slug": "other", "max_output_tokens": 4096}), "model_not_found"),
            (self._payload({"slug": "xopglm52"}), "max_output_tokens_missing"),
        )
        for payload, status in cases:
            with self.subTest(status=status):
                clear_model_limit_caches()
                with patch(
                    "src.utils.model_limits.urlopen", return_value=_Response(payload)
                ):
                    details = resolve_maas_max_tokens_details(
                        "xopglm52",
                        "https://maas-api.example/v1",
                        environ=self.environ,
                    )
                self.assertEqual(details["status"], status)
                self.assertIsNone(details["max_tokens"])

    def test_catalog_failure_or_missing_credentials_does_not_inject(self) -> None:
        with patch(
            "src.utils.model_limits.urlopen", side_effect=URLError("unavailable")
        ):
            details = resolve_maas_max_tokens_details(
                "xopglm52",
                "https://maas-api.example/v1",
                environ=self.environ,
            )
        self.assertEqual(details["status"], "catalog_unavailable")
        self.assertIsNone(details["max_tokens"])

        clear_model_limit_caches()
        details = resolve_maas_max_tokens_details(
            "xopglm52",
            "https://maas-api.example/v1",
            environ={"ASTRON_MODELS_BASE_URL": "https://catalog.example"},
        )
        self.assertEqual(details["status"], "catalog_credentials_missing")
        self.assertIsNone(details["max_tokens"])

    def test_catalog_is_fetched_once_across_concurrent_resolutions(self) -> None:
        payload = self._payload(
            {"slug": "xopglm52", "max_output_tokens": 128000}
        )
        calls = 0
        calls_lock = threading.Lock()

        def fake_open(*_args: object, **_kwargs: object) -> _Response:
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.01)
            return _Response(payload)

        with patch("src.utils.model_limits.urlopen", side_effect=fake_open):
            with ThreadPoolExecutor(max_workers=8) as executor:
                values = list(
                    executor.map(
                        lambda _: resolve_maas_max_tokens(
                            "xopglm52",
                            "https://maas-api.example/v1",
                            environ=self.environ,
                        ),
                        range(8),
                    )
                )

        self.assertEqual(values, [128000] * 8)
        self.assertEqual(calls, 1)

    def test_resume_reuses_non_secret_snapshot(self) -> None:
        payload = self._payload(
            {"slug": "xopglm52", "max_output_tokens": 128000}
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "src.utils.model_limits.urlopen", return_value=_Response(payload)
        ):
            output_root = Path(temp_dir)
            first = prepare_maas_max_tokens_resolution(
                "openrouter/xopglm52",
                "https://maas-api.example/v1",
                output_root,
                environ=self.environ,
            )
            clear_model_limit_caches()
            with patch("src.utils.model_limits.urlopen") as open_url:
                resumed = prepare_maas_max_tokens_resolution(
                    "openrouter/xopglm52",
                    "https://maas-api.example/v1",
                    output_root,
                    resume=True,
                    environ=self.environ,
                )
                effective = resolve_maas_max_tokens(
                    "openrouter/xopglm52",
                    "https://maas-api.example/v1",
                    environ=self.environ,
                )

            snapshot = json.loads(
                (output_root / MODEL_LIMIT_RESOLUTION_FILENAME).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(first["max_tokens"], 128000)
        self.assertTrue(resumed["reused_from_snapshot"])
        self.assertEqual(effective, 128000)
        self.assertNotIn("catalog-test-token", json.dumps(snapshot))
        open_url.assert_not_called()

    def test_snapshot_redacts_catalog_url_credentials_and_query(self) -> None:
        environ = {
            "ASTRON_MODELS_BASE_URL": (
                "https://user:password@catalog.example/model-manager"
                "?token=query-secret"
            ),
            "MAAS_MAX_TOKENS": "8192",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            resolution = prepare_maas_max_tokens_resolution(
                "xopglm52",
                "https://maas-api.example/v1",
                Path(temp_dir),
                environ=environ,
            )

        serialized = json.dumps(resolution)
        self.assertEqual(
            resolution["catalog_url"],
            "https://catalog.example/model-manager/models",
        )
        for secret in ("user", "password", "query-secret"):
            self.assertNotIn(secret, serialized)

    def test_non_maas_model_is_unchanged(self) -> None:
        self.assertFalse(is_maas_model("openrouter/gpt-5.5", "https://openrouter.ai/api/v1"))
        self.assertIsNone(
            resolve_maas_max_tokens(
                "openrouter/gpt-5.5",
                "https://openrouter.ai/api/v1",
                environ={"MAAS_MAX_TOKENS": "8192"},
            )
        )

    def test_generic_iflytek_endpoint_does_not_mark_gpt_as_maas(self) -> None:
        self.assertFalse(
            is_maas_model(
                "openrouter/gpt-5.5",
                "https://one.iflytek.com/api/llm/console/chat/v1",
            )
        )


if __name__ == "__main__":
    unittest.main()
