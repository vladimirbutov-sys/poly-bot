# Dual Bot Upgrade System: Oil Swing Bot ($100) + Oil Swing Bot2 ($105)

**Дата:** 2026-03-21
**Тип:** Полный редизайн стратегий + новые модули
**Источники данных:** 612 точек theta_calibration.json, 16 реальных сделок, 2 выходных гэпа

---

## 1. РЕЗУЛЬТАТЫ БЭКТЕСТА (ДОКАЗАТЕЛЬНАЯ БАЗА)

### Bot 1 — Oil Swing Bot ($100 market), 345 точек данных

| Конфигурация | Сделок | WR | P&L | Max DD | Avg hold |
|---|---|---|---|---|---|
| **BASELINE (текущий)** | 14 | 71% | +$62.59 | $13.53 | 8.2h |
| +YES>80% блок | 3 | 67% | +$7.74 | $0 | 8.7h |
| +YES>75% блок | 0 | - | $0 | - | - |
| **+momentum $2 блок** | **8** | **88%** | **+$57.91** | **$0** | **5.6h** |
| +weekend блок | 13 | 77% | +$37.05 | $6.09 | 7.9h |
| +weekend EXIT | 29 | 52% | +$47.69 | $15.22 | 3.8h |
| COMBINED (все фильтры) | 2 | 50% | +$3.54 | $0 | 10.5h |

**Ключевые выводы Bot1:**
- **YES>80% блок ВРЕДИТ** - убивает 79% сделок. YES почти всегда >80% когда WTI>$97 (зона входа). Прибыльные сделки тоже блокируются.
- **Momentum фильтр $2 - ПОБЕДИТЕЛЬ** - WR с 71% до 88%, P&L почти не падает ($62 -> $58), Max DD с $13.53 до $0!
- Weekend блок снижает P&L на 41% - слишком агрессивно
- Overfiltering (все вместе) убивает бота - всего 2 сделки

### Bot 2 — Oil Swing Bot2 ($105 market), 225 точек данных

| Конфигурация | Сделок | WR | P&L | Max DD | Avg hold |
|---|---|---|---|---|---|
| **BASELINE (текущий)** | 15 | 60% | +$467.75 | $90.34 | 12.5h |
| +YES>60% блок | 3 | 67% | +$15.69 | $12.04 | 17.0h |
| +YES>70% блок | 5 | 80% | +$40.40 | $12.04 | 29.2h |
| **+momentum $2 блок** | **9** | **89%** | **+$489.21** | **$12.04** | **18.4h** |
| +weekend блок | 11 | 64% | +$111.67 | $51.03 | 16.1h |
| +weekend EXIT | 38 | 50% | +$511.27 | $90.34 | 4.9h |
| COMBINED (все фильтры) | 2 | 50% | +$2.05 | $12.04 | 10.0h |
| profit 10% | 16 | 62% | +$455.16 | $90.34 | 11.6h |
| profit 20% | 13 | 54% | +$463.90 | $90.34 | 14.4h |

**Ключевые выводы Bot2:**
- **Momentum фильтр $2 - снова ПОБЕДИТЕЛЬ** - WR 60% -> 89%, P&L ВЫРОС с $467 до $489! Max DD упал с $90 до $12!
- YES блок (любой порог) убивает бота - слишком мало сделок
- Profit target 10-20% дает примерно одинаковый P&L - текущий 13% оптимален
- Weekend EXIT увеличивает P&L но при 50% WR и огромном DD

### Анализ выходных гэпов (Weekend Gaps)

| Дата | WTI пятница | WTI понедельник | Гэп | NO потери ($100) | NO потери ($105) |
|---|---|---|---|---|---|
| 8 марта (Hormuz) | $90.90 | $106.94 | **+$16.04** | **-65.4%** | **-58.6%** |
| 15 марта (тихий) | $99.31 | $99.60 | +$0.29 | -9.8% | -18.4% |

