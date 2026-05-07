"""
Metrics + report loop:
  - _reconcile.py       → every 5 minutes (fix any tracker drift vs on-chain)
  - _gen_report.py      → every 5 minutes (fast, regenerates the markdown)
  - _collect_metrics.py → every 30 minutes (heavier, talks to trades API for 4 wallets)
Used by the dashboard as a long-running process.
"""
import sys
import io
import os
import time
import traceback
import subprocess

# File-based logging so stdout redirection isn't required.
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metrics_loop.log')


class _TeeFile:
    """Write to both a log file and whatever the original stdout was."""
    def __init__(self, path):
        self._f = open(path, 'a', encoding='utf-8', errors='replace', buffering=1)
        try:
            self._orig = io.TextIOWrapper(sys.__stdout__.buffer, encoding='utf-8', errors='replace')
        except Exception:
            self._orig = None

    def write(self, s):
        try:
            self._f.write(s)
            self._f.flush()
        except Exception:
            pass
        if self._orig is not None:
            try:
                self._orig.write(s)
                self._orig.flush()
            except Exception:
                pass

    def flush(self):
        try:
            self._f.flush()
        except Exception:
            pass
        if self._orig is not None:
            try:
                self._orig.flush()
            except Exception:
                pass


sys.stdout = _TeeFile(LOG_PATH)
sys.stderr = sys.stdout

REPORT_INTERVAL_SEC = 300    # 5 minutes
METRICS_INTERVAL_SEC = 1800  # 30 minutes


def run_script(script_name: str) -> bool:
    """Run a Python script, stream output."""
    result = subprocess.run(
        ['py', '-3.12', '-X', 'utf8', script_name],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"[{script_name} STDERR] {result.stderr}", file=sys.stderr)
    return result.returncode == 0


def main():
    print(f"[metrics_loop] started: report every {REPORT_INTERVAL_SEC}s, "
          f"metrics every {METRICS_INTERVAL_SEC}s")
    last_metrics = 0.0
    while True:
        cycle_start = time.time()
        now_str = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        print(f"\n[metrics_loop] === cycle at {now_str} ===")

        # Metrics — only every METRICS_INTERVAL_SEC
        if cycle_start - last_metrics >= METRICS_INTERVAL_SEC:
            try:
                print("[metrics_loop] Running _collect_metrics.py ...")
                run_script('_collect_metrics.py')
                last_metrics = cycle_start
            except Exception as e:
                print(f"[metrics_loop] metrics ERROR: {e}")
                traceback.print_exc()

        # Reconcile — every cycle (MUST run before report so report reflects fixes)
        try:
            print("[metrics_loop] Running _reconcile.py ...")
            run_script('_reconcile.py')
        except Exception as e:
            print(f"[metrics_loop] reconcile ERROR: {e}")
            traceback.print_exc()

        # Report — every cycle (every REPORT_INTERVAL_SEC)
        try:
            print("[metrics_loop] Running _gen_report.py ...")
            run_script('_gen_report.py')
        except Exception as e:
            print(f"[metrics_loop] report ERROR: {e}")
            traceback.print_exc()

        # Sleep in 10s chunks so we can be killed gracefully
        elapsed = time.time() - cycle_start
        remaining = max(0, REPORT_INTERVAL_SEC - elapsed)
        while remaining > 0:
            time.sleep(min(10, remaining))
            remaining -= 10


if __name__ == '__main__':
    main()
