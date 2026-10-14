"""Coverage gates reject lowered floors, stale sources and incomplete measurement."""

from contextlib import chdir, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from coverage import Coverage, CoverageData

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_coverage as gate

CONFIG = Path(__file__).resolve().parents[1] / "config/coverage.ini"


class CoverageGateTests(unittest.TestCase):
    def fixture(self, root):
        (root / "config").mkdir()
        (root / "scripts").mkdir()
        (root / "tests").mkdir()
        (root / "scripts/core.py").write_text(
            "def choose(enabled):\n    if enabled:\n        return 1\n    return 2\n"
        )
        (root / "tests/test_fixture.py").write_text("# Synthetic guarded-inventory receipt fixture.\n")
        settings = {"schema": 1, "python_modules": ["scripts/core.py"],
                    "file_warning_lines": 500, "function_warning_lines": 80}
        (root / "config/quality_modules.json").write_text(json.dumps(settings))
        (root / "config/offline_tests.json").write_text(json.dumps({"included": ["test_fixture.py"], "excluded": {}}))
        (root / "config/coverage.ini").write_bytes(CONFIG.read_bytes())
        self.measure(root)
        gate.initialize_baseline(root)
        # The committed baseline becomes part of the source identity. Remeasure.
        self.measure(root)

    def measure(self, root, *, call=True, branch=True, context=None, extra=False):
        data_file = root / gate.COVERAGE_DIRECTORY / ".coverage"
        data_file.parent.mkdir(parents=True, exist_ok=True)
        source = root / "scripts/core.py"
        includes = [str(source)]
        if extra:
            other = root / "scripts/extra.py"
            other.write_text("value = 1\n")
            includes.append(str(other))
        environment = {
            "MAC_QUALITY_COVERAGE_SCOPE": ",".join(includes),
            "MAC_QUALITY_COVERAGE_CONTEXT": gate.measurement_context(root) if context is None else context,
        }
        with chdir(root), patch.dict(os.environ, environment):
            coverage = Coverage(config_file=str(root / "config/coverage.ini"), data_file=str(data_file), branch=branch)
            coverage.start()
            try:
                namespace = {}
                exec(compile(source.read_text(), str(source), "exec"), namespace)
                if call:
                    namespace["choose"](True)
                if extra:
                    exec(compile(other.read_text(), str(other), "exec"), {})
            finally:
                coverage.stop()
        receipt = {"schema": 1, "status": "passed", "sources": gate.fingerprint(root),
                   "inventory": gate.inventory(root), "tests_run": 1, "failures": 0, "errors": 0,
                   "models_loaded": False, "gpu_tests_run": False, "builds_run": False,
                   "native_cpu_self_tests_run": False, "real_sockets_opened": False}
        (root / gate.OFFLINE_RECEIPT).write_text(json.dumps(receipt))
        coverage.save()

    def save(self, root, relative, value):
        (root / relative).write_text(json.dumps(value))

    def test_real_branch_measurement_passes_at_rounded_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            data = CoverageData(basename=str(root / gate.COVERAGE_DIRECTORY / ".coverage"))
            data.read()
            self.assertEqual(data.measured_files(), {"scripts/core.py"})
            result = gate.check_coverage(root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["totals"], dict(covered_lines=3, missing_lines=1,
                                                   covered_branches=1, missing_branches=1))
            self.assertEqual(result["floors"], dict(line_percent=75, branch_percent=50))
            with redirect_stdout(StringIO()):
                self.assertEqual(gate.main([], root), 0)
            receipt = json.loads((root / gate.COVERAGE_DIRECTORY / "gate.json").read_text())
            self.assertEqual(receipt["status"], "passed")

    def test_lowered_aggregate_or_file_floors_and_bad_counts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            original = json.loads((root / gate.BASELINE).read_text())
            mutations = [lambda item: item["floors"].update(line_percent=74),
                         lambda item: item["floors"].update(branch_percent=49),
                         lambda item: item["files"]["scripts/core.py"]["floors"].update(line_percent=74),
                         lambda item: item["files"]["scripts/core.py"]["counts"].update(covered_lines=True),
                         lambda item: item["totals"].update(missing_lines=-1)]
            for mutate in mutations:
                current = json.loads(json.dumps(original))
                mutate(current)
                self.save(root, gate.BASELINE, current)
                with self.assertRaises(ValueError):
                    gate.load_baseline(root)

    def test_coverage_drop_is_rejected_and_failure_receipt_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            self.measure(root, call=False)
            with self.assertRaisesRegex(ValueError, "line coverage is below"):
                gate.check_coverage(root)
            with redirect_stdout(StringIO()):
                self.assertEqual(gate.main([], root), 1)
            receipt = json.loads((root / gate.COVERAGE_DIRECTORY / "gate.json").read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("below", receipt["error"])

    def test_branch_floor_is_enforced_independently_of_line_floor(self):
        actual = dict(covered_lines=10, missing_lines=0, covered_branches=1, missing_branches=3)
        required = dict(line_percent=75, branch_percent=50)
        with self.assertRaisesRegex(ValueError, "branch coverage is below"):
            gate.require_floors(actual, required, "fixture")

    def test_changed_source_or_configuration_invalidates_evidence(self):
        for relative in ("scripts/core.py", "config/coverage.ini"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                path = root / relative
                path.write_text(path.read_text() + "\n# Source changed after measurement.\n")
                with self.assertRaisesRegex(ValueError, "stale"):
                    gate.check_coverage(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            original = Coverage.json_report
            def change_source(coverage, *args, **kwargs):
                result = original(coverage, *args, **kwargs)
                source = root / "scripts/core.py"
                source.write_text(source.read_text() + "\n# Changed during reporting.\n")
                return result
            with patch.object(Coverage, "json_report", new=change_source):
                with self.assertRaisesRegex(ValueError, "changed while checking"):
                    gate.check_coverage(root)

    def test_wrong_or_unbound_context_and_branchless_data_are_rejected(self):
        for options in (dict(context="unbound"), dict(context="stale-source-context"), dict(branch=False)):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                self.measure(root, **options)
                with self.assertRaisesRegex(ValueError, "branch data is missing|context is stale"):
                    gate.check_coverage(root)

    def test_data_older_than_the_offline_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            data_file = root / gate.COVERAGE_DIRECTORY / ".coverage"
            receipt_file = root / gate.OFFLINE_RECEIPT
            old = receipt_file.stat().st_mtime_ns - 10_000_000
            os.utime(data_file, ns=(old, old))
            with self.assertRaisesRegex(ValueError, "predates"):
                gate.check_coverage(root)

    def test_missing_baseline_data_or_receipt_is_rejected(self):
        for relative in (gate.BASELINE, gate.OFFLINE_RECEIPT, gate.COVERAGE_DIRECTORY + "/.coverage"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                (root / relative).unlink()
                with self.assertRaises(OSError):
                    gate.check_coverage(root)

    def test_failed_or_native_enabled_offline_receipts_are_rejected(self):
        for changes in (dict(status="failed"), dict(failures=1), dict(errors=1), dict(tests_run=0),
                        dict(models_loaded=True), dict(real_sockets_opened=True), dict(inventory={})):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                receipt = json.loads((root / gate.OFFLINE_RECEIPT).read_text())
                receipt.update(changes)
                self.save(root, gate.OFFLINE_RECEIPT, receipt)
                with self.assertRaises(ValueError):
                    gate.check_coverage(root)

    def test_scope_disagreement_and_extra_measured_modules_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            baseline = json.loads((root / gate.BASELINE).read_text())
            baseline["python_modules"] = ["scripts/other.py"]
            self.save(root, gate.BASELINE, baseline)
            with self.assertRaisesRegex(ValueError, "scope differs"):
                gate.load_baseline(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            self.measure(root, extra=True)
            with self.assertRaisesRegex(ValueError, "scope differs"):
                gate.check_coverage(root)

    def test_exclusions_inconsistent_counts_and_wrong_tool_version_are_rejected(self):
        summary = dict(covered_lines=3, missing_lines=1, num_statements=4,
                       covered_branches=1, missing_branches=1, num_branches=2, excluded_lines=0)
        for changes in (dict(excluded_lines=1), dict(excluded_lines=False),
                        dict(num_statements=5), dict(num_branches=3)):
            value = dict(summary, **changes)
            with self.assertRaises(ValueError):
                gate.validate_summary(value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with patch.object(gate, "__version__", "0.0"):
                with self.assertRaisesRegex(ValueError, "pinned"):
                    gate.check_coverage(root)

    def test_scope_context_modes_need_no_coverage_or_baseline_and_initializer_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(gate.main(["--scope"], root), 0)
                self.assertEqual(gate.main(["--context"], root), 0)
            self.assertIn(str(root / "scripts/core.py"), output.getvalue())
            self.assertIn("strata-mac:", output.getvalue())
            previous = (root / gate.BASELINE).read_bytes()
            with self.assertRaises(FileExistsError):
                gate.initialize_baseline(root)
            self.assertEqual((root / gate.BASELINE).read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
