"""
Convert parsed signals to TradeIntent for broker-agnostic execution.

This module bridges the gap between parsed Whop alerts (ParsedSignal) 
and the execution layer (TradeIntent).
"""

from datetime import date
from typing import Optional, Literal, Dict, Any, Tuple

from trade_intent import TradeIntent, OptionLeg as IntentOptionLeg
from models import ParsedSignal


def classify_signal_type(parsed_signal: dict) -> Literal["ENTRY", "EXIT", "UNKNOWN"]:
    """
    Classify a signal as ENTRY, EXIT, or UNKNOWN.
    
    ENTRY: Opens a new position (buy to open, sell to open, spreads, longs)
    EXIT: Closes an existing position (exit, take profit, close, sell to close)
    UNKNOWN: Cannot determine
    """
    strategy = parsed_signal.get("strategy", "").upper()
    raw_text = parsed_signal.get("raw_text", "").lower()
    
    # Check for EXIT patterns first
    exit_strategies = ["EXIT"]
    exit_keywords = [
        "exit", "close", "take profit", "take profits", "cut position", 
        "stop hit", "stopped out", "sell to close", "selling to close",
        "buy to close", "buying to close", "trim", "cut", "out of"
    ]
    
    if strategy in exit_strategies:
        return "EXIT"
    
    if any(kw in raw_text for kw in exit_keywords):
        return "EXIT"
    
    # Check for ENTRY patterns
    entry_strategies = [
        "CALL_DEBIT_SPREAD", "PUT_DEBIT_SPREAD", 
        "CALL_CREDIT_SPREAD", "PUT_CREDIT_SPREAD",
        "IRON_CONDOR", "LONG_STOCK", "LONG_OPTION",
        "CALL", "PUT"
    ]
    entry_keywords = [
        "buy to open", "sell to open", "opening", "new position",
        "entering", "going long", "going short", "debit spread", 
        "credit spread", "iron condor"
    ]
    
    if strategy in entry_strategies:
        return "ENTRY"
    
    if any(kw in raw_text for kw in entry_keywords):
        return "ENTRY"
    
    # If has valid legs and strategy contains spread/option indicators, it's likely ENTRY
    legs = parsed_signal.get("legs", [])
    if legs and any(kw in strategy for kw in ["SPREAD", "CALL", "PUT", "OPTION"]):
        return "ENTRY"
    
    return "UNKNOWN"


def has_complete_leg_details(parsed_signal: dict) -> bool:
    """Check if signal has complete leg details for direct execution."""
    legs = parsed_signal.get("legs", [])
    if not legs:
        return False
    
    for leg in legs:
        if not isinstance(leg, dict):
            return False
        # Must have strike and option_type at minimum
        if not leg.get("strike") or not leg.get("option_type"):
            return False
    
    # Must have expiration either at signal level or in each leg
    expiration = parsed_signal.get("expiration")
    if not expiration:
        for leg in legs:
            if not leg.get("expiration"):
                return False
    
    return True


def build_trade_intent(
    parsed_signal: dict,
    execution_mode: Literal["PAPER", "LIVE", "HISTORICAL"] = "PAPER"
) -> TradeIntent:
    """
    Convert a parsed signal dictionary to a TradeIntent.
    
    Args:
        parsed_signal: Dictionary from alerts_parsed.jsonl with parsed_signal fields
        execution_mode: Execution mode (PAPER, LIVE, HISTORICAL)
        
    Returns:
        TradeIntent ready for execution
        
    Mapping rules:
    1. STOCK: instrument_type="STOCK", no legs
    2. SINGLE-LEG OPTION: instrument_type="OPTION" (or "INDEX_OPTION" for SPX)
    3. SPREADS: instrument_type="SPREAD", multiple legs
    """
    ticker = parsed_signal.get("ticker", "")
    strategy = parsed_signal.get("strategy", "")
    expiration = parsed_signal.get("expiration")
    legs_data = parsed_signal.get("legs", [])
    limit_min = parsed_signal.get("limit_min", 0.0)
    limit_max = parsed_signal.get("limit_max", 0.0)
    limit_kind = parsed_signal.get("limit_kind", "DEBIT")
    quantity = parsed_signal.get("quantity", 1)
    raw_text = parsed_signal.get("raw_text", "")
    
    if isinstance(expiration, str) and expiration:
        exp_str = expiration
    elif isinstance(expiration, date):
        exp_str = expiration.isoformat()
    else:
        exp_str = None
    
    action = _determine_action(strategy, raw_text)
    instrument_type = _determine_instrument_type(strategy, ticker, legs_data)
    order_type = _determine_order_type(limit_min, limit_max)
    limit_price = _determine_limit_price(limit_min, limit_max, limit_kind, strategy)
    
    intent_legs = _build_intent_legs(legs_data, exp_str)
    
    signal_type = classify_signal_type(parsed_signal)
    
    return TradeIntent(
        execution_mode=execution_mode,
        instrument_type=instrument_type,
        underlying=ticker.upper(),
        action=action,
        order_type=order_type,
        limit_price=limit_price,
        limit_min=limit_min if limit_min > 0 else None,
        limit_max=limit_max if limit_max > 0 else None,
        quantity=quantity if quantity > 0 else 1,
        legs=intent_legs,
        raw_signal=raw_text,
        metadata={
            "strategy": strategy,
            "limit_kind": limit_kind,
            "expiration": exp_str,
            "source": "whop_parsed_signal",
            "signal_type": signal_type
        }
    )


