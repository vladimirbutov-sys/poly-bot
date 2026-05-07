"""Stop all bot and dashboard processes."""
import psutil
import time

targets = ["main.py", "scanner.py", "manager.py", "app.py"]
killed = []

for p in psutil.process_iter(["pid", "cmdline"]):
    try:
        cmd = " ".join(p.info.get("cmdline") or [])
        if any(t in cmd for t in targets) and "stop_all" not in cmd:
            print(f"  Killing PID {p.info['pid']}: {cmd[:80]}")
            psutil.Process(p.info["pid"]).kill()
            killed.append(p.info["pid"])
    except Exception:
        pass

print(f"\nKilled {len(killed)} processes. Waiting 3s...")
time.sleep(3)
print("Ready for clean start.")
