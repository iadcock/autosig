"""
TradeIntent and ExecutionResult models for broker-agnostic trade execution.

TradeIntent represents a user's intent to trade, independent of any specific broker.
ExecutionResult represents the outcome of executing a TradeIntent.
"""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


class OptionLeg(BaseModel):
    """Represents a single leg of an options trade."""
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, description="Number of contracts (always positive)")
    strike: float
    option_type: Literal["CALL", "PUT"] = "CALL"
    expiration: str = Field(description="Expiration date in YYYY-MM-DD format")


class TradeIntent(BaseModel):
    """
    Broker-agnostic representation of a trade intent.
    
    This model captures everything needed to execute a trade across any broker.
    The execution layer maps this to broker-specific API calls.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    execution_mode: Literal["PAPER", "LIVE", "HISTORICAL"] = "PAPER"
    instrument_type: Literal["STOCK", "OPTION", "SPREAD"] = "STOCK"
    
    underlying: str = Field(description="Underlying symbol, e.g., SPY, SPX, AAPL")
    symbol: Optional[str] = Field(default=None, description="Specific symbol (OCC for options)")
    
    action: Literal["BUY", "SELL", "BUY_TO_OPEN", "BUY_TO_CLOSE", "SELL_TO_OPEN", "SELL_TO_CLOSE"] = "BUY"
    order_type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"] = "MARKET"
    
    limit_price: Optional[float] = Field(default=None, description="Limit price for limit orders")
    stop_price: Optional[float] = Field(default=None, description="Stop trigger price for stop orders")
    limit_min: Optional[float] = Field(default=None, description="Minimum acceptable price")
    limit_max: Optional[float] = Field(default=None, description="Maximum acceptable price")
    
    quantity: int = Field(default=1, gt=0, description="Number of shares or contracts")
    risk_pct: Optional[float] = Field(default=None, ge=0, le=1, description="Risk as percentage of account")
    
    legs: list[OptionLeg] = Field(default_factory=list, description="Option legs for spreads")
    
    raw_signal: Optional[str] = Field(default=None, description="Original signal text for reference")
    metadata: dict = Field(default_factory=dict, description="Additional broker-specific data")
    
    def get_effective_limit_price(self) -> Optional[float]:
        """Get the limit price to use for order submission."""
        if self.limit_price is not None:
            return self.limit_price
        if self.limit_max is not None:
            return self.limit_max
        return None


class ExecutionResult(BaseModel):
    """
    Result of executing a TradeIntent.
    
    Captures the outcome regardless of which broker executed the trade.
    """
    intent_id: str = Field(description="ID of the TradeIntent that was executed")
    status: Literal["FILLED", "SUBMITTED", "REJECTED", "SIMULATED", "ERROR"] = "SUBMITTED"
    
    broker: str = Field(description="Broker that executed the trade, e.g., 'tradier', 'alpaca', 'paper'")
    order_id: Optional[str] = Field(default=None, description="Broker-assigned order ID")
    
    message: Optional[str] = Field(default=None, description="Status message or error details")
    
    fill_price: Optional[float] = Field(default=None, description="Actual fill price")
    filled_quantity: Optional[int] = Field(default=None, description="Quantity that was filled")
    
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = Field(default=None)
    
    submitted_payload: Optional[dict] = Field(default=None, description="Raw payload sent to broker")
    raw_response: Optional[dict] = Field(default=None, description="Raw response from broker")
