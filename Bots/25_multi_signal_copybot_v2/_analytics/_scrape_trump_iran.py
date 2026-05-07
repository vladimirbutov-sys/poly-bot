"""Scrape Trump Truth Social posts about Iran from trumpstruth.org for fade-tweet feasibility research."""
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
        posts.append({'id': sid, 'timestamp_str': date_str, 'content': content[:3000]})
    return posts


def main():
    start_date = '2026-02-18'
    end_date = '2026-04-18'
    all_posts = []
    page = 1
    while page <= 40:
        url = (f'https://www.trumpstruth.org/search?query=iran&per_page=100&sort=date'
               f'&start_date={start_date}&end_date={end_date}&removed=include&page={page}')
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            html = urllib.request.urlopen(req, timeout=25).read().decode('utf-8', 'replace')
        except Exception as e:
            print('err', page, e)
            break
        posts = parse_page(html)
        has_content = sum(1 for p in posts if p['content'])
        print(f'page {page}: {len(posts)} posts, with-content: {has_content}')
        if not posts:
            break
        all_posts.extend(posts)
        if len(posts) < 100:
            break
        page += 1
        time.sleep(0.4)

    seen = set()
    uniq = []
    for p in all_posts:
        if p['id'] in seen:
            continue
        seen.add(p['id'])
        try:
            dt_naive = datetime.strptime(p['timestamp_str'], '%B %d, %Y, %I:%M %p')
            dt_utc = dt_naive.replace(tzinfo=ET).astimezone(timezone.utc)
            p['ts_utc'] = dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
            p['ts_unix'] = int(dt_utc.timestamp())
        except Exception:
            continue
        uniq.append(p)

    uniq.sort(key=lambda x: x['ts_unix'])
    print('\nUnique posts:', len(uniq))
    strict = [p for p in uniq if p['content'] and 'iran' in p['content'].lower()]
    print('Content contains "iran":', len(strict))
    if strict:
        print('earliest strict:', strict[0]['ts_utc'])
        print('latest strict:', strict[-1]['ts_utc'])

    out = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\trump_iran_tweets.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'all': uniq, 'strict_iran_in_content': strict}, f, ensure_ascii=False, indent=2)
    print('saved:', out)
    print('\n--- Sample strict posts (first 5) ---')
    for p in strict[:5]:
        print(p['ts_utc'], '|', p['content'][:200])
    print('\n--- Sample strict posts (last 5) ---')
    for p in strict[-5:]:
        print(p['ts_utc'], '|', p['content'][:200])


if __name__ == '__main__':
    main()
