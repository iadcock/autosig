"""
Unit tests for the risk management module.
"""

import pytest
from datetime import date
from typing import Literal, Tuple, cast

from risk import (
    RiskManager,
    calculate_debit_spread_risk,
    calculate_credit_spread_risk,
)
from models import ParsedSignal, OptionLeg

StrategyType = Literal["CALL_DEBIT_SPREAD", "CALL_CREDIT_SPREAD", "EXIT"]
LimitKindType = Literal["DEBIT", "CREDIT"]


def create_test_signal(
    strategy: StrategyType = "CALL_DEBIT_SPREAD",
    limit_max: float = 2.0,
    limit_min: float = 1.8,
    size_pct: float = 0.02,
    strikes: Tuple[float, float] = (100, 105)
) -> ParsedSignal:
    """Helper to create test signals."""
    legs = [
        OptionLeg(side="BUY", quantity=1, strike=strikes[0], option_type="CALL"),
        OptionLeg(side="SELL", quantity=1, strike=strikes[1], option_type="CALL"),
    ]
    limit_kind: LimitKindType = "DEBIT" if "DEBIT" in strategy else "CREDIT"
    return ParsedSignal(
        ticker="TEST",
        strategy=strategy,
        expiration=date(2025, 3, 21),
        legs=legs,
        limit_min=limit_min,
        limit_max=limit_max,
        limit_kind=limit_kind,
        size_pct=size_pct,
        raw_text="Test signal"
    )


class TestRiskManager:
    def test_debit_spread_position_sizing(self):
        manager = RiskManager(max_contracts_per_trade=10)
        signal = create_test_signal(
            strategy="CALL_DEBIT_SPREAD",
            limit_max=2.0,
            size_pct=0.02
        )
        
        num_contracts, reason = manager.calculate_position_size(signal, 100000)
        
        assert reason is None
        assert num_contracts == 10
    
    def test_credit_spread_position_sizing(self):
        manager = RiskManager(max_contracts_per_trade=20)
        signal = create_test_signal(
            strategy="CALL_CREDIT_SPREAD",
            limit_min=1.5,
            limit_max=1.7,
            size_pct=0.02,
            strikes=(100, 105)
        )
        
        num_contracts, reason = manager.calculate_position_size(signal, 100000)
        
        assert reason is None
        assert num_contracts > 0
    
    def test_exit_returns_zero_contracts(self):
        manager = RiskManager()
        signal = create_test_signal(strategy="EXIT")
        
        num_contracts, reason = manager.calculate_position_size(signal, 100000)
        
        assert num_contracts == 0
        assert reason is None
    
    def test_zero_equity_rejected(self):
        manager = RiskManager()
        signal = create_test_signal()
        
        num_contracts, reason = manager.calculate_position_size(signal, 0)
        
        assert num_contracts == 0
        assert reason is not None
        assert "zero or negative" in reason.lower()
    
    def test_max_contracts_cap(self):
        manager = RiskManager(max_contracts_per_trade=5)
        signal = create_test_signal(
            strategy="CALL_DEBIT_SPREAD",
            limit_max=1.0,
            size_pct=0.10
        )
        
        num_contracts, reason = manager.calculate_position_size(signal, 100000)
        
        assert num_contracts == 5
    
    def test_max_open_positions_limit(self):
        manager = RiskManager(max_open_positions=2)
        manager.open_positions_count = 2
        
        signal = create_test_signal()
        num_contracts, reason = manager.calculate_position_size(signal, 100000)
        
        assert num_contracts == 0
        assert reason is not None
        assert "max open positions" in reason.lower()
    
    def test_daily_risk_limit(self):
        manager = RiskManager(max_daily_risk_pct=0.05)
        manager.daily_risk_used = 4500
        
        signal = create_test_signal(
            strategy="CALL_DEBIT_SPREAD",
            limit_max=2.0,
            size_pct=0.02
        )
        num_contracts, reason = manager.calculate_position_size(signal, 100000)
        
        assert num_contracts == 0
        assert reason is not None
        assert "daily risk limit" in reason.lower()
    
    def test_record_trade(self):
        manager = RiskManager()
        initial_risk = manager.daily_risk_used
        initial_positions = manager.open_positions_count
        
        manager.record_trade(500)
        
        assert manager.daily_risk_used == initial_risk + 500
        assert manager.open_positions_count == initial_positions + 1
    
    def test_record_exit(self):
        manager = RiskManager()
        manager.open_positions_count = 3
        
        manager.record_exit()
        
        assert manager.open_positions_count == 2
    
    def test_reset_daily_limits(self):
        manager = RiskManager()
        manager.daily_risk_used = 5000
        
        manager.reset_daily_limits()
        
        assert manager.daily_risk_used == 0


class TestRiskCalculations:
    def test_debit_spread_risk(self):
        risk = calculate_debit_spread_risk(limit_max=2.0, num_contracts=5)
        assert risk == 1000.0
    
    def test_credit_spread_risk(self):
        risk = calculate_credit_spread_risk(
            spread_width=5.0,
            limit_min=1.5,
            num_contracts=5
        )
        assert risk == 1750.0
