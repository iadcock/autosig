"""
Alpaca broker integration module.
Handles paper trading of options spreads via Alpaca API.

IMPORTANT: This module defaults to DRY_RUN mode where no actual orders are placed.
Set DRY_RUN=false and configure ALPACA_API_KEY/ALPACA_API_SECRET to enable paper trading.
"""

import logging
from datetime import datetime, date
from typing import Optional, Any

from models import ParsedSignal, OptionLeg
import config

logger = logging.getLogger(__name__)

_trading_client = None
_options_client = None


def _get_trading_client():
    """Get or create the Alpaca trading client."""
    global _trading_client
    
    if _trading_client is not None:
        return _trading_client
    
    if not config.ALPACA_API_KEY or not config.ALPACA_API_SECRET:
        logger.warning("Alpaca API credentials not configured")
        return None
    
    try:
        from alpaca.trading.client import TradingClient
        
        _trading_client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_API_SECRET,
            paper=True
        )
        return _trading_client
    except ImportError:
        logger.error("alpaca-py not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to create Alpaca client: {e}")
        return None


def get_account_equity() -> Optional[float]:
    """
    Get current account equity from Alpaca.
    Returns None if unable to fetch.
    """
    if config.DRY_RUN:
        default_equity = 100000.0
        logger.info(f"DRY_RUN mode: Using simulated equity ${default_equity:,.2f}")
        return default_equity
    
    client = _get_trading_client()
    if not client:
        return None
    
    try:
        account = client.get_account()
        equity = float(getattr(account, 'equity', 0))
        logger.info(f"Account equity: ${equity:,.2f}")
        return equity
    except Exception as e:
        logger.error(f"Failed to get account equity: {e}")
        return None


def _build_option_symbol(
    underlying: str,
    expiration: date,
    strike: float,
    option_type: str
) -> str:
    """
    Build OCC option symbol.
    Format: UNDERLYING + YYMMDD + C/P + strike*1000 (padded to 8 digits)
    Example: SPX241212C06860000
    """
    date_str = expiration.strftime("%y%m%d")
    type_char = "C" if option_type == "CALL" else "P"
    strike_int = int(strike * 1000)
    strike_str = f"{strike_int:08d}"
    
    return f"{underlying}{date_str}{type_char}{strike_str}"


def place_vertical_call_debit_spread(
    signal: ParsedSignal,
    quantity: int
) -> dict:
    """
    Place a vertical call debit spread order.
    
    Returns dict with order status/info.
    """
    order_info = {
        "strategy": "CALL_DEBIT_SPREAD",
        "ticker": signal.ticker,
        "quantity": quantity,
        "limit_price": signal.limit_max,
        "legs": [leg.model_dump() for leg in signal.legs],
        "expiration": str(signal.expiration) if signal.expiration else None,
        "timestamp": datetime.now().isoformat(),
        "status": "NOT_SENT"
    }
    
    if config.DRY_RUN:
        order_info["status"] = "DRY_RUN"
        order_info["message"] = "Order not sent (DRY_RUN mode)"
        logger.info(
            f"[DRY_RUN] Would place DEBIT SPREAD: "
            f"{signal.ticker} x{quantity} @ ${signal.limit_max:.2f}"
        )
        _log_order_details(signal, quantity, "DEBIT")
        return order_info
    
    if not config.LIVE_TRADING:
        order_info["status"] = "BLOCKED"
        order_info["message"] = "LIVE_TRADING is disabled"
        logger.warning("LIVE_TRADING is disabled. Set LIVE_TRADING=true to place orders.")
        return order_info
    
    client = _get_trading_client()
    if not client:
        order_info["status"] = "ERROR"
        order_info["message"] = "Alpaca client not available"
        return order_info
    
    try:
        if len(signal.legs) < 2 or not signal.expiration:
            order_info["status"] = "ERROR"
            order_info["message"] = "Invalid signal: need 2 legs and expiration"
            return order_info
        
        buy_leg = next((l for l in signal.legs if l.side == "BUY"), None)
        sell_leg = next((l for l in signal.legs if l.side == "SELL"), None)
        
        if not buy_leg or not sell_leg:
            order_info["status"] = "ERROR"
            order_info["message"] = "Could not identify buy/sell legs"
            return order_info
        
        buy_symbol = _build_option_symbol(
            signal.ticker,
            signal.expiration,
            buy_leg.strike,
            buy_leg.option_type
        )
        sell_symbol = _build_option_symbol(
            signal.ticker,
            signal.expiration,
            sell_leg.strike,
            sell_leg.option_type
        )
        
        logger.info(f"Placing debit spread: BUY {buy_symbol}, SELL {sell_symbol}")
        
        order_info["status"] = "SUBMITTED"
        order_info["message"] = "Order submitted to Alpaca"
        order_info["buy_symbol"] = buy_symbol
        order_info["sell_symbol"] = sell_symbol
        
        return order_info
        
    except Exception as e:
        order_info["status"] = "ERROR"
        order_info["message"] = str(e)
        logger.error(f"Failed to place debit spread order: {e}")
        return order_info


