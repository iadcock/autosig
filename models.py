"""
Pydantic models for the trading bot.
Defines data structures for parsed trade signals and option legs.
"""

from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field


class OptionLeg(BaseModel):
    """Represents a single leg of an options spread."""
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, description="Always positive, side indicates direction")
    strike: float
    option_type: Literal["CALL", "PUT"] = "CALL"
    
    @property
    def signed_quantity(self) -> int:
        """Returns positive for BUY, negative for SELL."""
        return self.quantity if self.side == "BUY" else -self.quantity


class ParsedSignal(BaseModel):
    """Represents a fully parsed trade alert signal."""
    ticker: str = Field(description="Underlying symbol, e.g., GLD, SPX")
    strategy: Literal[
        "CALL_DEBIT_SPREAD", "CALL_CREDIT_SPREAD", 
        "PUT_DEBIT_SPREAD", "PUT_CREDIT_SPREAD", 
        "LONG_STOCK", "LONG_OPTION",
        "EXIT"
    ]
    expiration: Optional[date] = Field(default=None, description="Option expiration date")
    legs: list[OptionLeg] = Field(default_factory=list, description="Option legs for the trade")
    limit_min: float = Field(ge=0, description="Minimum limit price")
    limit_max: float = Field(ge=0, description="Maximum limit price")
    limit_kind: Literal["DEBIT", "CREDIT"] = "DEBIT"
    size_pct: float = Field(ge=0, le=1, description="Position size as decimal, e.g., 0.02 for 2%")
    raw_text: str = Field(description="Original alert text for reference")
    quantity: int = Field(default=1, description="Number of shares or contracts for long positions")
    
    @property
    def spread_width(self) -> float:
        """Calculate the width between strikes for vertical spreads."""
        if len(self.legs) >= 2:
            strikes = [leg.strike for leg in self.legs]
            return abs(max(strikes) - min(strikes))
        return 0.0
    
    def get_limit_price_for_order(self) -> float:
        """
        Returns the appropriate limit price for order submission.
        - For DEBIT orders: use limit_max (worst acceptable price to pay)
        - For CREDIT orders: use limit_min (minimum acceptable credit to receive)
        """
        if self.limit_kind == "DEBIT":
            return self.limit_max
        else:
            return self.limit_min


class TradeState(BaseModel):
    """Tracks state for preventing duplicate alert processing."""
    last_processed_id: Optional[str] = None
    last_processed_timestamp: Optional[str] = None
    processed_alert_hashes: list[str] = Field(default_factory=list)
    daily_trades_count: int = 0
    daily_risk_used: float = 0.0
    last_reset_date: Optional[str] = None
    last_summary_date: Optional[str] = None
