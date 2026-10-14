#!/usr/bin/env python3
"""Stop only this lab's recorded supervisor, allowing it to release both servers."""

import json
import signal
import psutil
from typing import TypedDict
from lab import ROOT


class ActiveSupervisor(TypedDict):
    pid: int
    create_time: float


def main() -> None:
    path = ROOT / "bench/runtime/active.json"
    if not path.exists():
        print("No running Strata lab is recorded.")
        return
    saved: ActiveSupervisor = json.loads(path.read_text())
    try:
        process = psutil.Process(saved["pid"])
    except psutil.NoSuchProcess:
        path.unlink()
        print("Strata is already stopped.")
        return
    if abs(process.create_time() - saved["create_time"]) > 0.01:
        raise RuntimeError(
            "Recorded process was replaced; refusing to signal an unrelated process"
        )
    command = process.cmdline()
    supervisors = {
        form
        for name in ("run.py", "runtime_profiles.py")
        for form in ("scripts/" + name, str(ROOT / "scripts" / name))
    }
    if not any(arg in supervisors for arg in command):
        raise RuntimeError("Recorded process is not this lab's supervisor")
    if process.cwd() != str(ROOT):
        raise RuntimeError("Recorded process belongs to another workspace")
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=25)
    print("Strata stopped. Model memory released.")


if __name__ == "__main__":
    main()
