"""
Execution router for broker-agnostic trade execution.

Routes TradeIntents to the appropriate executor based on execution_mode.

TEMPORARY: EXECUTION_BROKER_MODE controls broker routing for testing.
- TRADIER_ONLY: All trades go through Tradier sandbox (no Alpaca)
- MULTI: Normal routing based on intent execution_mode
"""

import os
import logging
from typing import Literal

from trade_intent import TradeIntent, ExecutionResult
from executors import TradierExecutor, PaperExecutor, HistoricalExecutor
from executors.base import BaseExecutor
from settings_store import EXECUTION_BROKER_MODE

logger = logging.getLogger(__name__)

LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"


_executors: dict[str, BaseExecutor] = {}


def get_execution_broker_mode() -> str:
    """Get current execution broker mode."""
    return EXECUTION_BROKER_MODE


def get_executor(mode: Literal["PAPER", "LIVE", "HISTORICAL"]) -> BaseExecutor:
    """
    Get the appropriate executor for the given mode.
    
    In TRADIER_ONLY mode, all trades go to TradierExecutor.
    
    Args:
        mode: Execution mode (PAPER, LIVE, HISTORICAL)
        
    Returns:
        BaseExecutor instance
    """
    if EXECUTION_BROKER_MODE == "TRADIER_ONLY":
        if "tradier" not in _executors:
            _executors["tradier"] = TradierExecutor()
        return _executors["tradier"]
    
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
    
    TEMPORARY: In TRADIER_ONLY mode, all trades route to Tradier sandbox.
    
    Args:
        intent: The TradeIntent to execute
        
    Returns:
        ExecutionResult from the executor
    """
    mode = intent.execution_mode
    
    if mode == "LIVE" and not LIVE_TRADING:
        logger.warning("LIVE mode requested but LIVE_TRADING is disabled. Using PAPER mode.")
        mode = "PAPER"
    
    if EXECUTION_BROKER_MODE == "TRADIER_ONLY":
        logger.info(f"[TRADIER_ONLY] Routing trade {intent.id} to Tradier sandbox")
    
    executor = get_executor(mode)
    
    logger.info(f"Routing trade {intent.id} to {executor.broker_name} executor")
    logger.info(f"  Intent: {intent.action} {intent.quantity} {intent.underlying} "
                f"({intent.instrument_type})")
    
    result = executor.execute(intent)
    
    logger.info(f"Execution result: {result.status} - {result.message}")
    
    return result
