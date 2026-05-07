# Monitor dedupe-key audit (monitor.py) — 2026-04-17

## 1. Резюме

В `monitor.py` dedupe-ключ `f"{tx}_{cond}_{ts_val}"` считает полные batch-ордеры денизза одним событием и выбрасывает вторую (третью, четвёртую) запись. Polymarket API **не возвращает уникальный идентификатор trade** (нет `id`, `orderHash`, `logIndex`) — единственный способ различать записи из одного batch-order — добавить к ключу `size` и `price`. Замена ключа на `f"{tx}_{cond}_{ts_val}_{size}_{price}"` безопасна: на 3000 живых записей денизза старый ключ терял 39 trade-записей на $37,189, новый — только 1 истинный дубликат на $2,444. Регрессия (36/36) и бэктест ($5251/$4604) не меняются — ключ читается только на входе и нигде не сохраняется. Рекомендация: **внедрять**. Точный diff — две строки ниже.

## 2. Масштаб бага

Источник: fresh fetch `activity?user=denizz&limit=500` × 6 страниц = 3000 записей (2978 TRADE).

| Метрика | OLD key (`tx+cond+ts`) | NEW key (`tx+cond+ts+size+price`) |
|---|---|---|
| Групп с N>1 | **35** | 1 (истинный дубликат) |
| Пропущенных TRADE-записей | **39** | 1 |
| Пропущенный USD (сумма `usdcSize`) | **$37,189.29** | $2,444.42 |

Топ-10 пропущенных batch-ордеров:

| # | Дата (UTC) | N | Всего $ | Пропущено $ | Рынок |
|---|---|---|---|---|---|
| 1 | 2026-04-15 06:52 | 3 | 29,327 | **11,305** | Iran x Israel/US conflict ends by April 7 |
| 2 | 2026-04-16 16:38 | 3 | 5,183 | **3,984** | US x Iran permanent peace by April 30 |
| 3 | 2026-04-15 00:42 | 2 | 6,091 | **3,215** | Trump announces end of military ops vs Iran |
| 4 | 2026-04-14 09:02 | 2 | 4,889 | **2,444** | US x Iran permanent peace by April 22 |
| 5 | 2026-04-16 03:08 | 4 | 2,645 | **2,090** | Israel suspends Lebanon offensive |
| 6 | 2026-04-15 06:53 | 2 | 2,711 | 1,705 | Iran x Israel/US conflict ends by April 15 |
| 7 | 2026-04-15 00:21 | 2 | 6,996 | 1,580 | Trump announces end of military ops |
| 8 | 2026-04-16 20:50 | 2 | 2,031 | 1,240 | Iran agrees to surrender enriched uranium |
| 9 | 2026-04-16 11:33 | 2 | 1,484 | 1,163 | US-Iran nuclear deal by April 30 |
| 10| 2026-04-15 05:21 | 2 | 1,178 | 1,053 | Iran agrees to surrender enriched uranium |

**Reported-case (2026-04-17):** `tx=0x2bb739...` — две записи с одинаковым `tx+cond+ts`, size 75.7 ($49.96) и 791.75 ($530.47). Старый ключ видел только первую, вторую ($530) пропускал → сигнал BUY с правильной суммой не доходил до логики ставок. Воспроизведено фетчем live API.

## 3. Анализ других типов событий

Scan тех же 3000 записей по `MERGE / REDEEM / SPLIT / TRANSFER / REWARD / YIELD`:

| Тип | N | Коллизий под OLD key |
|---|---|---|
| MERGE | 5 | 0 |
| REDEEM | 7 | 0 |
| REWARD | 10 | 0 |

Коллизий нет, но новый ключ всё равно их не ломает (строка `f"{size}_{price}"` для `size=None, price=0` работает, Test 6 проверил).

## 4. Рекомендованный ключ

```python
trade_key = f"{tx}_{cond}_{ts_val}_{size}_{price}"
```

Обоснование:
- **API не даёт уникального ID** (проверено: `id`/`orderHash`/`logIndex`/`tradeId` — не возвращаются ни одним полем в 50 живых записях). Комбинированный ключ — единственный вариант.
- `size` и `price` для одного batch-order в Polymarket **всегда различаются** между fill-записями (разные LP, разные цены исполнения).
- Python `f"{float}"` стабилен: тот же JSON от API → тот же Python-float → тот же `__str__` → тот же ключ. Нет плавающей ошибки между polls (Test 5 проверил).
- Для истинного дубликата (точно тот же fill возвращается дважды) новый ключ всё равно срабатывает как dedupe (Test 2 проверил).

Инициализация `seen_keys` при старте (строка 205) должна использовать **тот же формат**:

