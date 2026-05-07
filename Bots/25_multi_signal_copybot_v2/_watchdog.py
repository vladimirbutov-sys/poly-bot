"""
Watchdog for 25_multi_signal_copybot + _metrics_loop.py

Checks every 60 seconds that both processes are alive. If a process dies,
restarts it detached using subprocess and sends a Telegram alert.

State file: pids.json in dashboard/ (shared with dashboard so UI sees
the same PIDs).

Usage: py -3.12 -u -X utf8 _watchdog.py
"""
import os
import sys
import io
import json
import time
import subprocess
from datetime import datetime, timezone

import psutil
import requests
from dotenv import load_dotenv

# ---------- paths ----------
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
POLYMARKET_DIR = os.path.abspath(os.path.join(BOT_DIR, '..', '..'))
DASHBOARD_PIDS = os.path.join(POLYMARKET_DIR, 'dashboard', 'pids.json')
LOG_PATH = os.path.join(BOT_DIR, 'watchdog.log')

# ---------- file-based logging (survives detached launch) ----------
_log_f = open(LOG_PATH, 'a', encoding='utf-8', errors='replace', buffering=1)


def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    line = f'[{ts}] {msg}'
    try:
        _log_f.write(line + '\n')
        _log_f.flush()
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


# ---------- telegram ----------
load_dotenv(os.path.join(BOT_DIR, '..', '98_sure_bot', '.env'))
TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.getenv('TELEGRAM_CHAT_ID', '')


def tg_send(text):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            json={'chat_id': TG_CHAT, 'text': text, 'disable_notification': False},
            timeout=8,
        )
    except Exception as e:
        log(f'  tg error: {e}')


# ---------- monitored processes ----------
# Each entry: name, workdir, cmd (list), restart_cooldown_sec
V1_DIR = os.path.abspath(os.path.join(BOT_DIR, '..', '25_multi_signal_copybot'))

PROCESSES = {
    # v1 removed — migrated to v2 on 2026-04-12
    '25_multi_signal_copybot_v2': {
        'workdir': BOT_DIR,
        'cmd': ['py', '-3.12', '-u', '-X', 'utf8', 'main.py', '--bot-tag=25_multi_signal_copybot_v2'],
        'cooldown_until': 0,
        'cmdline_marker': ['main.py', '25_multi_signal_copybot_v2'],
    },
    '25_copybot_metrics': {
        'workdir': BOT_DIR,
        'cmd': ['py', '-3.12', '-u', '-X', 'utf8', '_metrics_loop.py', '--bot-tag=25_copybot_metrics'],
        'cooldown_until': 0,
        'cmdline_marker': ['_metrics_loop.py'],
    },
}

CHECK_INTERVAL_SEC = 60
RESTART_COOLDOWN_SEC = 120  # don't restart same process more than once per 2 min
MAX_RESTARTS_PER_HOUR = 10
MIN_ALIVE_SECONDS = 20  # wait this long after start before verifying


# ---------- pids.json helpers ----------
def load_pids():
    try:
        with open(DASHBOARD_PIDS, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_pids(data):
    try:
        tmp = DASHBOARD_PIDS + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DASHBOARD_PIDS)
    except Exception as e:
        log(f'  save_pids err: {e}')


# ---------- process check ----------
def _process_matches(p, cmdline_marker):
    """Check if a psutil.Process belongs to our bot.

    Strategy: marker is a list of substrings, ALL must match across
    either cwd or cmdline. This lets us require BOTH a script name
    (e.g. 'main.py') AND a working directory (e.g. '25_multi_signal_copybot'),
    which is necessary when multiple bots live in different folders
    and all run their own 'main.py'.
    """
    markers = cmdline_marker if isinstance(cmdline_marker, (list, tuple)) else [cmdline_marker]
    try:
        try:
            cwd = p.cwd()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cwd = ''
        try:
            cmdline = ' '.join(p.cmdline())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cmdline = ''
        haystack = (cwd + ' ' + cmdline).lower()
        for m in markers:
            if m.lower() not in haystack:
                return False
        return True
    except Exception:
        return False


def process_alive(pid, cmdline_marker=None):
    """Check if a PID exists AND (optionally) matches expected marker."""
    if not pid or pid <= 0:
        return False
    try:
        if not psutil.pid_exists(pid):
            return False
        p = psutil.Process(pid)
        if p.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
            return False
        if cmdline_marker:
            return _process_matches(p, cmdline_marker)
        return True
    except Exception:
        return False


def find_running_pid(cmdline_marker):
    """Scan all python processes looking for one with given marker.
    Used as fallback if pids.json is stale."""
    try:
        for p in psutil.process_iter(['pid', 'name']):
            try:
                info = p.info
                name = (info.get('name') or '').lower()
                if 'python' not in name:
                    continue
                if _process_matches(p, cmdline_marker):
                    return info['pid']
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
    except Exception:
        pass
    return None


