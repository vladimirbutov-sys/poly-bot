# `signal_player="unknown"` блокирует follow-sell

**Дата:** 2026-04-21
**Модуль:** `exit_manager.py` (cross-player guard block)
**Серьёзность:** средняя (adopted позиции застревают навсегда)
**Статус:** исправлено

---

## 1. Инцидент

Рынок [Iran agrees to unrestricted shipping through Hormuz in April](https://polymarket.com/event/iran-agrees-to-unrestricted-shipping-through-hormuz-in-april):
- CID: `0x3e1363efbf76899943f61797d0ffc2de5c47a716e2ec66189f45ab65b28078f9`
- Наша позиция: 205.23 sh YES, cost $62.13, avg $0.30 (**тип: orphan, адоптирована через `sync_with_onchain`**)
- tracker-ключ: `0xsync_996cd419531bf78497bb7066fca54bba`, `signal_player: "unknown"`, `_adopted_from: "onchain_sync"`

**Денизz**: 15–17.04 набрал ~$3 800 в YES, 17.04 12:54–13:32 продал всё за ~$5 800 (+$2 000 profit).

**Бот**: при каждом sell-событии denizz на этом рынке писал:
```
[EXIT] SKIP: denizz sold but position was opened by unknown | Iran agrees to unrestricted...
```

Результат: наш 205 sh YES **не закрылся**, просел с ~$0.65 (момент denizz-exit) до $0.235 сегодня. Упущенная прибыль ≈ $88.

---

## 2. Root cause

`exit_manager.py:853-858` (до фикса):
```python
pos_signal_player = pos.get("signal_player", "")
if (pos_signal_player
        and pos_signal_player != player_name
        and pos_signal_player != "manual"):
    print(f"[EXIT] SKIP: {player_name} sold but position was opened by {pos_signal_player} ...")
    return
if pos_signal_player == "manual":
    print(f"[EXIT] manual position following {player_name}: ...")
```

Проверка срабатывала когда:
- `pos_signal_player` truthy (не пустая строка) — `"unknown"` truthy → match
- `!= player_name` — `"unknown" != "denizz"` → match
- `!= "manual"` — `"unknown" != "manual"` → match
- **→ SKIP**

Позиция с `signal_player="unknown"` попадала в cross-player guard и блокировалась как если бы это был другой реальный игрок (например «car»).

### Откуда берётся `signal_player="unknown"`

`tracker.sync_with_onchain` (reverse scan) — когда on-chain баланс появляется без соответствующей записи в tracker, бот **адоптирует** его:
- `key = "0xsync_<hash>"`
- `signal_player = "unknown"` (мы не знаем кто открыл)
- `_adopted_from = "onchain_sync"`

Это происходит при:
1. Рестарте бота когда state-файлы потеряли часть истории
2. Manual-операциях которые не прошли через `_manual_buy_*.py` шаблон
3. Миграции между версиями

---

## 3. Фикс

`exit_manager.py:854-866` (после фикса):
```python
# Fix 2026-04-21: "unknown" / empty signal_player comes from
# tracker.sync_with_onchain reverse-scan — we found an on-chain balance
# with no matching tracker entry. These orphan positions have no known
# opener, so cross-player protection is meaningless — allow follow-sell
# from any active player, same as "manual". [...]
pos_signal_player = pos.get("signal_player", "")
_orphan_signals = ("", "unknown", None)
if (pos_signal_player not in _orphan_signals
        and pos_signal_player != player_name
        and pos_signal_player != "manual"):
    print(f"[EXIT] SKIP: {player_name} sold but position was opened by {pos_signal_player} ...")
    return
if pos_signal_player == "manual":
    print(f"[EXIT] manual position following {player_name}: ...")
elif pos_signal_player in _orphan_signals:
    print(f"[EXIT] orphan-sync position ({pos.get('_adopted_from', '?')}) following {player_name}: ...")
```

### Логика изменения

| `signal_player` | Было | Стало |
|---|---|---|
| `"denizz"` + сигнал от denizz | OK | OK (без изменений) |
| `"manual"` | OK | OK (фикс от 2026-04-15) |
| `"unknown"` | **SKIP** | **OK** — лечение |
| `""` / `None` | SKIP | OK — defensive |
| `"car"` + сигнал от denizz | SKIP | SKIP (cross-player защита **сохранена**) |

### Что НЕ трогаем

- Cross-player guard между реальными игроками (car vs denizz) — работает корректно, не трогаем.
- `tracker.sync_with_onchain` — продолжаем ставить `signal_player="unknown"` когда нет информации. Менять не нужно: «unknown» теперь в exit-логике обрабатывается корректно.

---

## 4. Тесты

Файл: `tests/test_unknown_signal_player_follow_sell.py` — **5/5 passed**:
1. `test_unknown_signal_player_follows_denizz` — **воспроизведение инцидента**
2. `test_empty_signal_player_follows_denizz` — defensive: пустая строка
3. `test_denizz_signaled_still_follows_denizz` — non-regression: обычный denizz-путь
4. `test_other_player_blocks_denizz_sell` — cross-player protection сохранена
5. `test_manual_still_follows_denizz` — non-regression: manual-фикс 15.04

---

## 5. Три бага подряд за сутки — что общего

| Баг | Файл | Суть | Фикс дата |
|---|---|---|---|
| cumul > 100% → dust SKIP | `exit_manager.py` tier loop | tier-таблица обрывается на 1.01, cumul 1.53 не матчит | 2026-04-21 AM |
| YES блок NO entry | `main.py:783` / `tracker` | `has_position_on_condition` без outcome-фильтра | 2026-04-21 afternoon |
| `unknown` → SKIP | `exit_manager.py:854` | cross-player guard считает "unknown" чужим игроком | 2026-04-21 evening |

Общая тема: **тонкая разница между "нет данных" и "данные другой стороны"**. Везде исходная логика не различала и трактовала по-жёсткому.

---

## 6. Воздействие на прошлые события

Пошёл по логам за 10 дней на строку `opened by unknown`:
- Каждый случай = пропущенный follow-sell на orphan-позицию.
- Оценка упущенной прибыли: только по Iran-shipping ~$88; ретроспективно можно посчитать по всем позициям с `signal_player="unknown"`.

Отдельная задача — пройти по бэктесту и оценить. Не блокер.

---

## 7. Deliverables

| Файл | Что |
|---|---|
| `exit_manager.py:853-870` | Patch — `_orphan_signals` tuple + allow branch |
| `tests/test_unknown_signal_player_follow_sell.py` | 5 тестов |
| `_manual_sell_iran_unrestricted_shipping_apr_205sh_cleanup.py` | Закрытие зависшей позиции |
| Этот документ | Анализ и обоснование |
