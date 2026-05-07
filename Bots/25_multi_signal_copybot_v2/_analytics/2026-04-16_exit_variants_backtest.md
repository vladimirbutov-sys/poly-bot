================================================================================
## Сводка бэктеста exit-стратегий
================================================================================

Всего позиций: 235
Закрытых позиций: 207
  - Resolved (есть итог рынка): 69
  - Unresolved (нет данных): 137
  - Bad data (avg_entry > 1): 1

| Метрика                                       |     Реальный |    Вариант A |    Вариант B |    Вариант C |
|-----------------------------------------------|--------------|--------------|--------------|--------------|
| Суммарный PnL                                 |     $-453.99 |     $-453.99 |     $-590.63 |     $-453.99 |
| Продаж заблокировано                          |            — |            3 |          110 |            3 |
| Из них рынок потом WON                        |            — |            0 |            1 |            0 |
| Из них рынок потом LOST                       |            — |            0 |            2 |            0 |
| Из них unresolved                             |            — |            3 |          107 |            3 |
| Сэкономлено (blocked -> рынок won)            |          --- |        $0.00 |       +$1.82 |        $0.00 |
| Потеряно (blocked -> рынок lost -> $0)        |          --- |        $0.00 |      $138.47 |        $0.00 |
| Чистый эффект vs реальный                     |            — |        $0.00 |     $-136.65 |        $0.00 |


### Вариант A: детализация заблокированных продаж (3 шт.)

|   # | Рынок                                    | Outcome |  Entry |  Sell$ |  Shares | Denizz% |   PnL% |  WON? |   Дельта$ | Reason                                   |
|-----|------------------------------------------|---------|--------|--------|---------|---------|--------|-------|-----------|------------------------------------------|
|   1 | Israel x Hezbollah ceasefire by April    |      No |  0.718 |  0.558 |   39.96 |     18% | -22.3% |   ??? |       N/A | denizz_mirror_loss_18%                   |
|   2 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.415 |  114.86 |     23% | -39.9% |   ??? |       N/A | denizz_mirror_unk_23%                    |
|   3 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.486 |   86.31 |     22% | -29.6% |   ??? |       N/A | denizz_mirror_unk_22%                    |


### Вариант B: детализация заблокированных продаж (110 шт.)

