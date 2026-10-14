"""Unwind trial drivers through their existing owned-child/guard cleanup."""

from contextlib import contextmanager
import signal
from collections.abc import Callable, Iterator, Sequence
from types import FrameType
from typing import NoReturn

SignalHandler = Callable[[int, FrameType | None], object] | int


def termination_signals() -> list[signal.Signals]:
    return [signal.SIGINT, signal.SIGTERM] + ([signal.SIGHUP] if hasattr(signal, "SIGHUP") else [])


def signal_handlers(numbers: Sequence[int]) -> dict[int, SignalHandler]:
    previous: dict[int, SignalHandler] = {}
    for number in numbers:
        handler = signal.getsignal(number)
        if handler is None:
            raise RuntimeError(f"Cannot safely restore unknown handler for signal {number}")
        previous[number] = handler
    return previous


@contextmanager
def cleanup_on_termination() -> Iterator[None]:
    signals = termination_signals()
    previous = signal_handlers(signals)

    def interrupted(number: int, frame: FrameType | None) -> NoReturn:
        # Do not wait/reenter Popen from a Python signal handler. Unwind to the
        # driver's finally blocks, and let bounded cleanup survive repeated stops.
        for stopping in signals:
            signal.signal(stopping, signal.SIG_IGN)
        raise KeyboardInterrupt(f"Termination requested ({signal.Signals(number).name})")

    try:
        for stopping in signals:
            signal.signal(stopping, interrupted)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


@contextmanager
def defer_termination() -> Iterator[None]:
    """Publish newly created child/monitor references before cancellation unwinds.

    Handlers only remember the signal in this short resource-creation section.
    Unlike blocking a POSIX signal mask, this does not leave a spawned tool with
    inherited blocked termination signals. Nested sections pass the stop outward.
    """
    previous = signal_handlers(termination_signals())
    pending: tuple[int, FrameType | None] | None = None

    def remember(number: int, frame: FrameType | None) -> None:
        nonlocal pending
        pending = (number, frame)

    try:
        for number in previous:
            signal.signal(number, remember)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        if pending:
            number, frame = pending
            handler = previous[number]
            if callable(handler):
                handler(number, frame)
            elif handler != signal.SIG_IGN:
                raise KeyboardInterrupt(f"Termination requested ({signal.Signals(number).name})")
