import psutil, time

PORT = 8083

# Kill any process on dashboard port
for c in psutil.net_connections():
    if c.laddr and c.laddr.port == PORT and c.pid:
        try:
            proc = psutil.Process(c.pid)
            print(f"Killing PID {c.pid} on port {PORT}")
            # Kill the whole process tree (parent + children)
            for child in proc.children(recursive=True):
                child.kill()
            proc.kill()
        except Exception as e:
            print(f"  error: {e}")

# Also kill any app.py processes
for p in psutil.process_iter(["pid", "cmdline"]):
    try:
        cmd = " ".join(p.info.get("cmdline") or [])
        if "app.py" in cmd and "dashboard" in cmd:
            print(f"Killing dashboard PID {p.info['pid']}")
            psutil.Process(p.info["pid"]).kill()
    except Exception:
        pass

print("Done, waiting 3s...")
time.sleep(3)
print("Ready")
