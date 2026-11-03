"""
Base Broker Interface
Defines the standard set of methods every broker integration must implement.
This allows the rest of the app (Auto-Trader, Portfolio View) to be broker-agnostic.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseBroker(ABC):
    @abstractmethod
    def get_connection_status(self) -> Dict[str, Any]:
        """Return connection status: {'connected': bool, 'message': str}"""
        pass

    @abstractmethod
    def get_profile(self) -> Dict[str, Any]:
        """Return account profile information"""
        pass

    @abstractmethod
    def get_margins(self) -> Dict[str, Any]:
        """Return available margins/balance"""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Return list of open positions"""
        pass

    @abstractmethod
    def get_holdings(self) -> List[Dict[str, Any]]:
        """Return list of long-term holdings"""
        pass

    @abstractmethod
    def place_order(self, order_details: Dict[str, Any]) -> Dict[str, Any]:
        """Place a trade. order_details should be a standardized dict."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order"""
        pass

    @abstractmethod
    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        """Get latest price/quote for symbols"""
        pass

    @abstractmethod
    def get_option_chain(self, symbol: str) -> Dict[str, Any]:
        """Fetch the option chain for a given symbol"""
        pass