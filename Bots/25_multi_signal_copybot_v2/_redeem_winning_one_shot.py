"""
One-shot script: redeem all WINNING redeemable positions on the wallet.

Fetches Polymarket positions API, filters those with:
  redeemable=True AND curPrice > 0.5 AND size > 0.01

Then calls the existing redeem_position() function from redeemer.py
for each. Skips losing positions (curPrice <= 0.5, payout $0) — those
are zombies we'll clear separately.

Groups by conditionId (avoid double-calling for Yes+No on same market).
Dedupes by (conditionId, is_neg_risk) tuples.

Usage: py -3.12 -u -X utf8 _redeem_winning_one_shot.py
"""
import sys
import io
import os
import time
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv('../98_sure_bot/.env')
WALLET = os.getenv('POLYMARKET_WALLET', '').lower()

# Use sure_bot's redeem implementation — it has the correct NegRiskAdapter
# (0xd91e80cf...) and call signature. The copybot's redeemer was built for
# the old neg_risk_ctf contract and doesn't work for weather markets.
sys.path.insert(0, os.path.abspath('../98_sure_bot'))
import redeemer as sure_redeemer


def fetch_redeemable():
    """Fetch all positions, return winning redeemable list."""
    out = []
    offset = 0
    while True:
        try:
            r = requests.get(
                'https://data-api.polymarket.com/positions',
                params={'user': WALLET, 'limit': 500, 'offset': offset, 'sizeThreshold': 0},
                timeout=20,
            )
        except Exception as e:
            print(f'fetch error: {e}')
            break
        if not r.ok:
            break
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
        time.sleep(0.2)
    return out


def main():
    print('=' * 60)
    print('One-shot redeem: WINNING positions only')
    print('=' * 60)
    print(f'Wallet: {WALLET}')

    all_positions = fetch_redeemable()
    print(f'\nTotal positions: {len(all_positions)}')

    winning = []
    for p in all_positions:
        if not p.get('redeemable', False):
            continue
        size = float(p.get('size', 0) or 0)
        if size < 0.01:
            continue
        cur_price = float(p.get('curPrice', 0) or 0)
        if cur_price <= 0.5:
            continue  # losing, skip
        winning.append(p)

    print(f'Winning redeemable: {len(winning)}')
    total_payout = sum(float(p.get('size', 0) or 0) for p in winning)
    print(f'Total expected payout: ${total_payout:.2f}')
    print()

    if not winning:
        print('Nothing to redeem.')
        return

    # Group by (conditionId, is_neg_risk) to avoid duplicate redeem calls
    seen = set()
    grouped = []
    for p in winning:
        cid = p.get('conditionId', '')
        is_neg = p.get('negativeRisk', False)
        key = (cid, is_neg)
        if key in seen:
            continue
        seen.add(key)
        grouped.append(p)

    print(f'Unique markets to redeem: {len(grouped)}')
    print()

    # Dry-run preview
    print('=== DRY RUN (showing what will be redeemed) ===')
    for i, p in enumerate(grouped, 1):
        size = float(p.get('size', 0) or 0)
        cid = p.get('conditionId', '')
        is_neg = p.get('negativeRisk', False)
        kind = 'NegRisk' if is_neg else 'CTF'
        print(f'  {i:>3}. [{kind:<7}] {size:>7.2f} sh → ${size:>7.2f}  cid={cid[:18]}...  {p.get("title","")[:50]}')
    print()

    # Skip interactive confirm — user already approved via main command.
    # If run manually, abort by pressing Ctrl+C within the 5-second window.
    print('Starting in 5 seconds... Ctrl+C to abort')
    time.sleep(5)

    # Execute
    print('\n=== EXECUTING ===')
    success_count = 0
    failed_count = 0
    total_redeemed_usd = 0

    for i, p in enumerate(grouped, 1):
        cid = p.get('conditionId', '')
        token_id = p.get('asset', '') or p.get('tokenId', '')
        is_neg = p.get('negativeRisk', False)
        size = float(p.get('size', 0) or 0)
        title = p.get('title', '')[:50]

        print(f'\n[{i}/{len(grouped)}] Redeem ${size:.2f} | {title}')
        try:
            success = sure_redeemer.redeem_position(
                cid, is_neg_risk=is_neg, token_id=token_id
            )
            if success is True:
                success_count += 1
                total_redeemed_usd += size
                print(f'  SUCCESS — got ~${size:.2f}')
            elif success is None:
                print('  DEFERRED (CTF payout not reported yet)')
                failed_count += 1
            else:
                failed_count += 1
                print('  FAILED')
        except Exception as e:
            failed_count += 1
            print(f'  EXCEPTION: {e}')

        # Small delay between redeems to avoid nonce collisions
        time.sleep(3)

    print('\n' + '=' * 60)
    print(f'DONE: {success_count} success, {failed_count} failed')
    print(f'Total redeemed (estimated): ${total_redeemed_usd:.2f}')
    print('=' * 60)


if __name__ == '__main__':
    main()
