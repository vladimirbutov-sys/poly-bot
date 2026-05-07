"""Position and P&L tracking. Persists to positions.json."""
import json
import os
import logging
import threading
from datetime import datetime, timezone

from config import POSITIONS_FILE

logger = logging.getLogger("tracker")

# Lock to prevent race conditions between fill-checker threads and main loop
_lock = threading.Lock()


def _default_data():
    return {
        "positions": {},
        "stats": {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "peak_balance": 0.0,
            "current_balance": 0.0,
        }
    }


def load():
    """Load tracker data from disk (thread-safe)."""
    with _lock:
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                pass
        return _default_data()


def save(data):
    """Atomic save to disk (thread-safe, with retry for Windows file locks)."""
    with _lock:
        tmp = POSITIONS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        for attempt in range(5):
            try:
                os.replace(tmp, POSITIONS_FILE)
                return
            except OSError:
                import time
                time.sleep(0.2 * (attempt + 1))
        # Last attempt — let it raise if still failing
        os.replace(tmp, POSITIONS_FILE)


def get_open_positions(data) -> dict:
    """Get all open positions."""
    return {
        key: pos for key, pos in data["positions"].items()
        if pos.get("status") == "open"
    }


def get_open_condition_ids(data) -> set:
    """Get set of condition_ids that have open positions."""
    return {
        pos["condition_id"]
        for pos in data["positions"].values()
        if pos.get("status") == "open" and pos.get("condition_id")
    }


def record_position(data, order_id: str, condition_id: str, token_id: str,
                     title: str, entry_price: float, size_shares: float,
                     cost_usd: float, neg_risk: bool = False,
                     category: str = "", end_date: str = ""):
    """Record a new position, keyed by order_id."""
    data["positions"][order_id] = {
        "condition_id": condition_id,
        "token_id": token_id,
        "title": title,
        "entry_price": entry_price,
        "size_shares": size_shares,
        "cost_usd": cost_usd,
        "neg_risk": neg_risk,
        "category": category,
        "end_date": end_date,
        "order_id": order_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }

    stats = data["stats"]
    stats["total_bets"] += 1
    stats["current_balance"] -= cost_usd

    save(data)
    logger.info("Recorded position: %s | %.2f shares @ %.3f = $%.2f",
                title[:50], size_shares, entry_price, cost_usd)


def update_position_fill(data, order_id: str, filled_shares: float, filled_cost: float):
    """
    Update a position after partial fill.
    Adjusts size_shares and cost_usd to reflect what was actually bought.
    Returns the cost difference (refund to balance).
    """
    pos = data["positions"].get(order_id)
    if not pos:
        return 0.0

    original_cost = pos["cost_usd"]
    pos["size_shares"] = filled_shares
    pos["cost_usd"] = filled_cost

    refund = original_cost - filled_cost
    data["stats"]["current_balance"] += refund

    save(data)
    logger.info("Updated position %s: %.2f shares, $%.2f (refund $%.2f)",
                order_id[:16], filled_shares, filled_cost, refund)
    return refund


def remove_position(data, order_id: str):
    """Remove a position that was never filled. Returns cost to balance."""
    pos = data["positions"].get(order_id)
    if not pos:
        return 0.0

    cost = pos["cost_usd"]
    data["stats"]["current_balance"] += cost
    data["stats"]["total_bets"] = max(0, data["stats"]["total_bets"] - 1)
    del data["positions"][order_id]

    save(data)
    logger.info("Removed unfilled position %s, refunded $%.2f", order_id[:16], cost)
    return cost


def resolve_position(data, key: str, won: bool):
    """Mark a position as won or lost."""
    pos = data["positions"].get(key)
    if not pos or pos["status"] != "open":
        return

    stats = data["stats"]
    if won:
        payout = pos["size_shares"]  # each share redeems for $1
        pnl = payout - pos["cost_usd"]
        pos["status"] = "won"
        stats["wins"] += 1
    else:
        pnl = -pos["cost_usd"]
        pos["status"] = "lost"
        stats["losses"] += 1

    pos["pnl"] = pnl
    pos["resolved_at"] = datetime.now(timezone.utc).isoformat()
    stats["total_pnl"] += pnl
    stats["current_balance"] += pos["cost_usd"] + pnl  # return cost + profit/loss
    stats["peak_balance"] = max(stats["peak_balance"], stats["current_balance"])

    save(data)


def get_portfolio_value(data) -> float:
    """Calculate fair value: cash balance + cost of open positions.
    Open positions are 98.5%+ probability, so fair value ≈ shares (redeem at $1).
    Conservative estimate uses cost_usd instead."""
    cash = data["stats"]["current_balance"]
    open_cost = sum(
        pos.get("cost_usd", 0)
        for pos in data["positions"].values()
        if pos.get("status") == "open"
    )
    return cash + open_cost


def get_summary(data) -> dict:
    """Get summary stats."""
    return dict(data["stats"])


