"""Start/stop bots as subprocesses. PIDs stored in pids.json."""
import json
import subprocess
import logging
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timezone

import psutil

from config import BOTS, PIDS_FILE, LOGS_DIR

# If no log/data file updated in this many seconds, bot is "stale"
# Scanner/Calibrator work hourly, Crock95 writes only on events — 10 min was too aggressive
HEALTH_STALE_SECONDS = 3900  # 65 minutes (covers hourly bots + margin)

log = logging.getLogger("bot_manager")

# Windows flag: child process survives parent death
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _load_pids() -> dict:
    try:
        if PIDS_FILE.exists():
            with open(PIDS_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_pids(pids: dict):
    with open(PIDS_FILE, "w") as f:
        json.dump(pids, f, indent=2)


def _is_bot_process(pid: int, bot_id: str) -> bool:
    """Check if PID is alive and matches the bot's expected command."""
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False
        # Check the process itself OR any of its children
        # (py.exe launcher spawns python.exe as child)
        all_procs = [proc] + proc.children(recursive=True)
        bot_cfg = BOTS.get(bot_id, {})
        main_script = bot_cfg.get("command", [""])[-1].lower()

        for p in all_procs:
            try:
                cmdline = " ".join(p.cmdline()).lower()
                if main_script in cmdline:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def _check_health(bot_id: str) -> dict:
    """Check if bot is actually working (not just alive as a process).
    Looks at modification time of data file and stdout log.
    Returns {"healthy": bool, "last_activity": float or None}.
    """
    bot_cfg = BOTS.get(bot_id, {})
    data_file = bot_cfg.get("path", Path()) / bot_cfg.get("data_file", "")
    log_stdout = LOGS_DIR / f"{bot_id}_stdout.log"
    log_stderr = LOGS_DIR / f"{bot_id}_stderr.log"

    now = time.time()
    last_activity = 0

    for f in [data_file, log_stdout, log_stderr]:
        try:
            mtime = os.path.getmtime(f)
            last_activity = max(last_activity, mtime)
        except OSError:
            pass

    if last_activity == 0:
        return {"healthy": False, "last_activity": None}

    healthy = (now - last_activity) < HEALTH_STALE_SECONDS
    return {"healthy": healthy, "last_activity": last_activity}


def get_status(bot_id: str) -> dict:
    """Get bot status: running/stopped/crashed, with health info."""
    pids = _load_pids()
    pid_info = pids.get(bot_id)

    if not pid_info:
        # Check if bot is running (started outside dashboard)
        pid = _find_running_bot(bot_id)
        if pid:
            health = _check_health(bot_id)
            return {"status": "running", "pid": pid, "started_by": "external",
                    "healthy": health["healthy"], "last_activity": health["last_activity"]}
        return {"status": "stopped", "pid": None}

    pid = pid_info.get("pid")
    if pid and _is_bot_process(pid, bot_id):
        health = _check_health(bot_id)
        return {
            "status": "running",
            "pid": pid,
            "started_at": pid_info.get("started_at", ""),
            "healthy": health["healthy"],
            "last_activity": health["last_activity"],
        }

    # PID exists in file but process dead — auto-clean pids.json
    pids.pop(bot_id, None)
    _save_pids(pids)
    return {"status": "crashed", "pid": pid, "started_at": pid_info.get("started_at", "")}


def _find_running_bot(bot_id: str) -> int | None:
    """Try to find a running bot process by scanning all Python processes."""
    bot_cfg = BOTS.get(bot_id)
    if not bot_cfg:
        return None

    main_script = bot_cfg["command"][-1].lower()
    bot_dir = str(bot_cfg["path"]).lower().replace("\\", "/")

    for proc in psutil.process_iter(["pid", "cmdline", "cwd"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            cwd = (proc.info.get("cwd") or "").lower().replace("\\", "/")
            if main_script in cmdline and (bot_dir in cmdline or bot_dir in cwd):
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def get_all_statuses() -> dict:
    """Get status of all bots."""
    return {bot_id: get_status(bot_id) for bot_id in BOTS}


def start_bot(bot_id: str) -> dict:
    """Start a bot. Returns status dict."""
    if bot_id not in BOTS:
        return {"status": "error", "message": f"Unknown bot: {bot_id}"}

    current = get_status(bot_id)
    if current["status"] == "running":
        return {"status": "already_running", "pid": current["pid"]}

    bot_cfg = BOTS[bot_id]
    LOGS_DIR.mkdir(exist_ok=True)

    log_out = open(LOGS_DIR / f"{bot_id}_stdout.log", "a", encoding="utf-8")
    log_err = open(LOGS_DIR / f"{bot_id}_stderr.log", "a", encoding="utf-8")

    # Write separator
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_out.write(f"\n{'='*60}\nStarted at {ts}\n{'='*60}\n")
    log_out.flush()

    try:
        proc = subprocess.Popen(
            bot_cfg["command"],
            cwd=str(bot_cfg["path"]),
            stdout=log_out,
            stderr=log_err,
            creationflags=CREATE_NEW_PROCESS_GROUP,
        )
    except Exception as e:
        log_out.close()
        log_err.close()
        return {"status": "error", "message": str(e)}

    # Wait briefly and verify the process didn't crash immediately
    time.sleep(1.5)
    if proc.poll() is not None:
        # Process already exited — read stderr for details
        log_out.close()
        log_err.close()
        error_text = ""
        try:
            stderr_path = LOGS_DIR / f"{bot_id}_stderr.log"
            error_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-500:]
        except OSError:
            pass
        log.error("Bot %s crashed immediately (code %s): %s", bot_id, proc.returncode, error_text[:200])
        return {"status": "error", "message": f"Crashed on start (code {proc.returncode}): {error_text[:200]}"}

    # Save PID only after confirming process is alive
    pids = _load_pids()
    pids[bot_id] = {
        "pid": proc.pid,
        "started_at": ts,
    }
    _save_pids(pids)

    log.info("Started %s (PID %d)", bot_id, proc.pid)
    return {"status": "started", "pid": proc.pid}


def _find_all_running_bot_pids(bot_id: str) -> list[int]:
    """Find ALL running processes for a bot (catches duplicates)."""
    bot_cfg = BOTS.get(bot_id)
    if not bot_cfg:
        return []

    main_script = bot_cfg["command"][-1].lower()
    bot_dir = str(bot_cfg["path"]).lower().replace("\\", "/")
    pids_found = []

    for proc in psutil.process_iter(["pid", "cmdline", "cwd"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            cwd = (proc.info.get("cwd") or "").lower().replace("\\", "/")
            if main_script in cmdline and (bot_dir in cmdline or bot_dir in cwd):
                pids_found.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids_found


def stop_bot(bot_id: str) -> dict:
    """Stop a bot — kills ALL matching processes (no orphans)."""
    # Find all processes for this bot
    all_pids = _find_all_running_bot_pids(bot_id)

    # Also include PID from pids.json
    pids_data = _load_pids()
    saved_pid = (pids_data.get(bot_id) or {}).get("pid")
    if saved_pid and saved_pid not in all_pids:
        all_pids.append(saved_pid)

    if not all_pids:
        pids_data.pop(bot_id, None)
        _save_pids(pids_data)
        return {"status": "not_running"}

    killed = []
    for pid in all_pids:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            log.warning("Could not stop PID %d: %s", pid, e)

    # Clean PID file
    pids_data.pop(bot_id, None)
    _save_pids(pids_data)

    log.info("Stopped %s (killed PIDs: %s)", bot_id, killed)
    return {"status": "stopped", "pid": killed[0] if killed else None, "killed_count": len(killed)}


def get_bot_log(bot_id: str, lines: int = 50) -> str:
    """Read last N lines from bot's stdout log."""
    log_path = LOGS_DIR / f"{bot_id}_stdout.log"
    if not log_path.exists():
        return "(no log file)"

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except OSError:
        return "(error reading log)"
