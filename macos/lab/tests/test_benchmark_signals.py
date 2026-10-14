"""Termination must reach owned-child cleanup and preserve caller signal handlers."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_signals import cleanup_on_termination, defer_termination


class BenchmarkSignalTests(unittest.TestCase):
    def test_unknown_native_handler_is_refused_before_changing_any_signal(self):
        scope = cleanup_on_termination()
        with patch('benchmark_signals.signal.getsignal', return_value=None), \
                patch('benchmark_signals.signal.signal') as setter:
            with self.assertRaisesRegex(RuntimeError, 'unknown handler'):
                scope.__enter__()
        setter.assert_not_called()

    def test_resource_references_are_published_before_pending_stop_unwinds(self):
        for number in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
            owned=[]
            with self.assertRaises(KeyboardInterrupt):
                with cleanup_on_termination():
                    try:
                        with defer_termination():
                            signal.getsignal(number)(number,None)
                            owned.extend(['child','monitor'])
                    finally:
                        self.assertEqual(owned,['child','monitor'])

    def test_nested_deferral_and_ignored_signals_preserve_caller_semantics(self):
        previous=signal.getsignal(signal.SIGTERM)
        try:
            signal.signal(signal.SIGTERM,signal.SIG_IGN)
            with defer_termination():
                with defer_termination():
                    signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
            self.assertEqual(signal.getsignal(signal.SIGTERM),signal.SIG_IGN)
        finally:
            signal.signal(signal.SIGTERM,previous)

    def test_termination_unwinds_cleanup_and_ignores_repeated_stops(self):
        for number in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
            previous={s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
            events=[]
            with self.assertRaisesRegex(KeyboardInterrupt,signal.Signals(number).name):
                with cleanup_on_termination():
                    try:
                        signal.getsignal(number)(number,None)
                    finally:
                        events.append('owned child stopped')
                        self.assertEqual(signal.getsignal(signal.SIGINT),signal.SIG_IGN)
                        self.assertEqual(signal.getsignal(signal.SIGTERM),signal.SIG_IGN)
                        self.assertEqual(signal.getsignal(signal.SIGHUP),signal.SIG_IGN)
                        events.append('monitor finalized')
            self.assertEqual(events,['owned child stopped','monitor finalized'])
            for s,handler in previous.items():
                self.assertEqual(signal.getsignal(s),handler)

    def test_normal_return_and_error_restore_previous_handlers(self):
        previous=signal.getsignal(signal.SIGTERM)
        @cleanup_on_termination()
        def call(fail=False):
            self.assertTrue(callable(signal.getsignal(signal.SIGTERM)))
            if fail: raise ValueError('fixture')
            return 'result'
        self.assertEqual(call(),'result')
        self.assertEqual(signal.getsignal(signal.SIGTERM),previous)
        with self.assertRaisesRegex(ValueError,'fixture'): call(True)
        self.assertEqual(signal.getsignal(signal.SIGTERM),previous)

    def test_each_new_trial_entry_point_installs_and_restores_handlers(self):
        from benchmark_editing import main as editing
        from benchmark_parent_metal import main as parent
        from benchmark_prompt_chunks import main as chunks
        from capture_lookup_long import main as lookup
        runs=[(editing,['--experiment','editing','--output','/unused/fixture']),
              (parent,['--output','/unused/fixture']),
              (chunks,['--candidate','1536','--output','/unused/fixture']),
              (lookup,['--output','/unused/fixture'])]
        setter=signal.signal
        for run,argv in runs:
            with self.subTest(driver=run.__module__):
                previous=signal.getsignal(signal.SIGTERM)
                with patch.object(sys,'argv',['trial',*argv]), redirect_stdout(StringIO()), \
                        patch('benchmark_signals.signal.signal',wraps=setter) as installed:
                    run()
                self.assertTrue(any(call.args[0]==signal.SIGTERM and callable(call.args[1])
                                    for call in installed.call_args_list))
                self.assertEqual(signal.getsignal(signal.SIGTERM),previous)


if __name__=='__main__':unittest.main()
