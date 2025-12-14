"""
Historical executor for backtesting trade execution.
"""

import logging
from datetime import datetime
from typing import Optional

from trade_intent import TradeIntent, ExecutionResult
from .base import BaseExecutor

logger = logging.getLogger(__name__)


class HistoricalExecutor(BaseExecutor):
    """
    Executor that mocks trade execution using historical data.
    
    Useful for backtesting strategies against historical price data.
    Returns predefined results or can be configured with historical prices.
    """
    
    def __init__(self, historical_prices: Optional[dict[str, float]] = None):
        """
        Initialize the historical executor.
        
        Args:
            historical_prices: Optional dict mapping symbols to historical prices
        """
        self._historical_prices: dict[str, float] = historical_prices or {}
        self._order_counter = 0
    
    @property
    def broker_name(self) -> str:
        return "historical"
    
    def set_price(self, symbol: str, price: float) -> None:
        """Set the historical price for a symbol."""
        self._historical_prices[symbol] = price
    
    def execute(self, intent: TradeIntent) -> ExecutionResult:
        """
        Execute a trade intent using historical prices.
        
        Args:
            intent: The TradeIntent to execute
            
        Returns:
            ExecutionResult with historical mock data
        """
        is_valid, error = self.validate_intent(intent)
        if not is_valid:
            return ExecutionResult(
                intent_id=intent.id,
                status="REJECTED",
                broker=self.broker_name,
                message=f"Validation failed: {error}"
            )
        
        self._order_counter += 1
        order_id = f"HIST-{self._order_counter:06d}"
        
        fill_price = self._get_historical_price(intent)
        
        logger.info(f"[HISTORICAL] Mock fill for {intent.underlying}: "
                    f"{intent.action} {intent.quantity} @ ${fill_price:.2f}")
        
        payload = {
            "underlying": intent.underlying,
            "action": intent.action,
            "quantity": intent.quantity,
            "order_type": intent.order_type,
            "instrument_type": intent.instrument_type,
            "historical_mode": True
        }
        
        return ExecutionResult(
            intent_id=intent.id,
            status="SIMULATED",
            broker=self.broker_name,
            order_id=order_id,
            message=f"Historical backtest - filled at ${fill_price:.2f}",
            fill_price=fill_price,
            filled_quantity=intent.quantity,
            filled_at=datetime.utcnow(),
            submitted_payload=payload
        )
    
    def _get_historical_price(self, intent: TradeIntent) -> float:
        """
        Get historical price for the intent's symbol.
        
        Falls back to limit price or default if no historical data available.
        """
        symbol = intent.symbol or intent.underlying
        
        if symbol in self._historical_prices:
            return self._historical_prices[symbol]
        
        effective_price = intent.get_effective_limit_price()
        if effective_price is not None:
            return effective_price
        
        return 100.00
