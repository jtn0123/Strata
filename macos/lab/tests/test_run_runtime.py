"""Cancellation at either app launch boundary retains owned-process cleanup."""
from argparse import Namespace
from contextlib import ExitStack
import json
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

    def test_invalid_ports_are_rejected_before_resource_checks_or_spawn(self):
        for field in ('port', 'native_port'):
            for value in (0, -1, 65536, True, 8095.0, '8095', '--api-key=unexpected'):
                with self.subTest(field=field, value=value):
                    args = self.args()
                    setattr(args, field, value)
                    with patch.object(run, 'experiment_environment', return_value=({}, {})), \
                            patch.object(run, 'assert_no_model_server', side_effect=AssertionError('Resource check reached')) as resources, \
                            patch.object(run.subprocess, 'Popen') as spawn:
                        with self.assertRaisesRegex(ValueError, 'Ports must be integers from 1 to 65535'):
                            run.execute(args)
                        resources.assert_not_called()
                        spawn.assert_not_called()

    def test_duplicate_ports_are_rejected_before_resource_checks_or_spawn(self):
        args = self.args()
        args.native_port = args.port
        with patch.object(run, 'experiment_environment', return_value=({}, {})), \
                patch.object(run, 'assert_no_model_server', side_effect=AssertionError('Resource check reached')) as resources, \
                patch.object(run.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'API and native ports must differ'):
                run.execute(args)
            resources.assert_not_called()
            spawn.assert_not_called()

    def test_port_boundaries_keep_numeric_values(self):
        args = self.args()
        args.port, args.native_port = 1, 65535
        self.assertEqual(run.validated_ports(args), (1, 65535))

    def test_json_writer_rejects_outside_and_escaping_runtime_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'bench/runtime'
            runtime.mkdir(parents=True)
            outside = root / 'outside.json'
            outside.write_text('original')
            escape = runtime / 'escaped.json'
            escape.symlink_to(outside)
            with patch.object(run, 'ROOT', root):
                for target in (outside, escape):
                    with self.subTest(target=target):
                        with self.assertRaisesRegex(ValueError, 'owned runtime directory'):
                            run.write_json(target, {'value': 'replacement'})
                        self.assertEqual(outside.read_text(), 'original')

    def test_json_writer_keeps_user_content_and_preserves_file_on_serialization_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'bench/runtime/config.json'
            target.parent.mkdir(parents=True)
            with patch.object(run, 'ROOT', root):
                payload = {'model': '../../kept-as-data', 'value': '--kept-as-data'}
                run.write_json(target, payload)
                original = target.read_text()
                self.assertEqual(original, json.dumps(payload, indent=2) + '\n')
                with self.assertRaises(TypeError):
                    run.write_json(target, {'value': object()})
                self.assertEqual(target.read_text(), original)

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
