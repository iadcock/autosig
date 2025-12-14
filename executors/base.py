"""
Base executor interface for trade execution.
"""

from abc import ABC, abstractmethod
from trade_intent import TradeIntent, ExecutionResult


class BaseExecutor(ABC):
    """
    Abstract base class for trade executors.
    
    All executors must implement the execute() method to process TradeIntents.
    """
    
    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Return the broker identifier for this executor."""
        pass
    
    @abstractmethod
    def execute(self, intent: TradeIntent) -> ExecutionResult:
        """
        Execute a trade intent.
        
        Args:
            intent: The TradeIntent to execute
            
        Returns:
            ExecutionResult with status and details
        """
        pass
    
    def validate_intent(self, intent: TradeIntent) -> tuple[bool, str]:
        """
        Validate a TradeIntent before execution.
        
        Args:
            intent: The TradeIntent to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not intent.underlying:
            return False, "underlying symbol is required"
        if intent.quantity <= 0:
            return False, "quantity must be positive"
        if intent.order_type == "LIMIT" and intent.get_effective_limit_price() is None:
            return False, "limit_price required for LIMIT orders"
        if intent.order_type in ("STOP", "STOP_LIMIT") and intent.stop_price is None:
            return False, "stop_price required for STOP/STOP_LIMIT orders"
        if intent.order_type == "STOP_LIMIT" and intent.get_effective_limit_price() is None:
            return False, "limit_price required for STOP_LIMIT orders"
        return True, ""
