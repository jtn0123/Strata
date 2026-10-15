"""The small-gains campaign's frozen protocol (W02): a fixed 10 ms first-token ceiling on every launch pair.

Load-free: it reads the campaign's own sequence.py from its results folder; nothing launches a model or GPU.
"""

import copy
import importlib.util
from pathlib import Path
import unittest

SEQUENCE = Path(__file__).resolve().parents[1] / "bench/results/20261010-small-gains-stack/sequence.py"


def load_sequence():
    spec = importlib.util.spec_from_file_location("stack_sequence", SEQUENCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sequence = load_sequence()


class ProtocolTests(unittest.TestCase):
    def rows(self, delay_ms=4):
        a = dict(generation_tok_s=50, prompt_tok_s=500, ttft_s=0.28, wall_s=6)
        b = dict(generation_tok_s=50.5, prompt_tok_s=500, ttft_s=0.28 + delay_ms / 1000, wall_s=5.95)
        row = sequence.b.launch_row([a, b, copy.deepcopy(b), copy.deepcopy(a)])
        return [dict(copy.deepcopy(row), workload=name, cached=False) for name in ("code", "prose")]

    def test_small_delay_only_qualifies_under_new_rule(self):
        rows = self.rows()
        self.assertFalse(sequence.speed_passed(sequence.evaluate(rows, True, False)[1]))
        self.assertTrue(sequence.speed_passed(sequence.evaluate(rows, True, True)[1]))
        self.assertIn("ttft_reduction_percent", rows[0]["regressions"])

    def test_fixed_ceiling_and_boundary(self):
        self.assertTrue(sequence.speed_passed(sequence.evaluate(self.rows(10), True, True)[1]))
        self.assertFalse(sequence.evaluate(self.rows(10.001), True, True)[1]["safety_passed"])

    def test_average_cannot_hide_one_slow_launch(self):
        rows = self.rows(9)
        for row in rows:
            row["launch_medians"][1]["ttft_s"] = 0.291
            row["launch_medians"][2]["ttft_s"] = 0.287
        self.assertFalse(sequence.evaluate(rows, True, True)[1]["safety_passed"])

    def test_memory_and_reply_losses_still_block(self):
        self.assertFalse(sequence.evaluate(self.rows(), False, True)[1]["safety_passed"])
        rows = self.rows()
        for row in rows:
            row["regressions"].append("total_time_reduction_percent")
        self.assertFalse(sequence.evaluate(rows, True, True)[1]["safety_passed"])

    def test_noise_gate_and_task_scope_are_unchanged(self):
        rows = self.rows()
        rows[1]["qualifying_metrics"]["generation_increase_percent"] = False
        decision = sequence.evaluate(rows, True, True)[1]
        self.assertFalse(sequence.speed_passed(decision))
        self.assertIn("reply", decision["common_metric_scopes"])


if __name__ == "__main__":
    unittest.main()
