"""
Generate a per-position report for ALL on-chain open positions (all bots combined).
Output: c:/Users/Honor/Desktop/Polymarket/_analytics/2026-04-08_wallet-full-report.md
"""
import sys
import io
import json
import os
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv('.env')
WALLET = os.getenv('POLYMARKET_WALLET', '').lower()

# Bot paths
BOT_PATHS_DICT = {
    '98_sure_bot': 'c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json',
    '25_multi_copybot': 'c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/positions.json',
    '27_overround_bot': 'c:/Users/Honor/Desktop/Polymarket/Bots/27_overround_bot/positions.json',
}
BOT_PATHS_LIST = {
    '26_weather_bot': 'c:/Users/Honor/Desktop/Polymarket/Bots/26_weather_bot/positions.json',
}


def load_bot_positions():
    """Build token → bot mapping. Also include resolved/sold (still on-chain) positions."""
    token_to_bot = {}

    # Dict format
    for bot, path in BOT_PATHS_DICT.items():
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            for oid, p in data.get('positions', {}).items():
                token = p.get('token_id', '') or p.get('no_token', '') or p.get('asset_id', '')
                if token and token not in token_to_bot:
                    token_to_bot[token] = {
                        'bot': bot,
                        'signal_player': p.get('signal_player', ''),
                        'status': p.get('status', ''),
                        'cost_usd_tracker': p.get('cost_usd', 0),
                    }
        except Exception as e:
            print(f"  {bot}: {e}")

    # List format (weather)
    for bot, path in BOT_PATHS_LIST.items():
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for p in data:
                    token = p.get('token_id', '')
                    if token and token not in token_to_bot:
                        token_to_bot[token] = {
                            'bot': bot,
                            'signal_player': '',
                            'status': p.get('status', ''),
                            'cost_usd_tracker': p.get('cost', 0),
                        }
        except Exception as e:
            print(f"  {bot}: {e}")

    return token_to_bot


def get_all_positions(wallet):
    all_p = []
    offset = 0
    while True:
        r = requests.get('https://data-api.polymarket.com/positions',
                         params={'user': wallet, 'limit': 500, 'offset': offset}, timeout=20)
        if not r.ok:
            break
        b = r.json()
        if not b:
            break
        all_p.extend(b)
        if len(b) < 500:
            break
        offset += 500
        time.sleep(0.2)
    return all_p


