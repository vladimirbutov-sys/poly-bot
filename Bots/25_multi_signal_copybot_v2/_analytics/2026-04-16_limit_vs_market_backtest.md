
======================================================================
## Бэктест: Лимитные ордера vs Рыночные
======================================================================

### ПОКУПКИ (Entry)
Проанализировано: 157 позиций (из 235 — для 57 не удалось получить данные, 21 пропущено по фильтрам)

| Метрика | 30 мин окно | 60 мин окно |
|---------|-------------|-------------|
| Откат был (лимит лучше) | 117 из 154 (76%) | 122 из 157 (78%) |
| Откат не было (рынок лучше) | 37 из 154 (24%) | 35 из 157 (22%) |
| Средняя экономия (когда откат был) | 4.4¢ на share | 4.9¢ на share |
| Средняя экономия в % от цены входа | 10.3% | 11.4% |
| Суммарная экономия (USD на наших размерах) | $1156.50 | $1266.36 |
| Суммарная потеря (если лимит не заполнился) | $133.52 | $130.52 |

### ПРОДАЖИ (Exit)
Проанализировано: 91 продаж (пропущено не-торговых: 143, API ошибки: 0)

| Метрика | 30 мин окно | 60 мин окно |
|---------|-------------|-------------|
| Откат вверх был (лимит лучше) | 70 из 91 (77%) | 74 из 91 (81%) |
| Откат не было (рынок лучше) | 21 из 91 (23%) | 17 из 91 (19%) |
| Средний выигрыш (когда откат был) | 3.5¢ на share | 4.0¢ на share |
| Суммарный выигрыш | $313.16 | $442.49 |

### Итог
| Сценарий | Суммарный эффект |
|----------|-----------------|
| Лимит на вход (30м) | +$1022.98 |
| Лимит на вход (60м) | +$1135.84 |
| Лимит на выход (30м) | +$313.16 |
| Лимит на выход (60м) | +$442.49 |

