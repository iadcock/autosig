"""
Alert parser module for the trading bot.
Parses Victory Trades style alerts into structured ParsedSignal objects.

Classification Rules:
- SIGNAL: Must have ticker + expiration + leg(s) + limit price + size indicator
- LONG_STOCK: "Long TICKER" or "Buy X shares of TICKER"
- LONG_OPTION: "Long TICKER strikeC/P expiration" or "Buying TICKER calls/puts"
- EXIT: Contains exit keywords with ticker reference
- NON_SIGNAL: Commentary, assignments, coaching, etc.
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
    Returns None if the alert cannot be parsed or is non-signal.
    
    A valid SIGNAL must have ALL of:
    - Ticker symbol (1-5 capital letters)
    - Expiration date
    - At least one option leg
    - Limit price
    - Size indicator
    
    LONG positions (LONG_STOCK, LONG_OPTION) have relaxed requirements.
    """
    if not raw_text or not raw_text.strip():
        return None
    
    text = raw_text.strip()
    
    if is_non_signal_content(text):
        return None
    
    if is_exit_signal(text):
        ticker = extract_ticker_anywhere(text)
        if ticker:
            return ParsedSignal(
                ticker=ticker,
                strategy="EXIT",
                expiration=None,
                legs=[],
                limit_min=0.0,
                limit_max=0.0,
                limit_kind="DEBIT",
                size_pct=0.0,
                raw_text=raw_text
            )
        return None
    
    long_signal = parse_long_position(text, raw_text)
    if long_signal:
        return long_signal
    
    ticker = extract_ticker_anywhere(text)
    expiration = extract_expiration(text)
    legs = extract_legs(text)
    limit_info = extract_limit_price(text)
    size_pct = extract_size_pct(text)
    has_size = has_size_indicator(text)
    
    if not ticker:
        return None
    if not expiration:
        return None
    if not legs:
        return None
    if not limit_info:
        return None
    if not has_size:
        return None
    
    limit_min, limit_max, limit_kind = limit_info
    
    strategy = determine_strategy(text, limit_kind)
    
    strategy_literal = cast(Literal["CALL_DEBIT_SPREAD", "CALL_CREDIT_SPREAD", "PUT_DEBIT_SPREAD", "PUT_CREDIT_SPREAD", "EXIT"], strategy)
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


def is_non_signal_content(text: str) -> bool:
    """
    Detect non-signal content that should be classified as NON_SIGNAL.
    These are commentary, assignments, coaching posts, etc.
    """
    text_lower = text.lower()
    
    non_signal_patterns = [
        r'\bwill be assigned\b',
        r'\bgot assigned\b',
        r'\bwas assigned\b',
        r'\bassignment\b',
        r'\bwatch out\b',
        r'\bmarket is doing\b',
        r'\bmarket update\b',
        r'\bI\'m cool with\b',
        r'\bmax profit\b.*\bclosed\b',
        r'\bhit max profit\b',
    ]
    
    for pattern in non_signal_patterns:
        if re.search(pattern, text_lower):
            if not has_trade_structure(text):
                return True
    
    if len(text) < 40:
        if not _looks_like_long_position(text):
            return True
    
    if text_lower.startswith("like\n") or text_lower.startswith("share\n"):
        return True
    
    return False


def _looks_like_long_position(text: str) -> bool:
    """Quick check if text looks like a long position alert (used before full parsing)."""
    long_patterns = [
        r'\blong\s+[A-Z]{1,5}\b',
        r'\bbuy(?:ing)?\s+\d+\s*shares?\s+(?:of\s+)?[A-Z]{1,5}\b',
        r'\bbuy(?:ing)?\s+[A-Z]{1,5}\s+(?:calls?|puts?)\b',
        r'\bgoing\s+long\b',
    ]
    for pattern in long_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def has_trade_structure(text: str) -> bool:
    """Check if text has the structure of a trade alert."""
    has_leg = bool(re.search(r'[+-]\d+\s+\d+\s*[CP]', text, re.IGNORECASE))
    has_limit = 'limit' in text.lower()
    has_size = has_size_indicator(text)
    
    return has_leg and has_limit and has_size


def is_exit_signal(text: str) -> bool:
    """Check if this is an exit/close signal."""
    text_lower = text.lower()
    
    exit_patterns = [
        r'\bexit\b',
        r'\btake profits?\b',
        r'\bcut\s+(the\s+)?position\b',
        r'\bclose\s+(the\s+)?position\b',
        r'\bclose\s+(it|this)\b',
        r'\bclosing\b.*\bposition\b',
        r'\bselling?\s+to\s+close\b',
        r'\bbuy\s+to\s+close\b',
    ]
    
    for pattern in exit_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def is_long_position(text: str) -> bool:
    """
    Check if this is a LONG position alert.
    Matches patterns like:
    - "Long AAPL"
    - "Buy 100 shares of TSLA"
    - "Long SPY 480C Jan 2026"
    - "Buying QQQ calls"
    - "Going long on NVDA"
    """
    long_patterns = [
        r'\blong\s+[A-Z]{1,5}\b',
        r'\bbuy(?:ing)?\s+\d+\s*shares?\s+(?:of\s+)?[A-Z]{1,5}\b',
        r'\bbuy(?:ing)?\s+[A-Z]{1,5}\s+(?:calls?|puts?)\b',
        r'\bgoing\s+long\s+(?:on\s+)?[A-Z]{1,5}\b',
        r'\blong\s+[A-Z]{1,5}\s+\d+\s*[CP]\b',
    ]
    
    for pattern in long_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False


