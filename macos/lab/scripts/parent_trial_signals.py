"""Forward closure without reentering Popen.wait from a Python signal handler."""
import threading


def forward_stop(child):
    # A handler can interrupt the main thread while Popen.wait holds _waitpid_lock.
    # Never wait here. The original wait reaps the child once the handler returns.
    if child is None or child.poll() is not None:
        return
    child.terminate()
    def force():
        if child.poll() is None:
            child.kill()
    timer = threading.Timer(5, force)
    timer.daemon = True
    timer.start()
    return timer
