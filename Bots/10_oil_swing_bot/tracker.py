"""Position tracking for oil swing bot."""
import json
import os
from datetime import datetime, timezone
from config import POSITIONS_FILE, BANKROLL


def _default_data():
    return {
        "stats": {
            "bankroll": BANKROLL,
            "current_balance": BANKROLL,
            "total_trades": 0,
            "total_pnl": 0.0,
        },
        "positions": {},
        "yes_entry_steps_done": [],   # which gradient steps completed [0,1,2]
        "yes_exit_steps_done": [],    # which exit steps completed [0,1,2]
        "no_entry_steps_done": [],    # which NO gradient steps completed [0,1,2]
        "history": [],
    }


def load() -> dict:
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                data = json.load(f)
            # Ensure new fields exist
            data.setdefault("yes_entry_steps_done", [])
            data.setdefault("yes_exit_steps_done", [])
            data.setdefault("no_entry_steps_done", [])
            return data
        except Exception:
            pass
    data = _default_data()
    save(data)
    return data


def save(data: dict):
    tmp = POSITIONS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, POSITIONS_FILE)


def get_balance(data: dict) -> float:
    return data["stats"]["current_balance"]


def get_invested(data: dict) -> float:
    """Total cost of all open positions."""
    total = 0
    for pos in data["positions"].values():
        if pos.get("status") == "open":
            total += pos.get("cost_usd", 0)
    return total


def get_free_balance(data: dict) -> float:
    """Balance minus invested = available for new bets."""
    return get_balance(data)


def get_portfolio_value(data: dict) -> float:
    """Balance + invested (approximate portfolio value)."""
    return get_balance(data) + get_invested(data)


def get_open_positions(data: dict, side: str = None) -> list:
    """Return list of (key, pos) for open positions, optionally filtered by side."""
    result = []
    for k, p in data["positions"].items():
        if p.get("status") == "open":
            if side is None or p.get("side") == side:
                result.append((k, p))
    return result


def has_open(data: dict, side: str) -> bool:
    return len(get_open_positions(data, side)) > 0


def get_total_shares(data: dict, side: str) -> float:
    """Total shares in open positions for a side."""
    return sum(p.get("size_shares", 0) for _, p in get_open_positions(data, side))


def record_buy(data: dict, order_id: str, side: str, price: float,
               shares: float, cost_usd: float, wti_price: float, step: int = -1):
    """Record a new buy position."""
    data["positions"][order_id] = {
        "side": side,
        "entry_price": price,
        "size_shares": shares,
        "cost_usd": cost_usd,
        "entry_wti": wti_price,
        "entry_step": step,
        "status": "open",
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }
    data["stats"]["current_balance"] -= cost_usd
    data["stats"]["total_trades"] += 1
    save(data)


def record_sell(data: dict, position_key: str, sell_price: float,
                shares_sold: float, revenue_usd: float, reason: str):
    """Record a sell. Supports partial sells."""
    pos = data["positions"].get(position_key)
    if not pos:
        return

    total_shares = pos.get("size_shares", 0)

    if shares_sold >= total_shares - 0.01:
        # Full close
        cost = pos.get("cost_usd", 0)
        pnl = revenue_usd - cost
        pos["status"] = "closed"
        pos["sell_price"] = sell_price
        pos["revenue_usd"] = revenue_usd
        pos["pnl"] = pnl
        pos["closed_at"] = datetime.now(timezone.utc).isoformat()
        pos["close_reason"] = reason
    else:
        # Partial close — reduce position proportionally
        sell_fraction = shares_sold / total_shares
        cost_portion = pos["cost_usd"] * sell_fraction
        pnl = revenue_usd - cost_portion
        pos["size_shares"] -= shares_sold
        pos["cost_usd"] -= cost_portion

    data["stats"]["current_balance"] += revenue_usd
    data["stats"]["total_pnl"] += (revenue_usd - (pos.get("cost_usd", 0) if pos["status"] == "closed" else revenue_usd - pnl))

    data["history"].append({
        "side": pos["side"],
        "entry": pos["entry_price"],
        "exit": sell_price,
        "shares": shares_sold,
        "pnl": pnl,
        "reason": reason,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    })

    save(data)


def reset_yes_steps(data: dict):
    """Reset entry/exit step tracking (after full cycle complete)."""
    data["yes_entry_steps_done"] = []
    data["yes_exit_steps_done"] = []
    save(data)


def reset_no_steps(data: dict):
    """Reset NO entry step tracking (after all NO sold)."""
    data["no_entry_steps_done"] = []
    save(data)
