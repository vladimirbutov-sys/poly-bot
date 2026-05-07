"""Background monitor: scan tier-1 sources every 15 min for sanctioned tanker seizure Apr 20-30, 2026.
Writes findings to _monitor_tanker.log. Sends TG alert via news_spike alerter if tier-1 confirms.
"""
import sys, io, time, json, hashlib, re, subprocess
from datetime import datetime, timezone
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

LOG_FILE = Path(__file__).parent / "_monitor_tanker.log"
SEEN_FILE = Path(__file__).parent / "_monitor_tanker_seen.json"
CHECK_INTERVAL = 900  # 15 min
MAX_DURATION = 12 * 3600  # 12 hours max

# Tier-1 sources with RSS or keyword-searchable feeds
SOURCES = [
    ("Reuters World (Al Jazeera)", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Middle East", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    ("Axios", "https://www.axios.com/feeds/feed.rss"),
    ("Jerusalem Post", "https://www.jpost.com/rss/rssfeedsheadlines.aspx"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
]

# Keywords to look for (case-insensitive)
KEYWORDS_ALL = [
    r"\btanker\b.*\bseiz",
    r"\bseiz.*\btanker\b",
    r"\btanker\b.*\bboard",
    r"\bboard.*\btanker\b",
    r"\bsanctioned\b.*\bship",
    r"\bsanctioned\b.*\bvessel",
    r"\bindo-pacific\b.*\bboard",
    r"\bpentagon\b.*\btanker\b",
    r"\btreasury\b.*\btanker\b",
]
KEYWORD_REGEX = re.compile("|".join(KEYWORDS_ALL), re.IGNORECASE)

# Load seen hashes
seen = set()
if SEEN_FILE.exists():
    try:
        seen = set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        pass


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def send_tg_alert(text: str):
    """Use news_spike alerter to send to Telegram."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "news_alerter",
            Path(__file__).parent / "news_spike" / "core" / "alerter.py"
        )
        mod = importlib.util.module_from_spec(spec)
        # need config & env loaded
        sys.path.insert(0, str(Path(__file__).parent / "news_spike"))
        import asyncio
        from core.alerter import send_alert
        asyncio.run(send_alert(text))
        return True
    except Exception as e:
        log(f"TG alert send failed: {e}")
        return False


def parse_rss(xml: str):
    """Return list of (title, link, description) from RSS 2.0."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
    except Exception:
        return []
    items = []
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            t = item.findtext("title") or ""
            l = item.findtext("link") or ""
            d = item.findtext("description") or ""
            items.append((t.strip(), l.strip(), d.strip()))
    return items


def scan_once():
    hits = []
    with httpx.Client(timeout=20, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 TankerMon/1.0"}) as c:
        for name, url in SOURCES:
            try:
                r = c.get(url)
                if r.status_code != 200:
                    continue
                items = parse_rss(r.text)
                for title, link, desc in items:
                    full_text = f"{title} {desc}"
                    if KEYWORD_REGEX.search(full_text):
                        h = hashlib.md5(link.encode()).hexdigest()
                        if h not in seen:
                            seen.add(h)
                            hits.append((name, title, link))
            except Exception as e:
                log(f"[{name}] error: {e}")
    return hits


def main():
    log(f"=== TANKER SEIZURE MONITOR STARTED ===")
    log(f"Sources: {len(SOURCES)}  interval: {CHECK_INTERVAL}s  max duration: {MAX_DURATION}s")
    start = time.time()

    while time.time() - start < MAX_DURATION:
        log(f"--- Scan cycle ---")
        hits = scan_once()
        if hits:
            for src, title, link in hits:
                log(f"🚨 HIT [{src}] {title}")
                log(f"   {link}")
                alert = (
                    f"🚨 <b>TANKER SEIZURE ALERT</b>\n"
                    f"\n📰 {src}\n"
                    f"\n<b>{title[:300]}</b>\n"
                    f"\n🔗 {link}\n"
                    f"\n⚠️ Проверьте нашу NO-позицию на <i>us-forces-seize-another-oil-tanker-by-april-30</i>"
                )
                send_tg_alert(alert)
        else:
            log(f"No new tanker-seizure hits. Sleeping {CHECK_INTERVAL}s...")

        SEEN_FILE.write_text(json.dumps(list(seen)))
        time.sleep(CHECK_INTERVAL)

    log(f"=== MONITOR ENDED (max duration reached) ===")


if __name__ == "__main__":
    main()
