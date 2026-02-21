"""
Tests for text-first cognitive architecture: world summarizer, LLM action guard,
and that malformed JSON does not crash the system.
"""

import re
import unittest

from core.world_summarizer import (
    summarize,
    world_brief_qualitative,
    detect_language,
    strip_digits,
    bucket_numeric,
    fa_label_for_key,
)
from core.llm_action_guard import LLMActionGuard
from simulation.loop import _parse_reasoning_from_output as loop_parse_reasoning


class TestWorldSummarizer(unittest.TestCase):
    """Test world_summarizer.summarize()."""

    def test_summarize_includes_variables_and_turn(self):
        """Legacy behavior: qualitative=False to get raw k:v and turn."""
        state = {
            "variables": {"cash": 100000, "runway_months": 18, "growth": 11},
            "global_state": {"cash": 100000, "runway_months": 18, "growth": 11},
            "turn": 2,
            "version": 2,
        }
        text = summarize(state, qualitative=False)
        self.assertIn("cash", text)
        self.assertIn("100000", text)
        self.assertIn("Turn: 2", text)

    def test_summarize_includes_derived_and_narrative(self):
        """Legacy behavior: qualitative=False for raw derived numbers."""
        state = {
            "variables": {"cash": 50},
            "derived": {"system_stability": 70, "dissatisfaction": 30, "instability_mode": False},
            "narrative": ["Event A happened.", "Event B happened."],
            "turn": 1,
        }
        text = summarize(state, qualitative=False)
        self.assertIn("70", text)
        self.assertIn("30", text)
        self.assertIn("Recent:", text)

    def test_qualitative_allow_numbers_false_has_no_digits(self):
        """When allow_numbers=False, output must not contain [0-9]."""
        state = {
            "variables": {"x": 0.3, "y": 0.8, "z": 0.5},
            "turn": 1,
        }
        text = world_brief_qualitative(state, allow_numbers=False)
        self.assertFalse(re.search(r"[0-9]", text), f"Output should have no digits: {text!r}")

    def test_qualitative_output_contains_persian_when_lang_fa(self):
        """When lang=fa, qualitative World Brief contains at least one Persian character."""
        state = {"variables": {"a": 0.5}, "turn": 0}
        text = world_brief_qualitative(state, allow_numbers=False, lang="fa")
        has_persian = any("\u0600" <= c <= "\u06FF" for c in text)
        self.assertTrue(has_persian, f"Output should contain Persian: {text!r}")

    def test_domain_agnostic_generic_keys(self):
        """Works with arbitrary keys (e.g. x, y, z) without hardcoded mappings. No digits in output."""
        state = {"variables": {"x": 10, "y": 20, "z": 30}, "turn": 0}
        for lang in ("en", "fa"):
            text = summarize(state, qualitative=True, allow_numbers=False, lang=lang)
            self.assertFalse(re.search(r"[0-9]", text), f"Output (lang={lang}) should have no digits: {text!r}")
            self.assertIn("x", text or "")

    def test_detect_language(self):
        self.assertEqual(detect_language("hello"), "en")
        self.assertEqual(detect_language("در آغاز"), "fa")
        self.assertEqual(detect_language(""), "en")

    def test_strip_digits(self):
        self.assertEqual(strip_digits("Turn 2 and 3.5", allow_numbers=False), "Turn and")
        self.assertEqual(strip_digits("Turn 2", allow_numbers=True), "Turn 2")

    def test_bucket_numeric(self):
        level, trend = bucket_numeric(0.5, {"min": 0, "max": 1}, history=None)
        self.assertIn(level, ("کم", "متوسط", "زیاد", "خیلی کم", "خیلی زیاد", "پایین", "بالا", "بسیار پایین", "بسیار بالا"))

    def test_fa_label_for_key(self):
        self.assertEqual(fa_label_for_key("foo_bar", None), "foo bar")
        self.assertEqual(fa_label_for_key("x", {"x": "مقدار ایکس"}), "مقدار ایکس")


class TestLLMActionGuard(unittest.TestCase):
    """Test guard extraction, validation, sanitization; malformed JSON does not crash."""

    def setUp(self):
        self.guard = LLMActionGuard(allowed_actions=["increase_cash", "decrease_cash", "steady_finance"])

    def test_extract_json_finds_action_json_block(self):
        llm_output = """### REASONING
We should conserve cash.
### ACTION_JSON
{"action": "steady_finance", "actor": "founder", "deltas": [{"variable": "cash", "change": 0}]}"""
        result = self.guard.extract_json(llm_output)
        self.assertNotIn("error", result)
        self.assertEqual(result.get("action"), "steady_finance")
        self.assertEqual(result.get("actor"), "founder")

    def test_extract_json_returns_structured_error_on_no_block(self):
        result = self.guard.extract_json("No JSON here at all.")
        self.assertIn("error", result)
        self.assertEqual(result.get("stage"), "extraction")

    def test_extract_json_returns_error_on_invalid_json(self):
        llm_output = """### REASONING
Ok
### ACTION_JSON
{action: "bad", no quotes}"""
        result = self.guard.extract_json(llm_output)
        self.assertIn("error", result)

    def test_validate_rejects_unknown_action(self):
        raw = {"action": "invalid_action", "actor": "founder", "deltas": []}
        result = self.guard.validate(raw)
        self.assertTrue(result.get("valid") is False)
        self.assertIn("errors", result)

    def test_validate_accepts_valid_block(self):
        raw = {"action": "steady_finance", "actor": "founder", "deltas": [{"variable": "cash", "change": 0.0}]}
        result = self.guard.validate(raw)
        self.assertNotEqual(result.get("valid"), False)
        self.assertEqual(result.get("action"), "steady_finance")

    def test_sanitize_caps_magnitude_and_drops_unknown_vars(self):
        world_state = {"variables": {"cash": 100}, "global_state": {"cash": 100}}
        guard_cap = LLMActionGuard(allowed_actions=["increase_cash"], delta_magnitude_cap=10.0)
        json_action = {"action": "increase_cash", "actor": "a", "deltas": [{"variable": "cash", "change": 999}, {"variable": "unknown_var", "change": 5}]}
        validated = guard_cap.validate(json_action)
        self.assertNotEqual(validated.get("valid"), False)
        sanitized = guard_cap.sanitize(validated, world_state)
        self.assertIn("cash", [d["variable"] for d in sanitized["deltas"]])
        self.assertNotIn("unknown_var", [d["variable"] for d in sanitized["deltas"]])
        cash_delta = next(d for d in sanitized["deltas"] if d["variable"] == "cash")
        self.assertLessEqual(abs(cash_delta["change"]), 10.0)

    def test_malformed_json_does_not_crash(self):
        """Malformed JSON returns structured error; no exception."""
        for bad_input in ["", "### ACTION_JSON\n{]", "### ACTION_JSON\nnull", "not even a section"]:
            result = self.guard.extract_json(bad_input)
            self.assertIsInstance(result, dict)
            if result.get("error"):
                self.assertEqual(result.get("stage"), "extraction")


class TestParseReasoning(unittest.TestCase):
    """Test reasoning extraction from agent output."""

    def test_parse_reasoning_extracts_text_before_action_json(self):
        out = "### REASONING\nI think we should save cash.\n\n### ACTION_JSON\n{}"
        self.assertEqual(loop_parse_reasoning(out).strip(), "I think we should save cash.")

    def test_parse_reasoning_empty_when_no_marker(self):
        self.assertEqual(loop_parse_reasoning("No markers here"), "")
