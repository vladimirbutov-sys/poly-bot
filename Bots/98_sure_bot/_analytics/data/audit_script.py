import json, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

with open('c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/usdc_transfers_parsed.json') as f:
    transfers = json.load(f)

wallet = '0x4717eccf1e1e2443e7563b330c6e0b3b6f96bdde'

address_labels = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e': 'CTF Exchange (Polymarket)',
    '0x4d97dcd97ec945f40cf65f87097ace5ea0476045': 'NegRiskAdapter (Polymarket)',
    '0xc5d563a36ae78145c45a50134d48a1215220f80a': 'NegRiskCtfExchange (Polymarket)',
    '0x3a3bd7bb9528e159577f7c2e685cc81a765002e2': 'WrappedCollateral (Polymarket)',
    '0xc590175e458b83680867afd273527ff58f74c02b': 'Polymarket Exchange Router',
    '0xf70da97812cb96acdf810712aa562db8dfa3dbef': 'Trade Counterparty (EOA)',
    '0xdef171fe48cf0115b1d80b88dc8eab59176fee57': 'ParaSwap (DEX)',
    '0xf89d7b9c864f589bbf53a82105107622b35eaa40': 'ParaSwap Augustus',
    '0xa85c29b94f8a22a7268facee89ef4eca051be2ce': 'Personal Wallet (EOA)',
    '0x4cd00e387622c35bddb9b4c962c136462338bc31': 'RelayDepository (Bridge)',
    '0xb92fe925dc43a0ecde6c8b1a2709c170ec4fff4f': 'RelayRouterV3 (Bridge)',
    '0xffbfb5abc0ee2db69133a48614ad0e7d91f8864f': 'Unknown Wallet (EOA)',
    '0x476d1cf61279400c3eada7dccb80c2ca306239c2': 'Unknown Contract',
}

polymarket_addrs = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e',
    '0x4d97dcd97ec945f40cf65f87097ace5ea0476045',
    '0xc5d563a36ae78145c45a50134d48a1215220f80a',
    '0x3a3bd7bb9528e159577f7c2e685cc81a765002e2',
    '0xc590175e458b83680867afd273527ff58f74c02b',
    '0xf70da97812cb96acdf810712aa562db8dfa3dbef',
}

bridge_addrs = {
    '0x4cd00e387622c35bddb9b4c962c136462338bc31',
    '0xb92fe925dc43a0ecde6c8b1a2709c170ec4fff4f',
}

swap_addrs = {
    '0xdef171fe48cf0115b1d80b88dc8eab59176fee57',
    '0xf89d7b9c864f589bbf53a82105107622b35eaa40',
}

balance_usdc = 0.0
balance_usdce = 0.0
categories_summary = defaultdict(lambda: {'in': 0.0, 'out': 0.0, 'count': 0})
ledger_entries = []

for i, t in enumerate(transfers):
    other = t['to'] if t['direction'] == 'OUT' else t['from']
    label = address_labels.get(other, f'Unknown ({other[:14]}...)')

    if other in polymarket_addrs:
        category = 'Polymarket Trading'
    elif other in bridge_addrs:
        category = 'Bridge (Relay)'
    elif other in swap_addrs:
        category = 'DEX Swap (ParaSwap)'
    elif other == '0xa85c29b94f8a22a7268facee89ef4eca051be2ce':
        category = 'Initial Deposit'
    elif other == '0xffbfb5abc0ee2db69133a48614ad0e7d91f8864f':
        category = 'Transfer Out (unknown wallet)'
    elif other == '0x476d1cf61279400c3eada7dccb80c2ca306239c2':
        category = 'Transfer Out (unknown contract)'
    else:
        category = f'Other ({label})'

    if t['direction'] == 'IN':
        if t['token'] == 'USDC':
            balance_usdc += t['amount']
        else:
            balance_usdce += t['amount']
        categories_summary[category]['in'] += t['amount']
    else:
        if t['token'] == 'USDC':
            balance_usdc -= t['amount']
        else:
            balance_usdce -= t['amount']
        categories_summary[category]['out'] += t['amount']
    categories_summary[category]['count'] += 1

    ledger_entries.append({
        'n': i + 1,
        'timestamp': t['timestamp'][:19].replace('T', ' '),
        'direction': t['direction'],
        'amount': round(t['amount'], 2),
        'token': t['token'],
        'balance_usdc': round(balance_usdc, 2),
        'balance_usdce': round(balance_usdce, 2),
        'balance_total': round(balance_usdc + balance_usdce, 2),
        'category': category,
        'counterparty': label,
        'address': other,
        'tx_hash': t.get('tx_hash', ''),
    })

# Print results
print("=" * 90)
print("                    FULL WALLET AUDIT REPORT")
print("=" * 90)
print(f"Wallet:  0x4717eccF1e1E2443e7563b330C6E0B3B6f96bDdE")
print(f"Period:  {transfers[0]['timestamp'][:10]} to {transfers[-1]['timestamp'][:10]} (14 days)")
print(f"Total USDC/USDC.e transfers: {len(transfers)}")
print()

print("--- CATEGORY BREAKDOWN ---")
fmt = "{:<45} {:>6} {:>12} {:>12} {:>12}"
print(fmt.format('Category', 'Count', 'IN ($)', 'OUT ($)', 'Net ($)'))
print("-" * 90)
for cat in sorted(categories_summary.keys()):
    s = categories_summary[cat]
    net = s['in'] - s['out']
    print(fmt.format(cat, s['count'], f"{s['in']:.2f}", f"{s['out']:.2f}", f"{net:.2f}"))