# ---------- restart ----------
def restart_process(name, cfg):
    """Launch process detached on Windows using CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS."""
    log(f'[RESTART] {name} — launching...')
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

        # Redirect output to nul so process doesn't block on any stdout write
        with open(os.devnull, 'wb') as devnull:
            p = subprocess.Popen(
                cfg['cmd'],
                cwd=cfg['workdir'],
                creationflags=flags,
                stdin=devnull,
                stdout=devnull,
                stderr=devnull,
                close_fds=True,
            )
        new_pid = p.pid
        log(f'[RESTART] {name} — started PID={new_pid}')

        # Wait a few seconds and verify it's still alive
        time.sleep(MIN_ALIVE_SECONDS)
        if process_alive(new_pid, cfg.get('cmdline_marker')):
            log(f'[RESTART] {name} — OK, still alive after {MIN_ALIVE_SECONDS}s')

            # Update pids.json
            pids = load_pids()
            pids[name] = {
                'pid': new_pid,
                'started_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'restarted_by_watchdog': True,
            }
            save_pids(pids)

            tg_send(f'🔄 Watchdog restarted {name}\nNew PID: {new_pid}')
            return new_pid
        else:
            log(f'[RESTART] {name} — FAILED (not alive after {MIN_ALIVE_SECONDS}s)')
            tg_send(f'⚠️ Watchdog FAILED to restart {name}')
            return None
    except Exception as e:
        log(f'[RESTART] {name} — exception: {e}')
        tg_send(f'⚠️ Watchdog restart exception for {name}: {e}')
        return None


# ---------- main ----------
def main():
    log('=' * 60)
    log('Watchdog started')
    log(f'  checking every {CHECK_INTERVAL_SEC}s')
    log(f'  monitoring: {list(PROCESSES.keys())}')
    log(f'  log file: {LOG_PATH}')
    tg_send('🟢 Watchdog started\n' + '\n'.join(f'  • {n}' for n in PROCESSES))

    restart_history = {name: [] for name in PROCESSES}

    while True:
        try:
            pids = load_pids()
            now = time.time()

            for name, cfg in PROCESSES.items():
                entry = pids.get(name, {}) or {}
                pid = entry.get('pid')

                alive = process_alive(pid, cfg.get('cmdline_marker'))

                if not alive:
                    # Try to find it by cmdline scan (fallback if pids.json is stale)
                    scanned_pid = find_running_pid(cfg['cmdline_marker'])
                    if scanned_pid:
                        log(f'[{name}] found by cmdline scan (PID={scanned_pid}), updating pids.json')
                        pids[name] = {
                            'pid': scanned_pid,
                            'started_at': entry.get('started_at') or datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                        }
                        save_pids(pids)
                        continue

                    # Actually dead — check cooldown
                    if now < cfg['cooldown_until']:
                        continue

                    # Rate limit
                    restart_history[name] = [t for t in restart_history[name] if now - t < 3600]
                    if len(restart_history[name]) >= MAX_RESTARTS_PER_HOUR:
                        log(f'[{name}] DEAD but rate-limited (>{MAX_RESTARTS_PER_HOUR}/hr)')
                        continue

                    log(f'[{name}] DEAD (pid={pid}) — restarting')
                    tg_send(f'💀 {name} DIED\nRestarting...')
                    new_pid = restart_process(name, cfg)
                    cfg['cooldown_until'] = now + RESTART_COOLDOWN_SEC
                    if new_pid:
                        restart_history[name].append(now)
            # === On-chain sync verification (every 10 cycles = ~10 min) ===
            if not hasattr(main, '_verify_counter'):
                main._verify_counter = 0
            main._verify_counter += 1
            if main._verify_counter % 10 == 0:
                try:
                    _verify_sync()
                except Exception as ve:
                    log(f'[VERIFY] error: {ve}')

        except Exception as e:
            log(f'[MAIN_LOOP] error: {e}')

        time.sleep(CHECK_INTERVAL_SEC)


def _verify_sync():
    """Check on-chain positions vs v2 state. Alert if mismatch."""
    try:
        import httpx
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BOT_DIR, '..', '98_sure_bot', '.env'))
        wallet = os.getenv('POLYMARKET_WALLET', '')
        if not wallet:
            return

        r = httpx.get(
            'https://data-api.polymarket.com/positions',
            params={'user': wallet, 'limit': 500, 'sizeThreshold': 0.5},
            timeout=15,
        )
        onchain = [p for p in r.json() if float(p.get('currentValue', 0)) > 1]

        positions_path = os.path.join(BOT_DIR, 'positions.json')
        import json
        with open(positions_path) as f:
            v2 = json.load(f)
        v2_keys = set()
        for p in v2.get('positions', {}).values():
            if p.get('status') == 'open':
                v2_keys.add((p.get('condition_id', ''), str(p.get('token_id', ''))))

        missing = []
        for p in onchain:
            key = (p.get('conditionId', ''), p.get('asset', ''))
            if key not in v2_keys:
                missing.append(p)

        if missing:
            total_val = sum(float(p.get('currentValue', 0)) for p in missing)
            msg = (f'⚠️ SYNC MISMATCH: {len(missing)} on-chain positions '
                   f'(${total_val:.0f}) NOT in v2 state')
            log(f'[VERIFY] {msg}')
            # TG отключено по запросу 2026-04-20: был шум каждые 10 мин по мелочёвке $1-8
            # tg_send(msg)
        else:
            log(f'[VERIFY] OK: {len(onchain)} on-chain = {len(onchain)} matched')
    except Exception as e:
        log(f'[VERIFY] fetch error: {e}')


if __name__ == '__main__':
    main()