**Вывод:** Один выходной гэп 8 марта уничтожил бы любую NO позицию. Даже "тихий" выходной 15 марта дал -10-18% потерь на NO.

---

## 2. РАЗДЕЛЬНЫЕ СТРАТЕГИИ

### Bot 1 "SNIPER" — Oil Swing Bot ($100)

**Роль:** Ловит развороты WTI вблизи $100. Высокий риск, высокий потенциал.

**Рынок:** YES/NO на "WTI >= $100 к 31 марта"

**Что меняем (подтверждено бэктестом):**

| Параметр | Было | Стало | Почему |
|---|---|---|---|
| Momentum фильтр | нет | $2.0 за 6 часов | WR 71%->88%, DD $13->$0 |
| YES блок для NO | нет | **НЕ добавляем** | Бэктест: убивает 79% сделок |
| Weekend | нет | Блок входа пт 20 ET - пн 09 ET | Гэп 8 марта: -65% |
| MAX_NO_ENTRY_PRICE | 0.26 | 0.22 | Снижаем риск при дорогом NO |
| STEP_COOLDOWN | 0 | 1800 (30 мин) | Защита от каскадного входа |

**Логика входа NO (обновленная):**
```
1. WTI >= $97 (как сейчас)
2. NO цена <= 22c (ужесточено с 26c)
3. Momentum: WTI НЕ вырос более $2 за последние 6 часов
4. НЕ выходные (пт 20 ET - пн 09 ET)
5. НЕ dead zone (14-15 ET)
6. Cooldown 30 мин между степами
```

**Логика входа YES (без изменений):**
```
Работает редко (1 сделка из 14). Оставляем как есть.
WTI <= $92 -> $5, WTI <= $90 -> $5, WTI <= $88 -> $15
```

**Ожидаемый эффект:** WR 71% -> ~85-88%, Max DD -85%, P&L -8% (компенсируется снижением риска)

---

### Bot 2 "HARVESTER" — Oil Swing Bot2 ($105)

**Роль:** Стабильный сбор прибыли на далёком рынке. Низкий риск, регулярный доход.

**Рынок:** NO на "WTI >= $105 к 31 марта"

**Что меняем (подтверждено бэктестом):**

| Параметр | Было | Стало | Почему |
|---|---|---|---|
| Momentum фильтр | нет | $2.0 за 6 часов | WR 60%->89%, P&L +$21 |
| YES блок для NO | нет | **НЕ добавляем** | Бэктест: убивает бота |
| Weekend | нет | Блок входа пт 20 ET - пн 09 ET | Гэп 8 марта: -59% |
| WTI_MAX_ENTRY | $98 | $99 | Больше возможностей входа |
| PROFIT_TARGET | 0.13 | Оставить 0.13 | Бэктест: 10% и 20% не лучше |

**Логика входа NO (обновленная):**
```
1. YES $105 > 55% (как сейчас, corrector может менять до 50%)
2. WTI < $99 (расширено с $98)
3. Momentum: WTI НЕ вырос более $2 за последние 6 часов
4. НЕ выходные (пт 20 ET - пн 09 ET)
5. НЕ dead zone (12-16 ET)
6. < 2 открытых позиций
```

**Ожидаемый эффект:** WR 60% -> ~85-89%, Max DD -87% ($90 -> $12), P&L +5%

---

### Сравнение ролей

| | Bot 1 "SNIPER" ($100) | Bot 2 "HARVESTER" ($105) |
|---|---|---|
| Рынок | $100 (close to settlement) | $105 (far from settlement) |
| Риск | Высокий | Низкий |
| Размер ставки | $5-20 (gradient) | $60 (fixed) |
| Profit target | 35-104% (per step) | 13% (fast) |
| Avg hold | 5-8 часов | 12-18 часов |
| WTI триггер | >= $97 | YES > 55% |
| Макс позиций | 3 степа | 2 позиции |
| Банкролл | $300 | $300 |

**Ключевое отличие:** SNIPER ловит большие свинги (35%+ прибыль), HARVESTER стабильно собирает 13% на каждой сделке. Вместе они покрывают разные рыночные условия.

