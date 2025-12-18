"""
Broker health checks - connectivity validation WITHOUT trading.
Tests API access, market data, and option chain availability.
"""

import requests
from datetime import datetime
from typing import Dict, List, Any

from env_loader import load_env, get_checked_sources

TIMEOUT = 10


def _make_step(name: str, ok: bool, status: int = 0, summary: str = "", details: str = "") -> dict:
    """Create a standardized step result dict."""
    return {
        "name": name,
        "ok": ok,
        "status": status,
        "summary": summary,
        "details": details[:200] if details else ""
    }


def alpaca_health_check() -> Dict[str, Any]:
    """
    Alpaca health check - NO orders placed.
    
    Steps:
    1) GET /v2/account
    2) GET /v2/clock
    3) GET stock snapshot for SPY
    
    Returns dict with broker, success, timestamp, steps.
    """
    api_key = load_env("ALPACA_API_KEY") or ""
    api_secret = load_env("ALPACA_API_SECRET") or ""
    base_url = load_env("ALPACA_PAPER_BASE_URL") or "https://paper-api.alpaca.markets"
    data_url = "https://data.alpaca.markets"
    
    steps = []
    
    checked = ", ".join(get_checked_sources())
    if not api_key or not api_secret:
        steps.append(_make_step(
            "Auth Check",
            False,
            0,
            "Missing ALPACA_API_KEY or ALPACA_API_SECRET",
            f"Checked: {checked}"
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
            status = data.get("status", "unknown")
            steps.append(_make_step("Get Account", True, 200, f"Equity: ${equity}, Status: {status}"))
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
            next_open = data.get("next_open", "N/A")
            next_close = data.get("next_close", "N/A")
            status_text = "Market OPEN" if is_open else "Market CLOSED"
            steps.append(_make_step("Get Clock", True, 200, f"{status_text}"))
        else:
            steps.append(_make_step("Get Clock", False, resp.status_code, "Failed to fetch clock", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get Clock", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get Clock", False, 0, f"Request error: {e}"))
    
    try:
        resp = requests.get(f"{data_url}/v2/stocks/SPY/snapshot", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            trade = data.get("latestTrade", {})
            price = trade.get("p", "N/A")
            quote = data.get("latestQuote", {})
            bid = quote.get("bp", "N/A")
            ask = quote.get("ap", "N/A")
            steps.append(_make_step("Get SPY Snapshot", True, 200, f"Price: ${price}, Bid: ${bid}, Ask: ${ask}"))
        else:
            steps.append(_make_step("Get SPY Snapshot", False, resp.status_code, "Failed to fetch snapshot", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get SPY Snapshot", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get SPY Snapshot", False, 0, f"Request error: {e}"))
    
    success = all(step["ok"] for step in steps)
    
    return {
        "broker": "alpaca",
        "success": success,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": steps
    }


def tradier_health_check() -> Dict[str, Any]:
    """
    Tradier health check - NO orders placed.
    
    Steps:
    1) GET /v1/user/profile
    2) GET quote for SPY
    3) GET SPX option expirations
    4) GET SPX option chain (fallback to SPY if SPX fails)
    
    Returns dict with broker, success, timestamp, steps.
    """
    token = load_env("TRADIER_TOKEN") or ""
    base_url = load_env("TRADIER_BASE_URL") or "https://sandbox.tradier.com"
    
    steps = []
    is_sandbox = "sandbox" in base_url.lower()
    
    checked = ", ".join(get_checked_sources())
    if not token:
        steps.append(_make_step(
            "Auth Check",
            False,
            0,
            "Missing TRADIER_TOKEN",
            f"Checked: {checked}"
        ))
        return {
            "broker": "tradier",
            "success": False,
            "is_sandbox": is_sandbox,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps
        }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    try:
        resp = requests.get(f"{base_url}/v1/user/profile", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            profile = data.get("profile", {})
            name = profile.get("name", "N/A")
            account_count = len(profile.get("account", []))
            steps.append(_make_step("Get Profile", True, 200, f"Name: {name}, Accounts: {account_count}"))
        else:
            steps.append(_make_step("Get Profile", False, resp.status_code, "Failed to fetch profile", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get Profile", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get Profile", False, 0, f"Request error: {e}"))
    
    try:
        resp = requests.get(f"{base_url}/v1/markets/quotes", headers=headers, params={"symbols": "SPY"}, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            quotes = data.get("quotes", {})
            quote = quotes.get("quote", {})
            if isinstance(quote, list):
                quote = quote[0] if quote else {}
            last = quote.get("last", "N/A")
            bid = quote.get("bid", "N/A")
            ask = quote.get("ask", "N/A")
            steps.append(_make_step("Get SPY Quote", True, 200, f"Last: ${last}, Bid: ${bid}, Ask: ${ask}"))
        else:
            steps.append(_make_step("Get SPY Quote", False, resp.status_code, "Failed to fetch quote", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get SPY Quote", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get SPY Quote", False, 0, f"Request error: {e}"))
    
    spx_expirations = []
    try:
        resp = requests.get(f"{base_url}/v1/markets/options/expirations", headers=headers, params={"symbol": "SPX"}, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            expirations = data.get("expirations", {})
            exp_list = expirations.get("date", []) if isinstance(expirations, dict) else []
            if isinstance(exp_list, str):
                exp_list = [exp_list]
            spx_expirations = exp_list[:5] if exp_list else []
            count = len(exp_list)
            steps.append(_make_step("Get SPX Expirations", True, 200, f"{count} expirations available"))
        else:
            steps.append(_make_step("Get SPX Expirations", False, resp.status_code, "Failed to fetch expirations", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get SPX Expirations", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get SPX Expirations", False, 0, f"Request error: {e}"))
    
    chain_symbol = "SPX"
    chain_expiration = spx_expirations[0] if spx_expirations else None
    
    if not chain_expiration:
        try:
            resp = requests.get(f"{base_url}/v1/markets/options/expirations", headers=headers, params={"symbol": "SPY"}, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                expirations = data.get("expirations", {})
                exp_list = expirations.get("date", []) if isinstance(expirations, dict) else []
                if isinstance(exp_list, str):
                    exp_list = [exp_list]
                if exp_list:
                    chain_symbol = "SPY"
                    chain_expiration = exp_list[0]
        except:
            pass
    
    if chain_expiration:
        try:
            resp = requests.get(
                f"{base_url}/v1/markets/options/chains",
                headers=headers,
                params={"symbol": chain_symbol, "expiration": chain_expiration},
                timeout=TIMEOUT
            )
            if resp.status_code == 200:
                data = resp.json()
                options = data.get("options", {})
                option_list = options.get("option", []) if isinstance(options, dict) else []
                if isinstance(option_list, dict):
                    option_list = [option_list]
                count = len(option_list) if option_list else 0
                steps.append(_make_step(f"Get {chain_symbol} Chain", True, 200, f"{count} contracts for {chain_expiration}"))
            else:
                steps.append(_make_step(f"Get {chain_symbol} Chain", False, resp.status_code, "Failed to fetch chain", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step(f"Get {chain_symbol} Chain", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step(f"Get {chain_symbol} Chain", False, 0, f"Request error: {e}"))
    else:
        steps.append(_make_step("Get Option Chain", False, 0, "No expirations available to test"))
    
    success = all(step["ok"] for step in steps)
    
    return {
        "broker": "tradier",
        "success": success,
        "is_sandbox": is_sandbox,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": steps
    }
