from __future__ import annotations

import unittest

from src.utils.model_limits import (
    DEFAULT_MAAS_MAX_TOKENS,
    is_maas_model,
    resolve_maas_max_tokens,
)


class ModelLimitTests(unittest.TestCase):
    def test_maas_model_defaults_to_4096(self) -> None:
        self.assertTrue(is_maas_model("openrouter/xopglm52", "https://openrouter.ai/api/v1"))
        self.assertEqual(
            resolve_maas_max_tokens(
                "openrouter/xopglm52",
                "https://openrouter.ai/api/v1",
                environ={},
            ),
            DEFAULT_MAAS_MAX_TOKENS,
        )

    def test_explicit_value_is_forwarded_and_invalid_value_falls_back(self) -> None:
        self.assertEqual(
            resolve_maas_max_tokens(
                "glm-custom",
                "https://maas-api.example/v1",
                environ={"MAAS_MAX_TOKENS": "8192"},
            ),
            8192,
        )
        for raw in ("", "0", "-1", "not-an-int"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    resolve_maas_max_tokens(
                        "glm-custom",
                        "https://maas-api.example/v1",
                        environ={"MAAS_MAX_TOKENS": raw},
                    ),
                    DEFAULT_MAAS_MAX_TOKENS,
                )

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
