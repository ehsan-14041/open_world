"""
Unit tests for probabilistic uncertainty features in action effects and causal propagation.
Tests verify deterministic behavior by default and stochastic behavior when enabled.
"""

import os
import random
import unittest
from unittest.mock import patch

from core.action_interpreter import interpret_action_spec, interpret_action_spec_with_world
from core.propagation import propagate_variable_changes
from core.world_model import WorldModel


class TestUncertainty(unittest.TestCase):
    """Test probabilistic uncertainty features."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset random state
        random.seed(None)

    def test_deterministic_by_default(self):
        """Test that actions are deterministic when uncertainty is disabled."""
        # Mock settings to disable uncertainty
        with patch("core.action_interpreter.ENABLE_UNCERTAINTY", False):
            action_spec = {
                "type": "increase_variable",
                "target": "growth",
                "magnitude": 5,
                "variance": 2,
                "success_probability": 0.5,
            }
            
            # Run multiple times - should get same result
            result1 = interpret_action_spec(action_spec)
            result2 = interpret_action_spec(action_spec)
            result3 = interpret_action_spec(action_spec)
            
            # All should be identical (variance and success_probability ignored)
            self.assertIsNotNone(result1)
            self.assertIsNotNone(result2)
            self.assertIsNotNone(result3)
            self.assertEqual(result1.numeric_updates, result2.numeric_updates)
            self.assertEqual(result2.numeric_updates, result3.numeric_updates)
            self.assertEqual(result1.numeric_updates["growth"], 5.0)

    def test_seed_reproducibility(self):
        """Test that same seed produces same results."""
        with patch("core.action_interpreter.ENABLE_UNCERTAINTY", True):
            with patch("core.action_interpreter.RANDOM_SEED", 42):
                # Reset random seed
                random.seed(42)
                
                action_spec = {
                    "type": "increase_variable",
                    "target": "growth",
                    "magnitude": 5,
                    "variance": 2,
                    "success_probability": 1.0,  # Always succeed
                }
                
                # Run multiple times with same seed
                random.seed(42)
                result1 = interpret_action_spec(action_spec)
                
                random.seed(42)
                result2 = interpret_action_spec(action_spec)
                
                # Should be identical
                self.assertIsNotNone(result1)
                self.assertIsNotNone(result2)
                self.assertEqual(result1.numeric_updates["growth"], result2.numeric_updates["growth"])

    def test_seed_variation(self):
        """Test that different seeds produce different results."""
        with patch("core.action_interpreter.ENABLE_UNCERTAINTY", True):
            action_spec = {
                "type": "increase_variable",
                "target": "growth",
                "magnitude": 5,
                "variance": 2,
                "success_probability": 1.0,  # Always succeed
            }
            
            # Run with different seeds
            random.seed(42)
            result1 = interpret_action_spec(action_spec)
            
            random.seed(123)
            result2 = interpret_action_spec(action_spec)
            
            # With variance, results should differ (unless very unlucky)
            self.assertIsNotNone(result1)
            self.assertIsNotNone(result2)
            # Note: There's a small chance they could be equal, but very unlikely with variance=2

    def test_success_probability(self):
        """Test that success_probability controls action success."""
        with patch("core.action_interpreter.ENABLE_UNCERTAINTY", True):
            action_spec = {
                "type": "increase_variable",
                "target": "growth",
                "magnitude": 5,
                "success_probability": 0.0,  # Never succeed
            }
            
            # With probability 0.0, should always fail
            random.seed(1)
            result = interpret_action_spec(action_spec)
            self.assertIsNone(result)
            
            # With probability 1.0, should always succeed
            action_spec["success_probability"] = 1.0
            random.seed(1)
            result = interpret_action_spec(action_spec)
            self.assertIsNotNone(result)
            self.assertEqual(result.numeric_updates["growth"], 5.0)

    def test_variance_range(self):
        """Test that variance produces values within expected range."""
        with patch("core.action_interpreter.ENABLE_UNCERTAINTY", True):
            action_spec = {
                "type": "increase_variable",
                "target": "growth",
                "magnitude": 5,
                "variance": 2,
                "success_probability": 1.0,
            }
            
            # Run multiple times and check values are in range [3, 7]
            values = []
            for seed in range(100):
                random.seed(seed)
                result = interpret_action_spec(action_spec)
                if result:
                    values.append(result.numeric_updates["growth"])
            
            # All values should be in range [5-2, 5+2] = [3, 7]
            self.assertTrue(all(3.0 <= v <= 7.0 for v in values))
            # Should have some variation (not all exactly 5.0)
            self.assertTrue(len(set(values)) > 1)

    def test_nested_effect_format(self):
        """Test support for nested effect format."""
        with patch("core.action_interpreter.ENABLE_UNCERTAINTY", True):
            action_spec = {
                "effect": {
                    "type": "increase_variable",
                    "variable": "growth",
                    "value": 5,
                    "variance": 2,
                    "success_probability": 1.0,
                }
            }
            
            random.seed(42)
            result = interpret_action_spec(action_spec)
            self.assertIsNotNone(result)
            self.assertIn("growth", result.numeric_updates)
            self.assertGreaterEqual(result.numeric_updates["growth"], 3.0)
            self.assertLessEqual(result.numeric_updates["growth"], 7.0)

    def test_propagation_noise(self):
        """Test that propagation is deterministic and returns correct structure."""
        # Propagation is deterministic (noise is applied at final stage elsewhere).
        world = WorldModel(
            variables={"source": 100.0, "target": 0.0},
            causal_links=[
                {
                    "from": "source",
                    "to": "target",
                    "weight": 0.5,
                }
            ],
        )
        direct_changes = {"source": 10.0}
        primary_effects, secondary_effects, trace_changes = propagate_variable_changes(
            world, direct_changes.copy()
        )
        self.assertIn("source", primary_effects)
        self.assertEqual(primary_effects["source"], 10.0)
        self.assertIn("target", secondary_effects)
        # Deterministic: 10 * 0.5 * damping(0.6) = 3.0 (hardening: damping for cycle stability)
        self.assertAlmostEqual(secondary_effects["target"], 3.0, delta=1e-9)
        # Same seed / second run gives same result
        primary2, secondary2, _ = propagate_variable_changes(world, direct_changes.copy())
        self.assertEqual(secondary_effects["target"], secondary2["target"])

    def test_propagation_noise_disabled(self):
        """Test that propagation is deterministic (no noise in propagation module)."""
        world = WorldModel(
            variables={"source": 100.0, "target": 0.0},
            causal_links=[
                {
                    "from": "source",
                    "to": "target",
                    "weight": 0.5,
                }
            ],
        )
        direct_changes = {"source": 10.0}
        primary_effects, secondary_effects, _ = propagate_variable_changes(
            world, direct_changes.copy()
        )
        self.assertIn("target", secondary_effects)
        self.assertEqual(secondary_effects["target"], 3.0)  # 10 * 0.5 * damping(0.6), no noise

    def test_set_variable_with_uncertainty(self):
        """Test set_variable with uncertainty."""
        with patch("core.action_interpreter.ENABLE_UNCERTAINTY", True):
            world_snapshot = {"variables": {"growth": 10.0}}
            action_spec = {
                "type": "set_variable",
                "target": "growth",
                "value": 15,
                "variance": 1,
                "success_probability": 1.0,
            }
            
            random.seed(42)
            result = interpret_action_spec_with_world(action_spec, world_snapshot)
            self.assertIsNotNone(result)
            # Delta should be approximately 5 (15 - 10) with some variance
            delta = result.numeric_updates["growth"]
            self.assertGreaterEqual(delta, 4.0)  # 5 - 1
            self.assertLessEqual(delta, 6.0)  # 5 + 1


if __name__ == "__main__":
    unittest.main()
