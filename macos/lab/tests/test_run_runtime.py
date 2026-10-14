"""Cancellation at either app launch boundary retains owned-process cleanup."""
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run


class RunRuntimeTests(unittest.TestCase):
    def args(self):
        return Namespace(batch=512, ubatch=512, context=4096, lookup_profile='off', model='small',
            engine='baseline', draft_vocab='off', tensor_api='auto', m5_tuning='stock', spec='none',
            draft_model='mtp', port=1, native_port=2, prompt_cache=True, cache_type='f16', draft=3,
            draft_placement='cpu', draft_threads=None, draft_p_min=None)

    def setup(self, stack, root, spawn, monitor):
        values = dict(ROOT=root, experiment_environment=({}, {}), configure=({}, {}),
                      assert_no_model_server=None, verify_engine={}, verify_models={},
                      assert_ports_available=None, server_command=['never-executed'],
                      admit_model={'baseline': {'swap_used_bytes': 0}}, wait_ready=None)
        for name, value in values.items():
            stack.enter_context(patch.object(run, name, root if name == 'ROOT' else Mock(return_value=value)))
        stack.enter_context(patch.object(run.subprocess, 'Popen', side_effect=spawn))
        stack.enter_context(patch.object(run, 'app_monitor', return_value=monitor))

    def test_stop_during_native_or_api_creation_finalizes_both_owned_children(self):
        for stage in (0, 1):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                native, app, monitor = Mock(), Mock(), Mock()
                native.poll.return_value = app.poll.return_value = None
                monitor.finish.return_value = {'fixture': 'finalized'}
                created = []
                previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
                def spawn(*args, **kwargs):
                    process = (native, app)[len(created)]
                    created.append(process)
                    if len(created) == stage + 1:
                        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                    return process
                self.setup(stack, Path(folder), spawn, monitor)
                try:
                    run.execute(self.args())
                    for process in created:
                        process.terminate.assert_called_once()
                    monitor.finish.assert_called_once()
                    self.assertFalse((Path(folder) / 'bench/runtime/active.json').exists())
                    for number, handler in previous.items(): self.assertEqual(signal.getsignal(number), handler)
                finally:
                    for number, handler in previous.items(): signal.signal(number, handler)


if __name__ == '__main__': unittest.main()
