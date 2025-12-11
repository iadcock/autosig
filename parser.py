"""
Alert parser module for the trading bot.
Parses Victory Trades style alerts into structured ParsedSignal objects.
"""

import re
import hashlib
from datetime import date, datetime
from typing import Optional, Literal, cast
from dateutil import parser as date_parser

from models import ParsedSignal, OptionLeg
import config


def parse_alert(raw_text: str) -> Optional[ParsedSignal]:
    """
    Parse a raw alert text into a ParsedSignal object.
    Returns None if the alert cannot be parsed or should be ignored.
    """
    if not raw_text or not raw_text.strip():
        return None
    
    text = raw_text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) < 2:
        return None
    
    if is_chatty_alert(text):
        return None
    
    strategy = extract_strategy(text)
    if not strategy:
        return None
    
    ticker = extract_ticker(lines[0])
    if not ticker:
        return None
    
    expiration = extract_expiration(text)
    
    legs = extract_legs(text)
    
    limit_info = extract_limit_price(text)
    if not limit_info:
        return None
    
    limit_min, limit_max, limit_kind = limit_info
    
    size_pct = extract_size_pct(text)
    
    strategy_literal = cast(Literal["CALL_DEBIT_SPREAD", "CALL_CREDIT_SPREAD", "EXIT"], strategy)
    limit_kind_literal = cast(Literal["DEBIT", "CREDIT"], limit_kind)
    
    return ParsedSignal(
        ticker=ticker,
        strategy=strategy_literal,
        expiration=expiration,
        legs=legs,
        limit_min=limit_min,
        limit_max=limit_max,
        limit_kind=limit_kind_literal,
        size_pct=size_pct,
        raw_text=raw_text
    )


def is_chatty_alert(text: str) -> bool:
    """
    Detect "chatty" alerts that should be ignored.
    These are conversational messages without clear trade instructions.
    """
    text_lower = text.lower()
    
    chatty_indicators = [
        "i'm tempted",
        "i am tempted",
        "thinking about",
        "might want to",
        "considering",
        "market is bear",
        "market is bull",
        "buy to close this week",
        "roll",
        "covered call roll",
    ]
    
    for indicator in chatty_indicators:
        if indicator in text_lower:
            if "debit spread" not in text_lower and "credit spread" not in text_lower and "exit" not in text_lower:
                return True
    
    if "limit" not in text_lower:
        if "debit spread" not in text_lower and "credit spread" not in text_lower:
            return True
    
    return False


def extract_strategy(text: str) -> Optional[str]:
    """Extract the strategy type from alert text."""
    text_lower = text.lower()
    
    if "exit" in text_lower or "close" in text_lower:
        if "debit" in text_lower or "credit" in text_lower:
            return "EXIT"
    
    if "debit spread" in text_lower or "debit to open" in text_lower:
        return "CALL_DEBIT_SPREAD"
    
    if "credit spread" in text_lower or "credit to open" in text_lower:
        return "CALL_CREDIT_SPREAD"
    
    return None


def extract_ticker(first_line: str) -> Optional[str]:
    """
    Extract the underlying ticker from the first line of the alert.
    Assumes ticker is the first word (all caps, 1-5 characters).
    """
    words = first_line.split()
    if not words:
        return None
    
    potential_ticker = words[0].upper()
    
    if re.match(r'^[A-Z]{1,5}$', potential_ticker):
        return potential_ticker
    
    for word in words:
        word_upper = word.upper()
        if re.match(r'^[A-Z]{1,5}$', word_upper):
            if word_upper not in ['LEAP', 'CALL', 'PUT', 'BEAR', 'BULL', 'DAY', 'NEXT', 'THE', 'AND']:
                return word_upper
    
    return None