|   # | Рынок                                    | Outcome |  Entry |  Sell$ |  Shares | Denizz% |   PnL% |  WON? |   Дельта$ | Reason                                   |
|-----|------------------------------------------|---------|--------|--------|---------|---------|--------|-------|-----------|------------------------------------------|
|   1 | Trump announces end of military operat   |     Yes |  0.240 |  0.220 |   43.75 |     N/A |  -8.3% |   ??? |       N/A | manual_sell_all                          |
|   2 | Israel strike on Yemen by April 30, 20   |     Yes |  0.730 |  0.680 |    6.58 |     N/A |  -6.8% |   ??? |       N/A | manual_sell_all                          |
|   3 | Israel strike on Yemen by April 30, 20   |     Yes |  0.630 |  0.560 |    5.00 |    100% | -11.1% |   ??? |       N/A | denizz_sell_detected                     |
|   4 | Will Mojtaba Khamenei be head of state   |     Yes |  0.517 |  0.510 |    5.00 |    100% |  -1.4% |   ??? |       N/A | denizz_sell_detected                     |
|   5 | Trump announces Hormuz deadline extens   |      No |  0.440 |  0.090 |    5.00 |     80% | -79.5% |   ??? |       N/A | stop_loss_80%                            |
|   6 | US x Iran ceasefire by April 7?          |      No |  0.680 |  0.667 |   48.04 |     23% |  -1.9% |    NO |   $-32.04 | Car_partial_23%                          |
|   7 | US x Iran ceasefire by April 7?          |      No |  0.680 |  0.650 |  163.73 |    100% |  -4.4% |    NO |  $-106.42 | Car_sell_detected_retry                  |
|   8 | Israeli forces cross the Litani River    |      No |  0.620 |  0.380 |  101.62 |    100% | -38.7% |   ??? |       N/A | denizz_full_exit                         |
|   9 | US x Iran ceasefire by April 15?         |     Yes |  0.975 |  0.963 |   49.24 |    100% |  -1.2% |   YES |    +$1.82 | Car_sell_detected                        |
|  10 | Israel strike on Yemen by April 30, 20   |      No |  0.890 |  0.760 |   15.74 |     N/A | -14.6% |   ??? |       N/A | reconciled_from_onchain_post_timeout     |
|  11 | Strait of Hormuz traffic returns to no   |     Yes |  0.460 |  0.250 |   59.97 |    100% | -45.7% |   ??? |       N/A | denizz_sell_detected                     |
|  12 | Will the United States send warships t   |     Yes |  0.350 |  0.240 |   47.15 |     N/A | -31.4% |   ??? |       N/A | manual_audit_dead_signal                 |
|  13 | Israel strike on Yemen by April 30, 20   |      No |  0.890 |  0.000 |    0.00 |     N/A | -100.0% |   ??? |       N/A | consolidation_merged_into_other_record   |
|  14 | Will the Iranian regime fall before 20   |      No |  0.820 |  0.780 |   73.18 |     N/A |  -4.9% |   ??? |       N/A | reconciled_from_onchain_post_timeout     |
|  15 | Iran x Israel/US conflict ends by Apri   |     Yes |  0.415 |  0.404 |  165.00 |     50% |  -2.6% |   ??? |       N/A | manual_50pct_follow_denizz               |
|  16 | Iran x Israel/US conflict ends by Apri   |     Yes |  0.415 |  0.311 |  155.50 |     N/A | -25.0% |   ??? |       N/A | reconciled_from_onchain_post_timeout     |
|  17 | Will Reza Pahlavi enter Iran by Decemb   |      No |  0.860 |  0.850 |   93.03 |     N/A |  -1.2% |   ??? |       N/A | reconciled_from_onchain_post_timeout     |
|  18 | Israel x Hezbollah ceasefire by April    |      No |  0.470 |  0.457 |  190.13 |     N/A |  -2.7% |   ??? |       N/A | manual_close_denizz_already_exited       |
|  19 | Trump announces end of military operat   |     Yes |  0.550 |  0.490 |  171.82 |     N/A | -10.9% |   ??? |       N/A | reconciled_from_onchain_post_timeout     |
|  20 | Will UAE strike Iran by April 30?        |     Yes |  0.430 |  0.100 |   69.77 |     77% | -76.7% |   ??? |       N/A | stop_loss_77%                            |
|  21 | Will UAE strike Iran by April 30?        |     Yes |  0.210 |  0.157 |   55.00 |     N/A | -25.1% |   ??? |       N/A | reconciled_from_onchain_post_timeout     |
|  22 | Iran x Israel/US conflict ends by Apri   |     Yes |  0.420 |  0.311 |  476.20 |     N/A | -26.0% |   ??? |       N/A | reconciled_from_onchain_post_timeout     |
|  23 | US-Iran nuclear deal by April 30?        |     Yes |  0.252 |  0.232 |   54.00 |     N/A |  -7.9% |   ??? |       N/A | cascade_exit_drift_fix                   |
|  24 | US-Iran nuclear deal by April 30?        |     Yes |  0.252 |  0.200 |  208.00 |     N/A | -20.6% |   ??? |       N/A | resting_order_filled_drift_fix           |
|  25 | US-Iran nuclear deal by April 30?        |     Yes |  0.252 |  0.187 |  154.67 |     N/A | -25.8% |   ??? |       N/A | reconciled_from_onchain_group            |
|  26 | Will the Iranian regime fall by June 3   |      No |  0.920 |  0.910 |   65.22 |     N/A |  -1.1% |   ??? |       N/A | reconciled_from_onchain_group            |
|  27 | Iran agrees to surrender enriched uran   |     Yes |  0.196 |  0.132 |  280.62 |    100% | -32.7% |   ??? |       N/A | denizz_big_dump_100%                     |
|  28 | Israel x Hezbollah ceasefire by April    |      No |  0.667 |  0.650 |  269.89 |     N/A |  -2.5% |   ??? |       N/A | manual_risk_reduction_hezbollah_concentration |
|  29 | Strait of Hormuz traffic returns to no   |     Yes |  0.260 |  0.250 |  297.74 |    100% |  -3.8% |   ??? |       N/A | denizz_sell_detected                     |
|  30 | Israel x Hezbollah ceasefire by April    |      No |  0.718 |  0.558 |   39.96 |     18% | -22.3% |   ??? |       N/A | denizz_mirror_loss_18%                   |
|  31 | Will Reza Pahlavi enter Iran by June 3   |      No |  0.940 |  0.920 |   63.83 |     N/A |  -2.1% |   ??? |       N/A | reconciled_from_onchain_group            |
|  32 | Will a Gulf State carry out military a   |     Yes |  0.170 |  0.058 |    8.48 |     66% | -65.9% |   ??? |       N/A | stop_loss_66%                            |
|  33 | Netanyahu out by end of 2026?            |     Yes |  0.380 |  0.000 |    2.00 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  34 | US x Iran meeting by April 10, 2026?     |     Yes |  0.375 |  0.374 |  146.67 |    100% |  -0.3% |   ??? |       N/A | denizz_full_exit                         |
|  35 | Strait of Hormuz traffic returns to no   |     Yes |  0.220 |  0.210 |  250.00 |    100% |  -4.5% |   ??? |       N/A | denizz_big_dump_100%                     |
|  36 | US x Iran meeting by April 10, 2026?     |     Yes |  0.260 |  0.210 |  115.39 |     94% | -19.2% |   ??? |       N/A | denizz_big_dump_94%                      |
|  37 | Iran x Israel/US conflict ends by Apri   |     Yes |  0.549 |  0.450 |  182.14 |     N/A | -18.1% |   ??? |       N/A | reconciled_from_onchain_group            |
|  38 | Iran x Israel/US conflict ends by Apri   |     Yes |  0.643 |  0.000 |  233.28 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  39 | Iran x Israel/US conflict ends by Apri   |     Yes |  0.700 |  0.680 |  142.85 |     N/A |  -2.9% |   ??? |       N/A | reconciled_from_onchain_group            |
|  40 | US-Iran nuclear deal by April 30?        |     Yes |  0.204 |  0.172 |  245.09 |     N/A | -15.6% |   ??? |       N/A | reconciled_from_onchain_group            |
|  41 | Israeli forces cross the Litani River    |      No |  0.680 |  0.380 |   73.52 |     N/A | -44.1% |   ??? |       N/A | reconciled_from_onchain_group            |
|  42 | Israel x Hezbollah ceasefire by June 3   |      No |  0.397 |  0.330 |    7.54 |     54% | -16.9% |   ??? |       N/A | denizz_mirror_loss_54%_partial           |
|  43 | Israel x Hezbollah ceasefire by June 3   |      No |  0.397 |  0.320 |   67.60 |     54% | -19.4% |   ??? |       N/A | denizz_mirror_loss_54%_retry             |
|  44 | Israel x Hezbollah ceasefire by June 3   |      No |  0.397 |  0.320 |   63.40 |    100% | -19.4% |   ??? |       N/A | denizz_big_dump_100%_retry               |
|  45 | US x Iran meeting by April 10, 2026?     |     Yes |  0.139 |  0.044 |  151.08 |     68% | -68.3% |   ??? |       N/A | stop_loss_68%                            |
|  46 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.415 |  114.86 |     23% | -39.9% |   ??? |       N/A | denizz_mirror_unk_23%                    |
|  47 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.486 |   86.31 |     22% | -29.6% |   ??? |       N/A | denizz_mirror_unk_22%                    |
|  48 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.490 |  289.07 |     N/A | -29.0% |   ??? |       N/A | manual_partial_50pct                     |
|  49 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.539 |  229.20 |     N/A | -21.9% |   ??? |       N/A | onchain_sync_down                        |
|  50 | US x Iran permanent peace deal by Apri   |      No |  0.745 |  0.000 |   59.03 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  51 | Israeli forces cross the Litani River    |      No |  0.690 |  0.650 |  142.00 |     N/A |  -5.8% |   ??? |       N/A | denizz_merge_exit                        |
|  52 | Iran leadership change by May 31?        |      No |  0.800 |  0.000 |   37.65 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  53 | Will Mojtaba Khamenei be head of state   |     Yes |  0.613 |  0.613 |    6.61 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  54 | Will Mojtaba Khamenei be head of state   |     Yes |  0.613 |  0.613 |   32.11 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  55 | Will Mojtaba Khamenei be head of state   |     Yes |  0.613 |  0.000 |   40.54 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  56 | Strait of Hormuz traffic returns to no   |     Yes |  0.231 |  0.210 |  176.98 |     N/A |  -9.3% |   ??? |       N/A | onchain_sync_down                        |
|  57 | Strait of Hormuz traffic returns to no   |     Yes |  0.231 |  0.160 |  707.12 |     N/A | -30.9% |   ??? |       N/A | reconciled_from_onchain_group            |
|  58 | Israel x Hezbollah ceasefire by April    |     Yes |  0.230 |  0.160 |  130.44 |    100% | -30.4% |   ??? |       N/A | denizz_big_dump_100%                     |
|  59 | Will the US x Iran ceasefire be extend   |     Yes |  0.650 |  0.350 |   91.47 |     46% | -46.2% |   ??? |       N/A | stop_loss_46%                            |
|  60 | Iran x Israel/US conflict ends by May    |      No |  0.260 |  0.260 |  177.86 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  61 | Iran x Israel/US conflict ends by May    |      No |  0.260 |  0.100 |   19.00 |     62% | -61.6% |   ??? |       N/A | stop_loss_62%_partial                    |
|  62 | Iran x Israel/US conflict ends by May    |      No |  0.260 |  0.090 |   14.68 |     65% | -65.4% |   ??? |       N/A | stop_loss_65%                            |
|  63 | Will the Kharg Island oil terminal be    |     Yes |  0.150 |  0.000 |    3.80 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  64 | Iran x Israel/US conflict ends by June   |      No |  0.120 |  0.040 |   74.37 |     67% | -66.7% |   ??? |       N/A | stop_loss_67%                            |
|  65 | Nothing Ever Happens: 2026               |     Yes |  0.530 |  0.000 |   33.00 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  66 | Iran x Israel/US conflict ends by Apri   |     Yes |  0.611 |  0.320 |  634.85 |     48% | -47.6% |   ??? |       N/A | stop_loss_48%                            |
|  67 | Iran x Israel/US conflict ends by Apri   |      No |  0.426 |  0.426 |   95.15 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  68 | Iran x Israel/US conflict ends by Apri   |      No |  0.426 |  0.426 |   23.94 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  69 | Strait of Hormuz traffic returns to no   |     Yes |  0.140 |  0.105 | 3380.95 |     N/A | -24.7% |   ??? |       N/A | reconciled_from_onchain_group            |
|  70 | Trump announces end of military operat   |      No |  0.580 |  0.000 |  207.26 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  71 | US x Iran permanent peace deal by Apri   |      No |  0.810 |  0.000 |  103.72 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  72 | Iran x Israel/US conflict ends by Apri   |      No |  0.499 |  0.000 |  273.61 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  73 | Iran leadership change by December 31?   |      No |  0.650 |  0.000 |   59.55 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  74 | Will the U.S. invade Iran before 2027?   |      No |  0.650 |  0.000 |   51.94 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  75 | Will the Iranian regime fall by June 3   |      No |  0.900 |  0.000 |  128.99 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  76 | US-Iran nuclear deal by April 30?        |     Yes |  0.140 |  0.000 |  281.73 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  77 | Iran agrees to surrender enriched uran   |     Yes |  0.216 |  0.089 |   70.76 |     N/A | -58.9% |   ??? |       N/A | onchain_sync_down                        |
|  78 | Iran agrees to surrender enriched uran   |     Yes |  0.216 |  0.089 |    5.72 |     N/A | -58.9% |   ??? |       N/A | onchain_sync_down                        |
|  79 | Iran agrees to surrender enriched uran   |     Yes |  0.216 |  0.089 |  134.75 |     N/A | -58.9% |   ??? |       N/A | onchain_sync_down                        |
|  80 | Iran agrees to surrender enriched uran   |     Yes |  0.216 |  0.089 |   26.10 |     N/A | -58.9% |   ??? |       N/A | onchain_sync_down                        |
|  81 | Iran agrees to surrender enriched uran   |     Yes |  0.216 |  0.089 |   37.27 |     N/A | -58.9% |   ??? |       N/A | onchain_sync_down                        |
|  82 | Iran agrees to surrender enriched uran   |     Yes |  0.216 |  0.000 |  235.12 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  83 | Iran agrees to end enrichment of urani   |     Yes |  0.155 |  0.079 |  137.53 |     N/A | -48.9% |   ??? |       N/A | onchain_sync_down                        |
|  84 | Iran agrees to end enrichment of urani   |     Yes |  0.155 |  0.155 |   90.11 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  85 | Will Trump agree to Iranian enrichment   |     Yes |  0.358 |  0.081 |   20.00 |     N/A | -77.4% |   ??? |       N/A | onchain_sync_down                        |
|  86 | Will Trump agree to Iranian enrichment   |     Yes |  0.358 |  0.081 |  259.80 |     N/A | -77.4% |   ??? |       N/A | onchain_sync_down                        |
|  87 | Will Trump agree to Iranian enrichment   |     Yes |  0.358 |  0.151 |   26.53 |     N/A | -57.7% |   ??? |       N/A | onchain_sync_down                        |
|  88 | Will Trump agree to Iranian enrichment   |     Yes |  0.358 |  0.270 |   26.52 |    100% | -24.5% |   ??? |       N/A | manual_100%_Trump_agree_enrichment       |
|  89 | Will Trump agree to Iranian enrichment   |     Yes |  0.358 |  0.254 |  278.35 |    100% | -29.0% |   ??? |       N/A | manual_100%_trump_agree_limit254         |
|  90 | Will Trump agree to Iranian enrichment   |     Yes |  0.358 |  0.260 |   89.63 |    100% | -27.3% |   ??? |       N/A | manual_100%_trump_enrichment_market      |
|  91 | Will Trump agree to Iranian enrichment   |     Yes |  0.358 |  0.240 |  134.10 |    100% | -32.9% |   ??? |       N/A | manual_100%_trump_enrichment_market_tail |
|  92 | Will Reza Pahlavi enter Iran by May 31   |      No |  0.954 |  0.954 |    1.03 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  93 | Will Reza Pahlavi enter Iran by May 31   |      No |  0.954 |  0.954 |    1.03 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  94 | US-Iran nuclear deal by April 30?        |     Yes |  0.222 |  0.151 |  244.26 |     N/A | -32.1% |   ??? |       N/A | onchain_sync_down                        |
|  95 | US-Iran nuclear deal by April 30?        |     Yes |  0.222 |  0.222 |  111.09 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
|  96 | Israel x Hezbollah ceasefire by April    |     Yes |  0.080 |  0.000 |  932.25 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
|  97 | Will the next diplomatic US-Iran meeti   |      No |  0.347 |  0.100 |   62.98 |     71% | -71.2% |   ??? |       N/A | stop_loss_71%                            |
|  98 | Will Trump endorse an Israeli Ceasefir   |      No |  0.720 |  0.670 |   89.59 |    100% |  -6.9% |   ??? |       N/A | denizz_loss_follow_100%                  |
|  99 | Israel x Hezbollah ceasefire by April    |      No |  0.954 |  0.461 |   59.51 |     52% | -51.7% |   ??? |       N/A | stop_loss_52%                            |
| 100 | Will Trump agree to unfreeze Iranian a   |      No |  0.562 |  0.460 |   93.86 |    100% | -18.2% |   ??? |       N/A | denizz_loss_follow_100%                  |
| 101 | US x Iran permanent peace deal by Apri   |     Yes |  0.220 |  0.210 |   78.77 |    100% |  -4.5% |   ??? |       N/A | manual_100%_us_iran_peace_april22_v2_market |
| 102 | Iran agrees to end enrichment of urani   |     Yes |  0.270 |  0.000 |  245.38 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
| 103 | Trump announces end of military operat   |     Yes |  0.240 |  0.000 |  380.96 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
| 104 | Will Israel conduct military action ag   |     Yes |  0.140 |  0.000 |  210.93 |     N/A | -100.0% |   ??? |       N/A | onchain_sync_disappeared                 |
| 105 | Israel x Hezbollah ceasefire by April    |     Yes |  0.709 |  0.709 |  110.12 |     N/A |  -0.0% |   ??? |       N/A | onchain_sync_down                        |
| 106 | Israel x Hezbollah ceasefire by April    |     Yes |  0.709 |  0.665 |  191.94 |     92% |  -6.2% |   ??? |       N/A | denizz_loss_follow_92%                   |
| 107 | Strait of Hormuz traffic returns to no   |     Yes |  0.260 |  0.240 |  210.18 |     87% |  -7.7% |   ??? |       N/A | denizz_loss_follow_87%                   |
| 108 | Strait of Hormuz traffic returns to no   |     Yes |  0.260 |  0.240 |   52.55 |     87% |  -7.7% |   ??? |       N/A | denizz_loss_follow_87%                   |
| 109 | Strait of Hormuz traffic returns to no   |     Yes |  0.260 |  0.240 |   13.14 |     87% |  -7.7% |   ??? |       N/A | denizz_loss_follow_87%                   |
| 110 | Strait of Hormuz traffic returns to no   |     Yes |  0.260 |  0.000 |    4.38 |     N/A | -100.0% |   ??? |       N/A | exit_skip_onchain_empty                  |


### Вариант C: детализация заблокированных продаж (3 шт.)

|   # | Рынок                                    | Outcome |  Entry |  Sell$ |  Shares | Denizz% |   PnL% |  WON? |   Дельта$ | Reason                                   |
|-----|------------------------------------------|---------|--------|--------|---------|---------|--------|-------|-----------|------------------------------------------|
|   1 | Israel x Hezbollah ceasefire by April    |      No |  0.718 |  0.558 |   39.96 |     18% | -22.3% |   ??? |       N/A | denizz_mirror_loss_18%                   |
|   2 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.415 |  114.86 |     23% | -39.9% |   ??? |       N/A | denizz_mirror_unk_23%                    |
|   3 | Israel x Hezbollah ceasefire by April    |      No |  0.690 |  0.486 |   86.31 |     22% | -29.6% |   ??? |       N/A | denizz_mirror_unk_22%                    |
