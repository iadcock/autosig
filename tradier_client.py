"""
Tradier API Client for AutoSig.
Provides connectivity to Tradier brokerage for stocks, ETFs, and SPX options.

Supports:
- Account management (balances, positions)
- Market data (quotes, option chains)
- Order placement (stocks, single-leg options)
"""

import os
import logging
from typing import Optional, Literal
import requests

logger = logging.getLogger(__name__)

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")


class TradierError(Exception):
    """Custom exception for Tradier API errors."""
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        self.message = message
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(self.message)


class TradierClient:
    """
    Tradier API client for trading stocks and options.
    """
    
    def __init__(self, token: str = None, base_url: str = None, account_id: str = None):
        self.token = token or TRADIER_TOKEN
        self.base_url = (base_url or TRADIER_BASE_URL).rstrip("/")
        self.account_id = account_id or TRADIER_ACCOUNT_ID
        
        if not self.token:
            raise TradierError("TRADIER_TOKEN is required")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
    
    def _request(self, method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
        """
        Make an API request to Tradier.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: POST data
            
        Returns:
            JSON response as dict
            
        Raises:
            TradierError: On API errors
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                data=data,
                timeout=30
            )
            
            if response.status_code >= 400:
                excerpt = response.text[:500] if response.text else "No response body"
                logger.error(f"Tradier API error: {response.status_code} - {excerpt}")
                raise TradierError(
                    message=f"Tradier API error: {response.status_code}",
                    status_code=response.status_code,
                    response_text=excerpt
                )
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Tradier request failed: {e}")
            raise TradierError(f"Request failed: {e}")
    
    def get_accounts(self) -> list:
        """
        Fetch all accounts associated with the token.
        
        Returns:
            List of account dictionaries
        """
        response = self._request("GET", "/v1/user/profile")
        profile = response.get("profile", {})
        account_data = profile.get("account", [])
        
        if isinstance(account_data, dict):
            return [account_data]
        return account_data
    
    def get_account_balance(self, account_id: str = None) -> dict:
        """
        Fetch account balance information.
        
        Args:
            account_id: Account ID (uses default if not provided)
            
        Returns:
            Balance dictionary with equity, cash, buying power, etc.
        """
        acct = account_id or self.account_id
        if not acct:
            raise TradierError("account_id is required")
        
        response = self._request("GET", f"/v1/accounts/{acct}/balances")
        return response.get("balances", {})
    
    def get_positions(self, account_id: str = None) -> list:
        """
        Fetch current positions for an account.
        
        Args:
            account_id: Account ID (uses default if not provided)
            
        Returns:
            List of position dictionaries
        """
        acct = account_id or self.account_id
        if not acct:
            raise TradierError("account_id is required")
        
        response = self._request("GET", f"/v1/accounts/{acct}/positions")
        positions = response.get("positions", {})
        
        if positions == "null" or positions is None:
            return []
        
        position_list = positions.get("position", [])
        if isinstance(position_list, dict):
            return [position_list]
        return position_list or []
    
    def quote(self, symbol: str) -> dict:
        """
        Fetch a quote for a symbol.
        
        Args:
            symbol: Stock/ETF symbol (e.g., "SPY")
            
        Returns:
            Quote dictionary with last, bid, ask, etc.
        """
        response = self._request("GET", "/v1/markets/quotes", params={"symbols": symbol})
        quotes = response.get("quotes", {})
        quote_data = quotes.get("quote", {})
        
        if isinstance(quote_data, list):
            return quote_data[0] if quote_data else {}
        return quote_data
    
    def get_option_expirations(self, underlying: str) -> list:
        """
        Fetch available option expiration dates for an underlying.
        
        Args:
            underlying: Underlying symbol (e.g., "SPX", "SPY")
            
        Returns:
            List of expiration date strings (YYYY-MM-DD)
        """
        response = self._request(
            "GET", 
            "/v1/markets/options/expirations",
            params={"symbol": underlying}
        )
        expirations = response.get("expirations", {})
        date_list = expirations.get("date", [])
        
        if isinstance(date_list, str):
            return [date_list]
        return date_list or []
    
    def option_chain(self, underlying: str, expiration: str, option_type: str = None) -> list:
        """
        Fetch option chain for an underlying and expiration.
        
        Args:
            underlying: Underlying symbol (e.g., "SPX")
            expiration: Expiration date (YYYY-MM-DD)
            option_type: Optional filter - "call" or "put"
            
        Returns:
            List of option dictionaries
        """
        params = {
            "symbol": underlying,
            "expiration": expiration
        }
        if option_type:
            params["option_type"] = option_type
        
        response = self._request("GET", "/v1/markets/options/chains", params=params)
        options = response.get("options", {})
        option_list = options.get("option", [])
        
        if isinstance(option_list, dict):
            return [option_list]
        return option_list or []
    
    def place_stock_order(
        self,
        account_id: str = None,
        symbol: str = None,
        side: Literal["buy", "sell", "buy_to_cover", "sell_short"] = "buy",
        quantity: int = 1,
        order_type: Literal["market", "limit", "stop", "stop_limit"] = "market",
        limit_price: float = None,
        tif: Literal["day", "gtc", "pre", "post"] = "day"
    ) -> dict:
        """
        Place a stock/ETF order.
        
        Args:
            account_id: Account ID (uses default if not provided)
            symbol: Stock symbol
            side: Order side (buy, sell, buy_to_cover, sell_short)
            quantity: Number of shares
            order_type: Order type (market, limit, stop, stop_limit)
            limit_price: Limit price (required for limit orders)
            tif: Time in force (day, gtc, pre, post)
            
        Returns:
            Order response dictionary
        """
        acct = account_id or self.account_id
        if not acct:
            raise TradierError("account_id is required")
        if not symbol:
            raise TradierError("symbol is required")
        
        order_data = {
            "class": "equity",
            "symbol": symbol,
            "side": side,
            "quantity": str(quantity),
            "type": order_type,
            "duration": tif
        }
        
        if order_type in ["limit", "stop_limit"] and limit_price:
            order_data["price"] = str(limit_price)
        
        response = self._request("POST", f"/v1/accounts/{acct}/orders", data=order_data)
        return response.get("order", response)
    
    def place_option_order_single_leg(
        self,
        account_id: str = None,
        underlying: str = None,
        expiration: str = None,
        strike: float = None,
        option_type: Literal["C", "P"] = "C",
        side: Literal["buy_to_open", "buy_to_close", "sell_to_open", "sell_to_close"] = "buy_to_open",
        quantity: int = 1,
        order_type: Literal["market", "limit"] = "market",
        limit_price: float = None,
        tif: Literal["day", "gtc"] = "day"
    ) -> dict:
        """
        Place a single-leg option order.
        
        Args:
            account_id: Account ID (uses default if not provided)
            underlying: Underlying symbol (e.g., "SPX")
            expiration: Expiration date (YYYY-MM-DD)
            strike: Strike price
            option_type: "C" for call, "P" for put
            side: Order side (buy_to_open, buy_to_close, sell_to_open, sell_to_close)
            quantity: Number of contracts
            order_type: Order type (market, limit)
            limit_price: Limit price (required for limit orders)
            tif: Time in force (day, gtc)
            
        Returns:
            Order response dictionary
        """
        acct = account_id or self.account_id
        if not acct:
            raise TradierError("account_id is required")
        if not all([underlying, expiration, strike]):
            raise TradierError("underlying, expiration, and strike are required")
        
        occ_symbol = self._build_occ_symbol(underlying, expiration, option_type, strike)
        
        order_data = {
            "class": "option",
            "symbol": underlying,
            "option_symbol": occ_symbol,
            "side": side,
            "quantity": str(quantity),
            "type": order_type,
            "duration": tif
        }
        
        if order_type == "limit" and limit_price:
            order_data["price"] = str(limit_price)
        
        response = self._request("POST", f"/v1/accounts/{acct}/orders", data=order_data)
        return response.get("order", response)
    
    def _build_occ_symbol(self, underlying: str, expiration: str, option_type: str, strike: float) -> str:
        """
        Build OCC option symbol.
        
        Format: SYMBOL + YYMMDD + C/P + strike*1000 (8 digits, zero-padded)
        Example: SPY241220C00500000 = SPY Dec 20, 2024 $500 Call
        
        Args:
            underlying: Underlying symbol
            expiration: Expiration date (YYYY-MM-DD)
            option_type: "C" or "P"
            strike: Strike price
            
        Returns:
            OCC symbol string
        """
        parts = expiration.split("-")
        yy = parts[0][2:]
        mm = parts[1]
        dd = parts[2]
        
        strike_int = int(strike * 1000)
        strike_str = f"{strike_int:08d}"
        
        symbol_padded = underlying.upper().ljust(6)[:6]
        
        return f"{symbol_padded}{yy}{mm}{dd}{option_type.upper()}{strike_str}"


def get_client(token: str = None, base_url: str = None, account_id: str = None) -> TradierClient:
    """
    Factory function to create a TradierClient instance.
    
    Args:
        token: API token (uses env var if not provided)
        base_url: Base URL (uses env var if not provided)
        account_id: Account ID (uses env var if not provided)
        
    Returns:
        TradierClient instance
    """
    return TradierClient(token=token, base_url=base_url, account_id=account_id)
