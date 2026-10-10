"""Reject unfair kernel comparisons and check shared-helper compatibility."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_mma
from lab import server_command


class MmaTests(unittest.TestCase):
    def records(self):
        order = benchmark_mma.plan([1])
        records = []
        for index, (depth, profile) in enumerate(order):
            rate = 50 if profile == "candidate" else 40
            cases = [{"workload": "synthetic", "prompt_tokens": n, "prompt_sha256": str(n),
                      "output_tokens": 128, "generation_tok_s": rate, "prompt_tok_s": 600,
                      "ttft_s": 1, "wall_s": 128 / rate + 1,
                      "response": {"final": {"timings": {}}}} for n in (512, 2048)]
            cached = [{"history_budget": n, "warmup": False, "prompt_sha256": str(n),
                       "ttft_s": 0.25, "wall_s": 0.25 + 24 / rate,
                       "native_timings": {"predicted_per_second": rate, "prompt_per_second": 600}}
                      for n in (512, 2048)]
            records.append({"settings": vars(benchmark_mma.settings(profile, depth, str(index), repeats=1)),
                            "status": "passed", "cases": cases, "cached_cases": cached,
                            "checks": [{"passed": True}], "memory": {"guard": None},
                            "selected_engine": {"engine": benchmark_mma.ENGINES[profile], "hash": profile},
                            **{k: {"same": True} for k in ("model", "runtime", "draft_model", "actual_sources")}})
        return records, order

    def test_percentages_use_fresh_matching_depth_controls(self):
        records, order = self.records()
        for row in benchmark_mma.compare(records, order, repeats=1):
            self.assertAlmostEqual(row["candidate_vs_control"]["generation_increase_percent"], 25)
            self.assertEqual(row["control_drift"]["generation_increase_percent"], 0)

    def test_unfair_data_is_rejected(self):
        original, order = self.records()
        mutations = (
            lambda r: r[1]["settings"].update(draft=3),
            lambda r: r[1]["settings"].update(draft_threads=6),
            lambda r: r[1]["selected_engine"].update(engine="mtp-shared"),
            lambda r: r[2]["selected_engine"].update(hash="replacement"),
            lambda r: r[1]["model"].update(same=False),
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
                benchmark_mma.compare(records, order, repeats=1)

    def test_preparation_does_not_load_the_model(self):
        with patch.object(benchmark_mma, "snapshot", return_value={}), \
             patch.object(benchmark_mma, "print_snapshot"), patch.object(benchmark_mma, "run") as run:
            benchmark_mma.main([])
            run.assert_not_called()

    def test_combined_engine_accepts_existing_shared_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/models.json").write_text(json.dumps({"mtp_shared_packed_q3": {
                "derived": {"required_engine": "mtp-shared"}}}))
            with patch("lab.ROOT", root), patch("lab.model_path", return_value=root / "unused.gguf"), \
                 patch("engines.engine_binary", return_value=root / "unused-server"):
                command = server_command("flash", spec="draft-mtp", engine="mtp-mma",
                                         draft_placement="mixed", draft_model="mtp_shared_packed_q3")
                self.assertIn("--spec-draft-cpu-moe", command)
                with self.assertRaisesRegex(ValueError, "requires the mtp-shared engine"):
                    server_command("flash", spec="draft-mtp", engine="baseline", draft_model="mtp_shared_packed_q3")


if __name__ == "__main__":
    unittest.main()
