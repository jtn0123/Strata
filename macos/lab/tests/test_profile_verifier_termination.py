"""Real profile-verifier termination with a tiny owned launcher fixture, never model/GPU execution."""
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


class ProfileVerifierTerminationTests(unittest.TestCase):
    def check_termination(self,stopping,repeated=False):
        with tempfile.TemporaryDirectory(prefix='strata-verifier-stop-') as temporary:
            folder=Path(temporary)
            (folder/'scripts').mkdir()
            (folder/'scripts/runtime_profiles.py').write_text('owned source fixture\n')
            (folder/'Start Strata.command').write_text('owned default fixture\n')
            marker=folder/'child.json';stopping_marker=folder/'child-stopping'
            launcher=folder/'owned-launcher'
            # The repeated case models a launcher that needs time to stop its own children,
            # so further stop requests land while the verifier is already cleaning up.
            launcher.write_text('#!'+sys.executable+'\nimport json,os,signal,sys,time\nfrom pathlib import Path\n'
                +'def stop(number,frame):\n'
                +'    Path('+repr(str(stopping_marker))+').write_text("stopping")\n'
                +('    time.sleep(1.5)\n' if repeated else '')
                +'    sys.exit(0)\n'
                +'signal.signal(signal.SIGTERM,stop)\n'
                +'pending=Path('+repr(str(marker))+').with_suffix(".tmp")\n'
                +'pending.write_text(json.dumps({"pid":os.getpid()}))\n'
                +'pending.replace(Path('+repr(str(marker))+'))\n'
                +'while True:time.sleep(1)\n')
            launcher.chmod(0o700)
            driver=folder/'driver.py'
            driver.write_text('''import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,'''+repr(str(ROOT/'scripts'))+''')
import verify_runtime_profiles as trial
import validate_offline
# Exercise the real main/launch/readiness/shutdown lifecycle, replacing only provenance,
# host probes, fixed app ports and the model launcher with owned fixtures.
trial.ROOT=Path('''+repr(str(folder))+''')
trial.OUT=trial.ROOT/'campaign'
trial.LAUNCHER=Path('''+repr(str(launcher))+''')
trial.SOURCE=trial.ROOT/'scripts/runtime_profiles.py'
trial.options=SimpleNamespace(profile='balanced')
trial.assert_no_model_server=lambda:None
trial.snapshot=lambda:{}
trial.verify_engine=lambda name:{'fixture':True}
trial.ports_closed=lambda:[]
validate_offline.require_pass=lambda:None
def not_ready(*args,**kwargs):raise OSError('owned fixture not ready')
trial.request=not_ready
trial.main()
''')
            process=subprocess.Popen([sys.executable,str(driver)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            owned=None;created=None
            try:
                deadline=time.monotonic()+10
                while not marker.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                if not marker.exists():self.fail('Owned launcher did not start; driver exit='+str(process.poll()))
                owned=psutil.Process(json.loads(marker.read_text())['pid']);created=owned.create_time()
                self.assertIn(str(launcher),owned.cmdline())
                process.send_signal(stopping)
                if repeated:
                    deadline=time.monotonic()+10
                    while not stopping_marker.exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertTrue(stopping_marker.exists(),'Verifier did not begin owned launcher cleanup')
                    for again in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):process.send_signal(again)
                stdout,stderr=process.communicate(timeout=30)
                self.assertNotEqual(process.returncode,0,'Interrupted verification must not pass')
                # Python preserves SIGINT's exit status for an uncaught
                # KeyboardInterrupt; the receipt/child prove cleanup.
                if stopping!=signal.SIGINT:self.assertNotEqual(process.returncode,-stopping,'Default signal bypassed cleanup')
                self.assertFalse(self.alive(owned),'Owned launcher survived verifier termination')
                receipt=json.loads((folder/'campaign/verification.json').read_text())
                self.assertEqual(receipt['status'],'failed')
                self.assertIn(signal.Signals(stopping).name,receipt['error'])
                self.assertEqual(receipt['exit_code'],0,'Launcher was not stopped through its own cleanup')
                self.assertIn('postflight',receipt)
            finally:
                if process.poll() is None:
                    process.kill();process.communicate(timeout=5)
                if owned is None and marker.exists():
                    try:
                        candidate=psutil.Process(json.loads(marker.read_text())['pid'])
                        if str(launcher) in candidate.cmdline():owned=candidate;created=candidate.create_time()
                    except psutil.NoSuchProcess:pass
                # A failing pre-fix run must still clean up its identified tiny launcher.
                if owned and self.alive(owned):
                    self.assertEqual(owned.create_time(),created)
                    self.assertIn(str(launcher),owned.cmdline())
                    owned.kill();owned.wait(timeout=5)

    @staticmethod
    def alive(process):
        try:return process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:return False

    def test_sigterm_stops_owned_launcher_and_fails_receipt(self):
        self.check_termination(signal.SIGTERM)

    def test_ctrl_c_stops_owned_launcher_and_fails_receipt(self):
        self.check_termination(signal.SIGINT)

    def test_sighup_stops_owned_launcher_and_fails_receipt(self):
        self.check_termination(signal.SIGHUP)

    def test_repeated_stops_during_cleanup_still_reap_launcher(self):
        self.check_termination(signal.SIGTERM,repeated=True)


if __name__=='__main__':unittest.main()