---

## 3. АЛГОРИТМ "ВЫХОД ИЗ ВЫХОДНЫХ" (Weekend-to-Monday)

### Проблема (из бэктеста)

Выходной гэп 8 марта ($90 -> $107, +$16) уничтожил бы любую NO позицию:
- Bot1 NO: **-65% потерь**
- Bot2 NO: **-59% потерь**

Даже "тихий" выходной 15 марта дал **-10 до -18%** потерь.

### Алгоритм: 4 фазы

```
ПЯТНИЦА (Phase 1: SHUTDOWN)
  16:00 ET: Закрыть ВСЕ открытые NO позиции по рынку
  16:30 ET: Отправить Telegram "Weekend shutdown complete"
  Содержание: P&L недели, закрытые позиции, текущий WTI

СУББОТА-ВОСКРЕСЕНЬЕ (Phase 2: WATCH)
  Каждые 2 часа: News Sentinel проверяет RSS-ленты
  При обнаружении RED/BLACK события: немедленный Telegram-алерт
  Формат алерта:
    "WEEKEND ALERT [RED]
     Headline: Iran strikes oil facility in Saudi Arabia
     Source: Reuters Energy RSS
     Impact: WTI likely +$5-10 at Monday open
     Recommendation: Do NOT enter NO positions Monday morning"

ВОСКРЕСЕНЬЕ 20:00 ET (Phase 3: PRE-MONDAY BRIEFING)
  News Sentinel собирает все события за выходные
  Генерирует риск-скор: GREEN/YELLOW/RED/BLACK
  Отправляет в Telegram полный брифинг:
    "PRE-MONDAY BRIEFING
     News Risk Level: YELLOW
     Key events: 2 escalation, 1 de-escalation
     WTI futures (Globex): $XX.XX
     Recommended strategy:
       Bot1 SNIPER: Normal mode, momentum filter active
       Bot2 HARVESTER: Reduced size (50%), tighter stop"

ПОНЕДЕЛЬНИК (Phase 4: GRADUAL RESTART)
  06:00 ET (13:00 MSK): News Sentinel делает финальную проверку
  09:00 ET (16:00 MSK): Боты возобновляют торговлю
  Первые 3 часа: Размер ставки 50% от нормы (защита от утреннего шума)
  12:00 ET: Полный размер ставок (если risk level не RED/BLACK)
```

### Таблица решений по риск-уровню

| Risk Level | Вход | Размер ставки | Стоп-лосс | Действие |
|---|---|---|---|---|
| GREEN | Разрешен | 100% | Стандартный | Нормальная торговля |
| YELLOW | Разрешен | 50% | Ужесточен на 20% | Осторожная торговля |
| RED | **Заблокирован** | 0% | - | Только мониторинг |
| BLACK | **Заблокирован** | 0% | Закрыть все | Экстренное закрытие |

### Изменения в коде

**strategy.py (оба бота)** - добавить:
```python
def is_weekend_blocked() -> bool:
    """Friday 20 ET to Monday 09 ET: no new positions."""
    dt = datetime.now(timezone.utc)
    weekday = dt.weekday()  # 0=Mon, 6=Sun
    hour_et = (dt.hour - 4) % 24

    if weekday == 4 and hour_et >= 20:  # Friday evening
        return True
    if weekday in (5, 6):  # Saturday, Sunday
        return True
    if weekday == 0 and hour_et < 9:  # Monday morning
        return True
    return False
```

**main.py (оба бота)** - в run_cycle():
```python
# Before buy checks
if is_weekend_blocked():
    log("Weekend block active, no new entries")
    return

# Friday auto-close
if is_friday_close_time():
    close_all_positions("weekend_shutdown")
    send_weekly_summary()
```

---

## 4. МОДУЛЬ NEWS SENTINEL (Анализ новостей и соцсетей)

### Архитектура

