"""
Risk management module for the trading bot.
Calculates position sizing and enforces safety limits.
"""

import math
import logging
from typing import Optional

from models import ParsedSignal
import config

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages position sizing and risk constraints."""
    
    def __init__(
        self,
        max_contracts_per_trade: int = config.MAX_CONTRACTS_PER_TRADE,
        max_open_positions: int = config.MAX_OPEN_POSITIONS,
        max_daily_risk_pct: float = config.MAX_DAILY_RISK_PCT
    ):
        self.max_contracts_per_trade = max_contracts_per_trade
        self.max_open_positions = max_open_positions
        self.max_daily_risk_pct = max_daily_risk_pct
        
        self.daily_risk_used = 0.0
        self.open_positions_count = 0
    
    def calculate_position_size(
        self,
        signal: ParsedSignal,
        account_equity: float
    ) -> tuple[int, Optional[str]]:
        """
        Calculate the number of contracts to trade based on risk parameters.
        
        Returns:
            tuple of (num_contracts, rejection_reason)
            If rejected, num_contracts will be 0 and reason will explain why.
        """
        if account_equity <= 0:
            return 0, "Account equity is zero or negative"
        
        max_dollar_risk = account_equity * signal.size_pct
        
        if signal.strategy == "CALL_DEBIT_SPREAD":
            cost_per_contract = signal.limit_max * 100
            if cost_per_contract <= 0:
                return 0, "Invalid limit price for debit spread"
            max_contracts = math.floor(max_dollar_risk / cost_per_contract)
            
        elif signal.strategy == "CALL_CREDIT_SPREAD":
            spread_width = signal.spread_width
            if spread_width <= 0:
                spread_width = 5.0
                logger.warning(f"Could not determine spread width, using default: {spread_width}")
            
            max_loss_per_contract = (spread_width - signal.limit_min) * 100
            if max_loss_per_contract <= 0:
                max_loss_per_contract = spread_width * 100
            
            max_contracts = math.floor(max_dollar_risk / max_loss_per_contract)
            
        elif signal.strategy == "EXIT":
            return 0, None
            
        else:
            return 0, f"Unknown strategy: {signal.strategy}"
        
        if max_contracts <= 0:
            return 0, f"Position size too small for {signal.size_pct*100}% risk"
        
        rejection = self._check_risk_constraints(
            max_contracts, 
            max_dollar_risk, 
            account_equity
        )
        
        if rejection:
            return 0, rejection
        
        final_contracts = min(max_contracts, self.max_contracts_per_trade)
        
        return final_contracts, None
    
    def _check_risk_constraints(
        self,
        num_contracts: int,
        dollar_risk: float,
        account_equity: float
    ) -> Optional[str]:
        """
        Check if trade violates any risk constraints.
        Returns rejection reason or None if acceptable.
        """
        if self.open_positions_count >= self.max_open_positions:
            return f"Max open positions limit reached ({self.max_open_positions})"
        
        daily_risk_limit = account_equity * self.max_daily_risk_pct
        if self.daily_risk_used + dollar_risk > daily_risk_limit:
            return (
                f"Daily risk limit would be exceeded "
                f"(used: ${self.daily_risk_used:.2f}, "
                f"limit: ${daily_risk_limit:.2f})"
            )
        
        return None
    
    def record_trade(self, dollar_risk: float) -> None:
        """Record a trade for daily tracking."""
        self.daily_risk_used += dollar_risk
        self.open_positions_count += 1
        logger.info(
            f"Trade recorded. Daily risk: ${self.daily_risk_used:.2f}, "
            f"Open positions: {self.open_positions_count}"
        )
    
    def record_exit(self) -> None:
        """Record a position exit."""
        if self.open_positions_count > 0:
            self.open_positions_count -= 1
        logger.info(f"Exit recorded. Open positions: {self.open_positions_count}")
    
    def reset_daily_limits(self) -> None:
        """Reset daily counters (call at start of each trading day)."""
        self.daily_risk_used = 0.0
        logger.info("Daily risk limits reset")


def calculate_debit_spread_risk(
    limit_max: float,
    num_contracts: int
) -> float:
    """Calculate total risk for a debit spread."""
    return limit_max * 100 * num_contracts


def calculate_credit_spread_risk(
    spread_width: float,
    limit_min: float,
    num_contracts: int
) -> float:
    """
    Calculate total risk for a credit spread.
    Max loss = (spread_width - credit_received) * 100 * contracts
    """
    max_loss_per_contract = (spread_width - limit_min) * 100
    return max_loss_per_contract * num_contracts
