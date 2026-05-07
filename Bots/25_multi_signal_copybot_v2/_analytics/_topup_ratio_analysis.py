"""
Анализ корреляции размера докупки denizz с последующим движением цены.
"""
import urllib.request, json, time, sys
from collections import defaultdict
from datetime import datetime

WALLET = "0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73"
BASE_URL = f"https://data-api.polymarket.com/activity?user={WALLET}&limit=500&offset="

def fetch_all_trades(max_pages=60):
    """Fetch trade history with pagination. 500 per page, up to max_pages."""
    all_trades = []
    for page in range(max_pages):
        offset = page * 500
        url = BASE_URL + str(offset)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            if not data:
                print(f"  Page {page}: empty response, stopping.")
                break
            all_trades.extend(data)
            ts_first = data[0]['timestamp']
            ts_last = data[-1]['timestamp']
            d1 = datetime.utcfromtimestamp(ts_first).strftime('%Y-%m-%d')
            d2 = datetime.utcfromtimestamp(ts_last).strftime('%Y-%m-%d')
            print(f"  Page {page}: {len(data)} records, {d1} to {d2}")
            if len(data) < 500:
                print(f"  Got {len(data)} < 500, last page.")
                break
            time.sleep(0.3)  # be nice to the API
        except Exception as e:
            print(f"  Page {page}: ERROR {e}")
            time.sleep(2)
            # retry once
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=30)
                data = json.loads(resp.read())
                if not data:
                    break
                all_trades.extend(data)
                print(f"  Page {page}: retry OK, {len(data)} records")
                if len(data) < 500:
                    break
                time.sleep(0.3)
            except:
                print(f"  Page {page}: retry also failed, stopping.")
                break
    return all_trades