```
news_sentinel.py (общий модуль для обоих ботов)
    |
    +-- RSS Monitor (каждые 15 мин)
    |     +-- Reuters Energy
    |     +-- CNBC Energy
    |     +-- Al Jazeera Middle East
    |     +-- Yahoo Finance Oil
    |     +-- TASS/RIA (русскоязычные)
    |
    +-- Keyword Scorer
    |     +-- Escalation words (+score)
    |     +-- De-escalation words (-score)
    |     +-- Oil-specific terms (multiplier)
    |
    +-- Risk Level Calculator
    |     +-- GREEN (score < 3)
    |     +-- YELLOW (3 <= score < 7)
    |     +-- RED (7 <= score < 12)
    |     +-- BLACK (score >= 12)
    |
    +-- Strategy Adjuster
          +-- Отправляет risk_level в оба бота
          +-- Боты корректируют размер ставки и стопы
```

### RSS-ленты (бесплатные)

| Источник | RSS URL | Задержка | Язык |
|---|---|---|---|
| EIA Press | `https://www.eia.gov/rss/press_rss.xml` | мгновенно | EN |
| EIA Today in Energy | `https://www.eia.gov/rss/todayinenergy.xml` | мгновенно | EN |
| Google News Oil | `https://news.google.com/rss/search?q=crude+oil+WTI&hl=en` | ~10 мин | EN |
| Google News Iran | `https://news.google.com/rss/search?q=iran+oil+sanctions&hl=en` | ~10 мин | EN |
| Google News OPEC | `https://news.google.com/rss/search?q=OPEC+production&hl=en` | ~10 мин | EN |
| ТАСС | `https://tass.com/rss/v2.xml` | ~3 мин | RU |
| Trump Truth Social | `https://www.trumpstruth.org/feed` | ~15 мин | EN |

**Дополнительные API (бесплатные):**
| Источник | URL | Лимит | Назначение |
|---|---|---|---|
| Oil Price API | `https://www.oilpriceapi.com/` | безлимит | WTI/Brent цены (5 мин) |
| GNews API | `https://gnews.io/` | 100 req/день | Поиск по ключевым словам |
| Iran Monitor | `https://www.iranmonitor.org/` | безлимит | Геополитический OSINT |
| GPR Index | `https://www.matteoiacoviello.com/gpr.htm` | безлимит | Индекс геополитического риска |

### Словарь ключевых слов

**Эскалация (повышают скор):**
```python
ESCALATION = {
    # +5 (критические)
    "nuclear strike": 5, "war declared": 5, "strait closed": 5,
    # +4 (высокие)
    "oil facility attack": 4, "sanctions imposed": 4, "embargo": 4,
    "hormuz blocked": 4, "military strike": 4,
    # +3 (средние)
    "missile launch": 3, "drone attack": 3, "pipeline explosion": 3,
    "supply disruption": 3, "refinery fire": 3, "OPEC emergency": 3,
    # +2 (умеренные)
    "troops deployed": 2, "naval blockade": 2, "sanctions threat": 2,
    "production cut": 2, "inventory decline": 2,
    # +1 (слабые)
    "tensions rise": 1, "warning issued": 1, "military exercise": 1,
}

DEESCALATION = {
    # -5 (критические)
    "ceasefire signed": -5, "peace deal": -5, "sanctions lifted": -5,
    # -4 (высокие)
    "ceasefire talks": -4, "de-escalation": -4, "troops withdrawal": -4,
    "strait reopened": -4, "deal reached": -4,
    # -3 (средние)
    "negotiations resume": -3, "diplomatic solution": -3,
    "production increase": -3, "OPEC boost": -3,
    # -2 (умеренные)
    "talks scheduled": -2, "tensions ease": -2, "surplus": -2,
    # -1 (слабые)
    "winding down": -1, "diplomatic channels": -1,
}

# Множители для контекста
OIL_MULTIPLIER = {
    "crude oil": 1.5, "WTI": 1.5, "brent": 1.3,
    "OPEC": 1.3, "Saudi": 1.2, "Iran": 1.5,
    "Russia": 1.2, "pipeline": 1.3, "refinery": 1.3,
}
```

