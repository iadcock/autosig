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
from trade_intent import TradeIntent, OptionLeg, ExecutionResult
from alpaca_option_resolver import is_alpaca_supported_underlying
from settings_store import load_settings, EXECUTION_BROKER_MODE
import config

logger = logging.getLogger(__name__)

COUNTERS_FILE = "data/auto_counters.json"
AUTO_STATE_FILE = "data/auto_state.json"

_auto_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_auto_enabled = True
_safety_checks_passed = False


def _validate_auto_mode_safety():
    """
    Validate all safety requirements before Auto Mode can activate.
    
    Returns:
        (passed: bool, failures: list[str])
    """
    failures = []
    
    # Check 1: DRY_RUN must be True (PAPER mode)
    if not config.DRY_RUN:
        failures.append("DRY_RUN must be True (currently False) - Auto Mode requires paper trading only")
    
    # Check 2: LIVE_TRADING must be False
    if config.LIVE_TRADING:
        failures.append(f"LIVE_TRADING must be False (currently True) - Auto Mode cannot run with live trading enabled")
    
    # Check 3: BROKER_MODE must be TRADIER_ONLY
    if EXECUTION_BROKER_MODE != "TRADIER_ONLY":
        failures.append(f"BROKER_MODE must be TRADIER_ONLY (currently {EXECUTION_BROKER_MODE})")
    
    # Check 4: Kill switch
    kill_switch = (load_env("AUTO_MODE_KILL_SWITCH") or os.getenv("AUTO_MODE_KILL_SWITCH", "")).lower()
    if kill_switch in ("true", "1", "yes", "on", "enabled"):
        failures.append("AUTO_MODE_KILL_SWITCH is enabled - Auto Mode is globally disabled")
    
    passed = len(failures) == 0
    return passed, failures


def _log_auto_mode_safety_checks() -> bool:
    """
    Log all Auto Mode safety checks at startup.
    
    Returns:
        True if all checks pass, False otherwise
    """
    logger.info("=" * 60)
    logger.info("AUTO MODE SAFETY PRE-FLIGHT CHECKS")
    logger.info("=" * 60)
    
    # Check 1: DRY_RUN
    dry_run_ok = config.DRY_RUN
    logger.info(f"  DRY_RUN: {dry_run_ok} {'✓' if dry_run_ok else '✗ FAIL'}")
    
    # Check 2: LIVE_TRADING
    live_trading_ok = not config.LIVE_TRADING
    logger.info(f"  LIVE_TRADING disabled: {live_trading_ok} {'✓' if live_trading_ok else '✗ FAIL'}")
    
    # Check 3: BROKER_MODE
    broker_mode_ok = EXECUTION_BROKER_MODE == "TRADIER_ONLY"
    logger.info(f"  BROKER_MODE == TRADIER_ONLY: {broker_mode_ok} ({EXECUTION_BROKER_MODE}) {'✓' if broker_mode_ok else '✗ FAIL'}")
    
    # Check 4: Kill switch
    kill_switch = (load_env("AUTO_MODE_KILL_SWITCH") or os.getenv("AUTO_MODE_KILL_SWITCH", "")).lower()
    kill_switch_enabled = kill_switch in ("true", "1", "yes", "on", "enabled")
    kill_switch_ok = not kill_switch_enabled
    logger.info(f"  AUTO_MODE_KILL_SWITCH disabled: {kill_switch_ok} {'✓' if kill_switch_ok else '✗ FAIL (KILL SWITCH ACTIVE)'}")
    
    # Daily limits
    max_daily_trades = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_daily_notional = float(load_env("AUTO_MAX_NOTIONAL_PER_DAY") or "50000")
    logger.info(f"  Daily limits: Max {max_daily_trades} trades, Max ${max_daily_notional:,.2f} notional")
    
    passed, failures = _validate_auto_mode_safety()
    
    if passed:
        logger.info("=" * 60)
        logger.info("ALL SAFETY CHECKS PASSED - Auto Mode can activate")
        logger.info("=" * 60)
    else:
        logger.error("=" * 60)
        logger.error("SAFETY CHECKS FAILED - Auto Mode will NOT activate")
        for failure in failures:
            logger.error(f"  ✗ {failure}")
        logger.error("=" * 60)
    
    return passed

# In-memory daily metrics (reset daily)
_daily_metrics: Dict[str, Any] = {
    "signals_seen": 0,
    "signals_accepted": 0,
    "signals_skipped": 0,
    "signals_blocked": 0,
    "executions_attempted": 0,
    "executions_succeeded": 0,
    "executions_failed": 0,
    "blocked_by_limits": 0,
    "blocked_by_safety": 0,
    "blocked_by_hours": 0,
    "skipped_duplicates": 0,
    "skipped_invalid_signal": 0,
    "skipped_auto_disabled": 0,
    "skipped_market_hours": 0,
    "total_notional_used": 0.0,
    "max_notional_used": 0.0,
    "trades_today_peak": 0,
    "trades_this_hour_peak": 0,
    "last_summary_date": None,
    "last_market_state": None,  # "open" or "closed" - track transitions
    "summary_emitted": False,
    # PnL tracking
    "trades_with_pnl": 0,
    "trades_without_pnl": 0,
    "estimated_gross_pnl": 0.0,
    "estimated_max_drawdown": 0.0,
    "estimated_win_count": 0,
    "estimated_loss_count": 0,
    "open_positions": []  # List of dicts with trade_id, entry_price, quantity, etc.
}


