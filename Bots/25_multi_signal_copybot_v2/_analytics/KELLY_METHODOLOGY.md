# Kelly Criterion для multi-copy bot — методология на будущее

## Когда применять
**После 50-100 closed trades per signal player** (Car, aenews2, denizz).
Сейчас (08.04.2026) у нас 5-9 closed trades per игрок — **недостаточно**.

## Источник данных
Closed trades **уже логируются** в `positions.json`:
- `signal_player` — кто дал сигнал
- `entry_price` — наша цена входа
- `cost_usd` — сколько потратили
- `final_pnl` — реальный профит/убыток
- `outcome` — Yes / No
- `status` — won / lost / sold
- `timestamp` — когда вошли
- `sells` — детали выходов

---

## Формула Kelly

```
f* = (b·p - q) / b
```

Где:
- `f*` — доля банкролла на ставку
- `b` — net коэффициент = `(1 - entry_price) / 1` для бинарных рынков
- `p` — реальная вероятность выигрыша
- `q = 1 - p`

**Упрощённая для бинарного No/Yes:**
```
f* = (p - entry_price) / (1 - entry_price)
```

---

## Как считать `p` (истинную вероятность)

### Шаг 1: разделить closed trades по игроку и ценовому диапазону

```python
def compute_player_win_rate_by_bucket(trades, player):
    buckets = {
        '0.05-0.15': [], '0.15-0.30': [], '0.30-0.50': [],
        '0.50-0.70': [], '0.70-0.85': [], '0.85-0.95': [], '0.95-0.98': []
    }
    for t in trades:
        if t['signal_player'] != player:
            continue
        if t['status'] not in ('won', 'lost'):
            continue
        price = t['entry_price']
        bucket = get_bucket(price)
        buckets[bucket].append(1 if t['status'] == 'won' else 0)
    
    return {b: sum(v)/len(v) if v else None for b, v in buckets.items()}
```

### Шаг 2: проверить статистическую значимость

**Минимум 30 наблюдений на bucket** для надёжной оценки p.

```python
def is_significant(bucket_trades, min_n=30):
    return len(bucket_trades) >= min_n
```

Если < 30 — **не использовать Kelly для этого bucket**, использовать дефолтный размер.

### Шаг 3: применить fractional Kelly (¼)

**Никогда не использовать full Kelly.** Стандарт — четверть Kelly.

```python
def kelly_size(banrkoll, entry_price, p, fraction=0.25, max_pct=0.10):
    """
    Returns position size in USD.
    Args:
        bankroll: total capital
        entry_price: market price (0.0-1.0)
        p: estimated true probability (from historical WR)
        fraction: Kelly fraction (default 0.25)
        max_pct: hard cap as % of bankroll (default 10%)
    """
    if p <= entry_price:
        return 0  # no edge
    
    b = (1 - entry_price) / entry_price  # use entry as proportion
    edge = (b * p - (1 - p)) / b
    
    full_kelly = max(0, edge)
    fractional = full_kelly * fraction
    capped = min(fractional, max_pct)
    
    return bankroll * capped
```

---

## Гипотетические Kelly-размеры для копибота (когда будут данные)

**ПРИМЕРЫ для иллюстрации, не для применения сейчас.**

При банкролле $2000, ¼ Kelly, cap 10%, условие p > entry+5%:

| Игрок | Entry | Истинная p | Full Kelly | ¼ Kelly | $ size |
|-------|-------|-----------|-----------|---------|--------|
| denizz | 0.10 | 0.15 | 5.6% | 1.4% | **$28** |
| denizz | 0.20 | 0.30 | 12.5% | 3.1% | **$62** |
| denizz | 0.40 | 0.50 | 16.7% | 4.2% | **$83** |
| denizz | 0.60 | 0.70 | 25.0% | 6.3% | **$125** |
| denizz | 0.80 | 0.90 | 50.0% | 12.5% | **$200** (cap) |
| Car | любой | edge ≤ 0 | 0% | 0% | **$0** |
| aenews2 | 0.20 | 0.25 | 6.3% | 1.6% | **$31** |