def get_usdc_balance():
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider('https://polygon.gateway.tenderly.co'))
    USDC = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
    abi = [{"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}]
    c = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=abi)
    return c.functions.balanceOf(Web3.to_checksum_address(WALLET)).call() / 1e6


def main():
    print("Loading tracker data...")
    token_to_bot = load_bot_positions()
    print(f"  Tokens tracked by bots: {len(token_to_bot)}")

    print("Fetching on-chain positions...")
    positions = get_all_positions(WALLET)
    print(f"  Total positions: {len(positions)}")

    print("Fetching USDC balance...")
    usdc = get_usdc_balance()
    print(f"  USDC: ${usdc:.2f}")

    rows = []
    for p in positions:
        asset = p.get('asset', '')
        bot_info = token_to_bot.get(asset, {})

        cost = float(p.get('initialValue', 0))
        curval = float(p.get('currentValue', 0))
        avg_price = float(p.get('avgPrice', 0))
        cur_price = float(p.get('curPrice', 0))
        cash_pnl = float(p.get('cashPnl', 0))

        roi_pct = ((cur_price - avg_price) / avg_price * 100) if avg_price > 0 else 0

        rows.append({
            'bot': bot_info.get('bot', 'ORPHANED'),
            'signal_player': bot_info.get('signal_player', ''),
            'title': p.get('title', '')[:60],
            'outcome': p.get('outcome', ''),
            'size': float(p.get('size', 0)),
            'avg_price': avg_price,
            'cur_price': cur_price,
            'cost': cost,
            'curval': curval,
            'unrealized': cash_pnl,
            'roi_pct': roi_pct,
            'condition_id': p.get('conditionId', '')[:20],
        })

    # Sort by cost desc
    rows.sort(key=lambda r: -r['cost'])

    total_cost = sum(r['cost'] for r in rows)
    total_curval = sum(r['curval'] for r in rows)
    total_unr = total_curval - total_cost

    # By bot
    by_bot = {}
    for r in rows:
        b = r['bot']
        if b not in by_bot:
            by_bot[b] = {'n': 0, 'cost': 0, 'curval': 0, 'unr': 0}
        by_bot[b]['n'] += 1
        by_bot[b]['cost'] += r['cost']
        by_bot[b]['curval'] += r['curval']
        by_bot[b]['unr'] += r['unrealized']

    # Write report
    out_dir = 'c:/Users/Honor/Desktop/Polymarket/_analytics'
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, '2026-04-08_wallet-full-report.md')

    lines = []
    lines.append("# Wallet — все открытые позиции (все боты)")
    lines.append("")
    lines.append(f"**Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Wallet:** `{WALLET}`")
    lines.append(f"**Source:** Polymarket positions API + tracker positions.json (для mapping bot↔token)")
    lines.append("")

    lines.append("## Wallet Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| USDC (free) | **${usdc:,.2f}** |")
    lines.append(f"| Open positions | **{len(rows)}** |")
    lines.append(f"| Cost basis | **${total_cost:,.2f}** |")
    lines.append(f"| Current value | **${total_curval:,.2f}** |")
    lines.append(f"| Unrealized PnL | **${total_unr:+,.2f}** |")
    lines.append(f"| **TOTAL EQUITY** | **${usdc + total_curval:,.2f}** |")
    lines.append("")

    lines.append("## Breakdown by Bot")
    lines.append("")
    lines.append("| Bot | N | Cost | Current | Unrealized | ROI |")
    lines.append("|-----|---|------|---------|------------|-----|")
    for bot_name, s in sorted(by_bot.items(), key=lambda x: -x[1]['cost']):
        roi = (s['unr'] / s['cost'] * 100) if s['cost'] > 0 else 0
        lines.append(f"| **{bot_name}** | {s['n']} | ${s['cost']:,.2f} | ${s['curval']:,.2f} | ${s['unr']:+,.2f} | {roi:+.2f}% |")
    lines.append("")

    lines.append(f"## All positions ({len(rows)}) — sorted by Cost desc")
    lines.append("")
    lines.append("| # | Bot | Player | Outcome | Size | Avg | Cur | ROI % | Cost | CurVal | Unr PnL | Title |")
    lines.append("|---|-----|--------|---------|------|-----|-----|-------|------|--------|---------|-------|")
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {r['bot']} | {r['signal_player'] or '—'} | {r['outcome']} | "
            f"{r['size']:.1f} | {r['avg_price']:.3f} | {r['cur_price']:.3f} | "
            f"{r['roi_pct']:+.1f}% | ${r['cost']:.2f} | ${r['curval']:.2f} | "
            f"${r['unrealized']:+.2f} | {r['title']} |"
        )
    lines.append("")

    # Top 10 winners
    winners = sorted(rows, key=lambda r: -r['unrealized'])[:10]
    lines.append("## Top 10 winners (by unrealized PnL)")
    lines.append("")
    lines.append("| # | Bot | Unr PnL | ROI % | Cost | Title |")
    lines.append("|---|-----|---------|-------|------|-------|")
    for i, r in enumerate(winners, 1):
        lines.append(f"| {i} | {r['bot']} | ${r['unrealized']:+.2f} | {r['roi_pct']:+.1f}% | ${r['cost']:.2f} | {r['title']} |")
    lines.append("")

    losers = sorted(rows, key=lambda r: r['unrealized'])[:10]
    lines.append("## Top 10 losers (by unrealized PnL)")
    lines.append("")
    lines.append("| # | Bot | Unr PnL | ROI % | Cost | Title |")
    lines.append("|---|-----|---------|-------|------|-------|")
    for i, r in enumerate(losers, 1):
        lines.append(f"| {i} | {r['bot']} | ${r['unrealized']:+.2f} | {r['roi_pct']:+.1f}% | ${r['cost']:.2f} | {r['title']} |")
    lines.append("")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"\nSaved to {out_path}")
    print(f"\nSummary:")
    print(f"  USDC:         ${usdc:>10,.2f}")
    print(f"  Positions:    {len(rows)} @ cost ${total_cost:,.2f}, curval ${total_curval:,.2f}")
    print(f"  Unrealized:   ${total_unr:+,.2f}")
    print(f"  TOTAL:        ${usdc + total_curval:,.2f}")
    print()
    print("By bot:")
    for bot_name, s in sorted(by_bot.items(), key=lambda x: -x[1]['cost']):
        roi = (s['unr'] / s['cost'] * 100) if s['cost'] > 0 else 0
        print(f"  {bot_name:<20} N={s['n']:>3} cost=${s['cost']:>9,.2f} unr=${s['unr']:>+9,.2f} ROI={roi:+.2f}%")


if __name__ == '__main__':
    main()