### Пример работы

```
Заголовок: "Iran drone attack hits Saudi oil facility, crude prices surge"

Разбор:
  "drone attack" -> +3
  "oil facility" -> +4
  "Iran" multiplier -> x1.5
  Score = (3 + 4) * 1.5 = 10.5 -> RED

Результат: risk_level = RED
  Bot1 SNIPER: вход заблокирован, NO не покупаем
  Bot2 HARVESTER: вход заблокирован, NO не покупаем
  Telegram: "RED ALERT: Iran drone attack on Saudi facility"
```

### Мониторинг соцсетей

**Trump Truth Social:**
- RSS-архив (включая удалённые посты): `https://www.trumpstruth.org/feed`
- Фильтр по дате: `https://www.trumpstruth.org/feed?start_date=2026-03-20&end_date=2026-03-21`
- Бэкап: Google News RSS `https://news.google.com/rss/search?q=trump+oil+iran+sanctions&hl=en`
- Ключевые фразы Трампа: "winding down", "deal", "sanctions", "drill baby drill"
- Особенность: Трамп пишет в 6-8 AM ET и 21-23 ET -> совпадает с нашим "золотым окном" МСК

**Telegram каналы (ручной мониторинг с алертами):**
- Военные каналы (Рыбарь, WarGonzo) -> для Иран/Ближний Восток
- Нефтяные каналы -> для ОПЕК новостей
- Sentinel НЕ читает Telegram автоматически (API платный), но может принимать ручные команды

### Интеграция с ботами

```python
# В main.py каждого бота:
from news_sentinel import NewsSentinel

sentinel = NewsSentinel()

def run_cycle():
    # Обновляем новостной фон
    risk_level = sentinel.get_risk_level()

    # Корректируем стратегию
    if risk_level == "BLACK":
        close_all_positions("news_black_alert")
        return
    if risk_level == "RED":
        log("RED alert - no new entries")
        return  # Только мониторинг, без входов

    size_mult = 1.0 if risk_level == "GREEN" else 0.5  # YELLOW = 50%

    # ... остальная логика с учётом size_mult
```

---

## 5. ЕЖЕДНЕВНАЯ АНАЛИТИЧЕСКАЯ ВЫЖИМКА В TELEGRAM

### Формат сообщения (отправляется в 07:00 МСК / 00:00 ET)

```
ЕЖЕДНЕВНЫЙ ОТЧЁТ НЕФТЯНЫХ БОТОВ | 22.03.2026

======= ПОРТФЕЛЬ =======
Bot1 SNIPER ($100): $347.54 (+15.8%)
Bot2 HARVESTER ($105): $316.16 (+5.4%)
ИТОГО: $663.70 (+10.6%)

======= ЗА ПОСЛЕДНИЕ 24Ч =======
Сделок: 3 (2 прибыльных, 1 убыточная)
  Bot1: продажа NO +$3.87 (+48%)
  Bot2: продажа NO +$8.02 (+20%)
  Bot2: продажа NO +$8.14 (+13%)
P&L за день: +$20.03

======= СОСТОЯНИЕ РЫНКА =======
WTI settlement: $98.32
YES $100: 70.5% | NO $100: 29.5%
YES $105: 43.6% | NO $105: 56.4%
Momentum (6ч): +$0.85 (НЕЙТРАЛЬНЫЙ)
Дней до экспирации: 7

======= НОВОСТНОЙ ФОН =======
Уровень риска: ЗЕЛЁНЫЙ
Заголовки: 0 эскалация, 0 деэскалация
Главная новость: "ОПЕК сохраняет уровень добычи"

======= ПРЕДЛОЖЕНИЯ БОТОВ =======
(сгенерировано автоматически, ручные изменения не нужны)

Bot1 SNIPER предлагает:
  - Изменений нет. Стратегия оптимальна.

Bot2 HARVESTER предлагает:
  - Корректор изменил: profit_target 0.13 -> 0.12
    Причина: осталось 7 дней, тета ускоряется
  - Ручных действий не требуется.

======= СТАТУС ВЫХОДНЫХ =======
Закрытие позиций: пятница 16:00 ET (23:00 МСК)
Брифинг перед понедельником: воскресенье 20:00 ET (03:00 МСК)
```

