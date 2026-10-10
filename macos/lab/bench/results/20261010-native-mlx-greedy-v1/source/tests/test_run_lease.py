"""The UI launcher must lose a held benchmark lease without launching anything."""
import fcntl
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run


class LeaseTests(unittest.TestCase):
    def test_app_cannot_launch_when_benchmark_lease_is_held(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/"bench").mkdir()
            with (root/"bench/.lock").open("w") as lease:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(run, "ROOT", root), patch.object(run, "execute") as execute:
                    with self.assertRaises(BlockingIOError): run.main(["small"])
                    execute.assert_not_called()


if __name__ == "__main__": unittest.main()