def extract_expiration(text: str) -> Optional[date]:
    """
    Extract expiration date from text.
    Handles formats like:
    - 6/17/2027 exp
    - 12/12/25 exp
    - December exp
    """
    exp_pattern = r'(\d{1,2}/\d{1,2}/\d{2,4})\s*exp'
    match = re.search(exp_pattern, text, re.IGNORECASE)
    
    if match:
        date_str = match.group(1)
        try:
            parsed = date_parser.parse(date_str)
            if parsed.year < 100:
                if parsed.year < 50:
                    parsed = parsed.replace(year=parsed.year + 2000)
                else:
                    parsed = parsed.replace(year=parsed.year + 1900)
            return parsed.date()
        except (ValueError, TypeError):
            pass
    
    month_pattern = r'(\w+)\s+exp'
    match = re.search(month_pattern, text, re.IGNORECASE)
    if match:
        month_name = match.group(1)
        try:
            parsed = date_parser.parse(f"{month_name} 15, {datetime.now().year}")
            if parsed.date() < datetime.now().date():
                parsed = parsed.replace(year=parsed.year + 1)
            return parsed.date()
        except (ValueError, TypeError):
            pass
    
    return None


def extract_legs(text: str) -> list[OptionLeg]:
    """
    Extract option legs from text.
    Handles formats like:
    - +1 415 C / -1 420 C
    - -1 6860 C / +1 6865 C
    """
    legs = []
    
    leg_pattern = r'([+-]\d+)\s+(\d+(?:\.\d+)?)\s*([CP])'
    matches = re.findall(leg_pattern, text, re.IGNORECASE)
    
    for qty_str, strike_str, opt_type in matches:
        quantity = int(qty_str)
        strike = float(strike_str)
        
        side = "BUY" if quantity > 0 else "SELL"
        abs_quantity = abs(quantity)
        option_type = "CALL" if opt_type.upper() == "C" else "PUT"
        
        legs.append(OptionLeg(
            side=side,
            quantity=abs_quantity,
            strike=strike,
            option_type=option_type
        ))
    
    return legs


def extract_limit_price(text: str) -> Optional[tuple[float, float, str]]:
    """
    Extract limit price range and type from text.
    Returns (min, max, kind) tuple or None.
    
    Handles formats like:
    - Limit 1.85-1.9 debit to open
    - Limit 2.6-2.7 credit to open
    - Limit 1.85-2.0 credit to close
    """
    range_pattern = r'limit\s+(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(debit|credit)'
    match = re.search(range_pattern, text, re.IGNORECASE)
    
    if match:
        min_price = float(match.group(1))
        max_price = float(match.group(2))
        kind = match.group(3).upper()
        
        if min_price > max_price:
            min_price, max_price = max_price, min_price
        
        return (min_price, max_price, kind)
    
    single_pattern = r'limit\s+(\d+(?:\.\d+)?)\s*(debit|credit)'
    match = re.search(single_pattern, text, re.IGNORECASE)
    
    if match:
        price = float(match.group(1))
        kind = match.group(2).upper()
        return (price, price, kind)
    
    return None


def extract_size_pct(text: str) -> float:
    """
    Extract position size percentage from text.
    Returns as decimal (e.g., 0.02 for 2%).
    Falls back to config.DEFAULT_SIZE_PCT if not found.
    """
    size_pattern = r'(\d+(?:\.\d+)?)\s*%\s*size'
    match = re.search(size_pattern, text, re.IGNORECASE)
    
    if match:
        pct = float(match.group(1))
        return pct / 100.0
    
    return config.DEFAULT_SIZE_PCT


def get_alert_hash(raw_text: str) -> str:
    """Generate a hash for an alert to detect duplicates."""
    normalized = ' '.join(raw_text.lower().split())
    return hashlib.md5(normalized.encode()).hexdigest()


def parse_multiple_alerts(text: str) -> list[ParsedSignal]:
    """
    Parse multiple alerts from a single text block.
    Alerts are typically separated by double newlines or clear breaks.
    """
    alerts = []
    
    chunks = re.split(r'\n\s*\n\s*\n', text)
    
    for chunk in chunks:
        chunk = chunk.strip()
        if chunk:
            parsed = parse_alert(chunk)
            if parsed:
                alerts.append(parsed)
    
    return alerts