def build_close_intent_from_position(
    position: Any,
    parsed_signal: dict,
    execution_mode: Literal["PAPER", "LIVE", "HISTORICAL"] = "PAPER"
) -> TradeIntent:
    """
    Build a closing TradeIntent from an open position.
    
    Args:
        position: PaperPosition object with open position details
        parsed_signal: The EXIT signal that triggered the close
        execution_mode: Execution mode
        
    Returns:
        TradeIntent with reversed legs for closing
    """
    open_intent = position.open_intent
    
    # Determine close action based on original open action
    original_action = open_intent.get("action", "BUY_TO_OPEN")
    if "SELL" in original_action:
        close_action = "BUY_TO_CLOSE"
    else:
        close_action = "SELL_TO_CLOSE"
    
    # Build closing legs with reversed sides
    close_legs = []
    for leg in position.legs:
        reversed_side = "SELL" if leg.side == "BUY" else "BUY"
        close_legs.append(IntentOptionLeg(
            side=reversed_side,
            quantity=leg.quantity,
            strike=leg.strike,
            option_type=leg.option_type,
            expiration=leg.expiration
        ))
    
    # Get limit price from exit signal if available
    limit_min = parsed_signal.get("limit_min", 0.0)
    limit_max = parsed_signal.get("limit_max", 0.0)
    limit_price = None
    if limit_min > 0:
        limit_price = limit_min
    elif limit_max > 0:
        limit_price = limit_max
    
    order_type = "LIMIT" if limit_price else "MARKET"
    
    return TradeIntent(
        execution_mode=execution_mode,
        instrument_type=position.instrument_type,
        underlying=position.underlying.upper(),
        action=close_action,
        order_type=order_type,
        limit_price=limit_price,
        quantity=position.quantity,
        legs=close_legs,
        raw_signal=parsed_signal.get("raw_text", ""),
        metadata={
            "strategy": "EXIT",
            "source": "position_close",
            "signal_type": "EXIT",
            "matched_position_id": position.position_id
        }
    )


def resolve_exit_to_trade_intent(
    parsed_signal: dict,
    execution_mode: Literal["PAPER", "LIVE", "HISTORICAL"] = "PAPER"
) -> Tuple[Optional[TradeIntent], Optional[str], Optional[str]]:
    """
    Resolve an EXIT signal to a TradeIntent by finding matching open position.
    
    Args:
        parsed_signal: The EXIT signal to resolve
        execution_mode: Execution mode
        
    Returns:
        Tuple of (TradeIntent or None, position_id or None, error_reason or None)
    """
    from paper_positions import find_open_position_for_exit
    
    position = find_open_position_for_exit(parsed_signal)
    
    if position is None:
        ticker = parsed_signal.get("ticker", "UNKNOWN")
        return None, None, f"No open PAPER position to close for ticker {ticker}"
    
    intent = build_close_intent_from_position(position, parsed_signal, execution_mode)
    return intent, position.position_id, None


def _determine_action(strategy: str, raw_text: str) -> Literal["BUY", "SELL", "BUY_TO_OPEN", "BUY_TO_CLOSE", "SELL_TO_OPEN", "SELL_TO_CLOSE"]:
    """
    Determine the trade action based on strategy and keywords.
    
    For EXIT signals:
    - Credit spreads (sold to open) must be BOUGHT to close -> BUY_TO_CLOSE
    - Debit spreads (bought to open) must be SOLD to close -> SELL_TO_CLOSE
    - Default to SELL_TO_CLOSE for long positions
    
    We infer the original position type from keywords in the raw text.
    """
    strategy_upper = strategy.upper()
    raw_lower = raw_text.lower()
    
    exit_keywords = ["exit", "close", "take profit", "cut position", "selling to close", "buy to close"]
    is_exit = any(kw in raw_lower for kw in exit_keywords) or strategy_upper == "EXIT"
    
    if is_exit:
        credit_keywords = ["credit spread", "credit", "sold", "sell to open", "iron condor", "put credit", "call credit"]
        is_credit_position = any(kw in raw_lower for kw in credit_keywords)
        
        if "buy to close" in raw_lower:
            return "BUY_TO_CLOSE"
        if "sell to close" in raw_lower or "selling to close" in raw_lower:
            return "SELL_TO_CLOSE"
        
        if is_credit_position:
            return "BUY_TO_CLOSE"
        
        return "SELL_TO_CLOSE"
    
    if strategy_upper in ["LONG_STOCK", "LONG_OPTION"]:
        return "BUY_TO_OPEN"
    
    if "DEBIT" in strategy_upper:
        return "BUY_TO_OPEN"
    
    if "CREDIT" in strategy_upper:
        return "SELL_TO_OPEN"
    
    return "BUY_TO_OPEN"


