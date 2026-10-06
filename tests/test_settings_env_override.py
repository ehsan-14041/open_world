"""
Regression: env overrides documented as OWE_<KEY> must actually take effect.

`config/settings._from_env` namespaces keys as OWE_<KEY>. One caller passed an
already-namespaced key ("OWE_PRODUCT_MODE"), which produced a lookup for
OWE_OWE_PRODUCT_MODE — so the documented `OWE_PRODUCT_MODE=true` override, which gates the
enterprise product-mode SKU, silently did nothing. These tests pin both spellings.
"""

from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch


def _reload_settings():
    import config.settings as settings

    return importlib.reload(settings)


class TestEnvOverrideNamespacing(unittest.TestCase):
    def tearDown(self) -> None:
        _reload_settings()  # restore process-wide settings for other tests

    def test_bare_key_resolves_to_namespaced_variable(self) -> None:
        import config.settings as settings

        with patch.dict(os.environ, {"OWE_DRY_RUN": "true"}, clear=False):
            reloaded = _reload_settings()
            self.assertEqual(reloaded._from_env("DRY_RUN"), "true")

    def test_prefixed_key_is_not_double_namespaced(self) -> None:
        with patch.dict(os.environ, {"OWE_PRODUCT_MODE": "false"}, clear=False):
            reloaded = _reload_settings()
            self.assertEqual(reloaded._from_env("OWE_PRODUCT_MODE"), "false")
            self.assertEqual(reloaded._from_env("PRODUCT_MODE"), "false")

    def test_product_mode_env_override_takes_effect(self) -> None:
        """The documented override must beat config/settings.json in both directions."""
        with patch.dict(os.environ, {"OWE_PRODUCT_MODE": "false"}, clear=False):
            self.assertFalse(_reload_settings().PRODUCT_MODE)
        with patch.dict(os.environ, {"OWE_PRODUCT_MODE": "true"}, clear=False):
            self.assertTrue(_reload_settings().PRODUCT_MODE)

    def test_double_prefixed_variable_no_longer_resolves(self) -> None:
        """OWE_OWE_PRODUCT_MODE was never documented; it must not be honoured."""
        env = {"OWE_OWE_PRODUCT_MODE": "false"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("OWE_PRODUCT_MODE", None)
            self.assertIsNone(_reload_settings()._from_env("OWE_PRODUCT_MODE"))

    def test_explicit_env_key_argument_is_respected(self) -> None:
        with patch.dict(os.environ, {"OWE_DEBUG_PERF": "1"}, clear=False):
            reloaded = _reload_settings()
            self.assertEqual(reloaded._from_env("DEBUG_PERF", "OWE_DEBUG_PERF"), "1")

    def test_falls_back_to_config_file_when_unset(self) -> None:
        env_keys = ("OWE_PRODUCT_MODE", "OWE_OWE_PRODUCT_MODE")
        saved = {k: os.environ.pop(k, None) for k in env_keys}
        try:
            reloaded = _reload_settings()
            self.assertIsInstance(reloaded.PRODUCT_MODE, bool)
            self.assertIsNone(reloaded._from_env("PRODUCT_MODE"))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