### Расписание отправки

| Время (МСК) | Время (ET) | Сообщение |
|---|---|---|
| 07:00 | 00:00 | Ежедневный отчёт (полный) |
| 10:00 | 03:00 | Старт золотого окна (если есть ночные новости) |
| 16:00 | 09:00 | Открытие рынка США (если риск не ЗЕЛЁНЫЙ) |
| 23:00 | 16:00 | Пятница: Итоги недели + Закрытие позиций |
| --- | Суббота | Выходные алерты (только при КРАСНЫЙ/ЧЁРНЫЙ) |
| 03:00 пн | 20:00 вс | Брифинг перед понедельником |

### Формат предложений по изменениям

Боты НЕ меняют стратегию сами — они присылают предложения в формате:

```
ПРЕДЛОЖЕНИЕ ПО СТРАТЕГИИ | Bot2 HARVESTER
Дата: 22.03.2026

ТЕКУЩЕЕ vs ПРЕДЛАГАЕМОЕ:
  profit_target: 0.13 -> 0.12
  Причина: Ускорение тета-распада (осталось 7 дней)

  WTI_MAX_ENTRY: $98 -> $97
  Причина: Средний WTI за 48ч = $97.5, снижаем риск

БЭКТЕСТ НА ДАННЫХ ЗА 48Ч:
  Текущие настройки: 2 сделки, +$16.16
  Предлагаемые: 2 сделки, +$18.42 (+14% улучшение)

СТАТУС: Применено корректором автоматически (в безопасных рамках)
Ручных действий не требуется.

Если не согласны, ответьте: /override profit_target 0.13
```

### Реализация

```python
# daily_report.py (общий для обоих ботов)

import json
from datetime import datetime
from telegram_notify import send_message

def generate_daily_report():
    """Generate and send daily analytics to Telegram."""
    # Load both bots' positions
    bot1_pos = load_positions("../10_oil_swing_bot/positions.json")
    bot2_pos = load_positions("../Oil_swing_bot2/positions.json")

    # Get news summary
    sentinel = NewsSentinel()
    news = sentinel.get_daily_summary()

    # Get corrector proposals
    bot2_proposals = load_corrector_proposals()

    # Format message
    msg = format_report(bot1_pos, bot2_pos, news, bot2_proposals)

    # Send to Telegram
    send_message(msg, parse_mode="HTML")

    # Save to file
    save_report_to_file(msg)
```

---

## 6. ПЛАН РЕАЛИЗАЦИИ

### Фаза 1: Momentum фильтр + Weekend блок (30 мин)

**Файлы для изменения:**

Bot 1 (10_oil_swing_bot):
- `config.py`: добавить `MOMENTUM_BLOCK = 2.0`, `MOMENTUM_WINDOW = 6`
- `strategy.py`: добавить `is_weekend_blocked()`, `check_momentum()`
- `main.py`: интегрировать новые проверки в `run_cycle()`

Bot 2 (Oil_swing_bot2):
- `config.py`: добавить `MOMENTUM_BLOCK = 2.0`, `MOMENTUM_WINDOW = 6`, изменить `WTI_MAX_ENTRY = 99`
- `strategy.py`: добавить `is_weekend_blocked()`, `check_momentum()`
- `main.py`: интегрировать новые проверки

### Фаза 2: News Sentinel (1-2 часа)

- Создать `shared/news_sentinel.py` (общий модуль)
- RSS парсинг + keyword scoring
- Интеграция в оба бота
- Тестирование на текущих новостях

### Фаза 3: Daily Report (1 час)