def generate_report(data) -> str:
    """Generate a human-readable report of bot performance."""
    stats = data["stats"]
    positions = data["positions"]

    open_p = [p for p in positions.values() if p.get("status") == "open"]
    won_p = [p for p in positions.values() if p.get("status") == "won"]
    lost_p = [p for p in positions.values() if p.get("status") == "lost"]

    lines = []
    lines.append("=" * 50)
    lines.append("  98_SURE_BOT — REPORT")
    lines.append(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 50)

    # --- Overview ---
    total_resolved = len(won_p) + len(lost_p)
    win_rate = len(won_p) / total_resolved * 100 if total_resolved else 0
    lines.append("")
    lines.append(f"  Balance:    ${stats['current_balance']:.2f}")
    lines.append(f"  Total PnL:  ${stats['total_pnl']:+.2f}")
    lines.append(f"  Total bets: {stats['total_bets']}")
    lines.append(f"  Resolved:   {total_resolved} (W:{len(won_p)} L:{len(lost_p)})")
    lines.append(f"  Win rate:   {win_rate:.1f}%")
    lines.append(f"  Open:       {len(open_p)}")

    # --- Wins/Losses summary ---
    if won_p:
        total_won_profit = sum(p.get("pnl", 0) for p in won_p)
        avg_won = total_won_profit / len(won_p)
        lines.append(f"  Won profit: ${total_won_profit:+.2f} (avg ${avg_won:+.3f}/bet)")

    if lost_p:
        total_lost = sum(p.get("pnl", 0) for p in lost_p)
        avg_lost = total_lost / len(lost_p)
        lines.append(f"  Lost:       ${total_lost:+.2f} (avg ${avg_lost:.3f}/bet)")

    # --- Open positions value ---
    if open_p:
        open_cost = sum(p.get("cost_usd", 0) for p in open_p)
        lines.append(f"  Frozen:     ${open_cost:.2f} in {len(open_p)} positions")

    # --- By price bucket ---
    lines.append("")
    lines.append("  --- By price bucket ---")
    buckets = [
        ("97.5-98.0c", 0.975, 0.980),
        ("98.0-98.5c", 0.980, 0.985),
        ("98.5-99.0c", 0.985, 0.990),
        ("99.0-99.3c", 0.990, 0.993),
    ]
    for name, lo, hi in buckets:
        b_won = [p for p in won_p if lo <= p.get("entry_price", 0) < hi]
        b_lost = [p for p in lost_p if lo <= p.get("entry_price", 0) < hi]
        b_total = len(b_won) + len(b_lost)
        if b_total == 0:
            lines.append(f"  {name:12s}: no data")
            continue
        b_pnl = sum(p.get("pnl", 0) for p in b_won) + sum(p.get("pnl", 0) for p in b_lost)
        b_wr = len(b_won) / b_total * 100
        lines.append(f"  {name:12s}: {len(b_won)}W/{len(b_lost)}L | WR:{b_wr:.0f}% | PnL:${b_pnl:+.2f}")

    # --- Last 5 wins ---
    if won_p:
        lines.append("")
        lines.append("  --- Recent wins ---")
        recent_won = sorted(won_p, key=lambda p: p.get("timestamp", ""), reverse=True)[:5]
        for p in recent_won:
            pnl = p.get("pnl", 0)
            lines.append(f"  +${pnl:.3f} | {p.get('entry_price', 0):.3f} | {p.get('title', '?')[:45]}")

    # --- Last 5 losses ---
    if lost_p:
        lines.append("")
        lines.append("  --- Recent losses ---")
        recent_lost = sorted(lost_p, key=lambda p: p.get("timestamp", ""), reverse=True)[:5]
        for p in recent_lost:
            pnl = p.get("pnl", 0)
            lines.append(f"  ${pnl:.2f} | {p.get('entry_price', 0):.3f} | {p.get('title', '?')[:45]}")

    # --- Stuck positions (open > 4 days) ---
    now = datetime.now(timezone.utc)
    stuck = []
    for p in open_p:
        ts = p.get("timestamp", "")
        if not ts:
            continue
        try:
            opened = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_hours = (now - opened).total_seconds() / 3600
            if age_hours > 96:  # > 4 days
                stuck.append((p, age_hours))
        except (ValueError, TypeError):
            pass
    if stuck:
        neg_stuck = [s for s in stuck if s[0].get("neg_risk", False)]
        reg_stuck = [s for s in stuck if not s[0].get("neg_risk", False)]
        lines.append("")
        lines.append(f"  !! STUCK: {len(stuck)} positions open > 4 days")
        if neg_stuck:
            lines.append(f"     neg_risk: {len(neg_stuck)} (check redeemer!)")
        if reg_stuck:
            lines.append(f"     regular:  {len(reg_stuck)}")
        oldest = max(stuck, key=lambda s: s[1])
        lines.append(f"     oldest:   {oldest[1]:.0f}h | {oldest[0].get('title', '?')[:40]}")

    # --- ROI ---
    if total_resolved > 0:
        total_cost = sum(p.get("cost_usd", 0) for p in won_p) + sum(p.get("cost_usd", 0) for p in lost_p)
        roi = stats["total_pnl"] / total_cost * 100 if total_cost > 0 else 0
        lines.append("")
        lines.append(f"  ROI: {roi:+.2f}% on ${total_cost:.2f} resolved")

    lines.append("=" * 50)
    return "\n".join(lines)
