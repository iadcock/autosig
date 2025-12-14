"""
Execution router for broker-agnostic trade execution.

Routes TradeIntents to the appropriate executor based on execution_mode.
"""

import os
import logging
from typing import Literal

from trade_intent import TradeIntent, ExecutionResult
from executors import TradierExecutor, PaperExecutor, HistoricalExecutor
from executors.base import BaseExecutor

logger = logging.getLogger(__name__)

LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"


_executors: dict[str, BaseExecutor] = {}


def get_executor(mode: Literal["PAPER", "LIVE", "HISTORICAL"]) -> BaseExecutor:
    """
    Get the appropriate executor for the given mode.
    
    Args:
        mode: Execution mode (PAPER, LIVE, HISTORICAL)
        
    Returns:
        BaseExecutor instance
    """
    if mode not in _executors:
        if mode == "PAPER":
            _executors[mode] = PaperExecutor()
        elif mode == "LIVE":
            _executors[mode] = TradierExecutor()
        elif mode == "HISTORICAL":
            _executors[mode] = HistoricalExecutor()
        else:
            raise ValueError(f"Unknown execution mode: {mode}")
    
    return _executors[mode]


def execute_trade(intent: TradeIntent) -> ExecutionResult:
    """
    Execute a trade intent, routing to the appropriate executor.
    
    If LIVE_TRADING is disabled and mode is LIVE, downgrades to PAPER mode.
    
    Args:
        intent: The TradeIntent to execute
        
    Returns:
        ExecutionResult from the executor
    """
    mode = intent.execution_mode
    
    if mode == "LIVE" and not LIVE_TRADING:
        logger.warning("LIVE mode requested but LIVE_TRADING is disabled. Using PAPER mode.")
        mode = "PAPER"
    
    executor = get_executor(mode)
    
    logger.info(f"Routing trade {intent.id} to {executor.broker_name} executor")
    logger.info(f"  Intent: {intent.action} {intent.quantity} {intent.underlying} "
                f"({intent.instrument_type})")
    
    result = executor.execute(intent)
    
    logger.info(f"Execution result: {result.status} - {result.message}")
    
    return result
