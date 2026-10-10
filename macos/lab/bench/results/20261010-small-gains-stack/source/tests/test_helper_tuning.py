"""Reject speed comparisons with changed inputs, sources, settings or failed checks."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_tuning


class TuningTests(unittest.TestCase):
    def records(self):
        order = (2, 1, 1, 2)
        records = []
        for index, value in enumerate(order):
            args = benchmark_tuning.settings("depth", value, str(index), repeats=1)
            rate = 50 if value == 1 else 40
            cases = [{"workload": "synthetic", "prompt_tokens": n, "prompt_sha256": str(n),
                      "output_tokens": 128, "generation_tok_s": rate, "prompt_tok_s": 600,
                      "ttft_s": 1, "wall_s": 128 / rate + 1,
                      "response": {"final": {"timings": {}}}} for n in (512, 2048)]
            cached = [{"history_budget": n, "warmup": False, "prompt_sha256": str(n),
                       "ttft_s": 0.25, "wall_s": 0.25 + 24 / rate,
                       "native_timings": {"predicted_per_second": rate, "prompt_per_second": 600}}
                      for n in (512, 2048)]
            records.append({"settings": vars(args), "status": "passed", "cases": cases,
                            "cached_cases": cached, "checks": [{"passed": True}], "memory": {"guard": None},
                            **{k: {"same": True} for k in
                               ("model", "runtime", "draft_model", "selected_engine", "actual_sources")}})
        return records, order

    def test_matched_percentages_use_the_current_control(self):
        records, order = self.records()
        for row in benchmark_tuning.compare(records, order, "depth", repeats=1):
            self.assertAlmostEqual(row["vs_control"]["1"]["generation_increase_percent"], 25)
            self.assertEqual(len(row["control_passes"]), 2)

    def test_unfair_or_incomplete_data_is_rejected(self):
        original, order = self.records()
        mutations = (
            lambda r: r[1]["settings"].update(draft_threads=6),
            lambda r: r[1]["selected_engine"].update(same=False),
            lambda r: r[1]["cases"][0].update(prompt_sha256="changed"),
            lambda r: r[1]["cases"][0].update(output_tokens=64),
            lambda r: r[1]["cases"].pop(),
            lambda r: r[1]["cached_cases"].pop(),
            lambda r: r[1]["checks"][0].update(passed=False),
            lambda r: r[1]["memory"].update(guard="swap limit"),
        )
        for mutation in mutations:
            records = copy.deepcopy(original)
            mutation(records)
            with self.assertRaises(ValueError):
                benchmark_tuning.compare(records, order, "depth", repeats=1)

    def test_preparation_does_not_load_the_model(self):
        with patch.object(benchmark_tuning, "snapshot", return_value={}), \
             patch.object(benchmark_tuning, "print_snapshot"), patch.object(benchmark_tuning, "run") as run:
            benchmark_tuning.main([])
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