def parse_long_position(text: str, raw_text: str) -> Optional[ParsedSignal]:
    """
    Parse a LONG position alert.
    Returns ParsedSignal with strategy LONG_STOCK or LONG_OPTION.
    """
    if not is_long_position(text):
        return None
    
    ticker = extract_ticker_for_long(text)
    if not ticker:
        return None
    
    quantity = extract_long_quantity(text)
    expiration = extract_expiration(text)
    option_type = extract_long_option_type(text)
    strike = extract_long_strike(text)
    
    is_option = (option_type is not None) or (expiration is not None) or (strike is not None)
    
    if is_option:
        strategy = "LONG_OPTION"
        legs = []
        if option_type:
            legs.append(OptionLeg(
                side="BUY",
                quantity=quantity,
                strike=strike if strike else 0.0,
                option_type=option_type
            ))
    else:
        strategy = "LONG_STOCK"
        legs = []
    
    strategy_literal = cast(Literal["CALL_DEBIT_SPREAD", "CALL_CREDIT_SPREAD", "PUT_DEBIT_SPREAD", "PUT_CREDIT_SPREAD", "LONG_STOCK", "LONG_OPTION", "EXIT"], strategy)
    
    return ParsedSignal(
        ticker=ticker,
        strategy=strategy_literal,
        expiration=expiration,
        legs=legs,
        limit_min=0.0,
        limit_max=0.0,
        limit_kind="DEBIT",
        size_pct=config.DEFAULT_SIZE_PCT,
        raw_text=raw_text,
        quantity=quantity
    )


