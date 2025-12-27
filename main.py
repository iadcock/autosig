"""
Main entry point for the trading bot.
Runs the polling loop to fetch, parse, and execute trade alerts.

EDUCATIONAL USE ONLY - PAPER TRADING
This bot is designed for learning purposes. All trades go to paper accounts by default.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import config
from models import ParsedSignal, TradeState
from parser import parse_alert, get_alert_hash
from scraper_whop import get_alerts
from risk import RiskManager
from summary import (
    get_today_market_close_run_time,
    get_next_summary_run_time,
    write_daily_summary,
    NY_TZ
)
from jsonl_logger import (
    log_raw_alert,
    log_parsed_alert,
    log_execution_plan
)
from settings_store import EXECUTION_BROKER_MODE, VALID_BROKER_MODES
import broker_alpaca

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


SIGNALS_LOG_FILE = "logs/parsed_signals.csv"


def validate_broker_mode() -> None:
    """
    Validate broker mode configuration at startup.
    Only TRADIER_ONLY is allowed in production.
    Exits safely if broker mode is invalid or unsupported.
    """
    broker_mode = EXECUTION_BROKER_MODE
    allowed_modes = VALID_BROKER_MODES
    
    if broker_mode not in allowed_modes:
        logger.error("=" * 60)
        logger.error("FATAL: Invalid or unsupported BROKER_MODE configuration")
        logger.error(f"  Current value: '{broker_mode}'")
        logger.error(f"  Allowed values: {', '.join(allowed_modes)}")
        logger.error("  Tradier is the only supported broker in production.")
        logger.error("  Application will exit to prevent unsafe execution.")
        logger.error("=" * 60)
        sys.exit(1)
    
    # Check if BROKER_MODE env var was explicitly set to something invalid
    broker_mode_env = os.getenv("BROKER_MODE", "").strip().upper()
    if broker_mode_env and broker_mode_env not in allowed_modes:
        logger.error("=" * 60)
        logger.error("FATAL: BROKER_MODE environment variable has invalid value")
        logger.error(f"  Environment value: '{broker_mode_env}'")
        logger.error(f"  Allowed values: {', '.join(allowed_modes)}")
        logger.error("  Tradier is the only supported broker in production.")
        logger.error("  Application will exit to prevent unsafe execution.")
        logger.error("=" * 60)
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("BROKER MODE VALIDATION")
    logger.info(f"  Selected broker mode: {broker_mode}")
    logger.info(f"  Allowed modes: {', '.join(allowed_modes)}")
    logger.info("  Alpaca execution paths are DISABLED")
    logger.info("  Only Tradier execution is enabled")
    logger.info("=" * 60)


def setup_file_logging() -> None:
    """Set up file logging to trades.log."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    file_handler = logging.FileHandler(config.TRADE_LOG_FILE)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    logging.getLogger().addHandler(file_handler)
    
    if not os.path.exists(SIGNALS_LOG_FILE):
        with open(SIGNALS_LOG_FILE, 'w') as f:
            f.write("timestamp,ticker,strategy,expiration,size_pct,limit_min,limit_max,limit_kind,legs,status\n")


def log_parsed_signal(signal: ParsedSignal, status: str = "PARSED") -> None:
    """Log a parsed signal to the CSV file for download."""
    try:
        legs_str = ""
        if signal.legs:
            legs_str = " | ".join([
                f"{leg.side} {leg.quantity}x ${leg.strike} {leg.option_type}"
                for leg in signal.legs
            ])
        
        with open(SIGNALS_LOG_FILE, 'a') as f:
            f.write(
                f"{datetime.now().isoformat()},"
                f"{signal.ticker},"
                f"{signal.strategy},"
                f"{signal.expiration},"
                f"{signal.size_pct:.2%},"
                f"${signal.limit_min:.2f},"
                f"${signal.limit_max:.2f},"
                f"{signal.limit_kind},"
                f"\"{legs_str}\","
                f"{status}\n"
            )
    except Exception as e:
        logger.error(f"Failed to log signal: {e}")