def _load_counters() -> Dict[str, Any]:
    """Load auto mode counters from file."""
    try:
        if os.path.exists(COUNTERS_FILE):
            with open(COUNTERS_FILE, "r") as f:
                counters = json.load(f)
                # Ensure notional tracking exists
                if "notional_today" not in counters:
                    counters["notional_today"] = 0.0
                return counters
    except:
        pass
    return {
        "trades_today": 0,
        "trades_this_hour": 0,
        "notional_today": 0.0,
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
        counters["notional_today"] = 0.0
        counters["last_trade_date"] = today
    
    if counters.get("last_trade_hour") != current_hour:
        counters["trades_this_hour"] = 0
        counters["last_trade_hour"] = current_hour
    
    return counters


def _reset_daily_metrics_if_needed(now: datetime) -> None:
    """Reset daily metrics if date has changed."""
    global _daily_metrics
    
    today = now.strftime("%Y-%m-%d")
    
    if _daily_metrics.get("last_summary_date") != today:
        # Emit summary for previous day if it exists and hasn't been emitted
        previous_date = _daily_metrics.get("last_summary_date")
        if previous_date is not None and not _daily_metrics.get("summary_emitted", False):
            _emit_daily_summary(previous_date)
        
        # Reset metrics for new day
        _daily_metrics = {
            "signals_seen": 0,
            "signals_accepted": 0,
            "signals_skipped": 0,
            "signals_blocked": 0,
            "executions_attempted": 0,
            "executions_succeeded": 0,
            "executions_failed": 0,
            "blocked_by_limits": 0,
            "blocked_by_safety": 0,
            "blocked_by_hours": 0,
            "skipped_duplicates": 0,
            "skipped_invalid_signal": 0,
            "skipped_auto_disabled": 0,
            "skipped_market_hours": 0,
            "total_notional_used": 0.0,
            "max_notional_used": 0.0,
            "trades_today_peak": 0,
            "trades_this_hour_peak": 0,
            "last_summary_date": today,
            "last_market_state": None,
            "summary_emitted": False,
            # PnL tracking
            "trades_with_pnl": 0,
            "trades_without_pnl": 0,
            "estimated_gross_pnl": 0.0,
            "estimated_max_drawdown": 0.0,
            "estimated_win_count": 0,
            "estimated_loss_count": 0,
            "open_positions": []
        }


def _emit_daily_summary(date_str: Optional[str] = None) -> None:
    """
    Emit the Auto Mode Daily Summary report.
    Ensures summary is emitted exactly once per day.
    
    Args:
        date_str: Date string (YYYY-MM-DD) or None to use today
    """
    global _daily_metrics
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Only prevent duplicate emissions for today's summary
    # If date_str is a previous day, always emit (catch-up)
    if date_str == today:
        if _daily_metrics.get("last_summary_date") == date_str and _daily_metrics.get("summary_emitted", False):
            return  # Already emitted for today
    
    # Mark as emitted (only if emitting for today)
    if date_str == today:
        _daily_metrics["summary_emitted"] = True
    
    # Get current counters and settings for snapshot
    counters = _load_counters()
    max_daily = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_hourly = int(load_env("AUTO_MAX_TRADES_PER_HOUR") or "3")
    daily_risk_used, max_daily_risk = _get_daily_risk_info()
    
    # Use metrics with safe defaults
    signals_seen = _daily_metrics.get("signals_seen", 0)
    signals_accepted = _daily_metrics.get("signals_accepted", 0)
    signals_skipped = _daily_metrics.get("signals_skipped", 0)
    signals_blocked = _daily_metrics.get("signals_blocked", 0)
    executions_attempted = _daily_metrics.get("executions_attempted", 0)
    executions_succeeded = _daily_metrics.get("executions_succeeded", 0)
    executions_failed = _daily_metrics.get("executions_failed", 0)
    
    blocked_by_limits = _daily_metrics.get("blocked_by_limits", 0)
    blocked_by_safety = _daily_metrics.get("blocked_by_safety", 0)
    blocked_by_hours = _daily_metrics.get("blocked_by_hours", 0)
    skipped_duplicates = _daily_metrics.get("skipped_duplicates", 0)
    skipped_invalid_signal = _daily_metrics.get("skipped_invalid_signal", 0)
    skipped_auto_disabled = _daily_metrics.get("skipped_auto_disabled", 0)
    skipped_market_hours = _daily_metrics.get("skipped_market_hours", 0)
    
    max_notional_used = _daily_metrics.get("max_notional_used", daily_risk_used)
    trades_today_peak = max(_daily_metrics.get("trades_today_peak", 0), counters.get("trades_today", 0))
    trades_this_hour_peak = max(_daily_metrics.get("trades_this_hour_peak", 0), counters.get("trades_this_hour", 0))
    
    # Emit banner-style summary
    logger.info("=" * 60)
    logger.info("AUTO MODE DAILY SUMMARY — PAPER TRADING ONLY")
    logger.info(f"Date: {date_str}")
    logger.info("-" * 60)
    logger.info(f"Signals seen: {signals_seen}")
    logger.info(f"Accepted: {signals_accepted}")
    logger.info(f"Skipped: {signals_skipped}")
    logger.info(f"Blocked: {signals_blocked}")
    logger.info("")
    logger.info(f"Trades executed (paper): {executions_succeeded}")
    logger.info(f"Execution failures: {executions_failed}")
    logger.info("")
    logger.info("-" * 60)
    logger.info("BLOCK REASONS:")
    logger.info(f"  - Daily trade limit: {blocked_by_limits}")
    logger.info(f"  - Hourly trade limit: {blocked_by_hours}")
    logger.info(f"  - Risk limit: 0")  # Not currently tracked separately
    logger.info(f"  - Safety guardrails: {blocked_by_safety}")
    logger.info(f"  - Market hours: {skipped_market_hours}")
    logger.info(f"  - Duplicate signals: {skipped_duplicates}")
    logger.info("")
    logger.info("-" * 60)
    logger.info("NOTIONAL USAGE:")
    if max_daily_risk > 0:
        logger.info(f"  - Max notional used: ${max_notional_used:,.2f} / ${max_daily_risk:,.2f}")
    else:
        logger.info(f"  - Max notional used: ${max_notional_used:,.2f} / N/A")
    logger.info(f"  - Trades today: {trades_today_peak} / {max_daily}")
    logger.info(f"  - Peak hourly trades: {trades_this_hour_peak} / {max_hourly}")
    logger.info("")
    logger.info("-" * 60)
    logger.info("STATUS:")
    logger.info("PAPER MODE ONLY — NO LIVE ORDERS SENT")
    logger.info("")
    logger.info("-" * 60)
    logger.info("PAPER PNL ESTIMATION (APPROXIMATE)")
    
    # PnL metrics
    trades_evaluated = executions_succeeded
    trades_with_pnl = _daily_metrics.get("trades_with_pnl", 0)
    trades_without_pnl = _daily_metrics.get("trades_without_pnl", 0)
    estimated_gross_pnl = _daily_metrics.get("estimated_gross_pnl", 0.0)
    estimated_max_drawdown = _daily_metrics.get("estimated_max_drawdown", 0.0)
    estimated_win_count = _daily_metrics.get("estimated_win_count", 0)
    estimated_loss_count = _daily_metrics.get("estimated_loss_count", 0)
    
    logger.info(f"Trades evaluated: {trades_evaluated}")
    logger.info(f"Trades with PnL estimate: {trades_with_pnl}")
    logger.info(f"Trades missing data: {trades_without_pnl}")
    logger.info(f"Estimated gross PnL: ${estimated_gross_pnl:,.2f}")
    logger.info(f"Estimated max drawdown: ${estimated_max_drawdown:,.2f}")
    logger.info(f"Win / Loss: {estimated_win_count} / {estimated_loss_count}")
    logger.info("NOTE: Estimates only — no live fills used")
    logger.info("-" * 60)
    logger.info("=" * 60)
    
    # Mark summary as emitted for this date
    _daily_metrics["last_summary_date"] = date_str


def _estimate_entry_price(trade_intent: TradeIntent, parsed_signal: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """
    Estimate entry price for a trade.
    
    Priority:
    1. limit_price from trade_intent
    2. limit_max for debit spreads, limit_min for credit spreads
    3. None (UNKNOWN) if no price data available
    
    Args:
        trade_intent: The TradeIntent object
        parsed_signal: Optional parsed signal dict for additional context
        
    Returns:
        Estimated entry price per contract/share, or None if unavailable
    """
    # Use limit_price if available
    if trade_intent.limit_price is not None:
        return trade_intent.limit_price
    
    # For spreads, use limit_max for debit, limit_min for credit
    if trade_intent.limit_max is not None:
        # Check if this is a debit or credit spread
        if parsed_signal:
            limit_kind = parsed_signal.get("limit_kind", "").upper()
            if limit_kind == "DEBIT" and trade_intent.limit_max:
                return trade_intent.limit_max
            elif limit_kind == "CREDIT" and trade_intent.limit_min:
                return trade_intent.limit_min
        # Default: use limit_max for debit assumption
        return trade_intent.limit_max
    
    if trade_intent.limit_min is not None:
        return trade_intent.limit_min
    
    # No price data available
    return None


def _estimate_exit_price(execution_result: ExecutionResult, trade_intent: TradeIntent) -> Optional[float]:
    """
    Estimate exit price for a trade.
    
    Priority:
    1. fill_price from execution_result if available
    2. None (UNKNOWN) - we can't get market data without broker calls
    
    Args:
        execution_result: ExecutionResult object
        trade_intent: The TradeIntent object
        
    Returns:
        Estimated exit price per contract/share, or None if unavailable
    """
    # Use fill_price if available from execution result
    if execution_result.fill_price is not None:
        return execution_result.fill_price
    
    # Can't estimate exit without market data (no broker calls allowed)
    return None


def _calculate_spread_pnl(
    entry_price: float,
    exit_price: Optional[float],
    quantity: int,
    limit_kind: str
) -> Optional[float]:
    """
    Calculate PnL for a spread trade.
    
    Args:
        entry_price: Entry price per contract
        exit_price: Exit price per contract (None if unknown)
        quantity: Number of contracts
        limit_kind: "DEBIT" or "CREDIT"
        
    Returns:
        Estimated PnL in dollars, or None if exit_price is unavailable
    """
    if exit_price is None:
        return None
    
    if limit_kind.upper() == "DEBIT":
        # Debit spread: profit = (exit_price - entry_price) * 100 * quantity
        pnl = (exit_price - entry_price) * 100 * quantity
    elif limit_kind.upper() == "CREDIT":
        # Credit spread: profit = (entry_price - exit_price) * 100 * quantity
        pnl = (entry_price - exit_price) * 100 * quantity
    else:
        # Unknown spread type
        return None
    
    return pnl


def _track_trade_pnl(
    trade_intent: TradeIntent,
    execution_result: ExecutionResult,
    parsed_signal: Optional[Dict[str, Any]] = None
) -> None:
    """
    Track PnL for an executed trade.
    
    Args:
        trade_intent: The TradeIntent that was executed
        execution_result: ExecutionResult from execution
        parsed_signal: Optional parsed signal dict
    """
    global _daily_metrics
    
    try:
        # Estimate entry price
        entry_price = _estimate_entry_price(trade_intent, parsed_signal)
        
        if entry_price is None:
            # No entry price available - can't estimate PnL
            _daily_metrics["trades_without_pnl"] = _daily_metrics.get("trades_without_pnl", 0) + 1
            logger.debug(f"PnL unavailable for {trade_intent.underlying}: No entry price data")
            return
        
        # Estimate exit price
        exit_price = _estimate_exit_price(execution_result, trade_intent)
        
        if exit_price is None:
            # No exit price available - mark as open position or unknown
            _daily_metrics["trades_without_pnl"] = _daily_metrics.get("trades_without_pnl", 0) + 1
            
            # Track as open position for potential later PnL calculation
            limit_kind = "DEBIT"
            if parsed_signal:
                limit_kind = parsed_signal.get("limit_kind", "DEBIT")
            
            open_position = {
                "trade_id": trade_intent.id,
                "underlying": trade_intent.underlying,
                "entry_price": entry_price,
                "quantity": trade_intent.quantity,
                "limit_kind": limit_kind,
                "entry_time": datetime.now().isoformat()
            }
            _daily_metrics["open_positions"] = _daily_metrics.get("open_positions", [])
            _daily_metrics["open_positions"].append(open_position)
            
            logger.debug(f"PnL unavailable for {trade_intent.underlying}: No exit price data (tracking as open)")
            return
        
        # Calculate PnL
        limit_kind = "DEBIT"
        if parsed_signal:
            limit_kind = parsed_signal.get("limit_kind", "DEBIT")
        
        pnl = _calculate_spread_pnl(entry_price, exit_price, trade_intent.quantity, limit_kind)
        
        if pnl is None:
            _daily_metrics["trades_without_pnl"] = _daily_metrics.get("trades_without_pnl", 0) + 1
            logger.debug(f"PnL unavailable for {trade_intent.underlying}: Could not calculate")
            return
        
        # Track PnL metrics
        _daily_metrics["trades_with_pnl"] = _daily_metrics.get("trades_with_pnl", 0) + 1
        _daily_metrics["estimated_gross_pnl"] = _daily_metrics.get("estimated_gross_pnl", 0.0) + pnl
        
        # Track wins/losses
        if pnl > 0:
            _daily_metrics["estimated_win_count"] = _daily_metrics.get("estimated_win_count", 0) + 1
        elif pnl < 0:
            _daily_metrics["estimated_loss_count"] = _daily_metrics.get("estimated_loss_count", 0) + 1
        
        # Track max drawdown (most negative cumulative PnL)
        cumulative_pnl = _daily_metrics.get("estimated_gross_pnl", 0.0)
        if cumulative_pnl < _daily_metrics.get("estimated_max_drawdown", 0.0):
            _daily_metrics["estimated_max_drawdown"] = cumulative_pnl
        
        # Log per-trade PnL (INFO level for visibility)
        logger.info(f"Estimated PnL for {trade_intent.underlying}: ${pnl:,.2f} "
                   f"(Entry: ${entry_price:.2f}, Exit: ${exit_price:.2f}, Qty: {trade_intent.quantity})")
        
    except Exception as e:
        # Fail gracefully - log and continue
        logger.debug(f"Error tracking PnL for {trade_intent.underlying}: {e}")
        _daily_metrics["trades_without_pnl"] = _daily_metrics.get("trades_without_pnl", 0) + 1


def _get_daily_risk_info() -> tuple[float, float]:
    """
    Get current daily risk used and max daily risk limit.
    
    Returns:
        (daily_risk_used, max_daily_risk) in dollars
    """
    daily_risk_used = 0.0
    max_daily_risk = 0.0
    
    # Try to load from state.json
    try:
        if os.path.exists(config.STATE_FILE):
            with open(config.STATE_FILE, "r") as f:
                state_data = json.load(f)
                daily_risk_used = float(state_data.get("daily_risk_used", 0.0))
    except Exception:
        pass
    
    # Get max daily risk from settings
    try:
        settings = load_settings()
        max_daily_risk_pct = settings.get("MAX_DAILY_RISK_PCT", 10) / 100.0
        # Use a default account equity for calculation (paper mode uses $100k simulated)
        account_equity = 100000.0
        max_daily_risk = account_equity * max_daily_risk_pct
    except Exception:
        pass
    
    return daily_risk_used, max_daily_risk


def _format_signal_summary(signal: Optional[Dict[str, Any]]) -> str:
    """
    Format a human-readable signal summary.
    
    Args:
        signal: Signal dict from list_recent_signals() or None
        
    Returns:
        Formatted string like "SPY 0DTE CALL CREDIT SPREAD"
    """
    if not signal:
        return "UNKNOWN"
    
    parsed_signal = signal.get("parsed_signal", {})
    ticker = parsed_signal.get("ticker", signal.get("ticker", "UNKNOWN"))
    strategy = parsed_signal.get("strategy", signal.get("strategy", "UNKNOWN"))
    
    # Format strategy name
    strategy_map = {
        "CALL_DEBIT_SPREAD": "CALL DEBIT SPREAD",
        "CALL_CREDIT_SPREAD": "CALL CREDIT SPREAD",
        "PUT_DEBIT_SPREAD": "PUT DEBIT SPREAD",
        "PUT_CREDIT_SPREAD": "PUT CREDIT SPREAD",
        "LONG_STOCK": "LONG STOCK",
        "LONG_OPTION": "LONG OPTION",
        "EXIT": "EXIT"
    }
    strategy_display = strategy_map.get(strategy, strategy)
    
    # Add expiration info if available
    expiration = parsed_signal.get("expiration")
    exp_str = ""
    if expiration:
        try:
            from datetime import date as date_type
            today = datetime.now().date()
            
            # Handle different expiration formats
            if isinstance(expiration, date_type):
                exp_date_only = expiration
            elif isinstance(expiration, datetime):
                exp_date_only = expiration.date()
            elif isinstance(expiration, str):
                # Try ISO format first
                if "T" in expiration or "Z" in expiration:
                    exp_date = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
                    exp_date_only = exp_date.date()
                else:
                    # Try date-only format (YYYY-MM-DD)
                    exp_date_only = datetime.strptime(expiration, "%Y-%m-%d").date()
            else:
                exp_date_only = None
            
            if exp_date_only:
                days_to_exp = (exp_date_only - today).days
                if days_to_exp == 0:
                    exp_str = " 0DTE"
                elif days_to_exp == 1:
                    exp_str = " 1DTE"
                elif days_to_exp > 1:
                    exp_str = f" {days_to_exp}DTE"
        except Exception:
            pass
    
    return f"{ticker}{exp_str} {strategy_display}"


def _log_auto_decision(
    signal: Optional[Dict[str, Any]],
    decision: str,
    reasons: List[str],
    counters: Dict[str, Any],
    max_daily: int,
    max_hourly: int
) -> None:
    """
    Log a structured decision entry for Auto Mode signal evaluation.
    Also tracks metrics for daily summary.
    
    Args:
        signal: Signal dict from list_recent_signals() or None
        decision: "ACCEPTED" | "SKIPPED" | "BLOCKED"
        reasons: List of reason strings explaining the decision
        counters: Current counter dict
        max_daily: Maximum trades per day
        max_hourly: Maximum trades per hour
    """
    global _daily_metrics
    
    signal_summary = _format_signal_summary(signal)
    
    trades_today = counters.get("trades_today", 0)
    trades_this_hour = counters.get("trades_this_hour", 0)
    
    daily_risk_used, max_daily_risk = _get_daily_risk_info()
    
    # Track metrics
    if signal is not None:  # Only count actual signals, not system-level skips
        _daily_metrics["signals_seen"] = _daily_metrics.get("signals_seen", 0) + 1
    
    if decision == "ACCEPTED":
        _daily_metrics["signals_accepted"] = _daily_metrics.get("signals_accepted", 0) + 1
    elif decision == "SKIPPED":
        _daily_metrics["signals_skipped"] = _daily_metrics.get("signals_skipped", 0) + 1
        # Categorize skip reasons
        reason_text_lower = "; ".join(reasons).lower()
        if "duplicate" in reason_text_lower or "already executed" in reason_text_lower:
            _daily_metrics["skipped_duplicates"] = _daily_metrics.get("skipped_duplicates", 0) + 1
        elif "invalid" in reason_text_lower or "build failed" in reason_text_lower:
            _daily_metrics["skipped_invalid_signal"] = _daily_metrics.get("skipped_invalid_signal", 0) + 1
        elif "auto mode disabled" in reason_text_lower:
            _daily_metrics["skipped_auto_disabled"] = _daily_metrics.get("skipped_auto_disabled", 0) + 1
        elif "trading window" in reason_text_lower or "market" in reason_text_lower:
            _daily_metrics["skipped_market_hours"] = _daily_metrics.get("skipped_market_hours", 0) + 1
    elif decision == "BLOCKED":
        _daily_metrics["signals_blocked"] = _daily_metrics.get("signals_blocked", 0) + 1
        # Categorize block reasons
        reason_text_lower = "; ".join(reasons).lower()
        if "daily limit" in reason_text_lower:
            _daily_metrics["blocked_by_limits"] = _daily_metrics.get("blocked_by_limits", 0) + 1
        elif "hourly limit" in reason_text_lower:
            _daily_metrics["blocked_by_hours"] = _daily_metrics.get("blocked_by_hours", 0) + 1
        elif "preflight" in reason_text_lower or "safety" in reason_text_lower:
            _daily_metrics["blocked_by_safety"] = _daily_metrics.get("blocked_by_safety", 0) + 1
    
    # Track peak values
    _daily_metrics["trades_today_peak"] = max(_daily_metrics.get("trades_today_peak", 0), trades_today)
    _daily_metrics["trades_this_hour_peak"] = max(_daily_metrics.get("trades_this_hour_peak", 0), trades_this_hour)
    _daily_metrics["max_notional_used"] = max(_daily_metrics.get("max_notional_used", 0.0), daily_risk_used)
    
    # Format reasons
    reason_text = "; ".join(reasons) if reasons else "No reason provided"
    
    # Build decision log banner
    logger.info("=" * 60)
    logger.info("AUTO MODE DECISION")
    logger.info(f"Signal: {signal_summary}")
    logger.info(f"Decision: {decision}")
    logger.info(f"Reason: {reason_text}")
    logger.info(f"Trades today: {trades_today} / {max_daily}")
    logger.info(f"Trades this hour: {trades_this_hour} / {max_hourly}")
    
    if max_daily_risk > 0:
        logger.info(f"Notional used: ${daily_risk_used:,.2f} / ${max_daily_risk:,.2f}")
    else:
        logger.info("Notional used: N/A")
    
    if decision == "ACCEPTED":
        logger.info("Proceeding to execution (paper)")
    
    logger.info("=" * 60)


def get_auto_status() -> Dict[str, Any]:
    """
    Get current auto mode status.
    
    OBSERVATIONAL ONLY — NOT USED FOR DECISION MAKING
    Returns execution state (enabled/disabled, limits, last action).
    Counters are for safety limit enforcement, not performance analysis.
    """
    global _auto_enabled, _safety_checks_passed
    
    counters = _load_counters()
    window_status = is_within_auto_trading_window()
    
    max_daily = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_hourly = int(load_env("AUTO_MAX_TRADES_PER_HOUR") or "3")
    max_notional = float(load_env("AUTO_MAX_NOTIONAL_PER_DAY") or "50000")
    poll_seconds = int(load_env("AUTO_POLL_SECONDS") or "30")
    
    safety_passed, safety_failures = _validate_auto_mode_safety()
    
    return {
        "enabled": _auto_enabled,
        "safety_checks_passed": safety_passed,
        "safety_failures": safety_failures if not safety_passed else [],
        "within_window": window_status.get("within_window", False),
        "window_status": window_status,
        "trades_today": counters.get("trades_today", 0),
        "trades_this_hour": counters.get("trades_this_hour", 0),
        "notional_today": counters.get("notional_today", 0.0),
        "max_daily": max_daily,
        "max_hourly": max_hourly,
        "max_notional": max_notional,
        "poll_seconds": poll_seconds,
        "last_tick_time": counters.get("last_tick_time"),
        "last_action": counters.get("last_action"),
        "thread_alive": _auto_thread is not None and _auto_thread.is_alive()
    }


def set_auto_enabled(enabled: bool) -> Dict[str, Any]:
    """Enable or disable auto mode."""
    global _auto_enabled
    
    was_enabled = _auto_enabled
    _auto_enabled = enabled
    
    if enabled:
        _start_auto_thread()
    else:
        if was_enabled:
            # Auto mode was just disabled - emit summary
            logger.info("Auto mode disabled - emitting daily summary")
            _emit_daily_summary()
        _stop_auto_thread()
    
    return get_auto_status()


def initialize_auto_mode():
    """
    Initialize Auto Mode based on environment variable.
    Called at application startup.
    """
    global _auto_enabled
    
    auto_enabled_env = (load_env("AUTO_MODE_ENABLED") or os.getenv("AUTO_MODE_ENABLED", "")).lower() == "true"
    
    if auto_enabled_env:
        logger.info("AUTO_MODE_ENABLED=true detected - Initializing Auto Mode")
        _auto_enabled = True
        _start_auto_thread()
    else:
        logger.info("AUTO_MODE_ENABLED not set or false - Auto Mode disabled")
        _auto_enabled = False


def _start_auto_thread():
    """Start the auto mode background thread."""
    global _auto_thread, _stop_event, _safety_checks_passed, _auto_enabled
    
    if _auto_thread is not None and _auto_thread.is_alive():
        return
    
    # Run safety pre-flight checks
    _safety_checks_passed = _log_auto_mode_safety_checks()
    
    if not _safety_checks_passed:
        logger.error("Auto Mode thread will NOT start due to failed safety checks")
        _auto_enabled = False
        return
    
    _stop_event.clear()
    _auto_thread = threading.Thread(target=_auto_loop, daemon=True)
    _auto_thread.start()
    
    # High-visibility banner
    max_daily_trades = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_daily_notional = float(load_env("AUTO_MAX_NOTIONAL_PER_DAY") or "50000")
    max_hourly = int(load_env("AUTO_MAX_TRADES_PER_HOUR") or "3")
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("  AUTO MODE ACTIVE — PAPER TRADING ONLY")
    logger.info("=" * 70)
    logger.info(f"  Mode: PAPER TRADING (DRY_RUN=True, LIVE_TRADING=False)")
    logger.info(f"  Broker: TRADIER_ONLY (Sandbox)")
    logger.info(f"  Daily Limits: {max_daily_trades} trades, ${max_daily_notional:,.2f} notional")
    logger.info(f"  Hourly Limit: {max_hourly} trades")
    logger.info(f"  Poll Interval: {int(load_env('AUTO_POLL_SECONDS') or '30')} seconds")
    logger.info("  Status: ACTIVE - Monitoring signals and executing trades")
    logger.info("=" * 70)
    logger.info("")
    
    logger.info("Auto mode thread started")


def _stop_auto_thread():
    """Stop the auto mode background thread."""
    global _auto_thread, _stop_event
    
    _stop_event.set()
    if _auto_thread is not None:
        _auto_thread.join(timeout=5)
    _auto_thread = None
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("  AUTO MODE DISABLED")
    logger.info("=" * 70)
    logger.info("  Status: STOPPED - No automated trading")
    logger.info("=" * 70)
    logger.info("")
    
    logger.info("Auto mode thread stopped")


def emit_auto_mode_summary() -> None:
    """
    Public function to emit Auto Mode daily summary.
    Can be called on application shutdown or by external code.
    Ensures summary is emitted exactly once per day.
    """
    global _daily_metrics
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_summary_date = _daily_metrics.get("last_summary_date")
    
    # Only emit if we haven't already emitted for today
    if last_summary_date != today:
        _emit_daily_summary(today)


def _auto_loop():
    """Main auto mode loop."""
    global _auto_enabled, _daily_metrics
    
    poll_seconds = int(load_env("AUTO_POLL_SECONDS") or "30")
    
    while not _stop_event.is_set():
        try:
            if _auto_enabled:
                # Check for market close transition
                window_status = is_within_auto_trading_window()
                current_market_state = "open" if window_status.get("is_market_open", False) else "closed"
                last_state = _daily_metrics.get("last_market_state")
                
                # Detect market close transition (open -> closed)
                if last_state == "open" and current_market_state == "closed":
                    logger.info("Market close detected - emitting Auto Mode daily summary")
                    _emit_daily_summary()
                
                _daily_metrics["last_market_state"] = current_market_state
                
                auto_tick()
        except Exception as e:
            logger.error(f"Auto tick error: {e}")
        
        for _ in range(poll_seconds):
            if _stop_event.is_set():
                break
            time.sleep(1)
    
    # Emit summary on thread shutdown
    logger.info("Auto mode thread stopping - emitting daily summary")
    _emit_daily_summary()


def auto_tick() -> Dict[str, Any]:
    """
    Execute one auto mode tick.
    
    Returns dict with action taken and details.
    """
    global _safety_checks_passed, _auto_enabled
    
    # Re-validate safety checks on each tick
    safety_passed, failures = _validate_auto_mode_safety()
    if not safety_passed:
        if _safety_checks_passed:  # Was passing, now failing
            logger.error("AUTO MODE SAFETY CHECK FAILED - Disabling Auto Mode")
            for failure in failures:
                logger.error(f"  Safety failure: {failure}")
            _auto_enabled = False
            _safety_checks_passed = False
        counters = _load_counters()
        counters["last_action"] = f"BLOCKED: Safety check failed - {failures[0]}"
        _save_counters(counters)
        return {"action": "blocked", "reason": f"Safety check failed: {failures[0]}"}
    
    _safety_checks_passed = True
    
    now = datetime.now()
    counters = _load_counters()
    counters = _reset_counters_if_needed(counters, now)
    _reset_daily_metrics_if_needed(now)
    counters["last_tick_time"] = now.isoformat()
    
    max_daily = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_hourly = int(load_env("AUTO_MAX_TRADES_PER_HOUR") or "3")
    
    auto_enabled_env = (load_env("AUTO_MODE_ENABLED") or "").lower() == "true"
    if not _auto_enabled and not auto_enabled_env:
        counters["last_action"] = "SKIP: Auto mode disabled"
        _save_counters(counters)
        _log_auto_decision(
            signal=None,
            decision="SKIPPED",
            reasons=["Auto mode disabled"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "skip", "reason": "Auto mode disabled"}
    
<<<<<<< Updated upstream
    window_status = is_within_auto_trading_window()
    if not window_status.get("within_window", False):
        window_reason = window_status.get("reason", "Outside trading window")
        counters["last_action"] = f"PAUSE: {window_reason}"
        _save_counters(counters)
        _log_auto_decision(
            signal=None,
            decision="SKIPPED",
            reasons=[f"Outside trading window: {window_reason}"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "pause", "reason": window_reason}
=======
    # PAPER MODE (DRY_RUN=True): Skip market window checks
    # Signal-based replay doesn't require market hours
    if not config.DRY_RUN:
    # PAPER MODE (DRY_RUN=True): Skip market window checks
    # Signal-based replay doesn't require market hours
    if not config.DRY_RUN:
        window_status = is_within_auto_trading_window()
        if not window_status.get("within_window", False):
            counters["last_action"] = f"PAUSE: {window_status.get('reason', 'Outside trading window')}"
            _save_counters(counters)
            return {"action": "pause", "reason": window_status.get("reason")}
    else:
        # PAPER MODE: Market hours not required for signal-based replay
        logger.debug("PAPER MODE — Market window check skipped (signal-based replay)")
    else:
        # PAPER MODE: Market hours not required for signal-based replay
        logger.debug("PAPER MODE — Market window check skipped (signal-based replay)")
    
    max_daily = int(load_env("AUTO_MAX_TRADES_PER_DAY") or "10")
    max_hourly = int(load_env("AUTO_MAX_TRADES_PER_HOUR") or "3")
    max_notional = float(load_env("AUTO_MAX_NOTIONAL_PER_DAY") or "50000")
>>>>>>> Stashed changes
    
    if counters.get("trades_today", 0) >= max_daily:
        counters["last_action"] = f"LIMIT: Daily trade limit reached ({max_daily})"
        _save_counters(counters)
<<<<<<< Updated upstream
        _log_auto_decision(
            signal=None,
            decision="BLOCKED",
            reasons=[f"Daily trade limit reached ({counters.get('trades_today', 0)} / {max_daily})"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "limit", "reason": f"Daily limit reached ({max_daily})"}
=======
        return {"action": "limit", "reason": f"Daily trade limit reached ({max_daily})"}
>>>>>>> Stashed changes
    
    if counters.get("trades_this_hour", 0) >= max_hourly:
        counters["last_action"] = f"LIMIT: Hourly limit reached ({max_hourly})"
        _save_counters(counters)
        _log_auto_decision(
            signal=None,
            decision="BLOCKED",
            reasons=[f"Hourly trade limit reached ({counters.get('trades_this_hour', 0)} / {max_hourly})"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "limit", "reason": f"Hourly limit reached ({max_hourly})"}
    
    if counters.get("notional_today", 0.0) >= max_notional:
        counters["last_action"] = f"LIMIT: Daily notional limit reached (${max_notional:,.2f})"
        _save_counters(counters)
        return {"action": "limit", "reason": f"Daily notional limit reached (${max_notional:,.2f})"}
    
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
        _log_auto_decision(
            signal=None,
            decision="SKIPPED",
            reasons=["No executable signals found"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "idle", "reason": "No executable signals"}
    
    post_id = selected.get("post_id", "")
    ticker = selected.get("ticker", "unknown")
    
    if is_executed(post_id):
        counters["last_action"] = f"SKIP: {ticker} already executed (dedupe)"
        _save_counters(counters)
        _log_auto_decision(
            signal=selected,
            decision="SKIPPED",
            reasons=["Already executed (dedupe check)"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "skip", "reason": "Already executed (dedupe)"}
    
    result = build_intent_and_preflight(selected, "paper")
    
    trade_intent_dict = result.get("trade_intent")
    preflight_result = result.get("preflight_result")
    
    if not trade_intent_dict:
        error = result.get("trade_intent_error", "Unknown error")
        counters["last_action"] = f"SKIP: {ticker} - {error}"
        _save_counters(counters)
        _log_auto_decision(
            signal=selected,
            decision="SKIPPED",
            reasons=[f"Trade intent build failed: {error}"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "skip", "reason": error, "ticker": ticker}
    
    if preflight_result and not preflight_result.get("ok"):
        blocked = preflight_result.get("blocked_reason", "Preflight failed")
        counters["last_action"] = f"BLOCKED: {ticker} - {blocked}"
        _save_counters(counters)
        _log_auto_decision(
            signal=selected,
            decision="BLOCKED",
            reasons=[f"Preflight check failed: {blocked}"],
            counters=counters,
            max_daily=max_daily,
            max_hourly=max_hourly
        )
        return {"action": "blocked", "reason": blocked, "ticker": ticker}
    
    # All checks passed - log ACCEPTED decision before execution
    _log_auto_decision(
        signal=selected,
        decision="ACCEPTED",
        reasons=["All safety checks passed"],
        counters=counters,
        max_daily=max_daily,
        max_hourly=max_hourly
    )
    
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
        
        # Track execution attempt
        _daily_metrics["executions_attempted"] = _daily_metrics.get("executions_attempted", 0) + 1
        
        execution_result = execute_trade(trade_intent)
        
<<<<<<< Updated upstream
        if execution_result.status in ("filled", "accepted", "success"):
            _daily_metrics["executions_succeeded"] = _daily_metrics.get("executions_succeeded", 0) + 1
            
            # Track PnL estimation (observational only, does not affect execution)
            parsed_signal_data = selected.get("parsed_signal", {})
            _track_trade_pnl(trade_intent, execution_result, parsed_signal_data)
            
=======
        # Consistency check: SUBMITTED/FILLED status must have order_id
        if execution_result.status in ("SUBMITTED", "FILLED") and not execution_result.order_id:
            logger.error(f"CONSISTENCY ERROR in auto_mode - Intent {trade_intent.id} marked {execution_result.status} but no broker order_id")
            logger.error(f"  Broker: {execution_result.broker}, Message: {execution_result.message}")
        
        if execution_result.status in ("filled", "accepted", "success", "SUBMITTED", "FILLED"):
>>>>>>> Stashed changes
            mark_executed(
                post_id=post_id,
                execution_mode="paper",
                trade_intent_id=trade_intent.id,
                result_status=execution_result.status,
                underlying=trade_intent.underlying
            )
            
            counters["trades_today"] = counters.get("trades_today", 0) + 1
            counters["trades_this_hour"] = counters.get("trades_this_hour", 0) + 1
            
            # Track notional exposure for safety limit enforcement (not performance analysis)
            notional = 0.0
            if execution_result.fill_price:
                notional = execution_result.fill_price * execution_result.filled_quantity * 100  # Options multiplier
            elif trade_intent.limit_price:
                notional = trade_intent.limit_price * trade_intent.quantity * 100
            elif trade_intent.limit_max:
                notional = trade_intent.limit_max * trade_intent.quantity * 100
            
            counters["notional_today"] = counters.get("notional_today", 0.0) + notional
            # OBSERVATIONAL ONLY — NOT USED FOR DECISION MAKING
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
            _daily_metrics["executions_failed"] = _daily_metrics.get("executions_failed", 0) + 1
            counters["last_action"] = f"FAILED: {ticker} - {execution_result.message}"
            _save_counters(counters)
            return {"action": "failed", "ticker": ticker, "reason": execution_result.message}
    
    except Exception as e:
        _daily_metrics["executions_failed"] = _daily_metrics.get("executions_failed", 0) + 1
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
