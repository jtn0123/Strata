"""Unwind trial drivers through their existing owned-child/guard cleanup."""
from contextlib import contextmanager
import signal


def termination_signals():
    return [signal.SIGINT,signal.SIGTERM]+([signal.SIGHUP] if hasattr(signal,'SIGHUP') else [])


@contextmanager
def cleanup_on_termination():
    signals=termination_signals()
    previous={number:signal.getsignal(number) for number in signals}

    def interrupted(number, frame):
        # Do not wait/reenter Popen from a Python signal handler. Unwind to the
        # driver's finally blocks, and let bounded cleanup survive repeated stops.
        for stopping in signals:
            signal.signal(stopping,signal.SIG_IGN)
        raise KeyboardInterrupt(f'Termination requested ({signal.Signals(number).name})')

    try:
        for number in signals:
            signal.signal(number,interrupted)
        yield
    finally:
        for number,handler in previous.items():
            signal.signal(number,handler)


@contextmanager
def defer_termination():
    """Publish newly created child/monitor references before cancellation unwinds.

    Handlers only remember the signal in this short resource-creation section.
    Unlike blocking a POSIX signal mask, this does not leave a spawned tool with
    inherited blocked termination signals. Nested sections pass the stop outward.
    """
    previous={number:signal.getsignal(number) for number in termination_signals()}
    pending=None

    def remember(number,frame):
        nonlocal pending
        pending=(number,frame)

    try:
        for number in previous:
            signal.signal(number,remember)
        yield
    finally:
        for number,handler in previous.items():
            signal.signal(number,handler)
        if pending:
            number,frame=pending
            handler=previous[number]
            if callable(handler):
                handler(number,frame)
            elif handler!=signal.SIG_IGN:
                raise KeyboardInterrupt(f'Termination requested ({signal.Signals(number).name})')
