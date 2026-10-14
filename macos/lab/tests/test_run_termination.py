"""Ordinary app startup cancellation reaps tiny owned native/API fixtures."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

ROOT = Path(__file__).resolve().parents[1]


class RunTerminationTests(unittest.TestCase):
    def check_stop(self, stopping, stage):
        with tempfile.TemporaryDirectory(prefix='strata-app-termination-') as temporary:
            folder = Path(temporary)
            (folder / 'bench').mkdir()
            observer, finished = folder / 'observer-ready', folder / 'monitor-finished'
            fake = folder / 'owned-fixture.py'
            fake.write_text('''import json,os,sys,time
from pathlib import Path
marker=Path(sys.argv[1])/(sys.argv[2]+'.json')
pending=marker.with_suffix('.tmp')
pending.write_text(json.dumps({'pid':os.getpid()}))
pending.replace(marker)
while True: time.sleep(1)
''')
            driver = folder / 'driver.py'
            driver.write_text('''import os,signal,sys,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, ''' + repr(str(ROOT / 'scripts')) + ''')
import run
folder=Path(''' + repr(str(folder)) + ''')
run.ROOT=folder
run.experiment_environment=lambda *args:({}, {})
run.configure=lambda *args:({}, {})
run.assert_no_model_server=lambda:None
run.verify_engine=lambda *args:{}
run.verify_models=lambda *args:{}
run.assert_ports_available=lambda *args:None
run.admit_model=lambda *args:{'baseline':{'swap_used_bytes':0}}
run.server_command=lambda *args,**kwargs:[sys.executable, ''' + repr(str(fake)) + ''',str(folder),'native']
run.wait_ready=lambda *args:None
class Monitor:
    guard=None
    thread=SimpleNamespace(start=lambda:None)
    def finish(self):
        (folder/'monitor-finished').write_text('finished')
        return {'fixture':'finalized'}
run.app_monitor=lambda *args:Monitor()
original_spawn=run.subprocess.Popen
def spawn(*args,**kwargs):
    role='api' if any(str(arg).endswith('strata_server.py') for arg in args[0]) else 'native'
    if role=='api':
        args=([sys.executable, ''' + repr(str(fake)) + ''',str(folder),role],)
        # An orphan must not retain the driver's captured pipes and turn a clear
        # ownership failure into a communicate() timeout in the regression test.
        kwargs=dict(kwargs,stdout=run.subprocess.DEVNULL,stderr=run.subprocess.DEVNULL)
    child=original_spawn(*args,**kwargs)
    if role==''' + repr(stage) + ''':
        deadline=time.monotonic()+10
        while not (folder/'observer-ready').exists() and time.monotonic()<deadline:time.sleep(.01)
        if not (folder/'observer-ready').exists():raise RuntimeError('Fixture observer not ready')
        os.kill(os.getpid(),''' + str(int(stopping)) + ''')
    return child
run.subprocess.Popen=spawn
run.main(['small'])
''')
            driver_process = subprocess.Popen([sys.executable, str(driver)], stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, text=True)
            owned = []
            try:
                roles = ['native'] if stage == 'native' else ['native', 'api']
                deadline = time.monotonic() + 10
                while not all((folder / (role + '.json')).exists() for role in roles):
                    if driver_process.poll() is not None or time.monotonic() > deadline:
                        self.fail('Owned startup fixtures did not become ready')
                    time.sleep(.02)
                for role in roles:
                    process = psutil.Process(json.loads((folder / (role + '.json')).read_text())['pid'])
                    self.assertIn(str(fake), process.cmdline())
                    owned.append((process, process.create_time()))
                observer.write_text('owned fixtures identified')
                stdout, stderr = driver_process.communicate(timeout=25)
                self.assertEqual(driver_process.returncode, 0, stdout + stderr)
                self.assertTrue(finished.exists(), 'Memory guard was not finalized')
                self.assertFalse((folder / 'bench/runtime/active.json').exists())
                for process, _ in owned:
                    self.assertFalse(self.alive(process), 'Owned fixture survived cancellation')
            finally:
                if driver_process.poll() is None:
                    driver_process.terminate()
                    try: driver_process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        driver_process.kill(); driver_process.communicate(timeout=5)
                # Every failing fixture run must still stop only identified children.
                known = {process.pid for process, _ in owned}
                for role in ('native', 'api'):
                    marker = folder / (role + '.json')
                    if marker.exists():
                        try:
                            process = psutil.Process(json.loads(marker.read_text())['pid'])
                            if process.pid not in known and str(fake) in process.cmdline():
                                owned.append((process, process.create_time()))
                        except psutil.NoSuchProcess: pass
                for process, created in owned:
                    if self.alive(process):
                        self.assertEqual(process.create_time(), created)
                        self.assertIn(str(fake), process.cmdline())
                        process.terminate()
                        try: process.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            process.kill(); process.wait(timeout=5)

    @staticmethod
    def alive(process):
        try: return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess: return False

    def test_termination_at_native_and_api_creation_reaps_every_owned_child(self):
        for stopping in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            for stage in ('native', 'api'):
                with self.subTest(stopping=stopping, stage=stage): self.check_stop(stopping, stage)


if __name__ == '__main__': unittest.main()
