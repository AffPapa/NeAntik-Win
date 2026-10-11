"""Reproducible disposable metadata/UI benchmark; never opens user Data."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nevision_win as nv


def summarize(values):
    ordered = sorted(values)
    return {"samples": len(values), "median_ms": round(statistics.median(values), 3),
            "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * .95))], 3),
            "max_ms": round(max(values), 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"version": nv.APP_VERSION, "python": platform.python_version(),
              "os": platform.platform(), "logical_cpus": os.cpu_count(), "cases": []}
    for count in (10, 100, 1000):
        with tempfile.TemporaryDirectory(prefix="nevision-benchmark-") as folder:
            paths = nv.AppPaths(Path(folder))
            storage = nv.Storage(paths)
            for index in range(count):
                storage.save_profile({"name": f"QA {index:05}", "group_name": f"Group {index % 5}", "tags": "test"})
            started = time.perf_counter()
            app = nv.NeVisionApp(storage, paths)
            app.root.update_idletasks()
            ready_ms = (time.perf_counter() - started) * 1000
            app.root.withdraw()
            search_times, refresh_times = [], []
            for _ in range(30):
                started = time.perf_counter()
                storage.list_profiles("QA")
                search_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter()
                app.refresh_profiles()
                app.root.update_idletasks()
                refresh_times.append((time.perf_counter() - started) * 1000)
            result["cases"].append({"profiles": count, "ui_ready_ms": round(ready_ms, 3),
                                    "search": summarize(search_times), "refresh": summarize(refresh_times)})
            if hasattr(app, "_executor"):
                app._executor.shutdown(wait=True)
            # The root is destroyed after synchronous measurements; no worker task was started.
            for timer in app.root.tk.call("after", "info"):
                app.root.after_cancel(timer)
            app.root.destroy()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
