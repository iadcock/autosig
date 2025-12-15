"""
Broker smoke tests for Alpaca and Tradier.
Each test returns a standardized result dict with success status and step details.
"""

import os
import logging
from datetime import datetime
from typing import Optional

import requests

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


def alpaca_smoke_test() -> dict:
    """
    Run smoke test for Alpaca paper trading API.
    
    Tests:
    A) Get account info
    B) Get market clock
    C) Get AAPL asset info
    D) Place a test market order (1 share AAPL)
    E) List recent orders
    
    Returns:
        dict with broker, success, timestamp, and steps
    """
    api_key = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")
    base_url = os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")
    
    steps = []
    
    if not api_key or not api_secret:
        steps.append(_make_step(
            "Auth Check",
            False,
            0,
            "Missing ALPACA_API_KEY or ALPACA_API_SECRET",
            "Please set both secrets in the Replit Secrets tab"
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
    
    try:
        resp = requests.get(f"{base_url}/v2/clock", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            is_open = data.get("is_open", False)
            status_text = "Market OPEN" if is_open else "Market CLOSED"
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
    
    try:
        order_data = {
            "symbol": "AAPL",
            "qty": "1",
            "side": "buy",
            "type": "market",
            "time_in_force": "day"
        }
        resp = requests.post(f"{base_url}/v2/orders", headers=headers, json=order_data, timeout=TIMEOUT)
        if resp.status_code in (200, 201):
            data = resp.json()
            order_id = data.get("id", "N/A")[:8]
            status = data.get("status", "unknown")
            steps.append(_make_step("Place Order", True, resp.status_code, f"Order {order_id}... status: {status}"))
        else:
            steps.append(_make_step("Place Order", False, resp.status_code, "Failed to place order", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Place Order", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Place Order", False, 0, f"Request error: {e}"))
    
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
    
    success = all(step["ok"] for step in steps)
    
    return {
        "broker": "alpaca",
        "success": success,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": steps
    }


def tradier_smoke_test() -> dict:
    """
    Run smoke test for Tradier API.
    
    Tests:
    A) Get account info (discover account_id)
    B) Get SPY quote
    C) Get option expirations (SPX, fallback to SPY)
    D) Get option chain (nearest expiration)
    E) Order placement (skipped if not available)
    
    Returns:
        dict with broker, success, timestamp, and steps
    """
    token = os.getenv("TRADIER_TOKEN", "")
    base_url = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com")
    account_id = os.getenv("TRADIER_ACCOUNT_ID", "")
    
    steps = []
    
    if not token:
        steps.append(_make_step(
            "Auth Check",
            False,
            0,
            "Missing TRADIER_TOKEN",
            "Please set TRADIER_TOKEN in the Replit Secrets tab"
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
    
    steps.append(_make_step(
        "Order Placement",
        True,
        0,
        "Skipped: order placement test not implemented for safety",
        "Use trade_intent_demo.py for order testing"
    ))
    
    success = all(step["ok"] for step in steps)
    
    return {
        "broker": "tradier",
        "success": success,
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