```python
seen_keys.add(f"{tx}_{cond}_{ts}_{size}_{price}")
```

иначе первый poll после рестарта заново увидит batch-ордера как «новые» и вызовет callbacks повторно.

## 5. Результаты регрессии

- **`_test_rebuy_v9.py`**: 36 passed, 0 failed (неизменно)
- **`_rebuy_trigger_backtest.py`**:
  - Control Final BR = **$4604.07** (ожидали ~$4604 ±50 — в пределах)
  - Treatment Final BR = **$5251.95** (ожидали ~$5251 ±50 — в пределах)
  - Delta +$647.88 / +16.20pp — матчит отчёт `2026-04-17_rebuy-trigger-backtest.md`
- **Новый `_test_dedupe_fix.py`** (7 кейсов, 11 ассертов): 11 passed, 0 failed
  - Test 1: batch-order (same tx+cond+ts, diff size/price) → OLD drops 1, NEW keeps оба
  - Test 2: точный дубликат → обе дедупят до 1
  - Test 3–4: разный только size ИЛИ только price → оба попадают
  - Test 5: float round-trip стабилен
  - Test 6: size=None, price=0 — не падает
  - Test 7: replay 2978 live TRADE записей: OLD lost $37,189 / NEW lost $2,444

Backtest неизменен потому что он кормится из файла `denizz_activity_ALL.json` — API-лимиты dedupe на уровне монитора там не применяются.

## 6. Edge cases

| Случай | Поведение | Статус |
|---|---|---|
| Batch-order (same tx+cond+ts, diff size/price) | OLD теряет, NEW сохраняет | Исправлено |
| Истинный дубликат (polls повторяют запись) | Оба дедупят | OK |
| Float precision между polls | API возвращает те же байты JSON → те же floats → те же строки. Прогнано 2978 записей, нет ложных несоответствий | OK |
| `size=None`, `price=0` (MERGE/SPLIT) | `f"{None}_{0}"` → валидная строка, не падает | OK |
| `seen_keys` persistence через рестарт | **Нет persistence** — `seen_keys` заводится в локальной переменной `_poll_player`. После рестарта пересобирается из первых 100 активити через API. Startup-recovery (строки 131–199) обрабатывает только пропущенные SELL'ы — на BUY не влияет. Это не регрессирует, но оставляет узкое место: batch-ордер, случившийся за 5-25 сек до рестарта, может быть перезасчитан как «новый» и вызвать `on_buy` повторно. Отдельная проблема, не относится к этому фиксу. | Не ухудшается |
| Неограниченный рост `seen_keys` | Уже известная проблема (HIGH-3 в `2026-04-16_ultrareview-analysis.md`). Не затрагивается фиксом: добавление 2 полей к ключу увеличивает память на ~10 байт/запись → +30-50 KB за месяц. Несущественно. | Не ухудшается |

## 7. Финальный diff для monitor.py

**Файл:** `C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\monitor.py`

**Две строки** (201–205 и 220–224):

```diff
@@ -201,7 +201,9 @@ def _poll_player(player_name, wallet, on_buy, on_sell, on_merge, start_time):
     for trade in initial:
         tx = trade.get("transactionHash", "")
         cond = trade.get("conditionId", "")
         ts = str(trade.get("timestamp", ""))
-        seen_keys.add(f"{tx}_{cond}_{ts}")
+        size = trade.get("size", 0)
+        price = trade.get("price", 0)
+        seen_keys.add(f"{tx}_{cond}_{ts}_{size}_{price}")

@@ -220,7 +222,9 @@
             for trade in activities:
                 tx = trade.get("transactionHash", "")
                 cond = trade.get("conditionId", "")
                 ts_val = trade.get("timestamp", 0)
-                trade_key = f"{tx}_{cond}_{ts_val}"
+                size = trade.get("size", 0)
+                price = trade.get("price", 0)
+                trade_key = f"{tx}_{cond}_{ts_val}_{size}_{price}"

                 if trade_key in seen_keys:
                     continue
```

**Важно:** оба места (строка 205 — seed при старте, строка 224 — dedupe в цикле) должны использовать идентичный формат, иначе первый poll увидит всё как «новое».

Никаких других файлов менять не нужно — `grep seen_keys|trade_key` показывает, что ключ используется только в `monitor.py` (другие упоминания — в `_analytics/*.md` как плановые улучшения, не код).

## Приложения

- `_analytics/data/_test_dedupe_fix.py` — новый unit-тест (11 assertions pass)
- `_analytics/data/_dedupe_audit_denizz_live.json` — 3000 живых записей денизза (срез 2026-04-17)