def load_state() -> TradeState:
    """Load state from state.json file."""
    if os.path.exists(config.STATE_FILE):
        try:
            with open(config.STATE_FILE, 'r') as f:
                data = json.load(f)
                return TradeState(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load state file: {e}. Starting fresh.")
    
    return TradeState()


def save_state(state: TradeState) -> None:
    """Save state to state.json file."""
    try:
        with open(config.STATE_FILE, 'w') as f:
            json.dump(state.model_dump(), f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def should_reset_daily_limits(state: TradeState) -> bool:
    """Check if we should reset daily limits (new trading day)."""
    today = date.today().isoformat()
    return state.last_reset_date != today


def _determine_non_signal_reason(alert_text: str) -> str:
    """Determine why an alert was classified as non-signal."""
    text_lower = alert_text.lower()
    
    if "roll" in text_lower:
        return "Roll/adjustment commentary"
    elif "assigned" in text_lower or "assignment" in text_lower:
        return "Assignment notification"
    elif "update" in text_lower or "status" in text_lower:
        return "Status update or commentary"
    elif "closed" in text_lower and "profit" in text_lower:
        return "Trade result commentary"
    elif len(alert_text) < 50:
        return "Too short - not a trade alert"
    elif not any(kw in text_lower for kw in ["call", "put", "debit", "credit", "spread"]):
        return "No options keywords found"
    else:
        return "Does not match trade signal pattern"


def _log_execution_plan_for_result(post_id: str, signal: ParsedSignal, result: dict) -> None:
    """Log the execution plan based on processing result."""
    status = result.get("status", "UNKNOWN")
    
    if status in ["SUBMITTED", "DRY_RUN"]:
        action = "CLOSE_ORDER" if signal.strategy == "EXIT" else "PLACE_ORDER"
    elif status in ["REJECTED", "SKIPPED"]:
        action = "SKIP"
    else:
        action = "SKIP"
    
    quantity = result.get("quantity") or result.get("filled_quantity") or result.get("ordered_contracts")
    
    if signal.strategy in ["LONG_STOCK", "LONG_OPTION"]:
        side = "buy"
    elif "DEBIT" in (signal.strategy or ""):
        side = "debit"
    elif "CREDIT" in (signal.strategy or ""):
        side = "credit"
    else:
        side = "debit"
    
    order_preview = {
        "ticker": signal.ticker,
        "strategy": signal.strategy,
        "quantity": quantity or signal.quantity,
        "limit_price": signal.limit_max if signal.limit_max else None,
        "order_type": "LIMIT" if signal.limit_max else "MARKET",
        "side": side,
        "legs": [leg.model_dump() for leg in signal.legs] if signal.legs else [],
    }
    
    log_execution_plan(
        post_id=post_id,
        action=action,
        reason=result.get("reason") or result.get("message") or status,
        order_preview=order_preview,
        dry_run=config.DRY_RUN,
        live_trading=config.LIVE_TRADING
    )


def process_signal(
    signal: ParsedSignal,
    risk_manager: RiskManager,
    account_equity: float
) -> dict:
    """
    Process a single parsed signal through risk management and order execution.
    Returns order result dict.
    """
    logger.info(f"Processing signal: {signal.strategy} for {signal.ticker}")
    
    if signal.strategy == "EXIT":
        result = broker_alpaca.close_matching_position(signal)
        if result["status"] in ["DRY_RUN", "SUBMITTED"]:
            risk_manager.record_exit()
        return result
    
    if signal.strategy in ["LONG_STOCK", "LONG_OPTION"]:
        if config.is_conservative_mode():
            logger.info(f"Long position skipped in CONSERVATIVE mode: {signal.ticker}")
            return {
                "status": "SKIPPED",
                "reason": "Long positions disabled in CONSERVATIVE mode",
                "ticker": signal.ticker,
                "strategy": signal.strategy,
                "quantity": signal.quantity
            }
        else:
            logger.info(f"Long position detected but execution not yet implemented: {signal.ticker}")
            return {
                "status": "SKIPPED",
                "reason": "Long position execution not yet implemented",
                "ticker": signal.ticker,
                "strategy": signal.strategy,
                "quantity": signal.quantity
            }
    
    num_contracts, rejection_reason = risk_manager.calculate_position_size(
        signal, account_equity
    )
    
    if rejection_reason:
        logger.warning(f"Trade rejected: {rejection_reason}")
        return {
            "status": "REJECTED",
            "reason": rejection_reason,
            "ticker": signal.ticker,
            "strategy": signal.strategy
        }
    
    if num_contracts == 0:
        logger.warning("Position size calculated as 0 contracts")
        return {
            "status": "SKIPPED",
            "reason": "Position size is 0",
            "ticker": signal.ticker,
            "strategy": signal.strategy
        }
    
    logger.info(f"Calculated position size: {num_contracts} contracts")
    
    if signal.strategy == "CALL_DEBIT_SPREAD":
        result = broker_alpaca.place_vertical_call_debit_spread(signal, num_contracts)
        dollar_risk = signal.limit_max * 100 * num_contracts
    elif signal.strategy == "CALL_CREDIT_SPREAD":
        result = broker_alpaca.place_vertical_call_credit_spread(signal, num_contracts)
        spread_width = signal.spread_width or 5.0
        dollar_risk = (spread_width - signal.limit_min) * 100 * num_contracts
    elif signal.strategy in ["PUT_DEBIT_SPREAD", "PUT_CREDIT_SPREAD"]:
        logger.info(f"Put spread execution not yet implemented: {signal.strategy}")
        return {
            "status": "SKIPPED",
            "reason": f"Put spread execution not yet implemented",
            "ticker": signal.ticker,
            "strategy": signal.strategy
        }
    else:
        return {
            "status": "ERROR",
            "reason": f"Unknown strategy: {signal.strategy}",
            "ticker": signal.ticker
        }
    
    if result["status"] in ["DRY_RUN", "SUBMITTED"]:
        risk_manager.record_trade(dollar_risk)
    
    return result


def check_and_run_daily_summary(state: TradeState) -> TradeState:
    """
    Check if it's time to run the daily summary and run it if needed.
    Uses NYSE calendar to determine market close time.
    """
    now = datetime.now(NY_TZ)
    today_ny = now.date()
    today_str = today_ny.isoformat()
    
    if state.last_summary_date == today_str:
        return state
    
    run_time = get_today_market_close_run_time()
    
    if run_time is None:
        logger.debug(f"{today_str} is not a trading day - no summary needed")
        return state
    
    if now >= run_time:
        logger.info(f"Running daily summary for {today_str} (market close + 5 min)")
        
        try:
            filepath = write_daily_summary(today_ny, SIGNALS_LOG_FILE)
            logger.info(f"Daily summary written to: {filepath}")
            
            state.last_summary_date = today_str
            save_state(state)
            
        except Exception as e:
            logger.error(f"Failed to generate daily summary: {e}")
    else:
        next_run = run_time.strftime("%I:%M %p %Z")
        logger.debug(f"Daily summary scheduled for {next_run}")
    
    return state


def run_polling_loop() -> None:
    """Main polling loop that fetches and processes alerts."""
    logger.info("Starting trading bot polling loop...")
    
    # Validate broker mode before starting execution
    validate_broker_mode()
    
    config.print_config_summary()
    
    next_summary_time = get_next_summary_run_time()
    if next_summary_time:
        logger.info(f"Next daily summary scheduled for: {next_summary_time.strftime('%Y-%m-%d %I:%M %p %Z')}")
    
    warnings = config.validate_config()
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")
    
    state = load_state()
    risk_manager = RiskManager()
    
    if should_reset_daily_limits(state):
        risk_manager.reset_daily_limits()
        state.daily_risk_used = 0.0
        state.daily_trades_count = 0
        state.last_reset_date = date.today().isoformat()
        save_state(state)
    
    # Heartbeat tracking
    heartbeat_interval_seconds = 300  # Log heartbeat every 5 minutes
    last_heartbeat = time.time()
    start_time = time.time()
    cycle_count = 0
    
    while True:
        try:
            logger.info("Fetching alerts...")
            alert_texts = get_alerts()
            
            if not alert_texts:
                logger.info("No alerts fetched")
            else:
                signals = []
                
                for alert_text in alert_texts:
                    alert_hash = get_alert_hash(alert_text)
                    
                    if alert_hash in state.processed_alert_hashes:
                        continue
                    
                    post_id = log_raw_alert(body=alert_text, source="whop")
                    
                    signal = parse_alert(alert_text)
                    if signal:
                        signal_with_post_id = (signal, post_id)
                        signals.append(signal_with_post_id)
                        
                        log_parsed_alert(
                            post_id=post_id,
                            classification="SIGNAL",
                            parsed_signal={
                                "ticker": signal.ticker,
                                "strategy": signal.strategy,
                                "expiration": str(signal.expiration) if signal.expiration else None,
                                "legs": [leg.model_dump() for leg in signal.legs] if signal.legs else [],
                                "limit_min": signal.limit_min,
                                "limit_max": signal.limit_max,
                            },
                            raw_excerpt=alert_text[:500]
                        )
                    else:
                        non_signal_reason = _determine_non_signal_reason(alert_text)
                        log_parsed_alert(
                            post_id=post_id,
                            classification="NON_SIGNAL",
                            non_signal_reason=non_signal_reason,
                            raw_excerpt=alert_text[:500]
                        )
                
                logger.info(f"Parsed {len(signals)} valid signals from {len(alert_texts)} alerts")
                
                account_equity = broker_alpaca.get_account_equity()
                if account_equity is None:
                    logger.error("Could not get account equity. Skipping this cycle.")
                else:
                    for signal, post_id in signals:
                        alert_hash = get_alert_hash(signal.raw_text)
                        
                        try:
                            result = process_signal(signal, risk_manager, account_equity)
                            
                            _log_execution_plan_for_result(post_id, signal, result)
                            
                            log_parsed_signal(signal, result.get('status', 'UNKNOWN'))
                            log_trade_result(signal, result)
                            
                            state.processed_alert_hashes.append(alert_hash)
                            if len(state.processed_alert_hashes) > 1000:
                                state.processed_alert_hashes = state.processed_alert_hashes[-500:]
                            
                            save_state(state)
                            
                        except Exception as e:
                            logger.error(f"Error processing signal for {signal.ticker}: {e}")
                            continue
            
            if should_reset_daily_limits(state):
                risk_manager.reset_daily_limits()
                state.daily_risk_used = 0.0
                state.daily_trades_count = 0
                state.last_reset_date = date.today().isoformat()
                save_state(state)
            
            state = check_and_run_daily_summary(state)
            
            # Heartbeat log every N minutes
            cycle_count += 1
            current_time = time.time()
            if current_time - last_heartbeat >= heartbeat_interval_seconds:
                uptime_minutes = int((current_time - start_time) / 60)
                logger.info(f"[HEARTBEAT] Bot alive - {cycle_count} cycles completed, uptime: {uptime_minutes} minutes")
                last_heartbeat = current_time
            
            logger.info(f"Sleeping for {config.POLL_INTERVAL_SECONDS} seconds...")
            time.sleep(config.POLL_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            logger.info("Received shutdown signal. Exiting...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            time.sleep(config.POLL_INTERVAL_SECONDS)


def log_trade_result(signal: ParsedSignal, result: dict) -> None:
    """Log trade result to trades.log."""
    logger.info("-" * 60)
    logger.info("TRADE LOG ENTRY")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info(f"  Ticker: {signal.ticker}")
    logger.info(f"  Strategy: {signal.strategy}")
    logger.info(f"  Status: {result.get('status', 'UNKNOWN')}")
    if result.get('message'):
        logger.info(f"  Message: {result['message']}")
    if result.get('reason'):
        logger.info(f"  Reason: {result['reason']}")
    if result.get('quantity'):
        logger.info(f"  Quantity: {result['quantity']}")
    logger.info("-" * 60)


def run_once() -> None:
    """Run a single cycle (useful for testing)."""
    logger.info("Running single cycle...")
    
    # Validate broker mode before starting execution
    validate_broker_mode()
    
    config.print_config_summary()
    
    state = load_state()
    risk_manager = RiskManager()
    
    alert_texts = get_alerts()
    if not alert_texts:
        logger.info("No alerts to process")
        return
    
    signals = []
    for alert_text in alert_texts:
        signal = parse_alert(alert_text)
        if signal:
            signals.append(signal)
    logger.info(f"Parsed {len(signals)} valid signals from {len(alert_texts)} alerts")
    
    account_equity = broker_alpaca.get_account_equity()
    if account_equity is None:
        logger.error("Could not get account equity")
        return
    
    for signal in signals:
        alert_hash = get_alert_hash(signal.raw_text)
        
        if alert_hash in state.processed_alert_hashes:
            logger.info(f"Skipping already processed: {signal.ticker}")
            continue
        
        result = process_signal(signal, risk_manager, account_equity)
        log_parsed_signal(signal, result.get('status', 'UNKNOWN'))
        log_trade_result(signal, result)
        
        state.processed_alert_hashes.append(alert_hash)
        save_state(state)


if __name__ == "__main__":
    setup_file_logging()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        run_polling_loop()