**ВНИМАНИЕ:** колонка "Истинная p" в этой таблице **выдумана**. Реальные p будут известны после 50-100 closed trades.

---

## Скрипт для расчёта Kelly из реальных данных

```python
"""
Run when we have 100+ closed trades per player.
"""
import json
from collections import defaultdict

def analyze_for_kelly(positions_file='positions.json'):
    with open(positions_file) as f:
        data = json.load(f)
    
    # Group by player + bucket
    buckets = {
        (0.00, 0.10): [], (0.10, 0.20): [], (0.20, 0.30): [],
        (0.30, 0.50): [], (0.50, 0.70): [], (0.70, 0.85): [],
        (0.85, 0.95): [], (0.95, 0.99): [],
    }
    
    by_player = {p: {b: [] for b in buckets} for p in ['Car', 'aenews2', 'denizz']}
    
    for oid, p in data['positions'].items():
        if p.get('status') not in ('won', 'lost'):
            continue
        player = p.get('signal_player', '')
        if player not in by_player:
            continue
        price = p.get('entry_price', 0)
        bucket = next((k for k in buckets if k[0] <= price < k[1]), None)
        if not bucket:
            continue
        won = 1 if p['status'] == 'won' else 0
        by_player[player][bucket].append(won)
    
    # Compute WR per bucket
    print(f"{'Player':<10} {'Range':<12} {'N':>5} {'WR':>7} {'Kelly p':>10}")
    print('-' * 50)
    for player, bs in by_player.items():
        for (lo, hi), wins in bs.items():
            n = len(wins)
            if n < 30:
                continue  # not enough data
            wr = sum(wins) / n
            print(f"{player:<10} {lo:.2f}-{hi:.2f}    {n:>5} {wr:>6.1%} {wr:>9.3f}")
    
    return by_player

if __name__ == '__main__':
    analyze_for_kelly()
```

---

## Risk caveats применения Kelly

1. **Survivorship bias данных.** Мы видим только то что игрок продолжает работать. Если он ошибётся — мы узнаём поздно.

2. **Non-stationary distribution.** Политические рынки меняются — Iran-фаза не повторится. WR в одну фазу ≠ WR в другую.

3. **Latency penalty.** Наш entry хуже игрока. Реальный наш p < его p. Применять discount factor:
   ```python
   p_us = p_player * 0.7  # мы хуже на 30% из-за latency
   ```

4. **Correlation across positions.** Kelly предполагает независимые ставки. Если все 7 позиций про Iran — они сильно коррелированы. Снижать Kelly при concentrated bets:
   ```python
   if positions_in_same_theme >= 5:
       kelly *= 0.5
   ```

5. **Drawdown risk.** Full Kelly даёт максимальный долгосрочный рост, но просадки достигают 50%+. ¼ Kelly — жертвуем 1/4 ростом, получаем drawdown ~10%.

---

## Roadmap

| Срок | Действие |
|------|----------|
| **Сейчас** | Использовать тиры (новые) |
| **Через 1 неделю** | 50-100 closed trades — посмотреть WR per игрок |
| **Через 2-3 недели** | Backtest Kelly на истории, сравнить с тирами |
| **Через 1 месяц** | Применить ¼ Kelly если backtest показывает преимущество |

---

## Closed trades — где смотреть

Все closed trades **уже логируются** в:
- `positions.json` — поле `final_pnl`, `status` для каждой
- Поля доступны: `signal_player`, `entry_price`, `cost_usd`, `outcome`, `timestamp`, `sells`, `parts_filled`, `tier`

**Никаких дополнительных изменений в боте не нужно** — данные собираются автоматически.

Для агрегации сделать:
```python
# Все закрытые сделки за период
closed = [p for p in positions.values()
          if p.get('status') in ('won', 'lost', 'sold')
          and p.get('timestamp', '') >= cutoff_date]
```
