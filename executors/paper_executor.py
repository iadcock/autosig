"""
Paper executor for simulated trade execution.
"""

import logging
from datetime import datetime
from typing import Optional
import random

from trade_intent import TradeIntent, ExecutionResult
from .base import BaseExecutor

logger = logging.getLogger(__name__)


class PaperExecutor(BaseExecutor):
    """
    Executor that simulates trade execution without sending real orders.
    
    Useful for testing and development without risking real money.
    Simulates immediate fills at the limit price (or a random price for market orders).
    """
    
    def __init__(self):
        """Initialize the paper executor."""
        self._order_counter = 0
    
    @property
    def broker_name(self) -> str:
        return "paper"
    
    def execute(self, intent: TradeIntent) -> ExecutionResult:
        """
        Simulate trade execution.
        
        Args:
            intent: The TradeIntent to execute
            
        Returns:
            ExecutionResult with simulated fill
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
        order_id = f"PAPER-{self._order_counter:06d}"
        
        fill_price = self._calculate_fill_price(intent)
        
        logger.info(f"[PAPER] Simulated fill for {intent.underlying}: "
                    f"{intent.action} {intent.quantity} @ ${fill_price:.2f}")
        
        payload = {
            "underlying": intent.underlying,
            "action": intent.action,
            "quantity": intent.quantity,
            "order_type": intent.order_type,
            "limit_price": intent.get_effective_limit_price(),
            "instrument_type": intent.instrument_type
        }
        
        return ExecutionResult(
            intent_id=intent.id,
            status="SIMULATED",
            broker=self.broker_name,
            order_id=order_id,
            message=f"Paper trade simulated - filled at ${fill_price:.2f}",
            fill_price=fill_price,
            filled_quantity=intent.quantity,
            filled_at=datetime.utcnow(),
            submitted_payload=payload
        )
    
    def _calculate_fill_price(self, intent: TradeIntent) -> float:
        """
        Calculate simulated fill price.
        
        For limit orders, uses the limit price.
        For market orders, simulates a price based on limit_min/limit_max if available.
        """
        if intent.order_type == "LIMIT" and intent.limit_price:
            return intent.limit_price
        
        if intent.limit_min is not None and intent.limit_max is not None:
            return round(random.uniform(intent.limit_min, intent.limit_max), 2)
        
        if intent.limit_price:
            return intent.limit_price
        
        return 100.00
