"""
Tradier executor for live/sandbox trade execution.
"""

import logging
from datetime import datetime
from typing import Optional, Literal, cast

from trade_intent import TradeIntent, ExecutionResult
from tradier_client import TradierClient, TradierError, get_client
from .base import BaseExecutor

logger = logging.getLogger(__name__)

StockSide = Literal["buy", "sell", "buy_to_cover", "sell_short"]
OptionSide = Literal["buy_to_open", "buy_to_close", "sell_to_open", "sell_to_close"]
StockOrderType = Literal["market", "limit", "stop", "stop_limit"]
OptionOrderType = Literal["market", "limit"]


class TradierExecutor(BaseExecutor):
    """
    Executor that sends trades to Tradier API.
    
    Supports:
    - Stock/ETF orders
    - Single-leg option orders
    - Market and limit orders
    """
    
    def __init__(self, client: Optional[TradierClient] = None):
        """
        Initialize the Tradier executor.
        
        Args:
            client: Optional TradierClient instance. Creates one if not provided.
        """
        self._client = client
    
    @property
    def client(self) -> TradierClient:
        """Lazy-load the Tradier client."""
        import config
        # PAPER MODE (DRY_RUN=True): Do NOT initialize broker client
        if config.DRY_RUN:
            raise RuntimeError("PAPER MODE — Signal-based replay does not require broker connectivity. "
                             "Tradier client initialization blocked when DRY_RUN=True.")
        if self._client is None:
            self._client = get_client()
        return self._client
    
    @property
    def broker_name(self) -> str:
        return "tradier"
    
    def execute(self, intent: TradeIntent) -> ExecutionResult:
        """
        Execute a trade intent via Tradier API.
        
        Args:
            intent: The TradeIntent to execute
            
        Returns:
            ExecutionResult with Tradier response
        """
        is_valid, error = self.validate_intent(intent)
        if not is_valid:
            return ExecutionResult(
                intent_id=intent.id,
                status="REJECTED",
                broker=self.broker_name,
                message=f"Validation failed: {error}"
            )
        
        try:
            if intent.instrument_type == "STOCK":
                return self._execute_stock_order(intent)
            elif intent.instrument_type == "OPTION":
                return self._execute_option_order(intent)
            elif intent.instrument_type == "SPREAD":
                return ExecutionResult(
                    intent_id=intent.id,
                    status="SKIPPED",
                    broker=self.broker_name,
                    message="SPREAD_SUBMIT_NOT_IMPLEMENTED - Multi-leg spread submission not yet supported"
                )
            elif intent.instrument_type == "OPTION_SPREAD":
                return ExecutionResult(
                    intent_id=intent.id,
                    status="SKIPPED",
                    broker=self.broker_name,
                    message="SPREAD_SUBMIT_NOT_IMPLEMENTED - Multi-leg spread submission not yet supported"
                )
            else:
                return ExecutionResult(
                    intent_id=intent.id,
                    status="REJECTED",
                    broker=self.broker_name,
                    message=f"Unsupported instrument type: {intent.instrument_type}"
                )
        except TradierError as e:
            logger.error(f"Tradier execution error for intent {intent.id}: {e}")
            return ExecutionResult(
                intent_id=intent.id,
                status="ERROR",
                broker=self.broker_name,
                order_id=None,
                message=f"Tradier API error: {str(e)}"
            )
        except Exception as e:
            logger.exception(f"Unexpected error executing trade {intent.id}: {e}")
            return ExecutionResult(
                intent_id=intent.id,
                status="ERROR",
                broker=self.broker_name,
                order_id=None,
                message=f"Unexpected error: {e}"
            )
    
    def _execute_stock_order(self, intent: TradeIntent) -> ExecutionResult:
        """Execute a stock/ETF order."""
        side = self._map_action_to_stock_side(intent.action)
        order_type = self._get_stock_order_type(intent.order_type)
        limit_price = intent.get_effective_limit_price()
        stop_price = intent.stop_price
        
        payload = {
            "symbol": intent.underlying,
            "side": side,
            "quantity": intent.quantity,
            "order_type": order_type,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "tif": "day"
        }
        
        logger.info(f"Submitting stock order to Tradier: {payload}")
        
        response = self.client.place_stock_order(
            symbol=intent.underlying,
            side=side,
            quantity=intent.quantity,
            order_type=order_type,
            limit_price=limit_price if limit_price else None,
            stop_price=stop_price if stop_price else None
        )
        
        order_id = response.get("id")
        broker_status = response.get("status", "unknown")
        
        # Consistency check: SUBMITTED status requires order_id
        if order_id:
            result_status = "SUBMITTED"
            order_id_str = str(order_id)
            logger.info(f"Tradier stock order accepted - Order ID: {order_id_str}, Broker status: {broker_status}")
        else:
            result_status = "ERROR"
            order_id_str = None
            logger.error(f"Tradier stock order failed - No order ID returned. Broker status: {broker_status}, Response: {response}")
        
        return ExecutionResult(
            intent_id=intent.id,
            status=result_status,
            broker=self.broker_name,
            order_id=order_id_str,
            message=f"Broker status: {broker_status}",
            submitted_payload=payload,
            raw_response=response
        )
    
    def _execute_option_order(self, intent: TradeIntent) -> ExecutionResult:
        """Execute a single-leg option order."""
        if not intent.legs:
            return ExecutionResult(
                intent_id=intent.id,
                status="REJECTED",
                broker=self.broker_name,
                message="Option order requires at least one leg"
            )
        
        if intent.order_type in ("STOP", "STOP_LIMIT"):
            return ExecutionResult(
                intent_id=intent.id,
                status="REJECTED",
                broker=self.broker_name,
                message=f"Tradier does not support {intent.order_type} orders for options"
            )
        
        leg = intent.legs[0]
        side = self._map_action_to_option_side(intent.action)
        order_type = self._get_option_order_type(intent.order_type)
        limit_price = intent.get_effective_limit_price()
        option_type: Literal["C", "P"] = "C" if leg.option_type == "CALL" else "P"
        
        payload = {
            "underlying": intent.underlying,
            "expiration": leg.expiration,
            "strike": leg.strike,
            "option_type": option_type,
            "side": side,
            "quantity": intent.quantity,
            "order_type": order_type,
            "limit_price": limit_price
        }
        
        logger.info(f"Submitting option order to Tradier: {payload}")
        
        response = self.client.place_option_order_single_leg(
            underlying=intent.underlying,
            expiration=leg.expiration,
            strike=leg.strike,
            option_type=option_type,
            side=side,
            quantity=intent.quantity,
            order_type=order_type,
            limit_price=limit_price if limit_price else None
        )
        
        order_id = response.get("id")
        broker_status = response.get("status", "unknown")
        
        # Consistency check: SUBMITTED status requires order_id
        if order_id:
            result_status = "SUBMITTED"
            order_id_str = str(order_id)
            logger.info(f"Tradier option order accepted - Order ID: {order_id_str}, Broker status: {broker_status}")
        else:
            result_status = "ERROR"
            order_id_str = None
            logger.error(f"Tradier option order failed - No order ID returned. Broker status: {broker_status}, Response: {response}")
        
        return ExecutionResult(
            intent_id=intent.id,
            status=result_status,
            broker=self.broker_name,
            order_id=order_id_str,
            message=f"Broker status: {broker_status}",
            submitted_payload=payload,
            raw_response=response
        )
    
    def _map_action_to_stock_side(self, action: str) -> StockSide:
        """Map TradeIntent action to Tradier stock side."""
        mapping: dict[str, StockSide] = {
            "BUY": "buy",
            "SELL": "sell",
            "BUY_TO_OPEN": "buy",
            "BUY_TO_CLOSE": "buy",
            "SELL_TO_OPEN": "sell_short",
            "SELL_TO_CLOSE": "sell"
        }
        return mapping.get(action, "buy")
    
    def _map_action_to_option_side(self, action: str) -> OptionSide:
        """Map TradeIntent action to Tradier option side."""
        mapping: dict[str, OptionSide] = {
            "BUY": "buy_to_open",
            "SELL": "sell_to_close",
            "BUY_TO_OPEN": "buy_to_open",
            "BUY_TO_CLOSE": "buy_to_close",
            "SELL_TO_OPEN": "sell_to_open",
            "SELL_TO_CLOSE": "sell_to_close"
        }
        return mapping.get(action, "buy_to_open")
    
    def _get_stock_order_type(self, order_type: str) -> StockOrderType:
        """Convert order type to Tradier stock order type."""
        mapping: dict[str, StockOrderType] = {
            "MARKET": "market",
            "LIMIT": "limit",
            "STOP": "stop",
            "STOP_LIMIT": "stop_limit"
        }
        return mapping.get(order_type, "market")
    
    def _get_option_order_type(self, order_type: str) -> OptionOrderType:
        """Convert order type to Tradier option order type."""
        mapping: dict[str, OptionOrderType] = {
            "MARKET": "market",
            "LIMIT": "limit"
        }
        return mapping.get(order_type, "market")
