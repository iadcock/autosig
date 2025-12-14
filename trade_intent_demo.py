"""
Demo script for TradeIntent schema and execution routing.

Demonstrates:
- Creating TradeIntent objects for stocks and options
- Routing through the execution system
- Paper mode execution (default)
- Live mode only when LIVE_TRADING=true
"""

import os
import logging

from trade_intent import TradeIntent, OptionLeg
from execution import execute_trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def demo_stock_order():
    """Demo a simple stock buy order."""
    print("\n" + "=" * 60)
    print("DEMO: Stock Order - Buy 1 share of SPY")
    print("=" * 60)
    
    intent = TradeIntent(
        execution_mode="PAPER",
        instrument_type="STOCK",
        underlying="SPY",
        action="BUY",
        order_type="MARKET",
        quantity=1
    )
    
    print(f"\nTradeIntent created:")
    print(f"  ID: {intent.id}")
    print(f"  Mode: {intent.execution_mode}")
    print(f"  Type: {intent.instrument_type}")
    print(f"  Symbol: {intent.underlying}")
    print(f"  Action: {intent.action}")
    print(f"  Quantity: {intent.quantity}")
    
    result = execute_trade(intent)
    
    print(f"\nExecutionResult:")
    print(f"  Status: {result.status}")
    print(f"  Broker: {result.broker}")
    print(f"  Order ID: {result.order_id}")
    print(f"  Message: {result.message}")
    if result.fill_price:
        print(f"  Fill Price: ${result.fill_price:.2f}")
    
    return result


def demo_option_order():
    """Demo a single-leg option order."""
    print("\n" + "=" * 60)
    print("DEMO: Option Order - Buy 1 SPX 6100C Jan 2025")
    print("=" * 60)
    
    intent = TradeIntent(
        execution_mode="PAPER",
        instrument_type="OPTION",
        underlying="SPX",
        action="BUY_TO_OPEN",
        order_type="LIMIT",
        limit_price=15.50,
        quantity=1,
        legs=[
            OptionLeg(
                side="BUY",
                quantity=1,
                strike=6100.0,
                option_type="CALL",
                expiration="2025-01-17"
            )
        ]
    )
    
    print(f"\nTradeIntent created:")
    print(f"  ID: {intent.id}")
    print(f"  Mode: {intent.execution_mode}")
    print(f"  Type: {intent.instrument_type}")
    print(f"  Underlying: {intent.underlying}")
    print(f"  Action: {intent.action}")
    print(f"  Order Type: {intent.order_type}")
    print(f"  Limit Price: ${intent.limit_price}")
    print(f"  Quantity: {intent.quantity}")
    print(f"  Leg: {intent.legs[0].strike} {intent.legs[0].option_type} {intent.legs[0].expiration}")
    
    result = execute_trade(intent)
    
    print(f"\nExecutionResult:")
    print(f"  Status: {result.status}")
    print(f"  Broker: {result.broker}")
    print(f"  Order ID: {result.order_id}")
    print(f"  Message: {result.message}")
    if result.fill_price:
        print(f"  Fill Price: ${result.fill_price:.2f}")
    
    return result


def demo_live_mode_protection():
    """Demo that LIVE mode is protected when LIVE_TRADING is disabled."""
    print("\n" + "=" * 60)
    print("DEMO: Live Mode Protection")
    print("=" * 60)
    
    live_trading = os.getenv("LIVE_TRADING", "false").lower() == "true"
    print(f"\nLIVE_TRADING environment: {live_trading}")
    
    intent = TradeIntent(
        execution_mode="LIVE",
        instrument_type="STOCK",
        underlying="AAPL",
        action="BUY",
        order_type="LIMIT",
        limit_price=200.00,
        quantity=1
    )
    
    print(f"\nAttempting LIVE mode order...")
    print(f"  Intent Mode: {intent.execution_mode}")
    
    result = execute_trade(intent)
    
    print(f"\nExecutionResult:")
    print(f"  Status: {result.status}")
    print(f"  Broker: {result.broker}")
    print(f"  Order ID: {result.order_id}")
    print(f"  Message: {result.message}")
    
    if result.broker == "paper" and intent.execution_mode == "LIVE":
        print(f"\n  [SAFETY] LIVE mode was downgraded to PAPER (LIVE_TRADING disabled)")
    
    return result


def main():
    """Run all demos."""
    print("\n" + "#" * 60)
    print("# TradeIntent Demo Script")
    print("#" * 60)
    
    demo_stock_order()
    demo_option_order()
    demo_live_mode_protection()
    
    print("\n" + "#" * 60)
    print("# Demo Complete")
    print("#" * 60 + "\n")


if __name__ == "__main__":
    main()
