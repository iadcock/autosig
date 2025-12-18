"""
AUTO MODE - Automated Paper Trading Execution.
Runs PAPER ONLY and mirrors to both brokers when supported.
"""

import os
import json
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from env_loader import load_env
from market_window import is_within_auto_trading_window
from review_queue import list_recent_signals, build_intent_and_preflight, record_review_action
from dedupe_store import is_executed, mark_executed
from execution import execute_trade
from trade_intent import TradeIntent, OptionLeg
from alpaca_option_resolver import is_alpaca_supported_underlying

logger = logging.getLogger(__name__)

COUNTERS_FILE = "data/auto_counters.json"
AUTO_STATE_FILE = "data/auto_state.json"

_auto_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_auto_enabled = False


def _load_counters() -> Dict[str, Any]:
    """Load auto mode counters from file."""
    try:
        if os.path.exists(COUNTERS_FILE):
            with open(COUNTERS_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {
        "trades_today": 0,
        "trades_this_hour": 0,
        "last_trade_date": None,
        "last_trade_hour": None,
        "last_tick_time": None,
        "last_action": None
    }


def _save_counters(counters: Dict[str, Any]):
    """Save auto mode counters to file."""
    os.makedirs(os.path.dirname(COUNTERS_FILE), exist_ok=True)
    with open(COUNTERS_FILE, "w") as f:
        json.dump(counters, f, indent=2, default=str)


def _reset_counters_if_needed(counters: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """Reset daily/hourly counters if period has changed."""
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    
    if counters.get("last_trade_date") != today:
        counters["trades_today"] = 0
        counters["last_trade_date"] = today
    
    if counters.get("last_trade_hour") != current_hour:
        counters["trades_this_hour"] = 0
        counters["last_trade_hour"] = current_hour
    
    return counters


def get_auto_status() -> Dict[str, Any]:
    """Get current auto mode status."""
    global _auto_enabled
    
    counters = _load_counters()
    window_status = is_within_auto_trading_window()
    
    max_daily = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_hourly = int(load_env("AUTO_MAX_TRADES_PER_HOUR") or "3")
    poll_seconds = int(load_env("AUTO_POLL_SECONDS") or "30")
    
    return {
        "enabled": _auto_enabled,
        "within_window": window_status.get("within_window", False),
        "window_status": window_status,
        "trades_today": counters.get("trades_today", 0),
        "trades_this_hour": counters.get("trades_this_hour", 0),
        "max_daily": max_daily,
        "max_hourly": max_hourly,
        "poll_seconds": poll_seconds,
        "last_tick_time": counters.get("last_tick_time"),
        "last_action": counters.get("last_action"),
        "thread_alive": _auto_thread is not None and _auto_thread.is_alive()
    }


def set_auto_enabled(enabled: bool) -> Dict[str, Any]:
    """Enable or disable auto mode."""
    global _auto_enabled
    
    _auto_enabled = enabled
    
    if enabled:
        _start_auto_thread()
    else:
        _stop_auto_thread()
    
    return get_auto_status()


def _start_auto_thread():
    """Start the auto mode background thread."""
    global _auto_thread, _stop_event
    
    if _auto_thread is not None and _auto_thread.is_alive():
        return
    
    _stop_event.clear()
    _auto_thread = threading.Thread(target=_auto_loop, daemon=True)
    _auto_thread.start()
    logger.info("Auto mode thread started")


def _stop_auto_thread():
    """Stop the auto mode background thread."""
    global _auto_thread, _stop_event
    
    _stop_event.set()
    if _auto_thread is not None:
        _auto_thread.join(timeout=5)
    _auto_thread = None
    logger.info("Auto mode thread stopped")


def _auto_loop():
    """Main auto mode loop."""
    global _auto_enabled
    
    poll_seconds = int(load_env("AUTO_POLL_SECONDS") or "30")
    
    while not _stop_event.is_set():
        try:
            if _auto_enabled:
                auto_tick()
        except Exception as e:
            logger.error(f"Auto tick error: {e}")
        
        for _ in range(poll_seconds):
            if _stop_event.is_set():
                break
            time.sleep(1)


def auto_tick() -> Dict[str, Any]:
    """
    Execute one auto mode tick.
    
    Returns dict with action taken and details.
    """
    now = datetime.now()
    counters = _load_counters()
    counters = _reset_counters_if_needed(counters, now)
    counters["last_tick_time"] = now.isoformat()
    
    auto_enabled_env = (load_env("AUTO_MODE_ENABLED") or "").lower() == "true"
    if not _auto_enabled and not auto_enabled_env:
        counters["last_action"] = "SKIP: Auto mode disabled"
        _save_counters(counters)
        return {"action": "skip", "reason": "Auto mode disabled"}
    
    window_status = is_within_auto_trading_window()
    if not window_status.get("within_window", False):
        counters["last_action"] = f"PAUSE: {window_status.get('reason', 'Outside trading window')}"
        _save_counters(counters)
        return {"action": "pause", "reason": window_status.get("reason")}
    
    max_daily = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_hourly = int(load_env("AUTO_MAX_TRADES_PER_HOUR") or "3")
    
    if counters.get("trades_today", 0) >= max_daily:
        counters["last_action"] = f"LIMIT: Daily limit reached ({max_daily})"
        _save_counters(counters)
        return {"action": "limit", "reason": f"Daily limit reached ({max_daily})"}
    
    if counters.get("trades_this_hour", 0) >= max_hourly:
        counters["last_action"] = f"LIMIT: Hourly limit reached ({max_hourly})"
        _save_counters(counters)
        return {"action": "limit", "reason": f"Hourly limit reached ({max_hourly})"}
    
    signals = list_recent_signals(limit=50)
    
    selected = None
    for sig in signals:
        if sig.get("classification") != "SIGNAL":
            continue
        if sig.get("already_executed"):
            continue
        
        signal_type = sig.get("signal_type", "UNKNOWN")
        
        if signal_type == "ENTRY":
            selected = sig
            break
        elif signal_type == "EXIT":
            pass
    
    if not selected:
        counters["last_action"] = "IDLE: No executable signals"
        _save_counters(counters)
        return {"action": "idle", "reason": "No executable signals"}
    
    post_id = selected.get("post_id", "")
    ticker = selected.get("ticker", "unknown")
    
    if is_executed(post_id):
        counters["last_action"] = f"SKIP: {ticker} already executed (dedupe)"
        _save_counters(counters)
        return {"action": "skip", "reason": "Already executed (dedupe)"}
    
    result = build_intent_and_preflight(selected, "paper")
    
    trade_intent_dict = result.get("trade_intent")
    preflight_result = result.get("preflight_result")
    
    if not trade_intent_dict:
        error = result.get("trade_intent_error", "Unknown error")
        counters["last_action"] = f"SKIP: {ticker} - {error}"
        _save_counters(counters)
        return {"action": "skip", "reason": error, "ticker": ticker}
    
    if preflight_result and not preflight_result.get("ok"):
        blocked = preflight_result.get("blocked_reason", "Preflight failed")
        counters["last_action"] = f"BLOCKED: {ticker} - {blocked}"
        _save_counters(counters)
        return {"action": "blocked", "reason": blocked, "ticker": ticker}
    
    try:
        legs = [
            OptionLeg(
                side=leg["side"],
                quantity=leg["quantity"],
                strike=leg["strike"],
                option_type=leg["option_type"],
                expiration=leg["expiration"]
            )
            for leg in trade_intent_dict.get("legs", [])
        ]
        
        trade_intent = TradeIntent(
            id=trade_intent_dict.get("id"),
            execution_mode="PAPER",
            instrument_type=trade_intent_dict.get("instrument_type", "option"),
            underlying=trade_intent_dict.get("underlying", ""),
            action=trade_intent_dict.get("action", "BUY_TO_OPEN"),
            order_type=trade_intent_dict.get("order_type", "MARKET"),
            limit_price=trade_intent_dict.get("limit_price"),
            quantity=trade_intent_dict.get("quantity", 1),
            legs=legs,
            raw_signal=trade_intent_dict.get("raw_signal", ""),
            metadata=trade_intent_dict.get("metadata", {})
        )
        
        execution_result = execute_trade(trade_intent)
        
        if execution_result.status in ("filled", "accepted", "success"):
            mark_executed(
                post_id=post_id,
                execution_mode="paper",
                trade_intent_id=trade_intent.id,
                result_status=execution_result.status,
                underlying=trade_intent.underlying
            )
            
            counters["trades_today"] = counters.get("trades_today", 0) + 1
            counters["trades_this_hour"] = counters.get("trades_this_hour", 0) + 1
            counters["last_action"] = f"EXECUTED: {ticker} ({execution_result.status})"
            _save_counters(counters)
            
            record_review_action(
                post_id=post_id,
                action="AUTO_PAPER",
                mode="paper",
                notes="Auto mode execution",
                preflight=preflight_result,
                result={
                    "status": execution_result.status,
                    "broker": execution_result.broker,
                    "order_id": execution_result.order_id,
                    "message": execution_result.message
                },
                ticker=ticker
            )
            
            mirror_result = None
            paper_mirror = (load_env("PAPER_MIRROR_ENABLED") or "").lower() == "true"
            if paper_mirror and is_alpaca_supported_underlying(trade_intent.underlying):
                mirror_result = _execute_mirror(trade_intent)
            
            return {
                "action": "executed",
                "ticker": ticker,
                "post_id": post_id,
                "status": execution_result.status,
                "mirror_result": mirror_result
            }
        else:
            counters["last_action"] = f"FAILED: {ticker} - {execution_result.message}"
            _save_counters(counters)
            return {"action": "failed", "ticker": ticker, "reason": execution_result.message}
    
    except Exception as e:
        counters["last_action"] = f"ERROR: {ticker} - {str(e)}"
        _save_counters(counters)
        logger.error(f"Auto execution error: {e}")
        return {"action": "error", "ticker": ticker, "reason": str(e)}


def _execute_mirror(trade_intent: TradeIntent) -> Optional[Dict[str, Any]]:
    """
    Execute a mirror trade on Alpaca (for supported underlyings).
    
    Only called for PAPER trades when PAPER_MIRROR_ENABLED=true.
    """
    try:
        pass
        return {"status": "skipped", "reason": "Mirror execution not yet implemented"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