total_in = sum(s['in'] for s in categories_summary.values())
total_out = sum(s['out'] for s in categories_summary.values())
print("-" * 90)
print(fmt.format('TOTAL', len(transfers), f"{total_in:.2f}", f"{total_out:.2f}", f"{total_in-total_out:.2f}"))

print()
print("--- CALCULATED BALANCES ---")
print(f"USDC (native) balance:    ${balance_usdc:>10.2f}")
print(f"USDC.e (bridged) balance: ${balance_usdce:>10.2f}")
print(f"Total calculated:         ${balance_usdc + balance_usdce:>10.2f}")
print(f"On-chain USDC.e:          $      4.41")
print(f"On-chain USDC:            $      0.00")
print(f"On-chain total:           $      4.41")
print()
discrepancy = (balance_usdc + balance_usdce) - 4.41
print(f"Discrepancy:              ${discrepancy:>10.2f}")
print(f"= Money in open Polymarket positions (conditional tokens)")

print()
print("--- EXTERNAL MONEY FLOW ---")
print(f"1. $496.00 USDC IN from personal wallet (0xa85c...)")
print(f"2. $494.79 USDC OUT to RelayDepository bridge (deposit into Polymarket)")
print(f"3. $1.00 USDC IN from RelayRouter bridge (small return)")
print(f"4. $199.00 USDC swapped to $198.99 USDC.e via ParaSwap")
print(f"5. $5.00 USDC.e OUT to unknown wallet")
print(f"6. $100.00 USDC.e OUT to unknown contract")

pm = categories_summary['Polymarket Trading']
poly_net = pm['in'] - pm['out']
print()
print("--- POLYMARKET TRADING ---")
print(f"Total sent to Polymarket:       ${pm['out']:>10.2f}")
print(f"Total received from Polymarket: ${pm['in']:>10.2f}")
print(f"Net Polymarket flow:            ${poly_net:>10.2f}")
print(f"Trading transactions:           {pm['count']}")

print()
print("--- NET P&L ---")
real_deposit = 496.00 + 1.00  # external money in
real_withdrawn = 5.00 + 100.00 + 494.79  # external money out (bridge deposit counts as still in system)
# Actually the $494.79 to RelayDepository is depositing INTO Polymarket
# So real capital = $496 + $1 = $497 deposited
# Withdrawn: $5 + $100 = $105
# Still in system: on-chain $4.41 + positions $859.63 = $864.04
# But wait - the $494.79 bridge deposit brought the money INTO Polymarket as USDC.e
# which then got used for trading. So effective capital deployed = $497

total_capital = 497.00
total_withdrawn_ext = 105.00
current_onchain = 4.41
est_positions = discrepancy
total_current = current_onchain + est_positions + total_withdrawn_ext

print(f"Capital deposited:              $    {total_capital:.2f}")
print(f"Withdrawn to external:          $    {total_withdrawn_ext:.2f}")
print(f"On-chain balance:               $      {current_onchain:.2f}")
print(f"Est. in positions:              $    {est_positions:.2f}")
print(f"Total current value:            $    {total_current:.2f}")
pnl = total_current - total_capital
print(f"NET P&L:                        $    {pnl:>+.2f}")
print(f"ROI:                            {pnl/total_capital*100:>+.1f}%")

# Save ledger
with open('c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/ledger_classified.json', 'w') as f:
    json.dump(ledger_entries, f, indent=2, ensure_ascii=False)

# Daily summary
print()
print("--- DAILY SUMMARY ---")
daily = defaultdict(lambda: {'in': 0, 'out': 0, 'poly_in': 0, 'poly_out': 0, 'txs': 0})
for t in transfers:
    day = t['timestamp'][:10]
    other = t['to'] if t['direction'] == 'OUT' else t['from']
    daily[day]['txs'] += 1
    if t['direction'] == 'IN':
        daily[day]['in'] += t['amount']
        if other in polymarket_addrs:
            daily[day]['poly_in'] += t['amount']
    else:
        daily[day]['out'] += t['amount']
        if other in polymarket_addrs:
            daily[day]['poly_out'] += t['amount']

print(f"{'Date':<12} {'Txs':>5} {'All IN':>10} {'All OUT':>10} {'Net':>10} {'PM IN':>10} {'PM OUT':>10} {'PM Net':>10}")
for day in sorted(daily.keys()):
    d = daily[day]
    print(f"{day:<12} {d['txs']:>5} ${d['in']:>9.2f} ${d['out']:>9.2f} ${d['in']-d['out']:>9.2f} ${d['poly_in']:>9.2f} ${d['poly_out']:>9.2f} ${d['poly_in']-d['poly_out']:>9.2f}")

# Polymarket contract breakdown
print()
print("--- POLYMARKET CONTRACT BREAKDOWN ---")
pm_contracts = defaultdict(lambda: {'in': 0.0, 'out': 0.0, 'count': 0})
for t in transfers:
    other = t['to'] if t['direction'] == 'OUT' else t['from']
    if other in polymarket_addrs:
        label = address_labels.get(other, other)
        if t['direction'] == 'IN':
            pm_contracts[label]['in'] += t['amount']
        else:
            pm_contracts[label]['out'] += t['amount']
        pm_contracts[label]['count'] += 1

for name in sorted(pm_contracts.keys()):
    c = pm_contracts[name]
    print(f"  {name:<40} {c['count']:>5} txs | IN=${c['in']:>10.2f} | OUT=${c['out']:>10.2f} | Net=${c['in']-c['out']:>10.2f}")

print("\nDone. Ledger saved to ledger_classified.json")