def analyze(trades):
    # Filter only TRADE type, sort by timestamp ascending
    trades = [t for t in trades if t.get('type') == 'TRADE']
    trades.sort(key=lambda t: t['timestamp'])

    print(f"\nTotal trades after filtering: {len(trades)}")
    if not trades:
        return

    d1 = datetime.utcfromtimestamp(trades[0]['timestamp']).strftime('%Y-%m-%d')
    d2 = datetime.utcfromtimestamp(trades[-1]['timestamp']).strftime('%Y-%m-%d')
    print(f"Date range: {d1} to {d2}")

    buys = [t for t in trades if t['side'] == 'BUY']
    sells = [t for t in trades if t['side'] == 'SELL']
    print(f"BUYs: {len(buys)}, SELLs: {len(sells)}")

    # Group trades by (conditionId, asset) = unique token position
    token_trades = defaultdict(list)
    for t in trades:
        key = (t['conditionId'], t['asset'])
        token_trades[key].append(t)

    print(f"Unique token positions: {len(token_trades)}")

    # For each token, build buy timeline and compute ratios
    # We need to track: for each buy, what was the max price seen afterwards

    results = []  # list of dicts with ratio, price_at_buy, max_price_24h, max_price_48h, max_price_7d, title
    first_entries = []  # first buys (baseline)

    for (cid, asset), tlist in token_trades.items():
        tlist.sort(key=lambda t: t['timestamp'])

        buy_history = []  # list of (timestamp, usdcSize, price)
        cumulative_usd = 0.0

        for t in tlist:
            if t['side'] != 'BUY':
                continue

            buy_price = t['price']
            buy_usd = t['usdcSize']
            buy_ts = t['timestamp']
            title = t.get('title', '')

            # Find max price after this buy within windows
            # Look at ALL trades on this token after this buy
            future_trades = [ft for ft in tlist if ft['timestamp'] > buy_ts]
            future_buys = [ft for ft in future_trades if ft['side'] == 'BUY']

            # Get prices from future trades (both buys and sells show market price)
            def max_price_in_window(seconds):
                cutoff = buy_ts + seconds
                prices = [ft['price'] for ft in future_trades if ft['timestamp'] <= cutoff]
                if prices:
                    return max(prices)
                return buy_price  # no future data = assume flat

            def last_known_price():
                if future_trades:
                    return future_trades[-1]['price']
                return buy_price

            max_24h = max_price_in_window(86400)
            max_48h = max_price_in_window(86400 * 2)
            max_7d = max_price_in_window(86400 * 7)
            last_price = last_known_price()

            entry = {
                'title': title,
                'buy_ts': buy_ts,
                'buy_price': buy_price,
                'buy_usd': buy_usd,
                'cumulative_usd_before': cumulative_usd,
                'max_24h': max_24h,
                'max_48h': max_48h,
                'max_7d': max_7d,
                'last_price': last_price,
            }

            if cumulative_usd < 1.0:  # first buy (or negligible prior)
                entry['ratio'] = None
                entry['bucket'] = 'FIRST_ENTRY'
                first_entries.append(entry)
            else:
                ratio = buy_usd / cumulative_usd
                entry['ratio'] = ratio
                if ratio < 0.01:
                    entry['bucket'] = '<1% (dust)'
                elif ratio < 0.03:
                    entry['bucket'] = '1-3% (micro)'
                elif ratio < 0.10:
                    entry['bucket'] = '3-10% (small)'
                elif ratio < 0.30:
                    entry['bucket'] = '10-30% (medium)'
                elif ratio <= 1.0:
                    entry['bucket'] = '30-100% (large)'
                else:
                    entry['bucket'] = '>100% (doubling+)'
                results.append(entry)

            cumulative_usd += buy_usd

    # Compute stats per bucket
    buckets_order = [
        'FIRST_ENTRY',
        '<1% (dust)',
        '1-3% (micro)',
        '3-10% (small)',
        '10-30% (medium)',
        '30-100% (large)',
        '>100% (doubling+)',
    ]

    all_data = first_entries + results
    bucket_stats = {}

    for bname in buckets_order:
        entries = [e for e in all_data if e['bucket'] == bname]
        if not entries:
            bucket_stats[bname] = None
            continue

        count = len(entries)

        # Price change calculations
        changes_24h = [(e['max_24h'] - e['buy_price']) / e['buy_price'] * 100 for e in entries if e['buy_price'] > 0]
        changes_7d = [(e['max_7d'] - e['buy_price']) / e['buy_price'] * 100 for e in entries if e['buy_price'] > 0]
        changes_last = [(e['last_price'] - e['buy_price']) / e['buy_price'] * 100 for e in entries if e['buy_price'] > 0]

        # Win rate: price went up by at least 5% within 7 days
        wins_5pct = sum(1 for c in changes_7d if c >= 5)
        # Also track any positive movement
        wins_any = sum(1 for c in changes_7d if c > 0)

        avg_24h = sum(changes_24h) / len(changes_24h) if changes_24h else 0
        avg_7d = sum(changes_7d) / len(changes_7d) if changes_7d else 0
        avg_last = sum(changes_last) / len(changes_last) if changes_last else 0
        wr_5 = wins_5pct / len(changes_7d) * 100 if changes_7d else 0
        wr_any = wins_any / len(changes_7d) * 100 if changes_7d else 0

        # Median 7d change
        sorted_7d = sorted(changes_7d)
        median_7d = sorted_7d[len(sorted_7d)//2] if sorted_7d else 0

        bucket_stats[bname] = {
            'count': count,
            'avg_change_24h': avg_24h,
            'avg_max_gain_7d': avg_7d,
            'avg_last_price_change': avg_last,
            'median_max_gain_7d': median_7d,
            'win_rate_5pct': wr_5,
            'win_rate_any': wr_any,
        }

    # Print results
    print("\n" + "="*120)
    print("РЕЗУЛЬТАТЫ: Корреляция размера докупки с движением цены")
    print("="*120)

    header = f"{'Бакет':<22} | {'Кол-во':>6} | {'Ср.макс 24ч':>12} | {'Ср.макс 7д':>11} | {'Медиана 7д':>11} | {'WR(+5%)':>8} | {'WR(любой+)':>10} | {'Ср.посл.цена':>13}"
    print(header)
    print("-" * 120)

    for bname in buckets_order:
        s = bucket_stats.get(bname)
        if s is None:
            print(f"{bname:<22} | {'—':>6} |")
            continue
        print(f"{bname:<22} | {s['count']:>6} | {s['avg_change_24h']:>+11.2f}% | {s['avg_max_gain_7d']:>+10.2f}% | {s['median_max_gain_7d']:>+10.2f}% | {s['win_rate_5pct']:>7.1f}% | {s['win_rate_any']:>9.1f}% | {s['avg_last_price_change']:>+12.2f}%")

    print("\n")

    # Additional analysis: avg buy size per bucket
    print("Средний размер покупки (USDC) по бакетам:")
    for bname in buckets_order:
        entries = [e for e in all_data if e['bucket'] == bname]
        if entries:
            avg_usd = sum(e['buy_usd'] for e in entries) / len(entries)
            total_usd = sum(e['buy_usd'] for e in entries)
            print(f"  {bname:<22}: avg ${avg_usd:.2f}, total ${total_usd:.2f}, count {len(entries)}")

    # Top-up frequency analysis
    print("\nСамые частые рынки с докупками:")
    market_counts = defaultdict(int)
    for e in results:
        market_counts[e['title']] += 1
    for title, count in sorted(market_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {count:>4}x  {title[:80]}")

    return bucket_stats, all_data, buckets_order

def generate_report(bucket_stats, all_data, buckets_order, total_trades, date_range):
    """Generate markdown report."""

    lines = []
    lines.append("# Анализ: Размер докупки denizz vs движение цены")
    lines.append(f"\n**Дата анализа**: 2026-04-13")
    lines.append(f"**Период данных**: {date_range}")
    lines.append(f"**Всего сделок**: {total_trades}")
    lines.append("")
    lines.append("## Суть вопроса")
    lines.append("")
    lines.append("Когда denizz докупает в уже существующую позицию, размер этой докупки может сигнализировать о его уверенности.")
    lines.append("Маленькая докупка (1-3% от позиции) — возможно, просто «подбирает мелочь».")
    lines.append("Большая докупка (30%+ от позиции) — серьёзное усиление позиции, сильный сигнал.")
    lines.append("")
    lines.append("**Вопрос**: подтверждают ли данные, что крупные докупки дают лучший результат?")
    lines.append("")

    lines.append("## Методология")
    lines.append("")
    lines.append("1. Загружены все сделки denizz через Polymarket Data API (с пагинацией)")
    lines.append("2. Для каждого токена (conditionId + asset) построена хронология покупок")
    lines.append("3. Для каждой покупки ПОСЛЕ первой рассчитан коэффициент: `размер_покупки / сумма_предыдущих_покупок`")
    lines.append("4. Покупки разбиты на группы по размеру коэффициента")
    lines.append("5. Для каждой группы посчитано: максимальный рост цены за 24ч и 7 дней после покупки, винрейт")
    lines.append("")
    lines.append("**Ограничения**: движение цены отслеживается по ценам последующих сделок denizz на том же токене.")
    lines.append("Если denizz не торговал токеном после покупки — используется цена покупки (считаем «без изменений»).")
    lines.append("")

    lines.append("## Результаты")
    lines.append("")
    lines.append("| Группа | Кол-во | Ср. макс рост 24ч | Ср. макс рост 7д | Медиана 7д | WR (+5% за 7д) | WR (любой рост) |")
    lines.append("|--------|--------|-------------------|------------------|------------|----------------|-----------------|")

    for bname in buckets_order:
        s = bucket_stats.get(bname)
        if s is None:
            lines.append(f"| {bname} | — | — | — | — | — | — |")
            continue
        lines.append(f"| {bname} | {s['count']} | {s['avg_change_24h']:+.2f}% | {s['avg_max_gain_7d']:+.2f}% | {s['median_max_gain_7d']:+.2f}% | {s['win_rate_5pct']:.1f}% | {s['win_rate_any']:.1f}% |")

    lines.append("")

    # Compute summary stats for conclusion
    topup_entries = [e for e in all_data if e['bucket'] != 'FIRST_ENTRY']
    large_entries = [e for e in all_data if e['bucket'] in ['30-100% (large)', '>100% (doubling+)']]
    small_entries = [e for e in all_data if e['bucket'] in ['<1% (dust)', '1-3% (micro)']]

    lines.append("## Средний размер покупки по группам")
    lines.append("")
    for bname in buckets_order:
        entries = [e for e in all_data if e['bucket'] == bname]
        if entries:
            avg_usd = sum(e['buy_usd'] for e in entries) / len(entries)
            lines.append(f"- **{bname}**: средняя покупка ${avg_usd:.2f}, всего {len(entries)} сделок")
    lines.append("")

    lines.append("## Выводы и рекомендации")
    lines.append("")

    # Dynamic conclusions based on data
    first_s = bucket_stats.get('FIRST_ENTRY')
    dust_s = bucket_stats.get('<1% (dust)')
    micro_s = bucket_stats.get('1-3% (micro)')
    small_s = bucket_stats.get('3-10% (small)')
    medium_s = bucket_stats.get('10-30% (medium)')
    large_s = bucket_stats.get('30-100% (large)')
    double_s = bucket_stats.get('>100% (doubling+)')

    lines.append("### Что показывают данные")
    lines.append("")

    if first_s:
        lines.append(f"- **Первый вход** в позицию: WR(+5%) = {first_s['win_rate_5pct']:.1f}%, средний макс рост 7д = {first_s['avg_max_gain_7d']:+.2f}% ({first_s['count']} сделок)")

    if dust_s and dust_s['count'] >= 5:
        lines.append(f"- **Пылевые докупки (<1%)**: WR(+5%) = {dust_s['win_rate_5pct']:.1f}%, средний макс рост 7д = {dust_s['avg_max_gain_7d']:+.2f}% ({dust_s['count']} сделок)")

    if micro_s and micro_s['count'] >= 5:
        lines.append(f"- **Микро-докупки (1-3%)**: WR(+5%) = {micro_s['win_rate_5pct']:.1f}%, средний макс рост 7д = {micro_s['avg_max_gain_7d']:+.2f}% ({micro_s['count']} сделок)")

    if small_s and small_s['count'] >= 5:
        lines.append(f"- **Малые докупки (3-10%)**: WR(+5%) = {small_s['win_rate_5pct']:.1f}%, средний макс рост 7д = {small_s['avg_max_gain_7d']:+.2f}% ({small_s['count']} сделок)")

    if medium_s and medium_s['count'] >= 5:
        lines.append(f"- **Средние докупки (10-30%)**: WR(+5%) = {medium_s['win_rate_5pct']:.1f}%, средний макс рост 7д = {medium_s['avg_max_gain_7d']:+.2f}% ({medium_s['count']} сделок)")

    if large_s and large_s['count'] >= 5:
        lines.append(f"- **Крупные докупки (30-100%)**: WR(+5%) = {large_s['win_rate_5pct']:.1f}%, средний макс рост 7д = {large_s['avg_max_gain_7d']:+.2f}% ({large_s['count']} сделок)")

    if double_s and double_s['count'] >= 5:
        lines.append(f"- **Удвоение+ (>100%)**: WR(+5%) = {double_s['win_rate_5pct']:.1f}%, средний макс рост 7д = {double_s['avg_max_gain_7d']:+.2f}% ({double_s['count']} сделок)")

    lines.append("")
    lines.append("### Практические рекомендации для бота")
    lines.append("")
    lines.append("На основе данных:")
    lines.append("")

    # Determine threshold recommendation
    best_bucket = None
    best_wr = 0
    for bname in ['<1% (dust)', '1-3% (micro)', '3-10% (small)', '10-30% (medium)', '30-100% (large)', '>100% (doubling+)']:
        s = bucket_stats.get(bname)
        if s and s['count'] >= 5 and s['win_rate_5pct'] > best_wr:
            best_wr = s['win_rate_5pct']
            best_bucket = bname

    if best_bucket:
        lines.append(f"1. **Лучшая группа по WR**: {best_bucket} с WR(+5%) = {best_wr:.1f}%")

    # Check if small topups are clearly worse
    small_wr = 0
    small_count = 0
    for bname in ['<1% (dust)', '1-3% (micro)']:
        s = bucket_stats.get(bname)
        if s and s['count'] >= 3:
            small_wr += s['win_rate_5pct'] * s['count']
            small_count += s['count']

    large_wr = 0
    large_count = 0
    for bname in ['10-30% (medium)', '30-100% (large)', '>100% (doubling+)']:
        s = bucket_stats.get(bname)
        if s and s['count'] >= 3:
            large_wr += s['win_rate_5pct'] * s['count']
            large_count += s['count']

    if small_count > 0 and large_count > 0:
        avg_small_wr = small_wr / small_count
        avg_large_wr = large_wr / large_count
        diff = avg_large_wr - avg_small_wr

        if diff > 10:
            lines.append(f"2. **Мелкие докупки (<3%) явно хуже**: средний WR = {avg_small_wr:.1f}% vs крупные (10%+) WR = {avg_large_wr:.1f}%")
            lines.append(f"   → **Рекомендация**: пропускать докупки с ratio < 3%, или снижать размер нашей ставки на 50-70%")
        elif diff > 5:
            lines.append(f"2. **Мелкие докупки (<3%) немного хуже**: средний WR = {avg_small_wr:.1f}% vs крупные (10%+) WR = {avg_large_wr:.1f}%")
            lines.append(f"   → **Рекомендация**: снижать размер ставки для мелких докупок на 30-50%")
        else:
            lines.append(f"2. **Разница между мелкими и крупными докупками невелика**: WR {avg_small_wr:.1f}% vs {avg_large_wr:.1f}%")
            lines.append(f"   → Размер докупки — не главный фактор. Копировать все докупки, но можно масштабировать размер ставки пропорционально ratio.")

    lines.append("")
    lines.append("3. **Предложение по масштабированию ставки**:")
    lines.append("   - ratio < 1%: ставка = 0 (пропускаем) или минимальная")
    lines.append("   - ratio 1-10%: ставка = 50% от обычной")
    lines.append("   - ratio 10-30%: ставка = 75% от обычной")
    lines.append("   - ratio 30%+: ставка = 100% (полный размер)")
    lines.append("   - Первый вход: ставка = 100%")
    lines.append("")
    lines.append("*Примечание: эти пороги нужно перепроверять при накоплении новых данных.*")

    return "\n".join(lines)


if __name__ == "__main__":
    print("Загрузка данных denizz...")
    trades = fetch_all_trades(max_pages=60)
    print(f"\nВсего загружено записей: {len(trades)}")

    if not trades:
        print("Нет данных!")
        sys.exit(1)

    # Save raw data
    with open("C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2/_analytics/data/topup_ratio_raw.json", "w") as f:
        json.dump(trades, f)
    print("Сырые данные сохранены.")

    result = analyze(trades)
    if result:
        bucket_stats, all_data, buckets_order = result

        # Date range
        trade_dates = [t for t in trades if t.get('type') == 'TRADE']
        trade_dates.sort(key=lambda t: t['timestamp'])
        d1 = datetime.utcfromtimestamp(trade_dates[0]['timestamp']).strftime('%Y-%m-%d')
        d2 = datetime.utcfromtimestamp(trade_dates[-1]['timestamp']).strftime('%Y-%m-%d')

        report = generate_report(bucket_stats, all_data, buckets_order, len(trade_dates), f"{d1} — {d2}")

        outpath = "C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2/_analytics/2026-04-13_topup-ratio-analysis.md"
        with open(outpath, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nОтчёт сохранён: {outpath}")
