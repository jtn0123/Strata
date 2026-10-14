from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from parent_trial_signals import forward_stop


class ParentSignalTests(unittest.TestCase):
    def test_signal_forwarding_returns_while_the_main_wait_lock_is_held(self):
        class Child:
            def __init__(self):
                self.wait_lock = threading.Lock()
                self.stopped = threading.Event()
                self.wait_called = False
            def poll(self): return 0 if self.stopped.is_set() else None
            def terminate(self): self.stopped.set()
            def kill(self): self.stopped.set()
            def wait(self, timeout=None):
                self.wait_called = True
                with self.wait_lock: return 0
        child = Child(); child.wait_lock.acquire()
        returned = threading.Event()
        timers = []
        def handler():
            timer = forward_stop(child)
            if timer: timers.append(timer)
            returned.set()
        worker = threading.Thread(target=handler, daemon=True)
        try:
            worker.start()
            self.assertTrue(returned.wait(0.25), 'A close handler must not reenter the held wait lock')
            self.assertTrue(child.stopped.is_set())
            self.assertFalse(child.wait_called)
        finally:
            child.wait_lock.release(); worker.join(timeout=1)
            for timer in timers: timer.cancel()

    def test_already_exited_and_unstarted_children_need_no_forwarding(self):
        class Exited:
            def poll(self): return 0
            def terminate(self): raise AssertionError('Already exited')
        self.assertIsNone(forward_stop(None))
        self.assertIsNone(forward_stop(Exited()))


if __name__ == '__main__': unittest.main()
