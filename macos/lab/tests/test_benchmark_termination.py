"""Real driver termination with a tiny owned fixture, never model/GPU execution."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

ROOT=Path(__file__).resolve().parents[1]


class BenchmarkTerminationTests(unittest.TestCase):
    def check_termination(self,stopping,during_spawn=False):
        with tempfile.TemporaryDirectory(prefix='strata-termination-fixture-') as temporary:
            folder=Path(temporary)
            parent=folder/'parent'; private=folder/'private'
            (parent/'build-metal').mkdir(parents=True)
            (private/'models').mkdir(parents=True)
            (folder/'bench').mkdir()
            for name in ('a.gguf','b.gguf'):
                (private/'models'/name).touch()  # Empty command arguments; no model reader is run.
            marker=folder/'child.json'; finished=folder/'monitor-finished'
            observed=folder/'observer-ready'
            fake=parent/'build-metal/strata'
            fake.write_text('#!'+sys.executable+'\nimport json,os,time\nfrom pathlib import Path\n'
                +'marker=Path('+repr(str(marker))+')\n'
                +'pending=marker.with_suffix(".tmp")\n'
                +'pending.write_text(json.dumps({"pid":os.getpid()}))\n'
                +'pending.replace(marker)\n'
                +'while True: time.sleep(1)\n')
            fake.chmod(0o700)
            driver=folder/'driver.py'
            driver.write_text('''import os,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, '''+repr(str(ROOT/'scripts'))+''')
import benchmark_parent_metal as trial
trial.ROOT=Path('''+repr(str(folder))+''')
trial.PARENT=Path('''+repr(str(parent))+''')
trial.PRIVATE=Path('''+repr(str(private))+''')
# Exercise the real main/launch/reader/shutdown lifecycle, replacing only unrelated
# provenance/admission/power operations and the model executable with owned fixtures.
trial.no_engines=lambda:None
trial.require_pass=lambda:None
trial.frozen_state=lambda:{}
trial.assert_unchanged=lambda models:None
trial.verify_models=lambda models:{}
trial.prepare_cases=lambda:([],None)
trial.wait_for_headroom=lambda:{}
trial.preflight=lambda *args:{}
trial.power=lambda:{}
trial.configure=lambda *args:(dict(os.environ),{})
trial.admit_model=lambda *args:{}
class Monitor:
    thread=SimpleNamespace(start=lambda:None)
    def finish(self):
        Path('''+repr(str(finished))+''').write_text('finished')
        return {}
trial.app_monitor=lambda *args:Monitor()
if '''+repr(during_spawn)+''':
    original_spawn=trial.subprocess.Popen
    def held_spawn(*args,**kwargs):
        child=original_spawn(*args,**kwargs)
        # Widen the real creation/ownership boundary until the test has identified
        # this exact tiny child, then deliver an actual signal before returning it.
        import time
        observed=Path('''+repr(str(observed))+''')
        deadline=time.monotonic()+10
        while not observed.exists() and time.monotonic()<deadline: time.sleep(.01)
        if not observed.exists(): raise RuntimeError('Fixture observer not ready')
        os.kill(os.getpid(),'''+str(int(stopping))+''')
        return child
    trial.subprocess.Popen=held_spawn
sys.argv=['trial','--output', '''+repr(str(folder/'campaign'))+''', '--run']
trial.main()
''')
            process=subprocess.Popen([sys.executable,str(driver)],stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,text=True)
            owned=None; created=None
            try:
                deadline=time.monotonic()+10
                while not marker.exists() and process.poll() is None and time.monotonic()<deadline:
                    time.sleep(.02)
                if not marker.exists():
                    self.fail('Owned fake did not start; driver exit='+str(process.poll()))
                owned=psutil.Process(json.loads(marker.read_text())['pid'])
                created=owned.create_time()
                self.assertIn(str(fake),owned.cmdline())
                if during_spawn: observed.write_text('identified owned child')
                else: process.send_signal(stopping)
                stdout,stderr=process.communicate(timeout=15)
                self.assertNotEqual(process.returncode,0,'Interrupted benchmark must not pass')
                self.assertNotEqual(process.returncode,-stopping,'Default signal bypassed cleanup')
                self.assertTrue(finished.exists(),'Guard finalization was skipped: '+stdout+stderr)
                self.assertFalse(self.alive(owned),'Owned child survived driver termination')
                result=json.loads((folder/'campaign/arm-1-parent/result.json').read_text())
                self.assertEqual(result['status'],'failed')
                self.assertIn(signal.Signals(stopping).name,result['error'])
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.communicate(timeout=5)
                if owned is None and marker.exists():
                    try:
                        candidate=psutil.Process(json.loads(marker.read_text())['pid'])
                        if str(fake) in candidate.cmdline():
                            owned=candidate; created=candidate.create_time()
                    except psutil.NoSuchProcess:
                        pass
                # A failing pre-fix run must still clean up its identified tiny child.
                if owned and self.alive(owned):
                    self.assertEqual(owned.create_time(),created)
                    self.assertIn(str(fake),owned.cmdline())
                    owned.terminate()
                    try: owned.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        owned.kill(); owned.wait(timeout=5)

    @staticmethod
    def alive(process):
        try: return process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess: return False

    def test_sigterm_reaps_owned_child_and_finalizes_guard(self):
        self.check_termination(signal.SIGTERM)

    def test_ctrl_c_reaps_owned_child_and_finalizes_guard(self):
        self.check_termination(signal.SIGINT)

    def test_sighup_reaps_owned_child_and_finalizes_guard(self):
        self.check_termination(signal.SIGHUP)

    def test_sigterm_during_spawn_waits_for_owned_child_and_guard_publication(self):
        self.check_termination(signal.SIGTERM,during_spawn=True)

    def test_ctrl_c_during_spawn_waits_for_owned_child_and_guard_publication(self):
        self.check_termination(signal.SIGINT,during_spawn=True)

    def test_sighup_during_spawn_waits_for_owned_child_and_guard_publication(self):
        self.check_termination(signal.SIGHUP,during_spawn=True)


if __name__=='__main__':unittest.main()