def extract_ticker_for_long(text: str) -> Optional[str]:
    """Extract ticker specifically from long position patterns."""
    patterns = [
        r'\bgoing\s+long\s+(?:on\s+)?([A-Z]{1,5})\b',
        r'\blong\s+([A-Z]{1,5})\b',
        r'\bbuy(?:ing)?\s+\d+\s*shares?\s+(?:of\s+)?([A-Z]{1,5})\b',
        r'\bbuy(?:ing)?\s+([A-Z]{1,5})\s+(?:calls?|puts?)\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            ticker = match.group(1).upper()
            if ticker not in {'ON', 'OF', 'THE', 'A', 'AN'}:
                return ticker
    
    return extract_ticker_anywhere(text)


def extract_long_quantity(text: str) -> int:
    """Extract quantity (shares or contracts) from long position alert."""
    shares_pattern = r'\b(\d+)\s*shares?\b'
    match = re.search(shares_pattern, text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    contracts_pattern = r'\b(\d+)\s*(?:contracts?|lots?)\b'
    match = re.search(contracts_pattern, text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    qty_pattern = r'\bbuy(?:ing)?\s+(\d+)\s+'
    match = re.search(qty_pattern, text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    return 1


def extract_long_option_type(text: str) -> Optional[Literal["CALL", "PUT"]]:
    """Extract option type (CALL or PUT) from long position alert."""
    text_lower = text.lower()
    
    if re.search(r'\bcalls?\b', text_lower):
        return "CALL"
    if re.search(r'\bputs?\b', text_lower):
        return "PUT"
    
    if re.search(r'\d+\s*C\b', text):
        return "CALL"
    if re.search(r'\d+\s*P\b', text):
        return "PUT"
    
    return None


def extract_long_strike(text: str) -> Optional[float]:
    """Extract strike price from long position alert."""
    strike_pattern = r'\b(\d+(?:\.\d+)?)\s*[CP]\b'
    match = re.search(strike_pattern, text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    
    strike_pattern2 = r'\$(\d+(?:\.\d+)?)\s+(?:calls?|puts?)'
    match = re.search(strike_pattern2, text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    
    return None


def extract_ticker_anywhere(text: str) -> Optional[str]:
    """
    Extract ticker symbol from anywhere in the text.
    Looks for 1-5 capital letter words that are likely tickers.
    """
    common_tickers = [
        'SPY', 'QQQ', 'IWM', 'DIA', 'SPX', 'NDX', 'GLD', 'SLV', 'TLT', 'XLF',
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'TSLA', 'NVDA', 'AMD',
        'NFLX', 'BABA', 'BA', 'DIS', 'JPM', 'V', 'MA', 'WMT', 'HD', 'NKE',
        'COST', 'MCD', 'SBUX', 'PEP', 'KO', 'XOM', 'CVX', 'CRM', 'ADBE', 'PYPL',
        'SQ', 'SHOP', 'UBER', 'LYFT', 'COIN', 'ROKU', 'ZM', 'SNAP', 'PINS', 'TWTR',
        'GME', 'AMC', 'PLTR', 'SOFI', 'RIVN', 'LCID', 'F', 'GM', 'INTC', 'MU',
        'EOSE', 'VIX', 'USO', 'EEM', 'FXI', 'EWZ', 'GDX', 'GDXJ', 'XLE', 'XLK'
    ]
    
    excluded_words = {
        'LEAP', 'LEAPS', 'CALL', 'PUT', 'BEAR', 'BULL', 'DAY', 'NEXT', 'THE', 'AND',
        'BUY', 'SELL', 'OPEN', 'CLOSE', 'LIMIT', 'SIZE', 'EXP', 'WITH', 'FOR',
        'DEBIT', 'CREDIT', 'SPREAD', 'IRON', 'CONDOR', 'BUTTERFLY', 'STRADDLE',
        'STRANGLE', 'LIKE', 'SHARE', 'COMMENTS', 'WRITE', 'COMMENT', 'AGO',
        'VICTORY', 'TRADES', 'VT', 'BULLISH', 'BEARISH'
    }
    
    for ticker in common_tickers:
        if re.search(rf'\b{ticker}\b', text, re.IGNORECASE):
            return ticker
    
    words = re.findall(r'\b([A-Z]{1,5})\b', text)
    
    for word in words:
        if word not in excluded_words:
            if len(word) >= 2 or word in ['F', 'V', 'X']:
                return word
    
    return None


def extract_expiration(text: str) -> Optional[date]:
    """
    Extract expiration date from text.
    Handles formats like:
    - 6/17/2027 exp
    - 12/12/25 exp
    - 6/17/2027
    - December exp
    """
    exp_pattern = r'(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:exp|expiration)?'
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
    
    month_exp_pattern = r'(\w+)\s+exp'
    match = re.search(month_exp_pattern, text, re.IGNORECASE)
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
    - Sell to open the 15 put
    - Buy the 420 call
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
    
    if not legs:
        sell_pattern = r'sell\s+(?:to\s+open\s+)?(?:the\s+)?(\d+(?:\.\d+)?)\s*(call|put)'
        sell_matches = re.findall(sell_pattern, text, re.IGNORECASE)
        for strike_str, opt_type in sell_matches:
            legs.append(OptionLeg(
                side="SELL",
                quantity=1,
                strike=float(strike_str),
                option_type="CALL" if opt_type.lower() == "call" else "PUT"
            ))
        
        buy_pattern = r'buy\s+(?:to\s+open\s+)?(?:the\s+)?(\d+(?:\.\d+)?)\s*(call|put)'
        buy_matches = re.findall(buy_pattern, text, re.IGNORECASE)
        for strike_str, opt_type in buy_matches:
            legs.append(OptionLeg(
                side="BUY",
                quantity=1,
                strike=float(strike_str),
                option_type="CALL" if opt_type.lower() == "call" else "PUT"
            ))
    
    return legs


def extract_limit_price(text: str) -> Optional[tuple[float, float, str]]:
    """
    Extract limit price range and type from text.
    Returns (min, max, kind) tuple or None.
    
    Handles formats like:
    - Limit 1.85-1.9 debit to open
    - Limit 2.6-2.7 credit to open
    - Limit .15 credit
    - Limit 1.85 debit
    """
    range_pattern = r'limit\s+\.?(\d+(?:\.\d+)?)\s*[-–]\s*\.?(\d+(?:\.\d+)?)\s*(debit|credit)'
    match = re.search(range_pattern, text, re.IGNORECASE)
    
    if match:
        min_price = float(match.group(1))
        max_price = float(match.group(2))
        kind = match.group(3).upper()
        
        if min_price > max_price:
            min_price, max_price = max_price, min_price
        
        return (min_price, max_price, kind)
    
    single_pattern = r'limit\s+\.?(\d+(?:\.\d+)?)\s*(debit|credit)'
    match = re.search(single_pattern, text, re.IGNORECASE)
    
    if match:
        price = float(match.group(1))
        kind = match.group(2).upper()
        return (price, price, kind)
    
    return None


def has_size_indicator(text: str) -> bool:
    """Check if text contains a size indicator."""
    text_lower = text.lower()
    
    if re.search(r'\d+(?:\.\d+)?\s*%\s*size', text_lower):
        return True
    
    if re.search(r'\$\d+(?:,\d+)*(?:\.\d+)?\s*(?:in\s+)?(?:buying\s+power|bp)', text_lower):
        return True
    
    if re.search(r'\d+\s*(?:contract|lot)s?', text_lower):
        return True
    
    return False


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


def determine_strategy(text: str, limit_kind: str) -> str:
    """
    Determine the strategy type based on text content and limit kind.
    """
    text_lower = text.lower()
    
    has_put = 'put' in text_lower or re.search(r'\d+\s*P\b', text)
    has_call = 'call' in text_lower or re.search(r'\d+\s*C\b', text)
    
    if limit_kind == "DEBIT":
        if has_put and not has_call:
            return "PUT_DEBIT_SPREAD"
        return "CALL_DEBIT_SPREAD"
    else:
        if has_put and not has_call:
            return "PUT_CREDIT_SPREAD"
        return "CALL_CREDIT_SPREAD"


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
