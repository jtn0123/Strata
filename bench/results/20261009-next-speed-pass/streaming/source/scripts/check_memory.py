#!/usr/bin/env python3
"""Read current Mac memory and RAM-heavy process names without starting inference."""
import subprocess

import psutil

GIB = 1024**3


def assert_no_model_server():
    servers = []
    for process in psutil.process_iter(["name"]):
        if (process.info["name"] or "").startswith("llama-server"):
            servers.append(process.pid)
    if servers:
        raise RuntimeError(f"Stop the running native model servers before a benchmark: PIDs {servers}")


def snapshot():
    groups = {}
    for process in psutil.process_iter(["name", "memory_info"]):
        try:
            info = process.info
            if info["memory_info"]:
                name = info["name"] or "unknown"
                groups[name] = groups.get(name, 0) + info["memory_info"].rss
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    pressure = subprocess.check_output(["memory_pressure", "-Q"], text=True).strip()
    return {"memory": psutil.virtual_memory()._asdict(), "swap": psutil.swap_memory()._asdict(),
            "pressure": pressure,
            "largest_process_groups": [{"name": name, "rss_bytes": rss} for name, rss in
                                       sorted(groups.items(), key=lambda pair: pair[1], reverse=True)[:12]],
            "note": "Process RSS can double-count shared pages and omit Metal/compressed memory. Available RAM is reclaimable, not simply unused. Existing swap is separate from new swap growth."}


def print_snapshot(info):
    memory = info["memory"]
    print(f"RAM: {memory['total']/GIB:.1f} GiB total, {memory['available']/GIB:.1f} GiB available, "
          f"{memory['wired']/GIB:.1f} GiB wired. Swap used: {info['swap']['used']/GIB:.2f} GiB.")
    print(info["pressure"])
    print("Largest process names (grouped RSS; approximate):")
    for item in info["largest_process_groups"]:
        print(f"  {item['rss_bytes']/GIB:5.2f} GiB  {item['name']}")
    print(info["note"])


if __name__ == "__main__":
    print_snapshot(snapshot())
