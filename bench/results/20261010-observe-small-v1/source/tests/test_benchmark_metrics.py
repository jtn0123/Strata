"""Malformed raw timing evidence must never become a performance percentage."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_metrics import METRICS, change, metrics


class MetricTests(unittest.TestCase):
    def case(self):
        return {"workload": "code", "prompt_tokens": 48, "repeat": 2,
                "generation_tok_s": 50, "prompt_tok_s": 500, "ttft_s": 0.2, "wall_s": 2.76,
                "response": {"final": {"timings": {"draft_n": 100, "draft_n_accepted": 80}}}}

    def test_rejects_one_invalid_sample_before_median_can_hide_it(self):
        for key in METRICS:
            for invalid in (float("nan"), float("inf"), float("-inf"), 0, -1, True):
                with self.subTest(key=key, invalid=invalid):
                    bad = self.case(); bad[key] = invalid
                    with self.assertRaisesRegex(ValueError, f"code/48/repeat=2/{key}"):
                        metrics([self.case(), bad, self.case()])

    def test_rejects_cached_native_rates_and_bad_percentage_operands(self):
        case = {"workload": "cached-ledger", "history_budget": 512, "repeat": 1,
                "ttft_s": 0.2, "wall_s": 0.7,
                "native_timings": {"predicted_per_second": float("nan"), "prompt_per_second": 500}}
        with self.assertRaisesRegex(ValueError, "cached-ledger/512"):
            metrics([case], cached=True)
        control = {k: self.case()[k] for k in METRICS}
        for key in METRICS:
            for operand in ("before", "after"):
                bad = copy.deepcopy(control); bad[key] = 0
                with self.assertRaises(ValueError):
                    change(bad, control) if operand == "before" else change(control, bad)

    def test_acceptance_counters_validate_without_inventing_missing_acceptance(self):
        for values in ({"draft_n": -1}, {"draft_n": 3.5}, {"draft_n": True},
                       {"draft_n": 2, "draft_n_accepted": 3}, {"draft_n_accepted": 1}):
            case = self.case(); case["response"]["final"]["timings"] = values
            with self.assertRaises(ValueError): metrics([case])
        case = self.case(); case["response"]["final"]["timings"] = {}
        self.assertIsNone(metrics([case])["draft_acceptance_percent"])
        self.assertEqual(metrics([self.case()])["draft_acceptance_percent"], 80)
        with self.assertRaises(ValueError): metrics([])

    def test_valid_gain_remains_based_on_fresh_control(self):
        control = metrics([self.case()])
        candidate = dict(control, generation_tok_s=60, wall_s=2, ttft_s=0.1)
        delta = change(control, candidate)
        self.assertAlmostEqual(delta["generation_increase_percent"], 20)
        self.assertAlmostEqual(delta["ttft_reduction_percent"], 50)

    def test_finite_operands_cannot_publish_an_overflowed_percentage(self):
        control = metrics([self.case()])
        candidate = dict(control, generation_tok_s=1e308)
        control["generation_tok_s"] = 1e-308
        with self.assertRaisesRegex(ValueError, "percentage is nonfinite"):
            change(control, candidate)
