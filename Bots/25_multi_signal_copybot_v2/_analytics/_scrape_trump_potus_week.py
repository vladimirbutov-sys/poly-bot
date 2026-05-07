"""Scrape Trump Truth Social posts from trumpstruth.org for POTUS mentions Apr 13-19, 2026."""
import urllib.request, sys, io, re, json, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ET = ZoneInfo('America/New_York')


def parse_page(html):
    posts = []
    blocks = re.split(r'<div class="search-result"\s+data-status-url="', html)[1:]
    for b in blocks:
        mid = re.match(r'[^"]*statuses/(\d+)"', b)
        if not mid:
            continue
        sid = mid.group(1)
        status_url_match = re.match(r'([^"]+)"', b)
        status_url = status_url_match.group(1) if status_url_match else ''
        dm = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4}, \d{1,2}:\d{2} (?:AM|PM))', b)
        if not dm:
            continue
        date_str = dm.group(1)
        # detect post type (repost/retruth markers)
        is_retruth = 'retruth' in b.lower() or 'reposted' in b.lower()
        is_reply = 'replied to' in b.lower() or 'reply-to' in b.lower()
        cm = re.search(r'<div class="snippet-content">(.*?)</div>', b, re.S)
        content = ''
        if cm:
            content = re.sub(r'<[^>]+>', ' ', cm.group(1))
            content = re.sub(r'\s+', ' ', content).strip()
            content = (content.replace('&amp;', '&').replace('&quot;', '"')
                       .replace('&#039;', "'").replace('&lt;', '<').replace('&gt;', '>'))
        posts.append({
            'id': sid, 'timestamp_str': date_str, 'content': content[:5000],
            'status_url': status_url, 'is_retruth_hint': is_retruth, 'is_reply_hint': is_reply,
        })
    return posts


def fetch_query(query, start_date='2026-04-13', end_date='2026-04-19'):
    all_posts = []
    page = 1
    while page <= 20:
        url = (f'https://www.trumpstruth.org/search?query={query}&per_page=100&sort=date'
               f'&start_date={start_date}&end_date={end_date}&removed=include&page={page}')
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            html = urllib.request.urlopen(req, timeout=25).read().decode('utf-8', 'replace')
        except Exception as e:
            print('err', page, e); break
        posts = parse_page(html)
        print(f'  query="{query}" page {page}: {len(posts)} posts')
        if not posts:
            break
        all_posts.extend(posts)
        if len(posts) < 100:
            break
        page += 1
        time.sleep(0.4)
    return all_posts


def main():
    print('=== Fetching posts for POTUS keyword (Apr 13-19, 2026) ===')
    posts_potus = fetch_query('POTUS')
    print(f'\nTotal POTUS-search posts: {len(posts_potus)}')

    # Also grab ALL posts in range to cross-check (unfiltered by search)
    print('\n=== Fetching ALL posts (no query) Apr 13-19 ===')
    posts_all = fetch_query('')
    print(f'\nTotal posts in range: {len(posts_all)}')

    # Dedupe
    seen = set()
    uniq_potus = []
    for p in posts_potus:
        if p['id'] in seen: continue
        seen.add(p['id'])
        try:
            dt_naive = datetime.strptime(p['timestamp_str'], '%B %d, %Y, %I:%M %p')
            dt_utc = dt_naive.replace(tzinfo=ET).astimezone(timezone.utc)
            p['ts_utc'] = dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        except Exception:
            continue
        uniq_potus.append(p)

    # Filter: content must contain "potus" (any case)
    potus_hits = [p for p in uniq_potus if re.search(r'\bpotus\b', p['content'], re.I)
                  or re.search(r'potus', p['content'], re.I)]

    uniq_all = []
    seen2 = set()
    for p in posts_all:
        if p['id'] in seen2: continue
        seen2.add(p['id'])
        try:
            dt_naive = datetime.strptime(p['timestamp_str'], '%B %d, %Y, %I:%M %p')
            dt_utc = dt_naive.replace(tzinfo=ET).astimezone(timezone.utc)
            p['ts_utc'] = dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        except Exception:
            continue
        uniq_all.append(p)

    # cross-check: find "potus" in ALL posts content
    potus_all_check = [p for p in uniq_all if re.search(r'potus', p['content'], re.I)]

    print(f'\n=== RESULTS ===')
    print(f'Unique posts matching POTUS query: {len(uniq_potus)}')
    print(f'With POTUS in content (case-insensitive): {len(potus_hits)}')
    print(f'Cross-check: ALL posts in range: {len(uniq_all)}')
    print(f'Cross-check: ALL posts with POTUS in content: {len(potus_all_check)}')

    print(f'\n=== POTUS hits (from targeted query): ===')
    for p in potus_hits:
        print(f'\n[{p["ts_utc"]}] id={p["id"]}  retruth_hint={p["is_retruth_hint"]}  reply_hint={p["is_reply_hint"]}')
        print(f'  content: {p["content"][:400]}')
        print(f'  url: {p["status_url"]}')

    print(f'\n=== POTUS hits (from ALL posts cross-check): ===')
    for p in potus_all_check:
        if not any(h['id'] == p['id'] for h in potus_hits):
            print(f'\n[{p["ts_utc"]}] id={p["id"]}  NEW (not in targeted search)')
            print(f'  content: {p["content"][:400]}')
            print(f'  url: {p["status_url"]}')

    out = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\trump_potus_week_apr13_19.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({
            'query_hits_raw': uniq_potus,
            'potus_content_hits': potus_hits,
            'all_posts_in_range': uniq_all,
            'cross_check_potus_hits': potus_all_check,
        }, f, ensure_ascii=False, indent=2)
    print(f'\nsaved: {out}')


if __name__ == '__main__':
    main()