def _determine_instrument_type(strategy: str, ticker: str, legs: list) -> Literal["STOCK", "OPTION", "SPREAD"]:
    """Determine the instrument type based on strategy and legs."""
    strategy_upper = strategy.upper()
    ticker_upper = ticker.upper()
    
    if strategy_upper == "LONG_STOCK":
        return "STOCK"
    
    if len(legs) >= 2:
        return "SPREAD"
    
    if len(legs) == 1 or strategy_upper in ["LONG_OPTION", "EXIT"]:
        return "OPTION"
    
    if "SPREAD" in strategy_upper:
        return "SPREAD"
    
    if any(kw in strategy_upper for kw in ["CALL", "PUT", "OPTION"]):
        return "OPTION"
    
    return "STOCK"


def _determine_order_type(limit_min: float, limit_max: float) -> Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"]:
    """Determine order type based on limit prices."""
    if limit_min > 0 or limit_max > 0:
        return "LIMIT"
    return "MARKET"


def _determine_limit_price(
    limit_min: float, 
    limit_max: float, 
    limit_kind: str,
    strategy: str
) -> Optional[float]:
    """
    Determine the appropriate limit price for order submission.
    
    For DEBIT orders (buying): use limit_max (worst price to pay)
    For CREDIT orders (selling): use limit_min (minimum credit to receive)
    """
    strategy_upper = strategy.upper()
    
    if strategy_upper == "EXIT":
        if limit_min > 0:
            return limit_min
        if limit_max > 0:
            return limit_max
        return None
    
    if limit_kind.upper() == "DEBIT" or "DEBIT" in strategy_upper:
        if limit_max > 0:
            return limit_max
        if limit_min > 0:
            return limit_min
    elif limit_kind.upper() == "CREDIT" or "CREDIT" in strategy_upper:
        if limit_min > 0:
            return limit_min
        if limit_max > 0:
            return limit_max
    
    if limit_max > 0:
        return limit_max
    if limit_min > 0:
        return limit_min
    
    return None


def _build_intent_legs(legs_data: list, expiration: Optional[str]) -> list[IntentOptionLeg]:
    """Convert parsed leg data to IntentOptionLeg objects."""
    intent_legs = []
    
    for leg in legs_data:
        if isinstance(leg, dict):
            side = leg.get("side", "BUY").upper()
            quantity = abs(int(leg.get("quantity", 1)))
            strike = float(leg.get("strike", 0))
            option_type = leg.get("option_type", "CALL").upper()
            leg_exp = leg.get("expiration") or expiration
            
            if side not in ["BUY", "SELL"]:
                side = "BUY"
            if option_type not in ["CALL", "PUT"]:
                option_type = "CALL"
            
            if isinstance(leg_exp, date):
                leg_exp = leg_exp.isoformat()
            elif not isinstance(leg_exp, str):
                leg_exp = expiration or ""
            
            intent_legs.append(IntentOptionLeg(
                side=side,
                quantity=quantity,
                strike=strike,
                option_type=option_type,
                expiration=leg_exp or ""
            ))
    
    return intent_legs


def signal_dict_to_parsed_signal(signal_dict: dict) -> ParsedSignal:
    """
    Convert a signal dictionary (from JSONL) to a ParsedSignal object.
    Useful for validation and accessing computed properties.
    """
    from models import OptionLeg as ModelOptionLeg
    from datetime import datetime as dt
    
    expiration_val = signal_dict.get("expiration")
    parsed_expiration: Optional[date] = None
    if isinstance(expiration_val, str) and expiration_val:
        try:
            parsed_expiration = dt.strptime(expiration_val, "%Y-%m-%d").date()
        except ValueError:
            parsed_expiration = None
    elif isinstance(expiration_val, date):
        parsed_expiration = expiration_val
    
    legs = []
    for leg_data in signal_dict.get("legs", []):
        if isinstance(leg_data, dict):
            legs.append(ModelOptionLeg(
                side=leg_data.get("side", "BUY"),
                quantity=leg_data.get("quantity", 1),
                strike=leg_data.get("strike", 0),
                option_type=leg_data.get("option_type", "CALL")
            ))
    
    return ParsedSignal(
        ticker=signal_dict.get("ticker", ""),
        strategy=signal_dict.get("strategy", "EXIT"),
        expiration=parsed_expiration,
        legs=legs,
        limit_min=signal_dict.get("limit_min", 0.0),
        limit_max=signal_dict.get("limit_max", 0.0),
        limit_kind=signal_dict.get("limit_kind", "DEBIT"),
        size_pct=signal_dict.get("size_pct", 0.0),
        raw_text=signal_dict.get("raw_text", ""),
        quantity=signal_dict.get("quantity", 1)
    )
