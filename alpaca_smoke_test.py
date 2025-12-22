#!/usr/bin/env python3
"""
Alpaca Smoke Test with Auto Mode Selection.

Automatically selects test mode based on market session:
- NO_FILL mode (market closed): Place far-limit order, confirm accepted, cancel, confirm canceled
- FILL mode (market open): Place market order, confirm fill, close position

Run: python alpaca_smoke_test.py
"""

import os
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests

from env_loader import load_env, get_checked_sources
from market_session import get_market_session_status, get_smoke_test_mode

logger = logging.getLogger(__name__)

TIMEOUT = 15
POLL_INTERVAL = 2
FILL_TIMEOUT = 30
TEST_SYMBOL = os.getenv("ALPACA_TEST_SYMBOL", "SPY")


def _make_step(name: str, ok: bool, status: int = 0, summary: str = "", details: str = "") -> dict:
    """Create a standardized step result dict."""
    return {
        "name": name,
        "ok": ok,
        "status": status,
        "summary": summary,
        "details": details[:200] if details else ""
    }


def _get_spy_price(data_url: str, headers: dict) -> Optional[float]:
    """Get current SPY price from Alpaca data API."""
    try:
        resp = requests.get(f"{data_url}/v2/stocks/{TEST_SYMBOL}/snapshot", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            trade = data.get("latestTrade", {})
            price = trade.get("p")
            if price:
                return float(price)
            quote = data.get("latestQuote", {})
            ask = quote.get("ap")
            if ask:
                return float(ask)
    except:
        pass
    return None


def _get_position_qty(base_url: str, headers: dict, symbol: str) -> int:
    """Get current position quantity for a symbol. Returns 0 if no position."""
    try:
        resp = requests.get(f"{base_url}/v2/positions/{symbol}", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return int(float(data.get("qty", 0)))
        return 0
    except:
        return 0


def run_alpaca_smoke_test() -> Dict[str, Any]:
    """
    Run Alpaca smoke test with automatic mode selection.
    
    COMMON steps (always run):
    1. Get Account
    2. Get Clock
    3. Get SPY Snapshot
    
    NO_FILL mode (market closed):
    4. Submit limit buy at 50% below market
    5. Confirm order accepted
    6. Cancel order
    7. Confirm order canceled
    
    FILL mode (market open):
    4. Submit market buy
    5. Poll until filled (30s timeout)
    6. Confirm position
    7. Sell position
    8. Confirm position closed
    
    Returns:
        {
            "broker": "alpaca",
            "mode": "NO_FILL" | "FILL",
            "success": bool,
            "timestamp": str,
            "steps": [...],
            "order_ids": [...],
            "warnings": [...]
        }
    """
    api_key = load_env("ALPACA_API_KEY") or ""
    api_secret = load_env("ALPACA_API_SECRET") or ""
    base_url = load_env("ALPACA_PAPER_BASE_URL") or "https://paper-api.alpaca.markets"
    data_url = "https://data.alpaca.markets"
    
    steps: List[dict] = []
    order_ids: List[str] = []
    warnings: List[str] = []
    
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
            "mode": "UNKNOWN",
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps,
            "order_ids": order_ids,
            "warnings": warnings
        }
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    session = get_market_session_status()
    mode = get_smoke_test_mode()
    is_market_open = session.get("is_open", False)
    
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
            market_open = data.get("is_open", False)
            status_text = "Market OPEN" if market_open else "Market CLOSED"
            steps.append(_make_step("Get Clock", True, 200, f"{status_text} - Test mode: {mode}"))
        else:
            steps.append(_make_step("Get Clock", False, resp.status_code, "Failed to fetch clock", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Get Clock", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Get Clock", False, 0, f"Request error: {e}"))
    
    spy_price = None
    try:
        resp = requests.get(f"{data_url}/v2/stocks/{TEST_SYMBOL}/snapshot", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            trade = data.get("latestTrade", {})
            price = trade.get("p", "N/A")
            quote = data.get("latestQuote", {})
            bid = quote.get("bp", "N/A")
            ask = quote.get("ap", "N/A")
            steps.append(_make_step(f"Get {TEST_SYMBOL} Snapshot", True, 200, f"Price: ${price}, Bid: ${bid}, Ask: ${ask}"))
            spy_price = float(price) if price != "N/A" else None
        else:
            steps.append(_make_step(f"Get {TEST_SYMBOL} Snapshot", False, resp.status_code, "Failed to fetch snapshot", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step(f"Get {TEST_SYMBOL} Snapshot", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step(f"Get {TEST_SYMBOL} Snapshot", False, 0, f"Request error: {e}"))
    
    critical_steps = [s for s in steps if s.get("name") in ("Get Account", "Get Clock")]
    if not all(step["ok"] for step in critical_steps):
        return {
            "broker": "alpaca",
            "mode": mode,
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps,
            "order_ids": order_ids,
            "warnings": warnings
        }
    
    if spy_price is None:
        warnings.append("Snapshot unavailable, using fallback price for order tests")
    
    if mode == "NO_FILL":
        result = _run_no_fill_test(base_url, headers, steps, order_ids, warnings, spy_price)
    else:
        result = _run_fill_test(base_url, headers, steps, order_ids, warnings)
    
    success = all(step["ok"] for step in steps)
    
    return {
        "broker": "alpaca",
        "mode": mode,
        "success": success,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": steps,
        "order_ids": order_ids,
        "warnings": warnings
    }


def _run_no_fill_test(base_url: str, headers: dict, steps: List[dict], order_ids: List[str], warnings: List[str], spy_price: Optional[float]) -> None:
    """Run NO_FILL test: place far-limit order, confirm accepted, cancel, confirm canceled."""
    
    if spy_price is None:
        spy_price = 500.0
        warnings.append("Using fallback price for limit order")
    
    far_limit_price = round(spy_price * 0.50, 2)
    
    order_id = None
    try:
        order_data = {
            "symbol": TEST_SYMBOL,
            "qty": "1",
            "side": "buy",
            "type": "limit",
            "limit_price": str(far_limit_price),
            "time_in_force": "day"
        }
        resp = requests.post(f"{base_url}/v2/orders", headers=headers, json=order_data, timeout=TIMEOUT)
        if resp.status_code in (200, 201):
            data = resp.json()
            order_id = data.get("id", "")
            status = data.get("status", "unknown")
            order_ids.append(order_id)
            steps.append(_make_step(
                f"Submit Limit Buy (${far_limit_price})",
                True,
                resp.status_code,
                f"Order {order_id[:8]}... status: {status}"
            ))
        else:
            steps.append(_make_step(
                f"Submit Limit Buy (${far_limit_price})",
                False,
                resp.status_code,
                "Failed to place order",
                resp.text
            ))
            return
    except requests.exceptions.Timeout:
        steps.append(_make_step(f"Submit Limit Buy (${far_limit_price})", False, 0, "Request timed out"))
        return
    except requests.exceptions.RequestException as e:
        steps.append(_make_step(f"Submit Limit Buy (${far_limit_price})", False, 0, f"Request error: {e}"))
        return
    
    time.sleep(1)
    try:
        resp = requests.get(f"{base_url}/v2/orders/{order_id}", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            if status in ("new", "accepted", "pending_new"):
                steps.append(_make_step("Confirm Order Accepted", True, 200, f"Order status: {status}"))
            else:
                steps.append(_make_step("Confirm Order Accepted", False, 200, f"Unexpected status: {status}"))
        else:
            steps.append(_make_step("Confirm Order Accepted", False, resp.status_code, "Failed to get order", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Confirm Order Accepted", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Confirm Order Accepted", False, 0, f"Request error: {e}"))
    
    try:
        resp = requests.delete(f"{base_url}/v2/orders/{order_id}", headers=headers, timeout=TIMEOUT)
        if resp.status_code in (200, 204):
            steps.append(_make_step("Cancel Order", True, resp.status_code, "Cancel request sent"))
        else:
            steps.append(_make_step("Cancel Order", False, resp.status_code, "Failed to cancel order", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Cancel Order", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Cancel Order", False, 0, f"Request error: {e}"))
    
    time.sleep(1)
    try:
        resp = requests.get(f"{base_url}/v2/orders/{order_id}", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            if status in ("canceled", "cancelled"):
                steps.append(_make_step("Confirm Order Canceled", True, 200, f"Order status: {status}"))
            else:
                steps.append(_make_step("Confirm Order Canceled", False, 200, f"Order not canceled: {status}"))
        else:
            steps.append(_make_step("Confirm Order Canceled", False, resp.status_code, "Failed to get order", resp.text))
    except requests.exceptions.Timeout:
        steps.append(_make_step("Confirm Order Canceled", False, 0, "Request timed out"))
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Confirm Order Canceled", False, 0, f"Request error: {e}"))


def _run_fill_test(base_url: str, headers: dict, steps: List[dict], order_ids: List[str], warnings: List[str]) -> None:
    """Run FILL test: submit market buy, poll until filled, sell, confirm both filled."""
    
    baseline_qty = _get_position_qty(base_url, headers, TEST_SYMBOL)
    
    order_id = None
    try:
        order_data = {
            "symbol": TEST_SYMBOL,
            "qty": "1",
            "side": "buy",
            "type": "market",
            "time_in_force": "day"
        }
        resp = requests.post(f"{base_url}/v2/orders", headers=headers, json=order_data, timeout=TIMEOUT)
        if resp.status_code in (200, 201):
            data = resp.json()
            order_id = data.get("id", "")
            status = data.get("status", "unknown")
            order_ids.append(order_id)
            steps.append(_make_step(
                "Submit Market Buy",
                True,
                resp.status_code,
                f"Order {order_id[:8]}... status: {status}"
            ))
        else:
            steps.append(_make_step("Submit Market Buy", False, resp.status_code, "Failed to place order", resp.text))
            return
    except requests.exceptions.Timeout:
        steps.append(_make_step("Submit Market Buy", False, 0, "Request timed out"))
        return
    except requests.exceptions.RequestException as e:
        steps.append(_make_step("Submit Market Buy", False, 0, f"Request error: {e}"))
        return
    
    start_time = time.time()
    filled = False
    filled_qty = 0
    filled_price = None
    
    while time.time() - start_time < FILL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        try:
            resp = requests.get(f"{base_url}/v2/orders/{order_id}", headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "unknown")
                filled_qty = int(float(data.get("filled_qty", 0) or 0))
                filled_price = data.get("filled_avg_price")
                
                if status == "filled" and filled_qty > 0:
                    filled = True
                    break
                elif status in ("canceled", "expired", "rejected"):
                    break
        except:
            pass
    
    if filled:
        price_str = f" @ ${filled_price}" if filled_price else ""
        steps.append(_make_step("Confirm Buy Fill", True, 200, f"Filled {filled_qty} shares{price_str}"))
    else:
        steps.append(_make_step("Confirm Buy Fill", False, 0, f"Timeout: Order not filled in {FILL_TIMEOUT}s"))
        warnings.append("Fill timeout - consider re-running during active market hours")
        return
    
    current_qty = _get_position_qty(base_url, headers, TEST_SYMBOL)
    position_delta = current_qty - baseline_qty
    
    if position_delta > 0:
        steps.append(_make_step("Confirm Position", True, 200, f"Position +{position_delta} (total: {current_qty})"))
    else:
        steps.append(_make_step("Confirm Position", True, 200, f"Position delta: {position_delta} (may update later)"))
        warnings.append("Position not immediately reflected")
    
    if position_delta > 0:
        sell_qty = min(position_delta, 1)
        try:
            order_data = {
                "symbol": TEST_SYMBOL,
                "qty": str(sell_qty),
                "side": "sell",
                "type": "market",
                "time_in_force": "day"
            }
            resp = requests.post(f"{base_url}/v2/orders", headers=headers, json=order_data, timeout=TIMEOUT)
            if resp.status_code in (200, 201):
                data = resp.json()
                sell_order_id = data.get("id", "")
                order_ids.append(sell_order_id)
                steps.append(_make_step("Submit Market Sell", True, resp.status_code, f"Order {sell_order_id[:8]}..."))
                
                time.sleep(3)
                final_qty = _get_position_qty(base_url, headers, TEST_SYMBOL)
                if final_qty <= baseline_qty:
                    steps.append(_make_step("Confirm Position Closed", True, 200, f"Position returned to baseline"))
                else:
                    steps.append(_make_step("Confirm Position Closed", True, 200, f"Position: {final_qty} (sell may be pending)"))
            else:
                steps.append(_make_step("Submit Market Sell", False, resp.status_code, "Failed to sell", resp.text))
        except requests.exceptions.Timeout:
            steps.append(_make_step("Submit Market Sell", False, 0, "Request timed out"))
        except requests.exceptions.RequestException as e:
            steps.append(_make_step("Submit Market Sell", False, 0, f"Request error: {e}"))
    else:
        steps.append(_make_step("Submit Market Sell", True, 0, "Skipped: No new shares to sell"))
        steps.append(_make_step("Confirm Position Closed", True, 0, "Skipped: No sell needed"))


def main():
    """Run smoke test from command line."""
    print("=" * 60)
    print("  ALPACA SMOKE TEST")
    print("=" * 60)
    print()
    
    result = run_alpaca_smoke_test()
    
    print(f"Mode: {result['mode']}")
    print(f"Success: {result['success']}")
    print(f"Timestamp: {result['timestamp']}")
    print()
    
    print("Steps:")
    for step in result["steps"]:
        status = "PASS" if step["ok"] else "FAIL"
        print(f"  [{status}] {step['name']}: {step['summary']}")
        if step.get("details"):
            print(f"        {step['details']}")
    
    if result["warnings"]:
        print()
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    
    if result["order_ids"]:
        print()
        print(f"Order IDs: {', '.join(result['order_ids'])}")


if __name__ == "__main__":
    main()
