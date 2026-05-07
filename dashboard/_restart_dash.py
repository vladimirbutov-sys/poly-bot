import sys, os, time
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import psutil, subprocess

PORT = 8083

# Step 1: Kill everything on the dashboard port (including child processes)
killed = set()
for c in psutil.net_connections():
    if c.laddr and c.laddr.port == PORT and c.pid and c.pid not in killed:
        try:
            proc = psutil.Process(c.pid)
            for child in proc.children(recursive=True):
                print(f"Killing child PID {child.pid}")
                child.kill()
                killed.add(child.pid)
            print(f"Killing PID {c.pid} on port {PORT}")
            proc.kill()
            killed.add(c.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"  skip: {e}")

# Step 2: Also kill any app.py dashboard processes by name
for p in psutil.process_iter(["pid", "cmdline"]):
    try:
        cmd = " ".join(p.info.get("cmdline") or [])
        if "app.py" in cmd and p.info["pid"] not in killed:
            print(f"Killing dashboard PID {p.info['pid']}")
            psutil.Process(p.info["pid"]).kill()
    except Exception:
        pass

time.sleep(2)

# Step 3: Start fresh
proc = subprocess.Popen(
    ['py', '-3.12', '-X', 'utf8', 'app.py'],
    cwd=os.path.dirname(os.path.abspath(__file__)),
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)
print(f"Dashboard started, PID {proc.pid}")
