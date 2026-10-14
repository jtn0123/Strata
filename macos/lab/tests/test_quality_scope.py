"""Mac check scope cannot drift into PC files or hide a lint/type disagreement."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_quality as quality


class QualityScopeTests(unittest.TestCase):
    def fixture(self, root):
        (root / "config").mkdir()
        (root / "scripts").mkdir()
        (root / "scripts/core.py").write_text("# Header\n\ndef core():\n    return 1\n")
        settings = {"schema": 1, "python_modules": ["scripts/core.py"],
                    "file_warning_lines": 500, "function_warning_lines": 80}
        self.save(root, settings)
        return settings

    def save(self, root, settings):
        (root / "config/quality_modules.json").write_text(json.dumps(settings))

    def test_pc_paths_missing_sources_and_escaping_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.fixture(root)
            (root / "pc.py").write_text("# outside the maintained scripts\n")
            (root / "scripts/escape.py").symlink_to(root / "pc.py")
            for source in ("", "../setup.py", "scripts/../pc.py", "serve/server.py", "scripts/missing.py",
                           "scripts/escape.py", str(root / "pc.py")):
                with self.subTest(source=source):
                    self.save(root, dict(settings, python_modules=[source]))
                    with self.assertRaises(ValueError):
                        quality.scope(root)

    def test_duplicate_modules_and_nonpositive_or_boolean_thresholds_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.fixture(root)
            invalid = [{"python_modules": []}, {"python_modules": ["scripts/core.py"] * 2},
                       {"python_modules": [1]}, {"file_warning_lines": 0},
                       {"function_warning_lines": -1}, {"function_warning_lines": True}]
            for changes in invalid:
                with self.subTest(changes=changes):
                    self.save(root, dict(settings, **changes))
                    with self.assertRaises(ValueError):
                        quality.scope(root)

    def test_lint_and_type_scopes_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.fixture(root)
            config = root / "config/mypy.ini"
            config.write_text("[mypy]\nfiles = $MYPY_CONFIG_FILE_DIR/../scripts/core.py\n")
            quality.check_mypy_scope(settings, root)
            config.write_text("[mypy]\nfiles = $MYPY_CONFIG_FILE_DIR/../scripts/other.py\n")
            with self.assertRaisesRegex(ValueError, "scope differ"):
                quality.check_mypy_scope(settings, root)

    def test_size_receipt_contains_source_identity_and_function_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.fixture(root)
            settings.update(file_warning_lines=3, function_warning_lines=1)
            quality.report_sizes(settings, root)
            receipt = json.loads((root / "bench/features/code-quality/latest-sizes.json").read_text())
            self.assertEqual(receipt["scope"], settings)
            self.assertEqual(receipt["files"][0]["path"], "scripts/core.py")
            self.assertEqual(receipt["files"][0]["lines"], 4)
            self.assertEqual(receipt["files"][0]["functions"], [{"name": "core", "line": 3, "lines": 2}])
            self.assertEqual(len(receipt["files"][0]["sha256"]), 64)
            self.assertEqual(len(receipt["warnings"]), 2)


if __name__ == "__main__":
    unittest.main()
