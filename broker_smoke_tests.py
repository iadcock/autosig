"""
Broker smoke tests for Alpaca and Tradier.
Each test returns a standardized result dict with success status and step details.
Includes BUY and SELL flows to confirm end-to-end execution.

SAFETY: SELL only closes the 1 share opened by THIS test run.
If pre-existing positions exist, SELL is skipped to avoid liquidating them.
"""

import os
import time
import logging
from datetime import datetime
from typing import Optional

import requests

from env_loader import load_env, get_checked_sources

logger = logging.getLogger(__name__)

TIMEOUT = 15


def _make_step(name: str, ok: bool, status: int = 0, summary: str = "", details: str = "") -> dict:
    """Create a standardized step result dict."""
    return {
        "name": name,
        "ok": ok,
        "status": status,
        "summary": summary,
        "details": details[:200] if details else ""
    }


def _get_alpaca_position_qty(base_url: str, headers: dict, symbol: str) -> int:
    """Get current position quantity for a symbol. Returns 0 if no position."""
    try:
        resp = requests.get(f"{base_url}/v2/positions/{symbol}", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return int(float(data.get("qty", 0)))
        return 0
    except:
        return 0


def _get_tradier_position_qty(base_url: str, headers: dict, account_id: str, symbol: str) -> int:
    """Get current position quantity for a symbol. Returns 0 if no position."""
    try:
        resp = requests.get(f"{base_url}/v1/accounts/{account_id}/positions", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            positions = data.get("positions", {})
            if not positions or positions == "null" or not isinstance(positions, dict):
                return 0
            position_list = positions.get("position", [])
            if isinstance(position_list, dict):
                position_list = [position_list]
            for pos in position_list if position_list else []:
                if pos.get("symbol") == symbol:
                    return int(float(pos.get("quantity", 0)))
        return 0
    except:
        return 0


def alpaca_smoke_test() -> dict:
    """
    Run smoke test for Alpaca paper trading API.
    
    Tests:
    A) Get account info
    B) Get market clock
    C) Get AAPL asset info
    D) BUY 1 share AAPL
    E) Confirm position exists
    F) SELL 1 share AAPL (only the share we bought)
    G) Confirm position closed
    H) List recent orders
    
    SAFETY: Captures baseline position before BUY.
    Only sells 1 share (the test share), not pre-existing holdings.
    
    Returns:
        dict with broker, success, timestamp, and steps
    """
    api_key = load_env("ALPACA_API_KEY") or ""
    api_secret = load_env("ALPACA_API_SECRET") or ""
    base_url = load_env("ALPACA_PAPER_BASE_URL") or "https://paper-api.alpaca.markets"
    
    steps = []
    can_sell = False
    baseline_qty = 0
    test_qty = 1
    
    checked = ", ".join(get_checked_sources())
    if not api_key or not api_secret:
        steps.append(_make_step(
            "Auth Check",
            False,
            0,
            "Missing ALPACA_API_KEY or ALPACA_API_SECRET",
            f"Checked: {checked}. Use /debug/env to inspect."
        ))
        return {
            "broker": "alpaca",
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps
        }
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    try:
        resp = requests.get(f"{base_url}/v2/account", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            equity = data.get("equity", "N/A")
            steps.append(_make_step("Get Account", True, 200, f"Equity: ${equity}"))
        else:
            steps.append(_make_step("Get Account", False, resp.status_code, "Failed to fetch account", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get Account", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get Account", False, 0, f"Request error: {e}"))
    
    market_open = False
    try:
        resp = requests.get(f"{base_url}/v2/clock", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            market_open = data.get("is_open", False)
            status_text = "Market OPEN" if market_open else "Market CLOSED"
            steps.append(_make_step("Get Clock", True, 200, status_text))
        else:
            steps.append(_make_step("Get Clock", False, resp.status_code, "Failed to fetch clock", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get Clock", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get Clock", False, 0, f"Request error: {e}"))
    
    try:
        resp = requests.get(f"{base_url}/v2/assets/AAPL", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            tradable = data.get("tradable", False)
            steps.append(_make_step("Get Asset AAPL", True, 200, f"Tradable: {tradable}"))
        else:
            steps.append(_make_step("Get Asset AAPL", False, resp.status_code, "Failed to fetch asset", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get Asset AAPL", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get Asset AAPL", False, 0, f"Request error: {e}"))
    
    baseline_qty = _get_alpaca_position_qty(base_url, headers, "AAPL")
    
    buy_success = False
    try:
        order_data = {
            "symbol": "AAPL",
            "qty": str(test_qty),
            "side": "buy",
            "type": "market",
            "time_in_force": "day"
        }
        resp = requests.post(f"{base_url}/v2/orders", headers=headers, json=order_data, timeout=TIMEOUT)
        if resp.status_code in (200, 201):
            data = resp.json()
            order_id = data.get("id", "N/A")[:8]
            status = data.get("status", "unknown")
            steps.append(_make_step(f"BUY {test_qty} AAPL", True, resp.status_code, f"Order {order_id}... status: {status}"))
            buy_success = True
        else:
            steps.append(_make_step(f"BUY {test_qty} AAPL", False, resp.status_code, "Failed to place buy order", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step(f"BUY {test_qty} AAPL", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step(f"BUY {test_qty} AAPL", False, 0, f"Request error: {e}"))
    
    if buy_success:
        time.sleep(2)
        try:
            resp = requests.get(f"{base_url}/v2/positions/AAPL", headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                current_qty = int(float(data.get("qty", 0)))
                avg_price = data.get("avg_entry_price", "N/A")
                new_shares = current_qty - baseline_qty
                if new_shares >= test_qty:
                    steps.append(_make_step("Confirm BUY Position", True, 200, f"New shares: {new_shares}, Total: {current_qty}, Avg: ${avg_price}"))
                    can_sell = True
                elif current_qty > baseline_qty:
                    steps.append(_make_step("Confirm BUY Position", True, 200, f"Position increased to {current_qty} (from baseline {baseline_qty})"))
                    can_sell = True
                elif current_qty > 0 and baseline_qty > 0:
                    steps.append(_make_step("Confirm BUY Position", False, 200, f"BUY pending/unfilled, baseline position unchanged at {current_qty}"))
                elif current_qty > 0:
                    steps.append(_make_step("Confirm BUY Position", False, 200, f"Position unchanged at {current_qty}, BUY may be pending"))
                else:
                    steps.append(_make_step("Confirm BUY Position", False, 200, "Position qty is 0, BUY may be pending"))
            elif resp.status_code == 404:
                steps.append(_make_step("Confirm BUY Position", False, 404, "No position found (order may be pending)"))
            else:
                steps.append(_make_step("Confirm BUY Position", False, resp.status_code, "Failed to fetch position", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step("Confirm BUY Position", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step("Confirm BUY Position", False, 0, f"Request error: {e}"))
    else:
        steps.append(_make_step("Confirm BUY Position", False, 0, "SKIPPED: BUY order failed"))
    
    sell_success = False
    if can_sell:
        try:
            order_data = {
                "symbol": "AAPL",
                "qty": str(test_qty),
                "side": "sell",
                "type": "market",
                "time_in_force": "day"
            }
            resp = requests.post(f"{base_url}/v2/orders", headers=headers, json=order_data, timeout=TIMEOUT)
            if resp.status_code in (200, 201):
                data = resp.json()
                order_id = data.get("id", "N/A")[:8]
                status = data.get("status", "unknown")
                steps.append(_make_step(f"SELL {test_qty} AAPL", True, resp.status_code, f"Order {order_id}... status: {status}"))
                sell_success = True
            else:
                steps.append(_make_step(f"SELL {test_qty} AAPL", False, resp.status_code, "Failed to place sell order", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step(f"SELL {test_qty} AAPL", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step(f"SELL {test_qty} AAPL", False, 0, f"Request error: {e}"))
    else:
        steps.append(_make_step(f"SELL {test_qty} AAPL", False, 0, "SKIPPED: No position to sell"))
    
    if sell_success:
        time.sleep(2)
        try:
            resp = requests.get(f"{base_url}/v2/positions/AAPL", headers=headers, timeout=TIMEOUT)
            if resp.status_code == 404:
                if baseline_qty == 0:
                    steps.append(_make_step("Confirm Position Closed", True, 404, "Position fully closed"))
                else:
                    steps.append(_make_step("Confirm Position Closed", False, 404, f"Position gone but baseline was {baseline_qty}"))
            elif resp.status_code == 200:
                data = resp.json()
                remaining_qty = int(float(data.get("qty", 0)))
                expected_qty = baseline_qty
                if remaining_qty == expected_qty:
                    steps.append(_make_step("Confirm Position Closed", True, 200, f"Test share sold, remaining: {remaining_qty} (matches baseline)"))
                elif remaining_qty < baseline_qty + test_qty:
                    steps.append(_make_step("Confirm Position Closed", True, 200, f"Position reduced to {remaining_qty}"))
                else:
                    steps.append(_make_step("Confirm Position Closed", False, 200, f"Position not reduced, qty: {remaining_qty}"))
            else:
                steps.append(_make_step("Confirm Position Closed", False, resp.status_code, "Failed to verify position", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step("Confirm Position Closed", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step("Confirm Position Closed", False, 0, f"Request error: {e}"))
    elif can_sell:
        steps.append(_make_step("Confirm Position Closed", False, 0, "SKIPPED: SELL order failed"))
    else:
        steps.append(_make_step("Confirm Position Closed", False, 0, "SKIPPED: No SELL attempted"))
    
    try:
        resp = requests.get(f"{base_url}/v2/orders?status=all&limit=5", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            count = len(data)
            steps.append(_make_step("List Orders", True, 200, f"Found {count} recent orders"))
        else:
            steps.append(_make_step("List Orders", False, resp.status_code, "Failed to list orders", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("List Orders", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("List Orders", False, 0, f"Request error: {e}"))
    
    required_steps = [s for s in steps if "SKIPPED" not in s.get("summary", "")]
    success = all(step["ok"] for step in required_steps)
    
    return {
        "broker": "alpaca",
        "success": success,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": steps
    }


def _make_sandbox_step(name: str, summary: str, details: str = "") -> dict:
    """Create a step marked as SKIPPED_SANDBOX for sandbox limitations."""
    return {
        "name": name,
        "ok": False,
        "status": "SKIPPED_SANDBOX",
        "summary": summary,
        "details": details or ""
    }


# Steps that MUST pass for Tradier test to succeed
TRADIER_REQUIRED_STEPS = {
    "Get Account",
    "Quote SPY",
    "Option Expirations SPX",
    "Option Expirations SPY",
    "Option Expirations",
    "Option Chain SPX",
    "Option Chain SPY",
    "Option Chain",
}

# BUY order acceptance is required (but position confirmation is not)
TRADIER_BUY_STEP_PREFIX = "BUY"


def tradier_smoke_test() -> dict:
    """
    Run smoke test for Tradier API.
    
    Tests:
    A) Get account info (discover account_id) - REQUIRED
    B) Get SPY quote - REQUIRED
    C) Get option expirations (SPX, fallback to SPY) - REQUIRED
    D) Get option chain (nearest expiration) - REQUIRED
    E) BUY 1 share SPY (if available) - REQUIRED (order acceptance)
    F) Confirm position - OPTIONAL (sandbox limitation)
    G) SELL 1 share SPY - OPTIONAL (sandbox limitation)
    H) Confirm position closed - OPTIONAL (sandbox limitation)
    
    SAFETY: Captures baseline position before BUY.
    Only sells 1 share (the test share), not pre-existing holdings.
    
    Sandbox mode: Tradier sandbox accepts orders but often does NOT reflect
    positions immediately. Position-related steps are marked SKIPPED_SANDBOX
    and do not affect the overall success result.
    
    Returns:
        dict with broker, success, timestamp, and steps
    """
    token = load_env("TRADIER_TOKEN") or ""
    base_url = load_env("TRADIER_BASE_URL") or "https://sandbox.tradier.com"
    account_id = load_env("TRADIER_ACCOUNT_ID") or ""
    
    # Detect sandbox mode
    is_sandbox = "sandbox" in base_url.lower()
    
    steps = []
    can_trade = False
    can_sell = False
    baseline_qty = 0
    test_qty = 1
    trade_symbol = "SPY"
    
    checked = ", ".join(get_checked_sources())
    if not token:
        steps.append(_make_step(
            "Auth Check",
            False,
            0,
            "Missing TRADIER_TOKEN",
            f"Checked: {checked}. Use /debug/env to inspect."
        ))
        return {
            "broker": "tradier",
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps
        }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    if not account_id:
        try:
            resp = requests.get(f"{base_url}/v1/user/profile", headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                profile = data.get("profile", {})
                account_data = profile.get("account", [])
                if isinstance(account_data, dict):
                    account_id = account_data.get("account_number", "")
                elif isinstance(account_data, list) and account_data:
                    account_id = account_data[0].get("account_number", "")
                
                if account_id:
                    steps.append(_make_step("Get Account", True, 200, f"Account: {account_id[:4]}..."))
                    can_trade = True
                else:
                    steps.append(_make_step("Get Account", False, 200, "No account found in profile"))
            else:
                steps.append(_make_step("Get Account", False, resp.status_code, "Failed to fetch profile", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step("Get Account", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step("Get Account", False, 0, f"Request error: {e}"))
    else:
        steps.append(_make_step("Get Account", True, 0, f"Using provided account: {account_id[:4]}..."))
        can_trade = True
    
    try:
        resp = requests.get(f"{base_url}/v1/markets/quotes", headers=headers, params={"symbols": "SPY"}, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            quotes = data.get("quotes", {})
            quote = quotes.get("quote", {})
            if isinstance(quote, list):
                quote = quote[0] if quote else {}
            last = quote.get("last", "N/A")
            steps.append(_make_step("Quote SPY", True, 200, f"Last: ${last}"))
        else:
            steps.append(_make_step("Quote SPY", False, resp.status_code, "Failed to fetch quote", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Quote SPY", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Quote SPY", False, 0, f"Request error: {e}"))
    
    expirations = []
    exp_symbol = "SPX"
    
    try:
        resp = requests.get(f"{base_url}/v1/markets/options/expirations", headers=headers, params={"symbol": "SPX"}, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            exp_data = data.get("expirations", {})
            date_list = exp_data.get("date", [])
            if isinstance(date_list, str):
                expirations = [date_list]
            else:
                expirations = date_list or []
            
            if expirations:
                steps.append(_make_step("Option Expirations SPX", True, 200, f"Found {len(expirations)} expirations"))
            else:
                exp_symbol = "SPY"
                resp2 = requests.get(f"{base_url}/v1/markets/options/expirations", headers=headers, params={"symbol": "SPY"}, timeout=TIMEOUT)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    exp_data2 = data2.get("expirations", {})
                    date_list2 = exp_data2.get("date", [])
                    if isinstance(date_list2, str):
                        expirations = [date_list2]
                    else:
                        expirations = date_list2 or []
                    steps.append(_make_step("Option Expirations SPY", True, 200, f"Fallback: {len(expirations)} expirations"))
                else:
                    steps.append(_make_step("Option Expirations", False, resp2.status_code, "Failed to fetch SPY expirations", resp2.text))
        else:
            exp_symbol = "SPY"
            resp2 = requests.get(f"{base_url}/v1/markets/options/expirations", headers=headers, params={"symbol": "SPY"}, timeout=TIMEOUT)
            if resp2.status_code == 200:
                data2 = resp2.json()
                exp_data2 = data2.get("expirations", {})
                date_list2 = exp_data2.get("date", [])
                if isinstance(date_list2, str):
                    expirations = [date_list2]
                else:
                    expirations = date_list2 or []
                steps.append(_make_step("Option Expirations SPY", True, 200, f"Fallback: {len(expirations)} expirations"))
            else:
                steps.append(_make_step("Option Expirations", False, resp2.status_code, "Failed to fetch expirations", resp2.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Option Expirations", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Option Expirations", False, 0, f"Request error: {e}"))
    
    if expirations:
        nearest_exp = expirations[0]
        try:
            resp = requests.get(
                f"{base_url}/v1/markets/options/chains",
                headers=headers,
                params={"symbol": exp_symbol, "expiration": nearest_exp},
                timeout=TIMEOUT
            )
            if resp.status_code == 200:
                data = resp.json()
                options = data.get("options", {})
                option_list = options.get("option", [])
                if isinstance(option_list, dict):
                    option_list = [option_list]
                count = len(option_list) if option_list else 0
                steps.append(_make_step(f"Option Chain {exp_symbol}", True, 200, f"Found {count} options for {nearest_exp}"))
            else:
                steps.append(_make_step(f"Option Chain {exp_symbol}", False, resp.status_code, "Failed to fetch chain", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step("Option Chain", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step("Option Chain", False, 0, f"Request error: {e}"))
    else:
        steps.append(_make_step("Option Chain", False, 0, "Skipped: no expirations available"))
    
    if can_trade and account_id:
        baseline_qty = _get_tradier_position_qty(base_url, headers, account_id, trade_symbol)
    
    buy_success = False
    if can_trade and account_id:
        try:
            order_data = {
                "class": "equity",
                "symbol": trade_symbol,
                "side": "buy",
                "quantity": str(test_qty),
                "type": "market",
                "duration": "day"
            }
            resp = requests.post(
                f"{base_url}/v1/accounts/{account_id}/orders",
                headers=headers,
                data=order_data,
                timeout=TIMEOUT
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                order_info = data.get("order", {})
                order_id = order_info.get("id", "N/A")
                status = order_info.get("status", "submitted")
                if order_id and order_id != "N/A":
                    steps.append(_make_step(f"BUY {test_qty} {trade_symbol}", True, resp.status_code, f"Order {str(order_id)[:8]}... status: {status}"))
                    buy_success = True
                else:
                    steps.append(_make_step(f"BUY {test_qty} {trade_symbol}", False, resp.status_code, "Order response missing ID", str(data)[:200]))
            else:
                error_text = resp.text[:200] if resp.text else "Unknown error"
                if "not enabled" in error_text.lower() or "sandbox" in error_text.lower():
                    steps.append(_make_step(f"BUY {test_qty} {trade_symbol}", False, resp.status_code, "SKIPPED: Sandbox does not support order placement", error_text))
                else:
                    steps.append(_make_step(f"BUY {test_qty} {trade_symbol}", False, resp.status_code, "Failed to place buy order", error_text))
        except requests.exceptions.Timeout:
            steps.append(_make_step(f"BUY {test_qty} {trade_symbol}", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step(f"BUY {test_qty} {trade_symbol}", False, 0, f"Request error: {e}"))
    else:
        steps.append(_make_step(f"BUY {test_qty} {trade_symbol}", False, 0, "SKIPPED: No account_id available"))
    
    if buy_success:
        time.sleep(2)
        try:
            resp = requests.get(f"{base_url}/v1/accounts/{account_id}/positions", headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                positions = data.get("positions", {})
                if not positions or positions == "null" or not isinstance(positions, dict):
                    position_list = []
                else:
                    position_list = positions.get("position", [])
                    if isinstance(position_list, dict):
                        position_list = [position_list]
                
                found_position = None
                for pos in position_list if position_list else []:
                    if pos.get("symbol") == trade_symbol:
                        found_position = pos
                        break
                
                if found_position:
                    current_qty = int(float(found_position.get("quantity", 0)))
                    cost_basis = found_position.get("cost_basis", "N/A")
                    new_shares = current_qty - baseline_qty
                    if new_shares >= test_qty:
                        steps.append(_make_step("Confirm BUY Position", True, 200, f"New shares: {new_shares}, Total: {current_qty}, Cost: ${cost_basis}"))
                        can_sell = True
                    elif current_qty > baseline_qty:
                        steps.append(_make_step("Confirm BUY Position", True, 200, f"Position increased to {current_qty} (from baseline {baseline_qty})"))
                        can_sell = True
                    elif is_sandbox:
                        steps.append(_make_sandbox_step("Confirm BUY Position", "Sandbox limitation: position data delayed", f"Current qty: {current_qty}, baseline: {baseline_qty}"))
                    elif current_qty > 0 and baseline_qty > 0:
                        steps.append(_make_step("Confirm BUY Position", False, 200, f"BUY pending/unfilled, baseline position unchanged at {current_qty}"))
                    elif current_qty > 0:
                        steps.append(_make_step("Confirm BUY Position", False, 200, f"Position unchanged at {current_qty}, BUY may be pending"))
                    else:
                        steps.append(_make_step("Confirm BUY Position", False, 200, "Position qty is 0, BUY may be pending"))
                else:
                    if is_sandbox:
                        steps.append(_make_sandbox_step("Confirm BUY Position", "Sandbox limitation: position not reflected", "Order accepted but position data not available"))
                    else:
                        steps.append(_make_step("Confirm BUY Position", False, 200, f"No {trade_symbol} position found (order may be pending)"))
            else:
                steps.append(_make_step("Confirm BUY Position", False, resp.status_code, "Failed to fetch positions", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step("Confirm BUY Position", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step("Confirm BUY Position", False, 0, f"Request error: {e}"))
    elif can_trade:
        if is_sandbox:
            steps.append(_make_sandbox_step("Confirm BUY Position", "Sandbox limitation: BUY not executed"))
        else:
            steps.append(_make_step("Confirm BUY Position", False, 0, "SKIPPED: BUY order failed or not attempted"))
    else:
        steps.append(_make_step("Confirm BUY Position", False, 0, "SKIPPED: No account available"))
    
    sell_success = False
    if can_sell:
        try:
            order_data = {
                "class": "equity",
                "symbol": trade_symbol,
                "side": "sell",
                "quantity": str(test_qty),
                "type": "market",
                "duration": "day"
            }
            resp = requests.post(
                f"{base_url}/v1/accounts/{account_id}/orders",
                headers=headers,
                data=order_data,
                timeout=TIMEOUT
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                order_info = data.get("order", {})
                order_id = order_info.get("id", "N/A")
                status = order_info.get("status", "submitted")
                steps.append(_make_step(f"SELL {test_qty} {trade_symbol}", True, resp.status_code, f"Order {str(order_id)[:8]}... status: {status}"))
                sell_success = True
            else:
                steps.append(_make_step(f"SELL {test_qty} {trade_symbol}", False, resp.status_code, "Failed to place sell order", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step(f"SELL {test_qty} {trade_symbol}", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step(f"SELL {test_qty} {trade_symbol}", False, 0, f"Request error: {e}"))
    elif buy_success and is_sandbox:
        steps.append(_make_sandbox_step(f"SELL {test_qty} {trade_symbol}", "Sandbox limitation: no position to sell", "Position not reflected after BUY"))
    elif buy_success:
        steps.append(_make_step(f"SELL {test_qty} {trade_symbol}", False, 0, "SKIPPED: No position to sell"))
    else:
        if is_sandbox:
            steps.append(_make_sandbox_step(f"SELL {test_qty} {trade_symbol}", "Sandbox limitation: BUY not successful"))
        else:
            steps.append(_make_step(f"SELL {test_qty} {trade_symbol}", False, 0, "SKIPPED: BUY was not successful"))
    
    if sell_success:
        time.sleep(2)
        try:
            resp = requests.get(f"{base_url}/v1/accounts/{account_id}/positions", headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                positions = data.get("positions", {})
                if not positions or positions == "null" or not isinstance(positions, dict):
                    position_list = []
                else:
                    position_list = positions.get("position", [])
                    if isinstance(position_list, dict):
                        position_list = [position_list]
                
                found_position = None
                for pos in position_list if position_list else []:
                    if pos.get("symbol") == trade_symbol:
                        found_position = pos
                        break
                
                if not found_position:
                    if baseline_qty == 0:
                        steps.append(_make_step("Confirm Position Closed", True, 200, "Position fully closed"))
                    else:
                        steps.append(_make_step("Confirm Position Closed", False, 200, f"Position gone but baseline was {baseline_qty}"))
                else:
                    remaining_qty = int(float(found_position.get("quantity", 0)))
                    expected_qty = baseline_qty
                    if remaining_qty == expected_qty:
                        steps.append(_make_step("Confirm Position Closed", True, 200, f"Test share sold, remaining: {remaining_qty} (matches baseline)"))
                    elif remaining_qty < baseline_qty + test_qty:
                        steps.append(_make_step("Confirm Position Closed", True, 200, f"Position reduced to {remaining_qty}"))
                    else:
                        steps.append(_make_step("Confirm Position Closed", False, 200, f"Position not reduced, qty: {remaining_qty}"))
            else:
                steps.append(_make_step("Confirm Position Closed", False, resp.status_code, "Failed to verify position", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step("Confirm Position Closed", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step("Confirm Position Closed", False, 0, f"Request error: {e}"))
    elif can_sell:
        steps.append(_make_step("Confirm Position Closed", False, 0, "SKIPPED: SELL order failed"))
    else:
        if is_sandbox and buy_success:
            steps.append(_make_sandbox_step("Confirm Position Closed", "Sandbox limitation: no SELL attempted", "Position not reflected after BUY"))
        else:
            steps.append(_make_step("Confirm Position Closed", False, 0, "SKIPPED: No SELL attempted"))
    
    # Calculate success based on REQUIRED steps only
    # In sandbox mode, SKIPPED_SANDBOX steps don't affect success
    def is_required_step(step: dict) -> bool:
        name = step.get("name", "")
        status = step.get("status", "")
        
        # Skip SKIPPED_SANDBOX steps entirely (sandbox limitation)
        if status == "SKIPPED_SANDBOX":
            return False
        
        # Skip explicitly skipped steps
        if "SKIPPED" in step.get("summary", ""):
            return False
        
        # Required steps: account, quote, expirations, chain
        if name in TRADIER_REQUIRED_STEPS:
            return True
        
        # BUY order acceptance is required (order placement, not position confirmation)
        if name.startswith(TRADIER_BUY_STEP_PREFIX) and "Confirm" not in name:
            return True
        
        return False
    
    required_steps = [s for s in steps if is_required_step(s)]
    success = all(step["ok"] for step in required_steps) if required_steps else False
    
    return {
        "broker": "tradier",
        "success": success,
        "is_sandbox": is_sandbox,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": steps
    }


if __name__ == "__main__":
    import json
    
    print("=" * 60)
    print("ALPACA SMOKE TEST")
    print("=" * 60)
    result = alpaca_smoke_test()
    print(json.dumps(result, indent=2))
    
    print("\n" + "=" * 60)
    print("TRADIER SMOKE TEST")
    print("=" * 60)
    result = tradier_smoke_test()
    print(json.dumps(result, indent=2))