### Детализация по покупкам
| Market | Entry | Min 30m | Min 60m | Savings 30m | Savings 60m | Our Size USD |
|--------|-------|---------|---------|-------------|-------------|--------------|
| Iran x Israel/US conflict ends by April 15? | 0.607 | 0.184 | 0.184 | +42.2¢ | +42.2¢ | $305.91 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.690 | 0.342 | 0.342 | +34.8¢ | +34.8¢ | $33.66 |
| Will Trump agree to Iranian enrichment of ura | 0.358 | 0.066 | 0.065 | +29.2¢ | +29.3¢ | $80.05 |
| US x Iran ceasefire by April 7? | 0.680 | 0.719 | 0.413 | --3.9¢ | +26.7¢ | $144.00 |
| Will UAE strike Iran by April 30? | 0.430 | 0.200 | 0.175 | +23.0¢ | +25.5¢ | $30.00 |
| Iran x Israel/US conflict ends by April 30? | 0.700 | 0.455 | 0.455 | +24.5¢ | +24.5¢ | $520.17 |
| Iran x Israel/US conflict ends by April 7? | 0.611 | 0.385 | 0.385 | +22.7¢ | +22.7¢ | $387.99 |
|  Iran agrees to end enrichment of uranium by  | 0.429 | 0.205 | 0.205 | +22.4¢ | +22.4¢ | $43.23 |
| Will Iran strike Iraq by April 30, 2026? | 0.737 | 0.580 | 0.540 | +15.7¢ | +19.7¢ | $84.18 |
| Iran x Israel/US conflict ends by April 30? | 0.700 | 0.535 | 0.535 | +16.5¢ | +16.5¢ | $30.00 |
| Will the next diplomatic US-Iran meeting be i | 0.347 | 0.185 | 0.185 | +16.2¢ | +16.2¢ | $21.89 |
| Iran x Israel/US conflict ends by April 15? | 0.558 | 0.398 | 0.398 | +16.0¢ | +16.0¢ | $94.01 |
| Nothing Ever Happens: 2026 | 0.530 | 0.410 | 0.375 | +12.0¢ | +15.5¢ | $33.00 |
| Iran agrees to surrender enriched uranium sto | 0.216 | 0.088 | 0.088 | +12.8¢ | +12.8¢ | $67.81 |
| US x Iran meeting by April 10, 2026? | 0.375 | 0.255 | 0.255 | +12.0¢ | +12.0¢ | $55.00 |
| Trump announces Hormuz deadline extension tod | 0.440 | 0.350 | 0.340 | +9.0¢ | +10.0¢ | $2.20 |
| Will UAE strike Iran by April 30? | 0.210 | 0.140 | 0.120 | +7.0¢ | +9.0¢ | $30.00 |
| Will Israel conduct military action against I | 0.830 | 0.740 | 0.740 | +9.0¢ | +9.0¢ | $27.37 |
| Israel x Hezbollah ceasefire by April 15, 202 | 0.954 | 0.944 | 0.868 | +1.0¢ | +8.6¢ | $56.77 |
| Iran agrees to end enrichment of uranium by A | 0.155 | 0.077 | 0.076 | +7.7¢ | +7.9¢ | $32.51 |
| US-Iran nuclear deal by April 30? | 0.222 | 0.150 | 0.150 | +7.2¢ | +7.2¢ | $40.44 |
| Israel x Hezbollah ceasefire by June 30, 2026 | 0.365 | 0.360 | 0.294 | +0.5¢ | +7.1¢ | $3.66 |
| Israel x Hezbollah ceasefire by June 30, 2026 | 0.366 | N/A | 0.296 | =N/A | +7.0¢ | $25.00 |
| Israeli forces cross the Litani River by June | 0.722 | 0.675 | 0.660 | +4.7¢ | +6.2¢ | $76.80 |
| US x Iran ceasefire by April 15? | 0.975 | 0.914 | 0.914 | +6.1¢ | +6.1¢ | $48.01 |
| Iran leadership change by December 31? | 0.540 | 0.480 | 0.480 | +6.0¢ | +6.0¢ | $2.70 |
| Iran x Israel/US conflict ends by April 7? | 0.315 | 0.265 | 0.258 | +5.0¢ | +5.7¢ | $1.96 |
| Will the U.S. invade Iran before 2027? | 0.650 | 0.595 | 0.595 | +5.5¢ | +5.5¢ | $33.76 |
| Iran x Israel/US conflict ends by April 7? | 0.194 | 0.142 | 0.142 | +5.2¢ | +5.2¢ | $150.00 |
| Israel strike on Yemen by June 30, 2026? | 0.610 | 0.560 | 0.560 | +5.0¢ | +5.0¢ | $6.14 |
| Iran x Israel/US conflict ends by April 15? | 0.533 | 0.488 | 0.487 | +4.5¢ | +4.6¢ | $46.59 |
| Will Trump endorse an Israeli Ceasefire in Le | 0.720 | 0.675 | 0.675 | +4.5¢ | +4.5¢ | $64.50 |
| Israel x Hamas Ceasefire Phase II by June 30? | 0.260 | 0.215 | 0.215 | +4.5¢ | +4.5¢ | $17.91 |
| Iran leadership change by December 31? | 0.660 | 0.615 | 0.615 | +4.5¢ | +4.5¢ | $39.30 |
| Iran x Israel/US conflict ends by April 30? | 0.499 | 0.465 | 0.455 | +3.4¢ | +4.4¢ | $136.58 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.470 | 0.433 | 0.433 | +3.7¢ | +3.7¢ | $96.74 |
| Iran agrees to surrender enriched uranium sto | 0.271 | 0.235 | 0.235 | +3.6¢ | +3.6¢ | $30.37 |
| Iran agrees to surrender enriched uranium sto | 0.278 | 0.242 | 0.242 | +3.6¢ | +3.6¢ | $123.59 |
| US x Iran meeting by April 10, 2026? | 0.260 | 0.253 | 0.225 | +0.8¢ | +3.6¢ | $30.00 |
| Iran x Israel/US conflict ends by April 30? | 0.380 | 0.345 | 0.345 | +3.5¢ | +3.5¢ | $143.38 |
| Israeli forces cross the Litani River by June | 0.620 | 0.585 | 0.585 | +3.5¢ | +3.5¢ | $63.00 |
| Trump announces end of military operations ag | 0.240 | 0.205 | 0.205 | +3.5¢ | +3.5¢ | $91.43 |
| Will the U.S. invade Iran before 2027? | 0.690 | 0.680 | 0.655 | +1.0¢ | +3.5¢ | $85.50 |
| Will Reza Pahlavi enter Iran by June 30? | 0.940 | 0.905 | 0.905 | +3.5¢ | +3.5¢ | $60.00 |
| Iran x Israel/US conflict ends by April 7? | 0.566 | 0.532 | 0.532 | +3.4¢ | +3.4¢ | $88.94 |
| Will Trump agree to unfreeze Iranian assets i | 0.562 | 0.530 | 0.530 | +3.2¢ | +3.2¢ | $52.75 |
| Israel x Hezbollah ceasefire by June 30, 2026 | 0.382 | 0.350 | 0.350 | +3.2¢ | +3.2¢ | $55.00 |
| Trump announces end of military operations ag | 0.170 | 0.155 | 0.140 | +1.5¢ | +3.0¢ | $35.32 |
| US x Iran permanent peace deal by April 30, 2 | 0.383 | 0.355 | 0.355 | +2.8¢ | +2.8¢ | $141.01 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.718 | 0.699 | 0.691 | +1.9¢ | +2.7¢ | $160.01 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.718 | 0.699 | 0.691 | +1.9¢ | +2.7¢ | $20.00 |
| Iran x Israel/US conflict ends by April 15? | 0.538 | 0.511 | 0.511 | +2.7¢ | +2.7¢ | $20.79 |
| Trump announces end of military operations ag | 0.520 | 0.495 | 0.495 | +2.5¢ | +2.5¢ | $31.50 |
| Israeli forces cross the Litani River by June | 0.680 | 0.655 | 0.655 | +2.5¢ | +2.5¢ | $49.99 |
| Will Israel conduct military action against I | 0.140 | 0.125 | 0.115 | +1.5¢ | +2.5¢ | $29.53 |
| Will Donald Trump announce that the United St | 0.554 | 0.530 | 0.530 | +2.4¢ | +2.4¢ | $45.93 |
| Will a Gulf State carry out military action a | 0.170 | 0.149 | 0.149 | +2.1¢ | +2.1¢ | $1.44 |
| Iran x Israel/US conflict ends by April 7? | 0.357 | 0.337 | 0.337 | +2.0¢ | +2.0¢ | $3.93 |
| Will Trump agree to unfreeze Iranian assets i | 0.580 | 0.560 | 0.560 | +2.0¢ | +2.0¢ | $30.00 |
| Strait of Hormuz traffic returns to normal by | 0.140 | 0.120 | 0.120 | +2.0¢ | +2.0¢ | $473.33 |
| US x Iran permanent peace deal by April 22, 2 | 0.135 | 0.125 | 0.115 | +1.0¢ | +2.0¢ | $50.25 |
| US x Iran ceasefire by June 30? | 0.593 | 0.575 | 0.575 | +1.8¢ | +1.8¢ | $30.61 |
| Israel x Hezbollah ceasefire by April 15, 202 | 0.947 | 0.930 | 0.930 | +1.7¢ | +1.7¢ | $113.91 |
| Strait of Hormuz traffic returns to normal by | 0.231 | 0.215 | 0.215 | +1.6¢ | +1.6¢ | $163.69 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.492 | 0.477 | 0.477 | +1.5¢ | +1.5¢ | $137.50 |
| Israel strike on Yemen by April 30, 2026? | 0.730 | 0.715 | 0.715 | +1.5¢ | +1.5¢ | $4.80 |
| Trump announces end of military operations ag | 0.140 | 0.125 | 0.125 | +1.5¢ | +1.5¢ | $2.63 |
| Trump announces end of military operations ag | 0.590 | 0.575 | 0.575 | +1.5¢ | +1.5¢ | $31.50 |
| Israel strike on Yemen by April 30, 2026? | 0.890 | 0.875 | 0.875 | +1.5¢ | +1.5¢ | $6.01 |
| Israel x Hezbollah ceasefire by April 15, 202 | 0.230 | 0.215 | 0.215 | +1.5¢ | +1.5¢ | $30.00 |
| Will the U.S. invade Iran before 2027? | 0.650 | 0.635 | 0.635 | +1.5¢ | +1.5¢ | $33.76 |
| Will the Iranian regime fall by June 30? | 0.900 | 0.895 | 0.885 | +0.5¢ | +1.5¢ | $116.09 |
| US x Iran permanent peace deal by April 22, 2 | 0.220 | 0.215 | 0.205 | +0.5¢ | +1.5¢ | $17.33 |
| Strait of Hormuz traffic returns to normal by | 0.260 | 0.255 | 0.245 | +0.5¢ | +1.5¢ | $72.86 |
| Israel x Hezbollah ceasefire by April 15, 202 | 0.080 | 0.065 | 0.065 | +1.5¢ | +1.5¢ | $74.58 |
| Iran leadership change by December 31? | 0.650 | 0.635 | 0.635 | +1.5¢ | +1.5¢ | $38.70 |
| Iran agrees to surrender enriched uranium sto | 0.196 | 0.182 | 0.182 | +1.4¢ | +1.4¢ | $55.00 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.709 | N/A | 0.696 | =N/A | +1.3¢ | $58.03 |
| US-Iran nuclear deal by April 30? | 0.140 | 0.129 | 0.129 | +1.1¢ | +1.1¢ | $39.44 |
| Will Reza Pahlavi enter Iran by May 31? | 0.954 | 0.944 | 0.943 | +1.1¢ | +1.1¢ | $0.00 |
| Israel x Hezbollah ceasefire by June 30, 2026 | 0.397 | 0.386 | 0.386 | +1.1¢ | +1.1¢ | $55.00 |
| Israel strike on Yemen by April 30, 2026? | 0.890 | 0.885 | 0.880 | +0.5¢ | +1.0¢ | $14.01 |
| Will the U.S. invade Iran before 2027? | 0.700 | 0.690 | 0.690 | +1.0¢ | +1.0¢ | $19.50 |
| Will UAE strike Iran by April 30? | 0.630 | 0.640 | 0.620 | --1.0¢ | +1.0¢ | $94.50 |
| Iran leadership change by May 31? | 0.800 | 0.790 | 0.790 | +1.0¢ | +1.0¢ | $30.12 |
| Israeli forces cross the Litani River by June | 0.690 | 0.685 | 0.680 | +0.5¢ | +1.0¢ | $97.98 |
| Will Mojtaba Khamenei be head of state in Ira | 0.613 | 0.603 | 0.603 | +1.0¢ | +1.0¢ | $24.85 |
| Iran leadership change by December 31? | 0.614 | 0.605 | 0.605 | +0.9¢ | +0.9¢ | $8.50 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.676 | 0.667 | 0.667 | +0.9¢ | +0.9¢ | $180.01 |
| Israel x Hezbollah ceasefire by June 30, 2026 | 0.670 | 0.666 | 0.661 | +0.4¢ | +0.8¢ | $24.99 |
| US x Iran permanent peace deal by April 30, 2 | 0.242 | 0.235 | 0.235 | +0.7¢ | +0.7¢ | $48.40 |
| US-Iran nuclear deal by April 30? | 0.252 | 0.245 | 0.245 | +0.7¢ | +0.7¢ | $38.98 |
| US x Iran meeting by April 10, 2026? | 0.139 | 0.133 | 0.133 | +0.7¢ | +0.7¢ | $21.00 |
| Iran agrees to end enrichment of uranium by A | 0.270 | 0.264 | 0.264 | +0.7¢ | +0.7¢ | $66.25 |
| Trump announces end of military operations ag | 0.948 | 0.943 | 0.943 | +0.5¢ | +0.5¢ | $102.39 |
| Will the US x Iran ceasefire be extended by A | 0.650 | 0.645 | 0.645 | +0.5¢ | +0.5¢ | $59.46 |
| US-Iran nuclear deal by June 30? | 0.610 | 0.605 | 0.605 | +0.5¢ | +0.5¢ | $112.04 |
| Trump announces end of military operations ag | 0.240 | 0.235 | 0.235 | +0.5¢ | +0.5¢ | $10.50 |
| Israel strike on Yemen by April 30, 2026? | 0.630 | 0.625 | 0.625 | +0.5¢ | +0.5¢ | $3.15 |
| Trump announces Hormuz deadline extension tod | 0.510 | 0.505 | 0.505 | +0.5¢ | +0.5¢ | $5.40 |
| Will the United States send warships through  | 0.350 | 0.355 | 0.345 | --0.5¢ | +0.5¢ | $20.00 |
| Will the Iranian regime fall before 2027? | 0.820 | 0.815 | 0.815 | +0.5¢ | +0.5¢ | $60.01 |
| Will Reza Pahlavi enter Iran by December 31? | 0.860 | 0.855 | 0.855 | +0.5¢ | +0.5¢ | $80.01 |
| Trump announces end of military operations ag | 0.550 | 0.545 | 0.545 | +0.5¢ | +0.5¢ | $94.50 |
| Will the Iranian regime fall by June 30? | 0.920 | 0.915 | 0.915 | +0.5¢ | +0.5¢ | $60.00 |
| Will the Iranian regime fall before 2027? | 0.790 | 0.785 | 0.785 | +0.5¢ | +0.5¢ | $160.01 |
| Will UAE strike Iran by April 30? | 0.660 | 0.655 | 0.655 | +0.5¢ | +0.5¢ | $94.51 |
| Strait of Hormuz traffic returns to normal by | 0.260 | 0.255 | 0.255 | +0.5¢ | +0.5¢ | $77.41 |
| Will Reza Pahlavi enter Iran by December 31? | 0.840 | 0.835 | 0.835 | +0.5¢ | +0.5¢ | $80.00 |
| Israel strike on Yemen by May 31, 2026? | 0.610 | 0.605 | 0.605 | +0.5¢ | +0.5¢ | $27.00 |
| Strait of Hormuz traffic returns to normal by | 0.220 | 0.215 | 0.215 | +0.5¢ | +0.5¢ | $55.00 |
| Iran x Israel/US conflict ends by April 15? | 0.643 | 0.640 | 0.638 | +0.3¢ | +0.5¢ | $150.00 |
| Iran x Israel/US conflict ends by April 30? | 0.700 | 0.695 | 0.695 | +0.5¢ | +0.5¢ | $100.00 |
| Strait of Hormuz traffic returns to normal by | 0.190 | 0.185 | 0.185 | +0.5¢ | +0.5¢ | $90.00 |
| Iran leadership change by June 30? | 0.760 | 0.755 | 0.755 | +0.5¢ | +0.5¢ | $44.00 |
| Will Trump agree to Iranian transit fees in t | 0.900 | 0.895 | 0.895 | +0.5¢ | +0.5¢ | $25.97 |
| US x Iran permanent peace deal by May 31, 202 | 0.390 | 0.385 | 0.385 | +0.5¢ | +0.5¢ | $112.14 |
| Strait of Hormuz traffic returns to normal by | 0.240 | 0.235 | 0.235 | +0.5¢ | +0.5¢ | $21.76 |
| US obtains Iranian enriched uranium by May 31 | 0.800 | 0.795 | 0.795 | +0.5¢ | +0.5¢ | $100.00 |
| Iran x Israel/US conflict ends by April 7? | 0.549 | 0.548 | 0.546 | +0.1¢ | +0.3¢ | $99.99 |
| US-Iran nuclear deal by April 30? | 0.204 | 0.202 | 0.201 | +0.2¢ | +0.3¢ | $50.00 |
| Will Mojtaba Khamenei be head of state in Ira | 0.589 | 0.587 | 0.587 | +0.2¢ | +0.2¢ | $2.94 |
| Will Trump agree to Iranian enrichment of ura | 0.283 | 0.285 | 0.282 | --0.3¢ | =0.1¢ | $144.22 |
| US x Iran permanent peace deal by April 30, 2 | 0.745 | N/A | 0.745 | =N/A | =0.0¢ | $44.00 |
| Will Mojtaba Khamenei be head of state in Ira | 0.517 | 0.525 | 0.517 | --0.8¢ | =0.0¢ | $2.58 |
| Netanyahu out by end of 2026? | 0.380 | 0.385 | 0.380 | --0.5¢ | =0.0¢ | $0.76 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.667 | 0.667 | 0.667 | =-0.0¢ | =-0.0¢ | $180.00 |
| US-Iran nuclear deal by April 30? | 0.370 | 0.376 | 0.372 | --0.6¢ | --0.2¢ | $116.41 |
| Israel strike on Yemen by June 30, 2026? | 0.520 | 0.525 | 0.525 | --0.5¢ | --0.5¢ | $67.20 |
| US x Iran ceasefire by April 30? | 0.257 | 0.265 | 0.265 | --0.8¢ | --0.8¢ | $80.00 |
| US x Iran permanent peace deal by April 22, 2 | 0.196 | 0.205 | 0.205 | --0.9¢ | --0.9¢ | $158.70 |
| Will the United States send warships through  | 0.826 | 0.835 | 0.835 | --0.9¢ | --0.9¢ | $84.01 |
| US obtains Iranian enriched uranium by May 31 | 0.805 | 0.815 | 0.815 | --1.0¢ | --1.0¢ | $200.14 |
| Will the U.S. invade Iran before 2027? | 0.422 | 0.435 | 0.435 | --1.3¢ | --1.3¢ | $75.01 |
| Iran agrees to unrestricted shipping through  | 0.322 | 0.335 | 0.335 | --1.3¢ | --1.3¢ | $36.07 |
| Will Iran conduct a military action against I | 0.986 | 1.000 | 1.000 | --1.4¢ | --1.4¢ | $50.00 |
| Strait of Hormuz traffic returns to normal by | 0.460 | 0.475 | 0.475 | --1.5¢ | --1.5¢ | $27.59 |
| Iran x Israel/US conflict ends by April 7? | 0.420 | 0.435 | 0.435 | --1.6¢ | --1.6¢ | $200.00 |
| US x Iran ceasefire by December 31? | 0.800 | 0.820 | 0.820 | --2.0¢ | --2.0¢ | $36.00 |
| Trump announces end of military operations ag | 0.510 | 0.535 | 0.535 | --2.5¢ | --2.5¢ | $85.50 |
| Will Iran conduct a military action against I | 0.909 | 0.939 | 0.939 | --2.9¢ | --2.9¢ | $15.01 |
| Trump announces end of military operations ag | 0.500 | 0.535 | 0.535 | --3.5¢ | --3.5¢ | $94.50 |
| Will Iran conduct a military action against I | 0.810 | 0.855 | 0.855 | --4.4¢ | --4.4¢ | $12.00 |
| Iran x Israel/US conflict ends by May 15? | 0.260 | 0.310 | 0.305 | --5.0¢ | --4.5¢ | $8.76 |
| US x Iran permanent peace deal by April 30, 2 | 0.810 | 0.855 | 0.855 | --4.5¢ | --4.5¢ | $84.00 |
| Israel x Hezbollah ceasefire by April 30, 202 | 0.436 | 0.482 | 0.482 | --4.6¢ | --4.6¢ | $35.00 |
| Will the Kharg Island oil terminal be hit by  | 0.150 | 0.205 | 0.205 | --5.5¢ | --5.5¢ | $1.50 |
| US x Iran permanent peace deal by April 30, 2 | 0.810 | 0.875 | 0.875 | --6.5¢ | --6.5¢ | $84.01 |
| Will Iran conduct a military action against I | 0.780 | 0.855 | 0.855 | --7.5¢ | --7.5¢ | $24.00 |
| Will Iran conduct a military action against I | 0.779 | 0.855 | 0.855 | --7.6¢ | --7.6¢ | $16.00 |
| Iran x Israel/US conflict ends by April 7? | 0.415 | 0.498 | 0.498 | --8.4¢ | --8.4¢ | $63.80 |
| Iran x Israel/US conflict ends by April 30? | 0.426 | 0.530 | 0.525 | --10.4¢ | --9.9¢ | $33.85 |
| Iran x Israel/US conflict ends by June 30? | 0.120 | 0.225 | 0.225 | --10.5¢ | --10.5¢ | $175.00 |
| Israel strike on Yemen by June 30, 2026? | 0.537 | 0.695 | 0.680 | --15.8¢ | --14.3¢ | $79.48 |
| Trump announces end of military operations ag | 0.580 | 0.745 | 0.745 | --16.5¢ | --16.5¢ | $120.21 |
| Trump announces end of military operations ag | 0.580 | 0.785 | 0.775 | --20.5¢ | --19.5¢ | $180.00 |
| Will the US x Iran ceasefire be extended by A | 0.005 | 0.685 | 0.685 | --68.0¢ | --68.0¢ | $0.78 |

