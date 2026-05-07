"""
Pre-launch architecture check for 25_multi_signal_copybot_v2
============================================================
Run BEFORE starting the bot after any reboot.

Usage:  py -3.12 _prelaunch_check.py

Exit codes:
  0 = all good, safe to launch
  1 = warnings only (can still launch, but review output)
  2 = critical errors found (DO NOT launch until fixed)
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime, timezone

# Force UTF-8 output on Windows (avoids cp1251 encoding errors)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
POLYMARKET_DIR = os.path.abspath(os.path.join(BOT_DIR, '..', '..'))
DASHBOARD_PIDS = os.path.join(POLYMARKET_DIR, 'dashboard', 'pids.json')
ENV_PATH = os.path.join(BOT_DIR, '.env')
SURE_ENV = os.path.join(BOT_DIR, '..', '98_sure_bot', '.env')

REQUIRED_FILES = [
    'main.py',
    'config.py',
    'tracker.py',
    'monitor.py',
    'entry_manager.py',
    'exit_manager.py',
    'executor.py',
    'filters.py',
    'telegram_notify.py',
    'telegram_cmd.py',
    'redeemer.py',
    'mode_manager.py',
    'daily_report.py',
    '_metrics_loop.py',
    '_watchdog.py',
    'positions.json',
    'buy_buffers.json',
    'signals.json',
    '.env',
]

REQUIRED_ENV_KEYS = [
    'POLYMARKET_WALLET',
    'POLYMARKET_PRIVATE_KEY',
    'TELEGRAM_BOT_TOKEN',
    'TELEGRAM_CHAT_ID',
]

REQUIRED_PACKAGES = [
    'requests', 'dotenv', 'web3', 'httpx', 'psutil',
]

# ───────────────── helpers ─────────────────

RED    = '\033[91m'
GREEN  = '\033[92m'
YELLOW = '\033[93m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

def ok(msg):    print(f"  {GREEN}\u2713{RESET}  {msg}")
def warn(msg):  print(f"  {YELLOW}!{RESET}    {msg}")
def err(msg):   print(f"  {RED}X{RESET}    {msg}")
def head(msg):  print(f"\n{BOLD}{msg}{RESET}")

errors   = []
warnings = []

def check(condition, ok_msg, fail_msg, critical=True):
    if condition:
        ok(ok_msg)
    else:
        if critical:
            err(fail_msg)
            errors.append(fail_msg)
        else:
            warn(fail_msg)
            warnings.append(fail_msg)

# ───────────────── 1. Python version ─────────────────

head("1. Python")
import platform
ver = sys.version_info
check(
    ver >= (3, 12),
    f"Python {ver.major}.{ver.minor}.{ver.micro} — OK",
    f"Python {ver.major}.{ver.minor} detected — bot requires 3.12+",
)

# ───────────────── 2. Required files ─────────────────

head("2. Файлы бота")
for fname in REQUIRED_FILES:
    fpath = os.path.join(BOT_DIR, fname)
    check(
        os.path.exists(fpath),
        fname,
        f"ОТСУТСТВУЕТ: {fname}",
    )

# ───────────────── 3. .env variables ─────────────────

head("3. Переменные окружения (.env)")
from dotenv import load_dotenv
load_dotenv(ENV_PATH, override=True)
load_dotenv(SURE_ENV, override=False)   # telegram token is in 98_sure_bot/.env

for key in REQUIRED_ENV_KEYS:
    val = os.getenv(key, '')
    if val:
        masked = val[:6] + '...' + val[-4:] if len(val) > 12 else '***'
        ok(f"{key} = {masked}")
    else:
        err(f"{key} — НЕ НАЙДЕН (бот не запустится)")
        errors.append(f"Missing env: {key}")

# ───────────────── 4. Python packages ─────────────────

head("4. Зависимости (пакеты)")
missing_pkgs = []
for pkg in REQUIRED_PACKAGES:
    try:
        import importlib
        importlib.import_module(pkg if pkg != 'dotenv' else 'dotenv')
        ok(pkg)
    except ImportError:
        err(f"{pkg} — не установлен (pip install {pkg})")
        missing_pkgs.append(pkg)
        errors.append(f"Missing package: {pkg}")

# ───────────────── 5. Stale lock file ─────────────────

head("5. Файл блокировки (bot.lock)")
lock_path = os.path.join(BOT_DIR, 'bot.lock')
if os.path.exists(lock_path):
    try:
        with open(lock_path) as f:
            locked_pid = int(f.read().strip())
        # Check if that PID is alive
        try:
            import psutil
            alive = psutil.pid_exists(locked_pid)
        except ImportError:
            # Fallback without psutil
            try:
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {locked_pid}'],
                    capture_output=True, text=True
                )
                alive = str(locked_pid) in result.stdout
            except Exception:
                alive = False

        if alive:
            err(f"bot.lock содержит PID {locked_pid} — процесс ЖИВОЙ! Бот уже запущен?")
            errors.append("Bot already running (lock alive)")
        else:
            warn(f"bot.lock содержит устаревший PID {locked_pid} (процесс мёртв после перезагрузки)")
            warn("Удаляю устаревший lock...")
            os.remove(lock_path)
            ok("bot.lock удалён — бот может запуститься")
    except Exception as e:
        warn(f"Не удалось прочитать bot.lock: {e}")
else:
    ok("bot.lock отсутствует — нет активного экземпляра")

# ───────────────── 6. Running Python processes ─────────────────

head("6. Запущенные Python-процессы")
try:
    import psutil
    bot_procs = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
        try:
            name = (p.info.get('name') or '').lower()
            if 'python' not in name:
                continue
            cmdline = ' '.join(p.info.get('cmdline') or [])
            cwd = p.info.get('cwd') or ''
            if 'main.py' in cmdline and '25_multi_signal_copybot' in (cwd + cmdline):
                bot_procs.append(f"PID={p.info['pid']} cmd={cmdline[:80]}")
            elif '_metrics_loop' in cmdline:
                bot_procs.append(f"PID={p.info['pid']} cmd={cmdline[:80]}")
            elif '_watchdog' in cmdline:
                bot_procs.append(f"PID={p.info['pid']} cmd={cmdline[:80]}")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    if bot_procs:
        for bp in bot_procs:
            warn(f"Уже запущен: {bp}")
        warnings.append("Bot processes already running")
    else:
        ok("Нет активных процессов бота — чистый старт")
except ImportError:
    warn("psutil не установлен — пропускаем проверку процессов")

# ───────────────── 7. positions.json integrity ─────────────────

head("7. positions.json — целостность")
positions_path = os.path.join(BOT_DIR, 'positions.json')
try:
    with open(positions_path, encoding='utf-8') as f:
        data = json.load(f)
    positions = data.get('positions', {})
    open_pos  = [k for k, v in positions.items() if v.get('status') == 'open']
    closed    = [k for k, v in positions.items() if v.get('status') != 'open']
    ok(f"Всего позиций: {len(positions)}  |  Открытых: {len(open_pos)}  |  Закрытых: {len(closed)}")

    # Check for positions missing token_id
    bad = [k for k, v in positions.items()
           if v.get('status') == 'open' and not v.get('token_id')]
    if bad:
        warn(f"{len(bad)} открытых позиций без token_id: {bad[:3]}...")
        warnings.append("Positions missing token_id")
    else:
        ok("У всех открытых позиций есть token_id")

    # Check for duplicate keys
    ok(f"Дубликатов ключей: нет (JSON корректен)")
except json.JSONDecodeError as e:
    err(f"positions.json ПОВРЕЖДЁН: {e}")
    errors.append("positions.json corrupt")
except FileNotFoundError:
    err("positions.json НЕ НАЙДЕН")
    errors.append("positions.json missing")
except Exception as e:
    err(f"positions.json ошибка: {e}")

# ───────────────── 8. buy_buffers.json ─────────────────

head("8. buy_buffers.json")
buf_path = os.path.join(BOT_DIR, 'buy_buffers.json')
try:
    with open(buf_path, encoding='utf-8') as f:
        buf_data = json.load(f)
    n_bufs = sum(len(v) for v in buf_data.get('buffers', {}).values())
    n_sig  = sum(len(v) for v in buf_data.get('signaled', {}).values())
    ok(f"Буферов покупок: {n_bufs}  |  Сигналов: {n_sig}")
except json.JSONDecodeError as e:
    err(f"buy_buffers.json ПОВРЕЖДЁН: {e}")
    errors.append("buy_buffers.json corrupt")
except FileNotFoundError:
    warn("buy_buffers.json не найден — бот создаст его при старте")
except Exception as e:
    warn(f"buy_buffers.json: {e}")

# ───────────────── 9. pids.json — обновить ─────────────────

head("9. pids.json (дашборд)")
try:
    with open(DASHBOARD_PIDS, encoding='utf-8') as f:
        pids = json.load(f)
    stale = []
    for name, entry in pids.items():
        pid = entry.get('pid', 0)
        try:
            import psutil
            alive = psutil.pid_exists(pid)
        except ImportError:
            alive = False
        status = "живой" if alive else "устаревший"
        if not alive:
            stale.append(name)
        fn = ok if alive else warn
        fn(f"{name}: PID={pid} — {status}")

    if stale:
        warn(f"Устаревшие PIDs: {stale}")
        warn("После запуска watchdog обновит pids.json автоматически")
except Exception as e:
    warn(f"Не удалось прочитать pids.json: {e}")

# ───────────────── 10. config sanity ─────────────────

head("10. config.py — ключевые параметры")
try:
    sys.path.insert(0, BOT_DIR)
    import importlib, config
    importlib.reload(config)
    ok(f"BOT_MODE = {config.BOT_MODE!r}  |  DRY_RUN = {config.DRY_RUN}")
    ok(f"BANKROLL = ${config.BANKROLL:.0f}  |  RESERVE = ${config.RESERVE_USD:.0f}")
    ok(f"MAX_POSITION = ${config.MAX_POSITION_USD:.0f}  |  MAX_BET = ${config.MAX_BET_USD:.0f}")
    ok(f"PLAYERS: {list(config.PLAYERS.keys())}")
    if config.BOT_MODE == 'live' and config.DRY_RUN:
        warn("BOT_MODE=live но DRY_RUN=True — реальных сделок не будет!")
    if config.BOT_MODE == 'live' and not config.DRY_RUN:
        warn("⚠ РЕЖИМ LIVE — реальные деньги! Убедись что это намеренно.")
except Exception as e:
    err(f"Ошибка при импорте config: {e}")
    errors.append("config.py import failed")

# ───────────────── Summary ─────────────────

print()
print("=" * 60)
if errors:
    print(f"{RED}{BOLD}РЕЗУЛЬТАТ: ОШИБКИ ({len(errors)}) — ЗАПУСК НЕБЕЗОПАСЕН{RESET}")
    for e in errors:
        print(f"  {RED}✗{RESET} {e}")
    print()
    print("Исправь ошибки выше, затем запусти снова.")
    sys.exit(2)
elif warnings:
    print(f"{YELLOW}{BOLD}РЕЗУЛЬТАТ: ПРЕДУПРЕЖДЕНИЯ ({len(warnings)}) — можно запускать{RESET}")
    for w in warnings:
        print(f"  {YELLOW}⚠{RESET} {w}")
    print()
    print(f"{GREEN}Порядок запуска:{RESET}")
    print("  1. py -3.12 -u -X utf8 main.py --bot-tag=25_multi_signal_copybot_v2")
    print("  2. py -3.12 -u -X utf8 _metrics_loop.py --bot-tag=25_copybot_metrics")
    print("  3. py -3.12 -u -X utf8 _watchdog.py")
    sys.exit(1)
else:
    print(f"{GREEN}{BOLD}РЕЗУЛЬТАТ: ВСЁ ГОТОВО — запуск безопасен{RESET}")
    print()
    print(f"{GREEN}Порядок запуска:{RESET}")
    print("  1. py -3.12 -u -X utf8 main.py --bot-tag=25_multi_signal_copybot_v2")
    print("  2. py -3.12 -u -X utf8 _metrics_loop.py --bot-tag=25_copybot_metrics")
    print("  3. py -3.12 -u -X utf8 _watchdog.py")
    sys.exit(0)
