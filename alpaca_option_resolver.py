"""
Alpaca Option Resolution Helper.
Resolves option contracts using Alpaca's options API.
"""

import requests
from datetime import datetime
from typing import Optional, Tuple

from env_loader import load_env

TIMEOUT = 10


def resolve_alpaca_option_contract(
    underlying: str,
    expiration: str,
    strike: float,
    option_type: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve an option contract symbol using Alpaca's options API.
    
    Args:
        underlying: The underlying symbol (e.g., "SPY", "AAPL")
        expiration: Expiration date in YYYY-MM-DD format
        strike: Strike price
        option_type: "call" or "put"
    
    Returns:
        Tuple of (contract_symbol, skip_reason)
        - If found: (symbol, None)
        - If not found: (None, reason)
    """
    api_key = load_env("ALPACA_API_KEY") or ""
    api_secret = load_env("ALPACA_API_SECRET") or ""
    base_url = load_env("ALPACA_PAPER_BASE_URL") or "https://paper-api.alpaca.markets"
    
    if not api_key or not api_secret:
        return None, "Missing Alpaca API credentials"
    
    underlying_upper = underlying.upper().strip()
    if underlying_upper in ("SPX", "$SPX", "SPXW"):
        return None, f"Alpaca does not support {underlying_upper} index options"
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    opt_type = option_type.lower().strip()
    if opt_type not in ("call", "put"):
        return None, f"Invalid option_type: {option_type}"
    
    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        exp_str = exp_date.strftime("%Y-%m-%d")
    except ValueError:
        return None, f"Invalid expiration format: {expiration}"
    
    try:
        params = {
            "underlying_symbols": underlying_upper,
            "expiration_date": exp_str,
            "type": opt_type,
            "strike_price_gte": str(strike - 0.01),
            "strike_price_lte": str(strike + 0.01),
            "limit": 10
        }
        
        resp = requests.get(
            f"{base_url}/v2/options/contracts",
            headers=headers,
            params=params,
            timeout=TIMEOUT
        )
        
        if resp.status_code == 200:
            data = resp.json()
            contracts = data.get("option_contracts", [])
            
            if not contracts:
                contracts = data.get("contracts", [])
            
            if not contracts and isinstance(data, list):
                contracts = data
            
            for contract in contracts:
                contract_strike = float(contract.get("strike_price", 0))
                if abs(contract_strike - strike) < 0.02:
                    symbol = contract.get("symbol") or contract.get("id")
                    if symbol:
                        return symbol, None
            
            return None, f"No matching contract found for {underlying_upper} {exp_str} {strike} {opt_type}"
        
        elif resp.status_code == 404:
            return None, f"Options endpoint not found - may not be available for {underlying_upper}"
        
        else:
            return None, f"Alpaca API error {resp.status_code}: {resp.text[:100]}"
    
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.RequestException as e:
        return None, f"Request error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"


def is_alpaca_supported_underlying(underlying: str) -> bool:
    """
    Check if Alpaca supports options for this underlying.
    
    SPX/SPXW index options are NOT supported by Alpaca.
    Most equity/ETF options are supported.
    """
    underlying_upper = underlying.upper().strip()
    
    unsupported = {"SPX", "$SPX", "SPXW", "NDX", "RUT", "VIX", "DJX"}
    
    if underlying_upper in unsupported:
        return False
    
    return True
