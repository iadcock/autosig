"""
Paper executor for simulated trade execution.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from trade_intent import TradeIntent, ExecutionResult
from .base import BaseExecutor

logger = logging.getLogger(__name__)


class PaperExecutor(BaseExecutor):
    """
    Executor that simulates trade execution without sending real orders.
    
    Useful for testing and development without risking real money.
    Simulates immediate fills at the limit price (or a random price for market orders).
    Maintains paper positions for open/close tracking.
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
        order_id = f"paper_{uuid.uuid4().hex[:8]}"
        
        fill_price = self._calculate_fill_price(intent)
        fill_summary = self._build_fill_summary(intent, fill_price)
        
        logger.info(f"[PAPER] {fill_summary}")
        
        payload = self._build_submitted_payload(intent)
        
        # Handle position tracking
        position_id = None
        signal_type = intent.metadata.get("signal_type", "ENTRY") if intent.metadata else "ENTRY"
        
        if signal_type == "ENTRY" or intent.action in ["BUY_TO_OPEN", "SELL_TO_OPEN"]:
            position_id = self._create_open_position(intent, fill_price, payload)
            if position_id:
                fill_summary += f" [Position: {position_id[:8]}...]"
        elif signal_type == "EXIT" or intent.action in ["BUY_TO_CLOSE", "SELL_TO_CLOSE"]:
            matched_id = intent.metadata.get("matched_position_id") if intent.metadata else None
            if matched_id:
                self._close_position(matched_id, intent)
                fill_summary += f" [Closed: {matched_id[:8]}...]"
        
        return ExecutionResult(
            intent_id=intent.id,
            status="SIMULATED",
            broker=self.broker_name,
            order_id=order_id,
            message=fill_summary,
            fill_price=fill_price,
            filled_quantity=intent.quantity,
            filled_at=datetime.utcnow(),
            submitted_payload=payload
        )
    
    def _create_open_position(self, intent: TradeIntent, fill_price: float, payload: dict) -> Optional[str]:
        """Create an open position record for ENTRY trades."""
        try:
            from paper_positions import PaperPosition, PositionLeg, append_open_position
            
            position_legs = []
            for leg in intent.legs:
                position_legs.append(PositionLeg(
                    side=leg.side,
                    quantity=leg.quantity,
                    strike=leg.strike,
                    option_type=leg.option_type,
                    expiration=leg.expiration
                ))
            
            position = PaperPosition(
                status="OPEN",
                source_post_id=payload.get("metadata", {}).get("source_post_id", ""),
                underlying=intent.underlying,
                instrument_type=intent.instrument_type,
                legs=position_legs,
                quantity=intent.quantity,
                open_intent={
                    "id": intent.id,
                    "action": intent.action,
                    "order_type": intent.order_type,
                    "limit_price": intent.limit_price,
                    "fill_price": fill_price,
                    "legs": [
                        {
                            "side": leg.side,
                            "quantity": leg.quantity,
                            "strike": leg.strike,
                            "option_type": leg.option_type,
                            "expiration": leg.expiration
                        }
                        for leg in intent.legs
                    ],
                    "metadata": intent.metadata
                }
            )
            
            append_open_position(position)
            logger.info(f"[PAPER] Created open position: {position.position_id[:8]}... for {intent.underlying}")
            return position.position_id
            
        except Exception as e:
            logger.warning(f"[PAPER] Could not create position record: {e}")
            return None
    
    def _close_position(self, position_id: str, intent: TradeIntent) -> bool:
        """Close an existing position."""
        try:
            from paper_positions import mark_position_closed
            
            close_intent = {
                "id": intent.id,
                "action": intent.action,
                "order_type": intent.order_type,
                "limit_price": intent.limit_price,
                "legs": [
                    {
                        "side": leg.side,
                        "quantity": leg.quantity,
                        "strike": leg.strike,
                        "option_type": leg.option_type,
                        "expiration": leg.expiration
                    }
                    for leg in intent.legs
                ]
            }
            
            success = mark_position_closed(position_id, close_intent)
            if success:
                logger.info(f"[PAPER] Closed position: {position_id[:8]}...")
            else:
                logger.warning(f"[PAPER] Position {position_id[:8]}... not found or already closed")
            return success
            
        except Exception as e:
            logger.warning(f"[PAPER] Could not close position: {e}")
            return False
    
    def _calculate_fill_price(self, intent: TradeIntent) -> float:
        """
        Calculate simulated fill price.
        
        For limit orders, uses the limit price.
        For market orders, uses a simulated mid price.
        For spreads, uses net debit/credit.
        """
        if intent.order_type == "LIMIT" and intent.limit_price:
            return intent.limit_price
        
        if intent.limit_max is not None and intent.limit_max > 0:
            return intent.limit_max
        
        if intent.limit_min is not None and intent.limit_min > 0:
            return intent.limit_min
        
        if intent.limit_price:
            return intent.limit_price
        
        if intent.instrument_type == "STOCK":
            return 100.00
        elif intent.instrument_type == "SPREAD":
            return 1.50
        else:
            return 2.50
    
    def _build_fill_summary(self, intent: TradeIntent, fill_price: float) -> str:
        """Build a human-readable fill summary."""
        if intent.instrument_type == "STOCK":
            return f"Simulated {intent.action} {intent.quantity} shares of {intent.underlying} @ ${fill_price:.2f}"
        
        elif intent.instrument_type == "SPREAD":
            leg_count = len(intent.legs)
            net_type = "debit" if intent.action in ["BUY", "BUY_TO_OPEN"] else "credit"
            legs_desc = []
            for leg in intent.legs:
                legs_desc.append(f"{leg.side} {leg.strike}{leg.option_type[0]} {leg.expiration}")
            legs_str = " / ".join(legs_desc) if legs_desc else f"{leg_count}-leg spread"
            return f"Simulated {intent.underlying} {legs_str} for ${fill_price:.2f} {net_type}"
        
        else:
            if intent.legs:
                leg = intent.legs[0]
                return f"Simulated {intent.action} {intent.quantity}x {intent.underlying} {leg.strike}{leg.option_type[0]} {leg.expiration} @ ${fill_price:.2f}"
            return f"Simulated {intent.action} {intent.quantity}x {intent.underlying} option @ ${fill_price:.2f}"
    
    def _build_submitted_payload(self, intent: TradeIntent) -> dict:
        """Build the submitted payload for logging."""
        payload = {
            "intent_id": intent.id,
            "underlying": intent.underlying,
            "action": intent.action,
            "quantity": intent.quantity,
            "order_type": intent.order_type,
            "limit_price": intent.get_effective_limit_price(),
            "instrument_type": intent.instrument_type,
            "execution_mode": intent.execution_mode,
        }
        
        if intent.legs:
            payload["legs"] = [
                {
                    "side": leg.side,
                    "quantity": leg.quantity,
                    "strike": leg.strike,
                    "option_type": leg.option_type,
                    "expiration": leg.expiration
                }
                for leg in intent.legs
            ]
        
        if intent.metadata:
            payload["metadata"] = intent.metadata
        
        return payload
