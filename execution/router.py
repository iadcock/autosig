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
    
    PAPER MODE SHORT-CIRCUIT (v1.0):
    When DRY_RUN=True, all execution routes to signal-based paper replay.
    No broker connectivity, no market hours, no price validation.
    
    Args:
        intent: The TradeIntent to execute
        
    Returns:
        ExecutionResult from the executor
    """
    import config
    
    # PAPER MODE SHORT-CIRCUIT: When DRY_RUN=True, use signal-based paper replay
    if config.DRY_RUN:
        logger.info(f"[PAPER MODE — SIGNAL-BASED REPLAY] Routing trade {intent.id} to paper executor")
        logger.info(f"  NO BROKER • NO MARKET HOURS • NO PRICE CONSTRAINTS")
        executor = get_executor("PAPER")
        result = executor.execute(intent)
        
        # Log execution result with paper mode labels
        if result.status == "SIMULATED":
            logger.info(f"PAPER MODE EXECUTION - Intent {intent.id} -> {result.message}")
        elif result.status == "REJECTED":
            logger.warning(f"PAPER MODE REJECTED - Intent {intent.id}: {result.message}")
        else:
            logger.info(f"PAPER MODE {result.status} - Intent {intent.id}: {result.message}")
        
        return result
    
    # LIVE MODE: Normal broker routing (unchanged)
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
    
    # Log execution result with broker truth
    if result.status == "SUBMITTED":
        if result.order_id:
            logger.info(f"Execution SUCCESS - Intent {intent.id} -> Broker order {result.order_id} ({result.broker})")
            logger.info(f"  Broker status: {result.message}")
        else:
            logger.error(f"CONSISTENCY ERROR - Intent {intent.id} marked SUBMITTED but no broker order_id")
            logger.error(f"  This indicates a broker response inconsistency. Result: {result.status}, Message: {result.message}")
    elif result.status == "ERROR":
        logger.error(f"Execution FAILED - Intent {intent.id} -> {result.broker}: {result.message}")
        if result.order_id:
            logger.error(f"  Note: Broker order_id exists despite ERROR status: {result.order_id}")
    elif result.status == "REJECTED":
        logger.warning(f"Execution REJECTED - Intent {intent.id} -> {result.broker}: {result.message}")
    else:
        logger.info(f"Execution {result.status} - Intent {intent.id} -> {result.broker}: {result.message}")
    
    # Consistency check: SUBMITTED status must have order_id
    if result.status == "SUBMITTED" and not result.order_id:
        logger.error("=" * 60)
        logger.error("CRITICAL: ExecutionResult inconsistency detected")
        logger.error(f"  Intent ID: {intent.id}")
        logger.error(f"  Status: {result.status}")
        logger.error(f"  Broker: {result.broker}")
        logger.error(f"  Order ID: {result.order_id}")
        logger.error("  A SUBMITTED status requires a broker order_id")
        logger.error("=" * 60)
        # Don't change the result, but log the error clearly
    
    return result
