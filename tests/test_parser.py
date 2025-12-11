"""
Unit tests for the alert parser module.
"""

import pytest
from datetime import date

from parser import (
    parse_alert,
    extract_ticker,
    extract_strategy,
    extract_expiration,
    extract_legs,
    extract_limit_price,
    extract_size_pct,
    is_chatty_alert,
    get_alert_hash,
)


class TestExtractTicker:
    def test_simple_ticker(self):
        assert extract_ticker("GLD leap bullish call debit spread") == "GLD"
    
    def test_three_letter_ticker(self):
        assert extract_ticker("SPX next day bear call credit spread") == "SPX"
    
    def test_four_letter_ticker(self):
        assert extract_ticker("AAPL bullish call debit spread") == "AAPL"
    
    def test_ignores_keywords(self):
        assert extract_ticker("GLD LEAP bullish call spread") == "GLD"


class TestExtractStrategy:
    def test_debit_spread(self):
        assert extract_strategy("GLD leap bullish call debit spread") == "CALL_DEBIT_SPREAD"
    
    def test_credit_spread(self):
        assert extract_strategy("SPX next day bear call credit spread") == "CALL_CREDIT_SPREAD"
    
    def test_exit_alert(self):
        assert extract_strategy("SPX December call debit exit") == "EXIT"
    
    def test_close_alert(self):
        assert extract_strategy("AAPL position close\nLimit 1.5 credit to close") == "EXIT"
    
    def test_unknown_strategy(self):
        assert extract_strategy("Random text without strategy") is None


class TestExtractExpiration:
    def test_full_date_format(self):
        result = extract_expiration("6/17/2027 exp")
        assert result == date(2027, 6, 17)
    
    def test_short_year_format(self):
        result = extract_expiration("12/12/25 exp")
        assert result == date(2025, 12, 12)
    
    def test_no_expiration(self):
        result = extract_expiration("Some text without expiration")
        assert result is None


class TestExtractLegs:
    def test_debit_spread_legs(self):
        legs = extract_legs("+1 415 C / -1 420 C")
        assert len(legs) == 2
        assert legs[0].side == "BUY"
        assert legs[0].strike == 415
        assert legs[0].option_type == "CALL"
        assert legs[1].side == "SELL"
        assert legs[1].strike == 420
        assert legs[1].option_type == "CALL"
    
    def test_credit_spread_legs(self):
        legs = extract_legs("-1 6860 C / +1 6865 C")
        assert len(legs) == 2
        assert legs[0].side == "SELL"
        assert legs[0].strike == 6860
        assert legs[1].side == "BUY"
        assert legs[1].strike == 6865
    
    def test_no_legs(self):
        legs = extract_legs("No legs here")
        assert legs == []


class TestExtractLimitPrice:
    def test_debit_range(self):
        result = extract_limit_price("Limit 1.85-1.9 debit to open")
        assert result == (1.85, 1.9, "DEBIT")
    
    def test_credit_range(self):
        result = extract_limit_price("Limit 2.6-2.7 credit to open")
        assert result == (2.6, 2.7, "CREDIT")
    
    def test_credit_to_close(self):
        result = extract_limit_price("Limit 1.85-2.0 credit to close")
        assert result == (1.85, 2.0, "CREDIT")
    
    def test_no_limit(self):
        result = extract_limit_price("No limit price here")
        assert result is None


class TestExtractSizePct:
    def test_two_percent(self):
        result = extract_size_pct("2% size")
        assert result == 0.02
    
    def test_one_percent(self):
        result = extract_size_pct("1% size")
        assert result == 0.01
    
    def test_decimal_percent(self):
        result = extract_size_pct("1.5% size")
        assert result == 0.015
    
    def test_default_fallback(self):
        result = extract_size_pct("No size specified")
        assert result == 0.01


class TestIsChattyAlert:
    def test_roll_alert(self):
        text = "CIFR covered call roll\nMarket is bear!!!!"
        assert is_chatty_alert(text) is True
    
    def test_tempted_alert(self):
        text = "I'm tempted to just exit though"
        assert is_chatty_alert(text) is True
    
    def test_valid_debit_spread(self):
        text = "GLD leap bullish call debit spread\n6/17/2027 exp\n+1 415 C / -1 420 C\nLimit 1.85-1.9 debit to open"
        assert is_chatty_alert(text) is False


class TestParseAlert:
    def test_full_debit_spread_alert(self):
        alert = """GLD leap bullish call debit spread

6/17/2027 exp

+1 415 C / -1 420 C
Limit 1.85-1.9 debit to open

2% size"""
        
        result = parse_alert(alert)
        assert result is not None
        assert result.ticker == "GLD"
        assert result.strategy == "CALL_DEBIT_SPREAD"
        assert result.expiration == date(2027, 6, 17)
        assert len(result.legs) == 2
        assert result.limit_min == 1.85
        assert result.limit_max == 1.9
        assert result.limit_kind == "DEBIT"
        assert result.size_pct == 0.02
    
    def test_full_credit_spread_alert(self):
        alert = """SPX next day bear call credit spread

12/12/25 exp

-1 6860 C / +1 6865 C
Limit 2.6-2.7 credit to open

1% size"""
        
        result = parse_alert(alert)
        assert result is not None
        assert result.ticker == "SPX"
        assert result.strategy == "CALL_CREDIT_SPREAD"
        assert result.expiration == date(2025, 12, 12)
        assert len(result.legs) == 2
        assert result.limit_min == 2.6
        assert result.limit_max == 2.7
        assert result.limit_kind == "CREDIT"
        assert result.size_pct == 0.01
    
    def test_chatty_alert_returns_none(self):
        alert = """CIFR covered call roll

Market is bear!!!!

Buy to close this week covered call then sell the 19 covered call expiring next week.

I'm tempted to just exit though"""
        
        result = parse_alert(alert)
        assert result is None
    
    def test_empty_alert_returns_none(self):
        assert parse_alert("") is None
        assert parse_alert("   ") is None


class TestGetAlertHash:
    def test_same_text_same_hash(self):
        text = "GLD debit spread"
        assert get_alert_hash(text) == get_alert_hash(text)
    
    def test_different_text_different_hash(self):
        assert get_alert_hash("GLD debit spread") != get_alert_hash("SPX credit spread")
    
    def test_whitespace_normalized(self):
        assert get_alert_hash("GLD  debit   spread") == get_alert_hash("GLD debit spread")
