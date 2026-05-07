import psutil
for p in psutil.process_iter(["pid", "cmdline"]):
    try:
        cmd = " ".join(p.info.get("cmdline") or [])
        if "app.py" in cmd and "dashboard" in cmd:
            print(f"Killing PID {p.info['pid']}")
            psutil.Process(p.info["pid"]).kill()
    except Exception:
        pass
print("Done")
