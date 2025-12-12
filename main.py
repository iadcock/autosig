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

import config
from models import ParsedSignal, TradeState
from parser import parse_alert, get_alert_hash
from scraper_whop import get_alerts
from risk import RiskManager
import broker_alpaca

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


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
    else:
        return {
            "status": "ERROR",
            "reason": f"Unknown strategy: {signal.strategy}",
            "ticker": signal.ticker
        }
    
    if result["status"] in ["DRY_RUN", "SUBMITTED"]:
        risk_manager.record_trade(dollar_risk)
    
    return result


def run_polling_loop() -> None:
    """Main polling loop that fetches and processes alerts."""
    logger.info("Starting trading bot polling loop...")
    config.print_config_summary()
    
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
    
    while True:
        try:
            logger.info("Fetching alerts...")
            alert_texts = get_alerts()
            
            if not alert_texts:
                logger.info("No alerts fetched")
            else:
                signals = []
                for alert_text in alert_texts:
                    signal = parse_alert(alert_text)
                    if signal:
                        signals.append(signal)
                logger.info(f"Parsed {len(signals)} valid signals from {len(alert_texts)} alerts")
                
                account_equity = broker_alpaca.get_account_equity()
                if account_equity is None:
                    logger.error("Could not get account equity. Skipping this cycle.")
                else:
                    for signal in signals:
                        alert_hash = get_alert_hash(signal.raw_text)
                        
                        if alert_hash in state.processed_alert_hashes:
                            logger.debug(f"Skipping already processed alert: {signal.ticker}")
                            continue
                        
                        try:
                            result = process_signal(signal, risk_manager, account_equity)
                            
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
        log_trade_result(signal, result)
        
        state.processed_alert_hashes.append(alert_hash)
        save_state(state)


if __name__ == "__main__":
    setup_file_logging()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        run_polling_loop()
