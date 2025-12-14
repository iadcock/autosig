"""
Executors package for broker-agnostic trade execution.

Each executor implements the same interface but targets different backends:
- TradierExecutor: Live/sandbox trading via Tradier API
- PaperExecutor: Simulated execution for testing
- HistoricalExecutor: Mock execution for backtesting
"""

from .base import BaseExecutor
from .tradier_executor import TradierExecutor
from .paper_executor import PaperExecutor
from .historical_executor import HistoricalExecutor

__all__ = ["BaseExecutor", "TradierExecutor", "PaperExecutor", "HistoricalExecutor"]
