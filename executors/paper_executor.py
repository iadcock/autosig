"""
Paper executor for signal-based replay execution (v1.0).

PAPER MODE = SIGNAL-BASED REPLAY
- Never connects to brokers
- Never checks market hours
- Never validates price ranges
- Assumes fills at signal timestamp
- Prices are annotations only, never block fills
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
    Signal-based paper executor for learning replay.
    
    PAPER MODE PHILOSOPHY (v1.0):
    - Signal-time-priority fills: Entry/exit filled immediately at signal timestamp
    - No broker connectivity required
    - No market hours constraints
    - No price range validation
    - Prices are non-blocking annotations
    
    This executor is used when DRY_RUN=True to provide signal-based learning
    without execution realism or broker dependencies.
    """
    
    def __init__(self):
        """Initialize the paper executor."""
        self._order_counter = 0
    
    @property
    def broker_name(self) -> str:
        return "paper_signal_replay"
    
    def execute(self, intent: TradeIntent) -> ExecutionResult:
        """
        Execute signal-based paper replay.
        
        PAPER MODE RULES:
        - Entry filled immediately at signal timestamp (or current time if not available)
        - Exit filled immediately at exit signal timestamp
        - No price validation - prices are annotations only
        - Status: SIMULATED_ENTRY_AT_SIGNAL_TIME or SIMULATED_EXIT_AT_SIGNAL_TIME
        
        Args:
            intent: The TradeIntent to execute
            
        Returns:
            ExecutionResult with signal-time simulated fill
        """
        is_valid, error = self.validate_intent(intent)
        if not is_valid:
            return ExecutionResult(
                intent_id=intent.id,
                status="REJECTED",
                broker=self.broker_name,
                message=f"Validation failed: {error}"
            )
        
        # Signal-time priority: Use signal timestamp from metadata, or current time
        signal_timestamp = intent.metadata.get("signal_timestamp") if intent.metadata else None
        if signal_timestamp:
            try:
                if isinstance(signal_timestamp, str):
                    fill_time = datetime.fromisoformat(signal_timestamp.replace("Z", "+00:00"))
                else:
                    fill_time = signal_timestamp
            except:
                fill_time = datetime.utcnow()
        else:
            fill_time = datetime.utcnow()
        
        self._order_counter += 1
        order_id = f"paper_signal_{uuid.uuid4().hex[:8]}"
        
        # Price handling: Non-blocking annotation
        fill_price = self._calculate_fill_price(intent)
        
        # Determine signal type and status label
        signal_type = intent.metadata.get("signal_type", "ENTRY") if intent.metadata else "ENTRY"
        is_capital_recapture = intent.metadata.get("capital_recapture", False) if intent.metadata else False
        
        if signal_type == "EXIT" or intent.action in ["BUY_TO_CLOSE", "SELL_TO_CLOSE"]:
            if is_capital_recapture:
                status_label = "CAPITAL_RECAPTURE — SIMULATED_EXIT_AT_SIGNAL_TIME"
                fill_summary = self._build_capital_recapture_summary(intent, fill_price, fill_time)
            else:
                status_label = "SIMULATED_EXIT_AT_SIGNAL_TIME"
                fill_summary = self._build_exit_summary(intent, fill_price, fill_time)
        else:
            status_label = "SIMULATED_ENTRY_AT_SIGNAL_TIME"
            fill_summary = self._build_entry_summary(intent, fill_price, fill_time)
        
        logger.info(f"[PAPER MODE — SIGNAL-BASED REPLAY] {fill_summary}")
        logger.info(f"  Status: {status_label}")
        logger.info(f"  NO BROKER • NO MARKET HOURS • NO PRICE CONSTRAINTS")
        
        payload = self._build_submitted_payload(intent)
        
        # Handle position tracking
        position_id = None
        if signal_type == "ENTRY" or intent.action in ["BUY_TO_OPEN", "SELL_TO_OPEN"]:
            position_id = self._create_open_position(intent, fill_price, payload)
            if position_id:
                fill_summary += f" [Position: {position_id[:8]}...]"
                # Explicitly label as OPEN_PAPER when position is created (no exit signal exists)
                status_label = f"OPEN_PAPER — {status_label}"
        elif signal_type == "EXIT" or intent.action in ["BUY_TO_CLOSE", "SELL_TO_CLOSE"]:
            matched_id = intent.metadata.get("matched_position_id") if intent.metadata else None
            if matched_id:
                self._close_position(matched_id, intent)
                fill_summary += f" [Closed: {matched_id[:8]}...]"
        
        return ExecutionResult(
            intent_id=intent.id,
            status="SIMULATED",  # Status will be labeled in message
            broker=self.broker_name,
            order_id=order_id,
            message=f"{status_label}: {fill_summary}",
            fill_price=fill_price,
            filled_quantity=intent.quantity,
            filled_at=fill_time,
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
        Calculate fill price annotation (non-blocking).
        
        PAPER MODE RULE: Prices are annotations only, never block fills.
        Priority order:
        1. Explicit signal price (if present)
        2. Midpoint of provided range (if present)
        3. "ASSUMED_AT_SIGNAL_TIME" fallback
        
        Prices must never block or delay fills.
        """
        # Priority 1: Explicit signal price
        if intent.order_type == "LIMIT" and intent.limit_price:
            return intent.limit_price
        
        # Priority 2: Midpoint of range (if both min and max provided)
        if intent.limit_max is not None and intent.limit_min is not None:
            if intent.limit_max > 0 and intent.limit_min > 0:
                return (intent.limit_max + intent.limit_min) / 2.0
        
        # Priority 2b: Use max if available
        if intent.limit_max is not None and intent.limit_max > 0:
            return intent.limit_max
        
        # Priority 2c: Use min if available
        if intent.limit_min is not None and intent.limit_min > 0:
            return intent.limit_min
        
        # Priority 3: Fallback assumptions (never blocks)
        if intent.instrument_type == "STOCK":
            return 100.00  # ASSUMED_AT_SIGNAL_TIME
        elif intent.instrument_type == "SPREAD":
            return 1.50  # ASSUMED_AT_SIGNAL_TIME
        else:
            return 2.50  # ASSUMED_AT_SIGNAL_TIME
    
    def _build_entry_summary(self, intent: TradeIntent, fill_price: float, fill_time: datetime) -> str:
        """Build entry fill summary with signal-time annotation."""
        time_str = fill_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        if intent.instrument_type == "STOCK":
            return f"Entry filled at signal time ({time_str}): {intent.action} {intent.quantity} shares of {intent.underlying} @ ${fill_price:.2f} (assumed)"
        
        elif intent.instrument_type == "SPREAD":
            leg_count = len(intent.legs)
            net_type = "debit" if intent.action in ["BUY", "BUY_TO_OPEN"] else "credit"
            legs_desc = []
            for leg in intent.legs:
                legs_desc.append(f"{leg.side} {leg.strike}{leg.option_type[0]} {leg.expiration}")
            legs_str = " / ".join(legs_desc) if legs_desc else f"{leg_count}-leg spread"
            return f"Entry filled at signal time ({time_str}): {intent.underlying} {legs_str} for ${fill_price:.2f} {net_type} (assumed)"
        
        else:
            if intent.legs:
                leg = intent.legs[0]
                return f"Entry filled at signal time ({time_str}): {intent.action} {intent.quantity}x {intent.underlying} {leg.strike}{leg.option_type[0]} {leg.expiration} @ ${fill_price:.2f} (assumed)"
            return f"Entry filled at signal time ({time_str}): {intent.action} {intent.quantity}x {intent.underlying} option @ ${fill_price:.2f} (assumed)"
    
    def _build_exit_summary(self, intent: TradeIntent, fill_price: float, fill_time: datetime) -> str:
        """Build exit fill summary with signal-time annotation."""
        time_str = fill_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        if intent.instrument_type == "STOCK":
            return f"Exit filled at signal time ({time_str}): {intent.action} {intent.quantity} shares of {intent.underlying} @ ${fill_price:.2f} (assumed)"
        
        elif intent.instrument_type == "SPREAD":
            leg_count = len(intent.legs)
            net_type = "debit" if intent.action in ["BUY", "BUY_TO_OPEN"] else "credit"
            legs_desc = []
            for leg in intent.legs:
                legs_desc.append(f"{leg.side} {leg.strike}{leg.option_type[0]} {leg.expiration}")
            legs_str = " / ".join(legs_desc) if legs_desc else f"{leg_count}-leg spread"
            return f"Exit filled at signal time ({time_str}): {intent.underlying} {legs_str} for ${fill_price:.2f} {net_type} (assumed)"
        
        else:
            if intent.legs:
                leg = intent.legs[0]
                return f"Exit filled at signal time ({time_str}): {intent.action} {intent.quantity}x {intent.underlying} {leg.strike}{leg.option_type[0]} {leg.expiration} @ ${fill_price:.2f} (assumed)"
            return f"Exit filled at signal time ({time_str}): {intent.action} {intent.quantity}x {intent.underlying} option @ ${fill_price:.2f} (assumed)"
    
    def _build_capital_recapture_summary(self, intent: TradeIntent, fill_price: float, fill_time: datetime) -> str:
        """Build capital recapture exit summary with explicit labeling."""
        time_str = fill_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        metadata = intent.metadata or {}
        
        q_sold = metadata.get("quantity_sold", intent.quantity)
        q_remaining = metadata.get("quantity_remaining", 0)
        capital_recovered = metadata.get("capital_recovered", 0.0)
        original_qty = metadata.get("original_quantity", intent.quantity)
        entry_price = metadata.get("entry_price", fill_price)
        
        if intent.instrument_type == "STOCK":
            return (f"Capital recapture exit at signal time ({time_str}): "
                   f"Sell {q_sold} shares of {intent.underlying} @ ${fill_price:.2f} "
                   f"(recover ${capital_recovered:.2f}, hold {q_remaining} shares risk-free)")
        else:
            return (f"Capital recapture exit at signal time ({time_str}): "
                   f"Sell {q_sold} contracts of {intent.underlying} @ ${fill_price:.2f} "
                   f"(recover ${capital_recovered:.2f}, hold {q_remaining} contracts risk-free)")
    
    def _build_fill_summary(self, intent: TradeIntent, fill_price: float) -> str:
        """Legacy method - use _build_entry_summary or _build_exit_summary instead."""
        return self._build_entry_summary(intent, fill_price, datetime.utcnow())
    
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