### Детализация по продажам
| Market | Sell Price | Max 30m | Max 60m | Improv 30m | Improv 60m | Shares | Reason |
|--------|-----------|---------|---------|------------|------------|--------|--------|
| Israel x Hezbollah ceasefire by April 15 | 0.461 | 0.660 | 0.680 | 19.9¢ | 21.9¢ | 59.5 | stop_loss_52% |
| US x Iran meeting by April 10, 2026? | 0.374 | 0.581 | 0.581 | 20.7¢ | 20.7¢ | 146.7 | denizz_full_exit |
| Iran x Israel/US conflict ends by April  | 0.270 | 0.340 | 0.465 | 7.0¢ | 19.5¢ | 773.2 | denizz_sell_detected |
| Israeli forces cross the Litani River by | 0.380 | 0.550 | 0.550 | 17.0¢ | 17.0¢ | 101.6 | denizz_full_exit |
| Israel x Hezbollah ceasefire by April 30 | 0.415 | 0.560 | 0.560 | 14.5¢ | 14.5¢ | 114.9 | denizz_mirror_unk_23% |
| Will Trump agree to unfreeze Iranian ass | 0.460 | 0.590 | 0.595 | 13.0¢ | 13.5¢ | 93.9 | denizz_loss_follow_100% |
| Trump announces end of military operatio | 0.250 | 0.340 | 0.355 | 9.0¢ | 10.5¢ | 18.8 | Car_sell_detected |
| Will Iran conduct a military action agai | 0.826 | 0.857 | 0.912 | 3.1¢ | 8.7¢ | 14.8 | Car_sell_detected |
| Iran x Israel/US conflict ends by April  | 0.320 | 0.389 | 0.406 | 6.9¢ | 8.6¢ | 634.8 | stop_loss_48% |
| Will the United States send warships thr | 0.880 | 0.940 | 0.960 | 6.0¢ | 8.0¢ | 101.8 | denizz_big_dump_100% |
| Will UAE strike Iran by April 30? | 0.100 | 0.130 | 0.175 | 3.0¢ | 7.5¢ | 69.8 | stop_loss_77% |
| Israel x Hezbollah ceasefire by April 30 | 0.486 | 0.560 | 0.560 | 7.4¢ | 7.4¢ | 86.3 | denizz_mirror_unk_22% |
| Will UAE strike Iran by April 30? | 0.750 | 0.805 | 0.805 | 5.5¢ | 5.5¢ | 35.1 | denizz_full_exit |
| Israel x Hezbollah ceasefire by June 30, | 0.320 | 0.371 | 0.371 | 5.1¢ | 5.1¢ | 67.6 | denizz_mirror_loss_54%_retry |
| Israel x Hezbollah ceasefire by June 30, | 0.320 | 0.371 | 0.371 | 5.1¢ | 5.1¢ | 63.4 | denizz_big_dump_100%_retry |
| Israel x Hezbollah ceasefire by April 30 | 0.867 | 0.880 | 0.917 | 1.3¢ | 5.0¢ | 80.3 | denizz_sell_detected |
| Israel announces suspension of Lebanon o | 0.220 | 0.270 | 0.270 | 5.0¢ | 5.0¢ | 241.0 | denizz_loss_follow_73% |
| Will Iran conduct a military action agai | 0.911 | 0.958 | 0.960 | 4.6¢ | 4.8¢ | 16.5 | Car_sell_detected |
| Iran x Israel/US conflict ends by April  | 0.680 | 0.725 | 0.725 | 4.5¢ | 4.5¢ | 377.3 | denizz_sell_detected |
| Will Trump endorse an Israeli Ceasefire  | 0.670 | 0.700 | 0.715 | 3.0¢ | 4.5¢ | 89.6 | denizz_loss_follow_100% |
| Israel x Hezbollah ceasefire by April 30 | 0.701 | 0.746 | 0.746 | 4.5¢ | 4.5¢ | 9.1 | denizz_follow_19%_sell25% |
| Israel x Hezbollah ceasefire by April 30 | 0.703 | 0.746 | 0.746 | 4.3¢ | 4.3¢ | 27.4 | denizz_follow_100%_sell100% |
| Will Iran conduct a military action agai | 0.870 | 0.912 | 0.912 | 4.2¢ | 4.2¢ | 20.5 | Car_sell_detected |
| Will Iran conduct a military action agai | 0.871 | 0.912 | 0.912 | 4.1¢ | 4.1¢ | 30.8 | Car_sell_detected |
| Israel x Hezbollah ceasefire by June 30, | 0.330 | 0.371 | 0.371 | 4.1¢ | 4.1¢ | 7.5 | denizz_mirror_loss_54%_partial |
| Israel x Hezbollah ceasefire by April 30 | 0.690 | 0.725 | 0.730 | 3.5¢ | 4.0¢ | 48.1 | denizz_partial_18% |
| Israel x Hezbollah ceasefire by April 30 | 0.558 | 0.552 | 0.595 | -0.6¢ | 3.6¢ | 40.0 | denizz_mirror_loss_18% |
| Will the US x Iran ceasefire be extended | 0.350 | 0.385 | 0.385 | 3.5¢ | 3.5¢ | 91.5 | stop_loss_46% |
| Israel x Hezbollah ceasefire by April 30 | 0.715 | 0.710 | 0.746 | -0.5¢ | 3.1¢ | 12.2 | denizz_follow_19%_sell25% |
| US x Iran ceasefire by April 15? | 0.963 | 0.993 | 0.993 | 3.0¢ | 3.0¢ | 49.2 | Car_sell_detected |
| Will UAE strike Iran by April 30? | 0.720 | 0.745 | 0.750 | 2.5¢ | 3.0¢ | 96.0 | denizz_partial_73% |
| Israel x Hezbollah ceasefire by April 30 | 0.703 | 0.725 | 0.730 | 2.2¢ | 2.7¢ | 218.2 | denizz_sell_detected |
| Will UAE strike Iran by April 30? | 0.720 | 0.735 | 0.745 | 1.5¢ | 2.5¢ | 3.8 | denizz_partial_3% |
| Will UAE strike Iran by April 30? | 0.720 | 0.735 | 0.745 | 1.5¢ | 2.5¢ | 6.8 | denizz_partial_5% |
| Will UAE strike Iran by April 30? | 0.720 | 0.735 | 0.745 | 1.5¢ | 2.5¢ | 1.5 | denizz_partial_1% |
| Trump announces end of military operatio | 0.530 | 0.555 | 0.555 | 2.5¢ | 2.5¢ | 189.0 | denizz_big_dump_100% |
| Trump announces end of military operatio | 0.530 | 0.555 | 0.555 | 2.5¢ | 2.5¢ | 167.7 | denizz_big_dump_100% |
| US x Iran ceasefire by April 30? | 0.280 | 0.300 | 0.305 | 2.0¢ | 2.5¢ | 311.1 | Car_sell_detected |
| US x Iran meeting by April 10, 2026? | 0.044 | 0.069 | 0.069 | 2.5¢ | 2.5¢ | 151.1 | stop_loss_68% |
| US x Iran meeting by April 10, 2026? | 0.210 | 0.231 | 0.231 | 2.1¢ | 2.1¢ | 115.4 | denizz_big_dump_94% |
| Iran x Israel/US conflict ends by April  | 0.790 | 0.807 | 0.810 | 1.7¢ | 2.0¢ | 29.5 | denizz_follow_10%_sell25%_retr |
| Trump announces Hormuz deadline extensio | 0.600 | 0.575 | 0.620 | -2.5¢ | 2.0¢ | 10.6 | Car_sell_detected |
| Israel announces suspension of Lebanon o | 0.250 | 0.270 | 0.270 | 2.0¢ | 2.0¢ | 80.3 | denizz_loss_follow_93% |
| Iran x Israel/US conflict ends by April  | 0.754 | 0.771 | 0.771 | 1.7¢ | 1.7¢ | 39.3 | denizz_follow_15%_sell25% |
| Iran x Israel/US conflict ends by April  | 0.627 | 0.643 | 0.643 | 1.6¢ | 1.6¢ | 504.1 | denizz_big_dump_100% |
| Will Mojtaba Khamenei be head of state i | 0.510 | 0.526 | 0.526 | 1.6¢ | 1.6¢ | 5.0 | denizz_sell_detected |
| Strait of Hormuz traffic returns to norm | 0.250 | 0.265 | 0.265 | 1.5¢ | 1.5¢ | 60.0 | denizz_sell_detected |
| Will UAE strike Iran by April 30? | 0.650 | 0.665 | 0.665 | 1.5¢ | 1.5¢ | 46.2 | denizz_partial_31% |
| Will UAE strike Iran by April 30? | 0.650 | 0.665 | 0.665 | 1.5¢ | 1.5¢ | 103.8 | denizz_sell_detected |
| Strait of Hormuz traffic returns to norm | 0.250 | 0.265 | 0.265 | 1.5¢ | 1.5¢ | 297.7 | denizz_sell_detected |
| Strait of Hormuz traffic returns to norm | 0.210 | 0.215 | 0.225 | 0.5¢ | 1.5¢ | 250.0 | denizz_big_dump_100% |
| Iran agrees to end enrichment of uranium | 0.328 | 0.341 | 0.341 | 1.3¢ | 1.3¢ | 105.1 | denizz_follow_44%_sell50% |
| Will a Gulf State carry out military act | 0.058 | 0.071 | 0.071 | 1.3¢ | 1.3¢ | 8.5 | stop_loss_66% |
| Israel x Hezbollah ceasefire by June 30, | 0.380 | 0.388 | 0.393 | 0.8¢ | 1.3¢ | 20.9 | denizz_mirror_unk_29%_retry |
| Israel x Hezbollah ceasefire by June 30, | 0.380 | 0.388 | 0.393 | 0.8¢ | 1.3¢ | 20.9 | denizz_mirror_unk_29%_retry |
| Israel x Hezbollah ceasefire by June 30, | 0.380 | 0.388 | 0.393 | 0.8¢ | 1.3¢ | 20.9 | denizz_mirror_unk_29%_retry |
| Israel x Hezbollah ceasefire by June 30, | 0.380 | 0.388 | 0.393 | 0.8¢ | 1.3¢ | 2.9 | denizz_mirror_unk_29%_retry |
| Israel x Hezbollah ceasefire by June 30, | 0.380 | 0.388 | 0.393 | 0.8¢ | 1.3¢ | 2.9 | denizz_mirror_unk_29%_retry |
| Iran x Israel/US conflict ends by May 15 | 0.090 | 0.095 | 0.100 | 0.5¢ | 1.0¢ | 14.7 | stop_loss_65% |
| Will the Kharg Island oil terminal be hi | 0.210 | 0.220 | 0.220 | 1.0¢ | 1.0¢ | 6.2 | denizz_mirror_unk_62% |
| Israel x Hezbollah ceasefire by June 30, | 0.530 | 0.536 | 0.536 | 0.6¢ | 0.6¢ | 144.0 | denizz_follow_100%_sell100%_re |
| US x Iran ceasefire by December 31? | 0.991 | 0.988 | 0.996 | -0.3¢ | 0.5¢ | 45.0 | price_target_90c |
| Will the Iranian regime fall before 2027 | 0.790 | 0.795 | 0.795 | 0.5¢ | 0.5¢ | 202.5 | denizz_big_dump_100% |
| Israel x Hezbollah ceasefire by April 15 | 0.160 | 0.165 | 0.165 | 0.5¢ | 0.5¢ | 130.4 | denizz_big_dump_100% |
| Iran agrees to surrender enriched uraniu | 0.440 | 0.445 | 0.445 | 0.5¢ | 0.5¢ | 56.0 | denizz_follow_49%_sell50% |
| Strait of Hormuz traffic returns to norm | 0.240 | 0.245 | 0.245 | 0.5¢ | 0.5¢ | 90.7 | denizz_loss_follow_100% |
| Strait of Hormuz traffic returns to norm | 0.240 | 0.245 | 0.245 | 0.5¢ | 0.5¢ | 210.2 | denizz_loss_follow_87% |
| Strait of Hormuz traffic returns to norm | 0.240 | 0.245 | 0.245 | 0.5¢ | 0.5¢ | 52.5 | denizz_loss_follow_87% |
| Strait of Hormuz traffic returns to norm | 0.240 | 0.245 | 0.245 | 0.5¢ | 0.5¢ | 13.1 | denizz_loss_follow_87% |
| Iran x Israel/US conflict ends by June 3 | 0.040 | 0.045 | 0.045 | 0.5¢ | 0.5¢ | 74.4 | stop_loss_67% |
| Iran agrees to surrender enriched uraniu | 0.132 | 0.137 | 0.137 | 0.5¢ | 0.5¢ | 280.6 | denizz_big_dump_100% |
| Israel x Hezbollah ceasefire by April 15 | 0.990 | 0.992 | 0.993 | 0.2¢ | 0.3¢ | 120.3 | price_target_99c |
| Israel x Hezbollah ceasefire by April 30 | 0.665 | 0.668 | 0.668 | 0.3¢ | 0.3¢ | 191.9 | denizz_loss_follow_92% |
| Iran x Israel/US conflict ends by April  | 0.859 | 0.861 | 0.861 | 0.2¢ | 0.2¢ | 66.3 | denizz_follow_60%_sell75% |
| Iran x Israel/US conflict ends by May 15 | 0.100 | 0.095 | 0.100 | -0.5¢ | 0.0¢ | 19.0 | stop_loss_62%_partial |
| Iran x Israel/US conflict ends by April  | 0.510 | 0.510 | 0.510 | 0.0¢ | 0.0¢ | 19.9 | denizz_follow_24%_sell25% |
| Will Israel conduct military action agai | 0.990 | 0.990 | 0.990 | -0.0¢ | -0.0¢ | 33.0 | price_target_99c |
| Trump announces end of military operatio | 0.990 | 0.985 | 0.988 | -0.5¢ | -0.2¢ | 108.0 | price_target_99c |
| Israel x Hezbollah ceasefire by April 30 | 0.813 | 0.810 | 0.810 | -0.2¢ | -0.2¢ | 97.5 | denizz_follow_31%_sell50% |
| Iran agrees to surrender enriched uraniu | 0.252 | 0.248 | 0.248 | -0.4¢ | -0.4¢ | 78.4 | denizz_follow_11%_sell25% |
| US x Iran permanent peace deal by April  | 0.320 | 0.315 | 0.315 | -0.5¢ | -0.5¢ | 50.0 | denizz_follow_11%_sell25% |
| Trump announces end of military operatio | 0.680 | 0.675 | 0.675 | -0.5¢ | -0.5¢ | 17.5 | denizz_follow_30%_sell35%_retr |
| US x Iran ceasefire by April 7? | 0.667 | 0.660 | 0.660 | -0.7¢ | -0.7¢ | 48.0 | Car_partial_23% |
| Israeli forces cross the Litani River by | 0.650 | 0.640 | 0.640 | -1.0¢ | -1.0¢ | 142.0 | denizz_merge_exit |
| Trump announces end of military operatio | 0.690 | 0.675 | 0.675 | -1.5¢ | -1.5¢ | 31.1 | denizz_follow_30%_sell35%_part |
| Israel strike on Yemen by April 30, 2026 | 0.560 | 0.545 | 0.545 | -1.5¢ | -1.5¢ | 5.0 | denizz_sell_detected |
| Will the next diplomatic US-Iran meeting | 0.100 | 0.080 | 0.080 | -2.0¢ | -2.0¢ | 63.0 | stop_loss_71% |
| Trump announces Hormuz deadline extensio | 0.090 | 0.065 | 0.065 | -2.5¢ | -2.5¢ | 5.0 | stop_loss_80% |
| Trump announces end of military operatio | 0.600 | 0.575 | 0.575 | -2.5¢ | -2.5¢ | 60.6 | denizz_sell_detected |
| Trump announces end of military operatio | 0.600 | 0.575 | 0.575 | -2.5¢ | -2.5¢ | 53.4 | denizz_sell_detected |
| US x Iran ceasefire by April 7? | 0.650 | 0.413 | 0.413 | -23.7¢ | -23.7¢ | 163.7 | Car_sell_detected_retry |