#!/usr/bin/env python3
"""
Tradier Smoke Test Script for AutoSig.

This script verifies Tradier connectivity by:
1. Fetching accounts
2. Getting balance and positions
3. Fetching quotes
4. Fetching option chains
5. Placing test orders (sandbox)

Run: python tradier_smoketest.py
"""

import os
import sys
from datetime import datetime, timedelta

from tradier_client import TradierClient, TradierError, get_client

def separator(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)

def main():
    print("=" * 60)
    print("  TRADIER CONNECTIVITY SMOKE TEST")
    print("=" * 60)
    print()
    
    token = os.getenv("TRADIER_TOKEN")
    base_url = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com")
    
    print(f"Base URL: {base_url}")
    print(f"Token configured: {'Yes' if token else 'NO - MISSING!'}")
    
    if not token:
        print("\nERROR: TRADIER_TOKEN environment variable is not set.")
        print("Please add your Tradier API token to Replit Secrets.")
        sys.exit(1)
    
    try:
        client = get_client()
    except TradierError as e:
        print(f"\nERROR: Failed to create client: {e.message}")
        sys.exit(1)
    
    separator("1. FETCH ACCOUNTS")
    try:
        accounts = client.get_accounts()
        print(f"Found {len(accounts)} account(s):")
        for acct in accounts:
            acct_id = acct.get("account_number", "N/A")
            acct_type = acct.get("type", "N/A")
            status = acct.get("status", "N/A")
            print(f"  - Account: {acct_id} | Type: {acct_type} | Status: {status}")
        
        if accounts:
            account_id = os.getenv("TRADIER_ACCOUNT_ID") or accounts[0].get("account_number")
            client.account_id = account_id
            print(f"\nUsing account: {account_id}")
        else:
            print("\nNo accounts found!")
            sys.exit(1)
            
    except TradierError as e:
        print(f"ERROR: {e.message}")
        if e.response_text:
            print(f"Response: {e.response_text[:200]}")
        sys.exit(1)
    
    separator("2. FETCH BALANCE")
    try:
        balance = client.get_account_balance()
        print(f"Account Balance:")
        print(f"  Total Equity:    ${balance.get('total_equity', 0):,.2f}")
        print(f"  Total Cash:      ${balance.get('total_cash', 0):,.2f}")
        print(f"  Option BP:       ${balance.get('option_buying_power', 0):,.2f}")
        print(f"  Stock BP:        ${balance.get('stock_buying_power', 0):,.2f}")
        print(f"  Day Trade BP:    ${balance.get('day_trade_buying_power', 0):,.2f}")
    except TradierError as e:
        print(f"ERROR: {e.message}")
        if e.response_text:
            print(f"Response: {e.response_text[:200]}")
    
    separator("3. FETCH POSITIONS")
    try:
        positions = client.get_positions()
        if positions:
            print(f"Current Positions ({len(positions)}):")
            for pos in positions:
                symbol = pos.get("symbol", "N/A")
                qty = pos.get("quantity", 0)
                cost = pos.get("cost_basis", 0)
                print(f"  - {symbol}: {qty} shares @ ${cost:,.2f}")
        else:
            print("No open positions.")
    except TradierError as e:
        print(f"ERROR: {e.message}")
        if e.response_text:
            print(f"Response: {e.response_text[:200]}")
    
    separator("4. FETCH SPY QUOTE")
    try:
        quote = client.quote("SPY")
        print(f"SPY Quote:")
        print(f"  Last:   ${quote.get('last', 0):.2f}")
        print(f"  Bid:    ${quote.get('bid', 0):.2f}")
        print(f"  Ask:    ${quote.get('ask', 0):.2f}")
        print(f"  Volume: {quote.get('volume', 0):,}")
        print(f"  Change: {quote.get('change_percentage', 0):.2f}%")
        spy_price = quote.get('last', 600)
    except TradierError as e:
        print(f"ERROR: {e.message}")
        spy_price = 600
    
    separator("5. FETCH SPX OPTION EXPIRATIONS")
    spx_expiration = None
    try:
        expirations = client.get_option_expirations("SPX")
        if expirations:
            print(f"SPX has {len(expirations)} available expirations:")
            for exp in expirations[:5]:
                print(f"  - {exp}")
            if len(expirations) > 5:
                print(f"  ... and {len(expirations) - 5} more")
            spx_expiration = expirations[0]
        else:
            print("No SPX expirations found.")
            future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            spx_expiration = future_date
            print(f"Using fallback expiration: {spx_expiration}")
    except TradierError as e:
        print(f"ERROR: {e.message}")
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        spx_expiration = future_date
        print(f"Using fallback expiration: {spx_expiration}")
    
    separator("6. FETCH SPX OPTION CHAIN (CALLS, NEAR ATM)")
    try:
        chain = client.option_chain("SPX", spx_expiration, option_type="call")
        if chain:
            spx_quote = client.quote("$SPX.X") if "$SPX.X" else None
            current_price = spx_quote.get("last", 6000) if spx_quote else 6000
            
            atm_options = sorted(
                chain, 
                key=lambda x: abs(x.get("strike", 0) - current_price)
            )[:5]
            
            print(f"SPX Calls near ATM ({spx_expiration}):")
            for opt in atm_options:
                strike = opt.get("strike", 0)
                bid = opt.get("bid", 0)
                ask = opt.get("ask", 0)
                symbol = opt.get("symbol", "N/A")
                print(f"  Strike ${strike}: Bid ${bid:.2f} / Ask ${ask:.2f} | {symbol}")
        else:
            print("No option chain data returned.")
    except TradierError as e:
        print(f"ERROR: {e.message}")
        if e.response_text:
            print(f"Response: {e.response_text[:200]}")
    
    separator("7. PLACE TEST STOCK ORDER (SPY)")
    print("Placing a test BUY order for 1 share of SPY...")
    print("(Using limit order far from market to avoid execution)")
    try:
        far_limit = 1.00
        order_result = client.place_stock_order(
            symbol="SPY",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=far_limit,
            tif="day"
        )
        print(f"Order Response:")
        print(f"  Order ID: {order_result.get('id', 'N/A')}")
        print(f"  Status:   {order_result.get('status', 'N/A')}")
        print(f"  Details:  {order_result}")
    except TradierError as e:
        print(f"Order failed (expected in some sandbox configs):")
        print(f"  Status Code: {e.status_code}")
        print(f"  Message: {e.message}")
        if e.response_text:
            print(f"  Response: {e.response_text[:300]}")
    
    separator("8. PLACE TEST SPX OPTION ORDER")
    print("Attempting single-leg SPX call option order...")
    print("(May fail if sandbox doesn't support SPX options)")
    try:
        strike = 6000.0
        order_result = client.place_option_order_single_leg(
            underlying="SPX",
            expiration=spx_expiration,
            strike=strike,
            option_type="C",
            side="buy_to_open",
            quantity=1,
            order_type="limit",
            limit_price=0.01,
            tif="day"
        )
        print(f"Order Response:")
        print(f"  Order ID: {order_result.get('id', 'N/A')}")
        print(f"  Status:   {order_result.get('status', 'N/A')}")
        print(f"  Details:  {order_result}")
    except TradierError as e:
        print(f"Order failed (expected for SPX in sandbox):")
        print(f"  Status Code: {e.status_code}")
        print(f"  Message: {e.message}")
        if e.response_text:
            print(f"  Response: {e.response_text[:300]}")
        
        print("\nShowing what the order payload would be:")
        occ_symbol = client._build_occ_symbol("SPX", spx_expiration, "C", 6000.0)
        print(f"  OCC Symbol: {occ_symbol}")
        print(f"  Payload: class=option, symbol=SPX, option_symbol={occ_symbol}")
        print(f"           side=buy_to_open, quantity=1, type=limit, price=0.01")
    
    separator("SMOKE TEST COMPLETE")
    print("Tradier connectivity verified!")
    print()

if __name__ == "__main__":
    main()