- Создать `shared/daily_report.py`
- Шаблон Telegram-сообщения
- Расписание отправки (cron или встроенный scheduler)
- Формат предложений по изменениям

### Фаза 4: Trump Monitor + Telegram Commands (по желанию)

- RSS-прокси для Truth Social
- Команды в Telegram: `/status`, `/override`, `/pause`, `/resume`

---

## 7. СВОДНАЯ ТАБЛИЦА ИЗМЕНЕНИЙ

### Bot 1 "SNIPER" ($100)

| Компонент | Текущее | Предлагается | Бэктест |
|---|---|---|---|
| Momentum фильтр | Нет | $2.0/6h | WR 71%->88%, DD -100% |
| Weekend блок | Нет | Пт 20 ET - Пн 09 ET | Защита от -65% гэпа |
| MAX_NO_ENTRY_PRICE | 0.26 | 0.22 | Меньше убыточных входов |
| STEP_COOLDOWN | 0 | 1800 (30 мин) | Защита от каскада |
| YES блок NO | Нет | **НЕ добавляем** | Бэктест: убивает 79% сделок |
| News Sentinel | Нет | risk_level -> size_mult | Защита от tail risk |
| Friday auto-close | Нет | 16:00 ET close all | -65% gap protection |

### Bot 2 "HARVESTER" ($105)

| Компонент | Текущее | Предлагается | Бэктест |
|---|---|---|---|
| Momentum фильтр | Нет | $2.0/6h | WR 60%->89%, P&L +$21 |
| Weekend блок | Нет | Пт 20 ET - Пн 09 ET | Защита от -59% гэпа |
| WTI_MAX_ENTRY | $98 | $99 | Больше входов в зону |
| PROFIT_TARGET | 0.13 | 0.13 (без изменений) | Бэктест: 10-20% не лучше |
| YES блок NO | Нет | **НЕ добавляем** | Бэктест: убивает бота |
| News Sentinel | Нет | risk_level -> size_mult | Защита от tail risk |
| Friday auto-close | Нет | 16:00 ET close all | -59% gap protection |

### Общие модули (новые)

| Модуль | Описание | Файл |
|---|---|---|
| News Sentinel | RSS + keyword scoring -> risk level | `shared/news_sentinel.py` |
| Daily Report | Ежедневная выжимка в Telegram | `shared/daily_report.py` |
| Weekend Manager | Пятничное закрытие + воскресный брифинг | Встроено в strategy.py |
| Momentum Tracker | 6-часовой буфер WTI для фильтра | Встроено в strategy.py |

---

## 8. ОТВЕТ НА ИСХОДНЫЙ ВОПРОС: YES > 80% БЛОК

**Математически обоснован, но БЭКТЕСТ ОПРОВЕРГАЕТ.**

Теоретически YES > 80% = опасная зона (EV отрицательный, Келли ~0). На практике:
- YES ВСЕГДА > 80% когда WTI > $97 (зона входа бота)
- Блок при 80% убивает 79% сделок (14 -> 3)
- Блок при 75% убивает ВСЕ сделки (14 -> 0)
- Самые прибыльные сделки бота были при YES = 84-85%

**Правильное решение — momentum фильтр**, который:
- Не блокирует прибыльные сделки на развороте
- Блокирует убыточные входы на растущем тренде
- Подтверждено бэктестом: WR 71% -> 88%, DD -> $0

---

## МЕТОДОЛОГИЯ

- **Данные:** 612 часовых точек из theta_calibration.json (22 дня торговли)
- **Бэктест:** Симуляция NO-свинговой торговли с разными фильтрами
- **Реальные сделки:** 14 сделок Bot1, 2 сделки Bot2
- **Weekend gaps:** 2 выходных (8 марта — Hormuz crisis, 15 марта — тихий)
- **Ограничения:**
  - Симуляция не учитывает slippage и ликвидность orderbook
  - YES+NO = 1.0 (упрощение, реальный spread ~0.5-1%)
  - Weekend gap данных мало (2 точки) — нужно больше истории
