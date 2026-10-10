"""Offline checks for the hold switch, fair comparisons and exact source provenance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_q2
import engines


class ComparisonTests(unittest.TestCase):
    def records(self):
        records = []
        for index, engine in enumerate(benchmark_q2.ORDER):
            args = benchmark_q2.settings(engine, f"test-{index}", repeats=1)
            candidate = engine == "q2-masked"
            cases = [{"prompt_tokens": n, "prompt_sha256": f"same-{n}", "output_tokens": 512,
                      "generation_tok_s": 50 if candidate else 40, "prompt_tok_s": 750 if candidate else 600,
                      "ttft_s": 0.8 if candidate else 1.0, "wall_s": 8 if candidate else 10} for n in args.prompts]
            records.append({"settings": vars(args), "status": "passed", "cases": cases, "memory": {"guard": None}})
        return records

    def test_default_does_not_load_or_benchmark(self):
        with patch.object(benchmark_q2, "snapshot", return_value={}), \
             patch.object(benchmark_q2, "print_snapshot"), \
             patch.object(benchmark_q2, "execute_plan") as execute:
            benchmark_q2.main([])
            execute.assert_not_called()

    def test_percentage_math(self):
        for item in benchmark_q2.compare(self.records()):
            self.assertAlmostEqual(item["generation_increase_percent"], 25)
            self.assertAlmostEqual(item["ttft_reduction_percent"], 20)
            self.assertAlmostEqual(item["total_time_reduction_percent"], 20)

    def test_reject_unfair_or_incomplete_comparisons(self):
        for mutation in (lambda r: r[1]["settings"].update(ubatch=128),
                         lambda r: r[1]["cases"][0].update(prompt_sha256="different"),
                         lambda r: r[1]["cases"][0].update(output_tokens=128),
                         lambda r: r[1].update(status="failed"),
                         lambda r: r[1]["memory"].update(guard="swap limit"),
                         lambda r: r[1]["cases"].pop()):
            records = self.records()
            mutation(records)
            with self.assertRaises(ValueError):
                benchmark_q2.compare(records)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "vendor/llama.cpp"
        self.path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.path)], check=True)
        (self.path / "kernel.metal").write_text("original\n")
        self.git("add", "kernel.metal")
        self.git("-c", "user.name=Offline Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
        self.revision = self.git("rev-parse", "HEAD").decode().strip()
        (self.root / "config").mkdir()
        (self.root / "config/runtime.json").write_text(json.dumps({"llama_cpp": {"revision": self.revision}}))

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.path), *args])

    def test_baseline_rejects_dirty_source(self):
        self.assertEqual(engines.source_info("baseline", self.root)["revision"], self.revision)
        (self.path / "kernel.metal").write_text("unexpected\n")
        with self.assertRaises(RuntimeError):
            engines.source_info("baseline", self.root)

    def test_candidate_accepts_only_exact_patch(self):
        (self.path / "kernel.metal").write_text("patched\n")
        (self.root / "patches").mkdir()
        diff = self.git("diff", "HEAD", "--binary")
        patch_file = self.root / "patches/test.patch"
        patch_file.write_bytes(diff)
        manifest = {"base_revision": self.revision, "directory": "vendor/llama.cpp", "patch": "patches/test.patch",
                    "patch_sha256": engines.sha256(patch_file), "source_diff_sha256": hashlib.sha256(diff).hexdigest(),
                    "modified_files": ["kernel.metal"]}
        (self.root / "config/q2_experiment.json").write_text(json.dumps(manifest))
        engines.source_info("q2-masked", self.root)
        (self.path / "kernel.metal").write_text("extra change\n")
        with self.assertRaises(RuntimeError):
            engines.source_info("q2-masked", self.root)
        (self.path / "kernel.metal").write_text("patched\n")
        (self.path / "unrelated.txt").write_text("extra file\n")
        with self.assertRaises(RuntimeError):
            engines.source_info("q2-masked", self.root)

    def test_receipt_rejects_replaced_native_library(self):
        (self.path / ".git/info/exclude").write_text("/build/\n")
        binary = self.path / "build/bin/llama-server"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"offline executable fixture")
        library = binary.parent / "libggml-metal.dylib"
        library.write_bytes(b"verified library fixture")
        info = engines.source_info("baseline", self.root)
        info["artifacts"] = engines.artifact_hashes(binary.parent)
        (binary.parent.parent / "lab-receipt.json").write_text(json.dumps(info))
        engines.verify_engine("baseline", self.root)
        library.write_bytes(b"unexpected replacement")
        with self.assertRaises(RuntimeError):
            engines.verify_engine("baseline", self.root)


if __name__ == "__main__":
    unittest.main()
