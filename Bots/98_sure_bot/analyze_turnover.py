"""Turnover analysis: neg_risk impact on capital."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

wr = 0.995
avg_profit_per_win = 0.07  # ~1.4c * 5 shares
avg_loss = 4.93

print("=== MATH MODEL: TURNOVER ===")
print()
print("SCENARIO 1: ALL MARKETS (current)")
print("  Bets/day: ~300")
print("  avg hold neg_risk: ~18h (UMA finalization)")
print("  avg hold non-neg:  ~6h")
neg_locked = 185 * 5 * (18/24)   # 185 neg bets/day * $5 * 18h/24h
non_locked = 119 * 5 * (6/24)    # 119 non-neg bets/day * $5 * 6h/24h
print(f"  Capital locked at any moment:")
print(f"    neg_risk: ${neg_locked:.0f}")
print(f"    non-neg:  ${non_locked:.0f}")
print(f"    TOTAL:    ${neg_locked + non_locked:.0f}")
print(f"  BANKROLL NEEDED: ~${neg_locked + non_locked + 100:.0f}")
print()

print("SCENARIO 2: WITHOUT NEG_RISK")
print("  Bets/day: ~119")
non_only = 119 * 5 * (6/24)
print(f"  Capital locked: ${non_only:.0f}")
print(f"  BANKROLL NEEDED: ~${non_only + 50:.0f}")
print()

print("SCENARIO 3: NO NEG_RISK + $3K volume filter")
bets3 = 83  # ~30% reduction from volume filter
locked3 = bets3 * 5 * (6/24)
print(f"  Bets/day: ~{bets3}")
print(f"  Capital locked: ${locked3:.0f}")
print(f"  BANKROLL NEEDED: ~${locked3 + 50:.0f}")
print()

print("=== DAILY PROFIT (at 99.5% WR) ===")
for name, bpd in [("All markets", 300), ("No neg_risk", 119), ("No neg + $3K vol", 83)]:
    wins = bpd * wr
    losses = bpd * (1 - wr)
    daily = wins * avg_profit_per_win - losses * avg_loss
    monthly = daily * 30
    print(f"  {name:22s}: {bpd:3d} bets/day | ${daily:+.2f}/day | ${monthly:+.1f}/month")

print()
print("=== VERDICT ===")
print("Removing neg_risk: -61% bets, -60% profit, but capital freed $217+")
print("Better idea: KEEP neg_risk, but cap max frozen capital (e.g. $300 in neg_risk)")
print("When neg_risk frozen > $300, skip new neg_risk bets until some resolve.")
print("This preserves most of the volume while preventing capital lockup.")
