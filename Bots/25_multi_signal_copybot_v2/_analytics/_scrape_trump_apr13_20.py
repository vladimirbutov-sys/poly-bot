"""Scrape Trump Truth Social posts (iran/israel/hormuz/ceasefire) for Apr 13-20 2026 window."""
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
        dm = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4}, \d{1,2}:\d{2} (?:AM|PM))', b)
        if not dm:
            continue
        date_str = dm.group(1)
        cm = re.search(r'<div class="snippet-content">(.*?)</div>', b, re.S)
        content = ''
        if cm:
            content = re.sub(r'<[^>]+>', ' ', cm.group(1))
            content = re.sub(r'\s+', ' ', content).strip()
            content = (content.replace('&amp;', '&').replace('&quot;', '"')
                       .replace('&#039;', "'").replace('&lt;', '<').replace('&gt;', '>'))
        # Detect post type from surrounding classes / text
        ptype = 'original'
        low = b[:2000].lower()
        if 'retruth' in low or 'reposted' in low:
            ptype = 'retruth'
        elif 'replying to' in low or 'in-reply-to' in low:
            ptype = 'reply'
        elif 'quoted' in low:
            ptype = 'quote-truth'
        posts.append({'id': sid, 'timestamp_str': date_str, 'content': content[:3000], 'post_type': ptype})
    return posts


def scrape_query(query, start_date, end_date):
    all_posts = []
    page = 1
    while page <= 10:
        url = (f'https://www.trumpstruth.org/search?query={query}&per_page=100&sort=date'
               f'&start_date={start_date}&end_date={end_date}&removed=include&page={page}')
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            html = urllib.request.urlopen(req, timeout=25).read().decode('utf-8', 'replace')
        except Exception as e:
            print(f'err {query} page {page}:', e)
            break
        posts = parse_page(html)
        print(f'query={query} page {page}: {len(posts)} posts')
        if not posts:
            break
        for p in posts:
            p['query'] = query
        all_posts.extend(posts)
        if len(posts) < 100:
            break
        page += 1
        time.sleep(0.4)
    return all_posts


def main():
    start_date = '2026-04-13'
    end_date = '2026-04-20'
    queries = ['iran', 'israel', 'hormuz', 'ceasefire']
    combined = []
    for q in queries:
        combined.extend(scrape_query(q, start_date, end_date))
        time.sleep(0.5)

    # Dedupe by id, keep list of query matches
    by_id = {}
    for p in combined:
        pid = p['id']
        if pid not in by_id:
            try:
                dt_naive = datetime.strptime(p['timestamp_str'], '%B %d, %Y, %I:%M %p')
                dt_utc = dt_naive.replace(tzinfo=ET).astimezone(timezone.utc)
                p['timestamp_utc'] = dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
                p['ts_unix'] = int(dt_utc.timestamp())
            except Exception as e:
                print('ts parse err', p.get('timestamp_str'), e)
                continue
            p['url'] = f'https://www.trumpstruth.org/statuses/{pid}'
            p['matched_queries'] = [p.pop('query')]
            by_id[pid] = p
        else:
            q = p.pop('query', None)
            if q and q not in by_id[pid]['matched_queries']:
                by_id[pid]['matched_queries'].append(q)

    uniq = sorted(by_id.values(), key=lambda x: x['ts_unix'])
    # Filter strict to window in UTC
    window_start = int(datetime(2026, 4, 13, tzinfo=timezone.utc).timestamp())
    window_end = int(datetime(2026, 4, 21, tzinfo=timezone.utc).timestamp())
    uniq = [p for p in uniq if window_start <= p['ts_unix'] < window_end]

    print(f'\nUnique posts in window: {len(uniq)}')
    # Date distribution
    from collections import Counter
    date_counts = Counter(p['timestamp_utc'][:10] for p in uniq)
    for d in sorted(date_counts):
        print(f'  {d}: {date_counts[d]}')

    out = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\trump_truth_iran_apr13_20.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(uniq, f, ensure_ascii=False, indent=2)
    print('saved:', out)
    print('\n--- First 8 posts ---')
    for p in uniq[:8]:
        print(p['timestamp_utc'], p['id'], '|', (p['content'] or '(empty snippet)')[:180])
    print('\n--- Last 8 posts ---')
    for p in uniq[-8:]:
        print(p['timestamp_utc'], p['id'], '|', (p['content'] or '(empty snippet)')[:180])


if __name__ == '__main__':
    main()