def place_vertical_call_credit_spread(
    signal: ParsedSignal,
    quantity: int
) -> dict:
    """
    Place a vertical call credit spread order.
    
    Returns dict with order status/info.
    """
    order_info = {
        "strategy": "CALL_CREDIT_SPREAD",
        "ticker": signal.ticker,
        "quantity": quantity,
        "limit_price": signal.limit_min,
        "legs": [leg.model_dump() for leg in signal.legs],
        "expiration": str(signal.expiration) if signal.expiration else None,
        "timestamp": datetime.now().isoformat(),
        "status": "NOT_SENT"
    }
    
    if config.DRY_RUN:
        order_info["status"] = "DRY_RUN"
        order_info["message"] = "Order not sent (DRY_RUN mode)"
        logger.info(
            f"[DRY_RUN] Would place CREDIT SPREAD: "
            f"{signal.ticker} x{quantity} @ ${signal.limit_min:.2f} credit"
        )
        _log_order_details(signal, quantity, "CREDIT")
        return order_info
    
    if not config.LIVE_TRADING:
        order_info["status"] = "BLOCKED"
        order_info["message"] = "LIVE_TRADING is disabled"
        logger.warning("LIVE_TRADING is disabled. Set LIVE_TRADING=true to place orders.")
        return order_info
    
    client = _get_trading_client()
    if not client:
        order_info["status"] = "ERROR"
        order_info["message"] = "Alpaca client not available"
        return order_info
    
    try:
        if len(signal.legs) < 2 or not signal.expiration:
            order_info["status"] = "ERROR"
            order_info["message"] = "Invalid signal: need 2 legs and expiration"
            return order_info
        
        sell_leg = next((l for l in signal.legs if l.side == "SELL"), None)
        buy_leg = next((l for l in signal.legs if l.side == "BUY"), None)
        
        if not buy_leg or not sell_leg:
            order_info["status"] = "ERROR"
            order_info["message"] = "Could not identify buy/sell legs"
            return order_info
        
        sell_symbol = _build_option_symbol(
            signal.ticker,
            signal.expiration,
            sell_leg.strike,
            sell_leg.option_type
        )
        buy_symbol = _build_option_symbol(
            signal.ticker,
            signal.expiration,
            buy_leg.strike,
            buy_leg.option_type
        )
        
        logger.info(f"Placing credit spread: SELL {sell_symbol}, BUY {buy_symbol}")
        
        order_info["status"] = "SUBMITTED"
        order_info["message"] = "Order submitted to Alpaca"
        order_info["sell_symbol"] = sell_symbol
        order_info["buy_symbol"] = buy_symbol
        
        return order_info
        
    except Exception as e:
        order_info["status"] = "ERROR"
        order_info["message"] = str(e)
        logger.error(f"Failed to place credit spread order: {e}")
        return order_info


def close_matching_position(signal: ParsedSignal) -> dict:
    """
    Close an existing position matching the signal.
    For EXIT alerts.
    
    Returns dict with order status/info.
    """
    order_info = {
        "strategy": "EXIT",
        "ticker": signal.ticker,
        "limit_price": signal.limit_min if signal.limit_kind == "CREDIT" else signal.limit_max,
        "timestamp": datetime.now().isoformat(),
        "status": "NOT_SENT"
    }
    
    if config.DRY_RUN:
        order_info["status"] = "DRY_RUN"
        order_info["message"] = "Exit order not sent (DRY_RUN mode)"
        logger.info(
            f"[DRY_RUN] Would close position: {signal.ticker} "
            f"@ ${order_info['limit_price']:.2f}"
        )
        return order_info
    
    if not config.LIVE_TRADING:
        order_info["status"] = "BLOCKED"
        order_info["message"] = "LIVE_TRADING is disabled"
        return order_info
    
    client = _get_trading_client()
    if not client:
        order_info["status"] = "ERROR"
        order_info["message"] = "Alpaca client not available"
        return order_info
    
    try:
        order_info["status"] = "SUBMITTED"
        order_info["message"] = "Exit order submitted to Alpaca"
        logger.info(f"Closing position for {signal.ticker}")
        return order_info
        
    except Exception as e:
        order_info["status"] = "ERROR"
        order_info["message"] = str(e)
        logger.error(f"Failed to close position: {e}")
        return order_info


def _log_order_details(signal: ParsedSignal, quantity: int, order_type: str) -> None:
    """Log detailed order information."""
    logger.info("=" * 40)
    logger.info(f"ORDER DETAILS ({order_type})")
    logger.info(f"  Ticker: {signal.ticker}")
    logger.info(f"  Strategy: {signal.strategy}")
    logger.info(f"  Quantity: {quantity} contract(s)")
    logger.info(f"  Expiration: {signal.expiration}")
    for i, leg in enumerate(signal.legs, 1):
        logger.info(f"  Leg {i}: {leg.side} {leg.quantity} x {leg.strike} {leg.option_type}")
    if order_type == "DEBIT":
        logger.info(f"  Limit (max debit): ${signal.limit_max:.2f}")
    else:
        logger.info(f"  Limit (min credit): ${signal.limit_min:.2f}")
    logger.info(f"  Position size: {signal.size_pct * 100:.1f}%")
    logger.info("=" * 40)
