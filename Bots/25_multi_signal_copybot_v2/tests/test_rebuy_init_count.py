"""Tests for _init_exec_count_from_log() — persistent rebuy counter (2026-04-18).

Smoke-test cap logic itself unchanged: this just initializes the counter from
disk so cap doesn't re-engage with every restart. Tests verify the counter
loading is correct without touching the cap mechanism.
"""
import json
import os
import importlib
import pytest


def _write_log(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _exec_entry(title="Test market"):
    return {"decision": "EXECUTED", "title": title, "final": 20.0,
            "timestamp": "2026-04-17T00:00:00+00:00"}


def _skip_entry(title="Test market", reason="SKIP_THROTTLE"):
    return {"decision": reason, "title": title,
            "timestamp": "2026-04-17T00:00:00+00:00"}


def _reload_rebuy(monkeypatch, log_path):
    """Patch config.REBUY_LOG_PATH then reload rebuy module so init runs fresh."""
    import config
    monkeypatch.setattr(config, "REBUY_LOG_PATH", str(log_path))
    import rebuy
    importlib.reload(rebuy)
    return rebuy


# ---------- 1. Empty/missing log ----------

def test_init_with_missing_log_yields_zero(tmp_path, monkeypatch):
    """No log file → counter stays at 0 (smoke cap engages, current behavior)."""
    log_path = tmp_path / "rebuy_log.jsonl"
    # Don't create the file
    rebuy = _reload_rebuy(monkeypatch, log_path)
    assert rebuy._rebuy_exec_count == 0


def test_init_with_empty_log_yields_zero(tmp_path, monkeypatch):
    """Empty log file → counter = 0."""
    log_path = tmp_path / "rebuy_log.jsonl"
    log_path.touch()
    rebuy = _reload_rebuy(monkeypatch, log_path)
    assert rebuy._rebuy_exec_count == 0


# ---------- 2. Counts EXECUTED only ----------

def test_counts_only_executed_entries(tmp_path, monkeypatch):
    """SKIP_THROTTLE, SKIP_DISABLED etc must NOT count toward smoke threshold."""
    log_path = tmp_path / "rebuy_log.jsonl"
    _write_log(log_path, [
        _exec_entry("Market A"),
        _skip_entry("Market B", "SKIP_THROTTLE"),
        _exec_entry("Market C"),
        _skip_entry("Market D", "SKIP_KILL_SWITCH"),
        _skip_entry("Market E", "SKIP_DISABLED"),
        _exec_entry("Market F"),
    ])
    rebuy = _reload_rebuy(monkeypatch, log_path)
    assert rebuy._rebuy_exec_count == 3


# ---------- 3. Above threshold → cap auto-disabled ----------

def test_count_above_n_disables_cap(tmp_path, monkeypatch):
    """If counter >= REBUY_INITIAL_N (3), _initial_cap_active() returns None."""
    log_path = tmp_path / "rebuy_log.jsonl"
    _write_log(log_path, [_exec_entry() for _ in range(5)])  # 5 EXECUTED
    rebuy = _reload_rebuy(monkeypatch, log_path)
    assert rebuy._rebuy_exec_count == 5
    cap = rebuy._initial_cap_active()
    assert cap is None, "5 EXECUTED >= 3 → cap should be inactive"


# ---------- 4. Below threshold → cap still active ----------

def test_count_below_n_keeps_cap_active(tmp_path, monkeypatch):
    """1 EXECUTED < 3 → cap STILL applies."""
    log_path = tmp_path / "rebuy_log.jsonl"
    _write_log(log_path, [_exec_entry()])
    rebuy = _reload_rebuy(monkeypatch, log_path)
    assert rebuy._rebuy_exec_count == 1
    cap = rebuy._initial_cap_active()
    assert cap == 20.0, "1 EXECUTED < 3 → cap should still be $20"


# ---------- 5. Malformed lines tolerated ----------

def test_malformed_lines_skipped(tmp_path, monkeypatch):
    """Non-JSON lines should be skipped silently, valid entries still counted."""
    log_path = tmp_path / "rebuy_log.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(_exec_entry()) + "\n")
        f.write("garbled-non-json-line\n")
        f.write("\n")  # blank
        f.write(json.dumps(_exec_entry()) + "\n")
        f.write("{incomplete json\n")
        f.write(json.dumps(_exec_entry()) + "\n")
    rebuy = _reload_rebuy(monkeypatch, log_path)
    assert rebuy._rebuy_exec_count == 3, "valid entries counted, malformed skipped"


# ---------- 6. Exactly threshold = cap off ----------

def test_count_at_threshold_disables_cap(tmp_path, monkeypatch):
    """Exactly REBUY_INITIAL_N (3) EXECUTED → cap should be off (>= comparison)."""
    log_path = tmp_path / "rebuy_log.jsonl"
    _write_log(log_path, [_exec_entry() for _ in range(3)])
    rebuy = _reload_rebuy(monkeypatch, log_path)
    assert rebuy._rebuy_exec_count == 3
    assert rebuy._initial_cap_active() is None
