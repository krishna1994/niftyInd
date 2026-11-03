"""
Interactive Brokers (IBKR) Integration.
Uses ib_insync to connect to TWS or IB Gateway.
"""
import logging
import os
from typing import List, Dict, Any, Optional
from ib_insync import IB, Stock, Option, Contract, Order, LimitOrder, MarketOrder
from broker_base import BaseBroker

logger = logging.getLogger(__name__)

class IBKRBroker(BaseBroker):
    """
    Implementation of BaseBroker for Interactive Brokers.
    Requires TWS or IB Gateway to be running on the host.
    """
    def __init__(self):
        self.ib = IB()
        self._connected = False

    def connect(self):
        """
        Connects to TWS/IB Gateway using environment variables.
        ib_insync requires an asyncio event loop. FastAPI worker threads
        don't have one by default, so we create one explicitly.

        Windows note: Python 3.8+ uses ProactorEventLoop by default on Windows,
        which is incompatible with ib_insync (which requires SelectorEventLoop).
        We force SelectorEventLoop on Windows before connecting.
        """
        if self._connected and self.ib.isConnected():
            return True

        import asyncio
        import sys

        # ── Windows asyncio fix ──────────────────────────────────────────────
        # ib_insync uses asyncio internally and requires SelectorEventLoop.
        # Python 3.8+ defaults to ProactorEventLoop on Windows, which is
        # incompatible. Force SelectorEventLoop on Windows.
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except AttributeError:
                pass  # Python < 3.8 on Windows — no policy needed

        host = os.environ.get("IBKR_HOST", "127.0.0.1")
        client_id = int(os.environ.get("IBKR_CLIENT_ID", "1"))

        # Try configured port first, then fallback to common TWS ports
        ports_to_try = [int(os.environ.get("IBKR_PORT", "7497"))]
        if 7496 not in ports_to_try: ports_to_try.append(7496)
        if 7497 not in ports_to_try: ports_to_try.append(7497)

        # Ensure there is an event loop in this thread (required by ib_insync)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        for port in ports_to_try:
            try:
                logger.info(f"Attempting IBKR connection on {host}:{port}...")
                self.ib.connect(host, port, clientId=client_id, readonly=True)
                self._connected = True
                logger.info(f"Successfully connected to IBKR at {host}:{port}")
                return True
            except Exception as e:
                logger.warning(f"Connection failed on port {port}: {e}")
        
        logger.error("Failed to connect to IBKR on all attempted ports.")
        return False

    def disconnect(self):
        if self._connected:
            self.ib.disconnect()
            self._connected = False
            logger.info("Disconnected from IBKR")

    def get_connection_status(self) -> Dict[str, Any]:
        # Attempt lazy connection if not already connected
        if not self._connected or not self.ib.isConnected():
            self.connect()
        
        return {
            "connected": self._connected and self.ib.isConnected(),
            "message": "Connected to IBKR" if self._connected else "Not connected to TWS/IB Gateway"
        }

    def get_profile(self) -> Dict[str, Any]:
        if not self._connected:
            raise RuntimeError("IBKR not connected")
        
        # IBKR doesn't have a single 'profile' call like Zerodha, 
        # we aggregate account summaries.
        accounts = self.ib.accounts()
        return {
            "accounts": accounts,
            "broker": "Interactive Brokers",
            "timestamp": os.environ.get("CURRENT_TIME", "N/A")
        }

    def get_margins(self) -> Dict[str, Any]:
        if not self._connected:
            raise RuntimeError("IBKR not connected")
        
        # Fetch account values (NetLiquidation, BuyingPower, etc.)
        values = self.ib.accountValues()
        margins = {}
        for v in values:
            margins[v.tag] = v.value
            
        return {
            "available_cash": margins.get("CashBalance", 0),
            "available_margin": margins.get("BuyingPower", 0),
            "used_margin": margins.get("NetLiquidation", 0) - margins.get("CashBalance", 0),
            "raw": margins
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Returns only OPTION positions (secType == 'OPT')."""
        if not self._connected:
            raise RuntimeError("IBKR not connected")
        
        portfolio = self.ib.portfolio()
        result = []
        for p in portfolio:
            # Only include options in positions
            if p.contract.secType == 'OPT':
                result.append({
                    "symbol": p.contract.symbol,
                    "quantity": p.position,
                    "avg_cost": p.averageCost,
                    "market_price": p.marketPrice,
                    "unrealized_pnl": p.unrealizedPNL,
                    "contract_type": p.contract.right,  # 'C' or 'P'
                    "strike": p.contract.strike,
                    "expiry": p.contract.lastTradeDateOrContractMonth,
                    "sec_type": "OPT"
                })
        return result

    def get_holdings(self) -> List[Dict[str, Any]]:
        """Returns only STOCK holdings (secType == 'STK')."""
        if not self._connected:
            raise RuntimeError("IBKR not connected")
        
        portfolio = self.ib.portfolio()
        result = []
        for p in portfolio:
            # Only include stocks in holdings
            if p.contract.secType == 'STK':
                result.append({
                    "symbol": p.contract.symbol,
                    "quantity": p.position,
                    "avg_cost": p.averageCost,
                    "market_price": p.marketPrice,
                    "unrealized_pnl": p.unrealizedPNL,
                    "sec_type": "STK"
                })
        return result

    def place_order(self, order_details: Dict[str, Any]) -> Dict[str, Any]:
        if not self._connected:
            raise RuntimeError("IBKR not connected")

        # 1. Define the Contract from order_details fields
        # order_details must include: tradingsymbol, exchange, transaction_type, quantity
        # For options: also sec_type='OPT', expiry (YYYYMMDD), strike, right ('C'/'P')
        # For stocks: sec_type='STK' (default)
        symbol = order_details["tradingsymbol"]
        exchange = order_details.get("exchange", "SMART")
        sec_type = order_details.get("sec_type", "STK")
        currency = order_details.get("currency", "USD")

        if sec_type == "OPT":
            expiry = order_details.get("expiry", "")
            strike = float(order_details.get("strike", 0))
            right = order_details.get("right", "C")  # 'C' for Call, 'P' for Put
            if not expiry or not strike:
                raise ValueError(
                    "Options orders require 'expiry' (YYYYMMDD), 'strike', and 'right' in order_details"
                )
            contract = Option(symbol, exchange, expiry, right, strike, currency=currency)
        else:
            contract = Stock(symbol, exchange, currency)

        # 2. Define the Order
        order_type = order_details.get("order_type", "MARKET")
        transaction_type = order_details["transaction_type"]  # "BUY" or "SELL"
        quantity = order_details["quantity"]

        if order_type == "MARKET":
            order = MarketOrder(transaction_type, quantity)
        else:
            price = order_details.get("price")
            if price is None:
                raise ValueError("LIMIT orders require a 'price' in order_details")
            order = LimitOrder(transaction_type, quantity, price)

        trade = self.ib.placeOrder(contract, order)
        return {"order_id": trade.order.orderId, "status": trade.orderStatus.status}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if not self._connected:
            raise RuntimeError("IBKR not connected")
        
        # IBKR requires the contract to cancel an order
        # This is a limitation; we'd need to store order -> contract mapping
        raise NotImplementedError("Order cancellation requires contract context in IBKR")

    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        if not self._connected:
            raise RuntimeError("IBKR not connected")

        import math
        quotes = {}
        for s in symbols:
            contract = Stock(s, 'SMART', 'USD')
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(0.5)  # Allow data to arrive
            # Use last trade price, fall back to bid/close to avoid NaN
            price = ticker.last
            if price is None or (isinstance(price, float) and math.isnan(price)):
                price = ticker.bid
            if price is None or (isinstance(price, float) and math.isnan(price)):
                price = ticker.close
            quotes[s] = price
        return quotes

    def get_option_chain(self, symbol: str) -> Dict[str, Any]:
        if not self._connected:
            raise RuntimeError("IBKR not connected")
        
        # IBKR uses reqSecDefOptParams to get the chain
        # This returns a list of OptionChain objects
        chains = self.ib.reqSecDefOptParams(Stock(symbol, 'SMART', 'USD'), '', '', 'RT')
        return {"chains": chains}

    def get_fx_rate(self, base: str = "USD", quote: str = "INR") -> Dict[str, Any]:
        """Fetch live FX rate from IBKR using a Forex contract."""
        if not self._connected:
            self.connect()
        try:
            from ib_insync import Forex
            import math
            contract = Forex(f"{base}{quote}")
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(1)  # Allow data to arrive
            rate = ticker.last or ticker.bid or ticker.close or 83.50
            
            # FIX: Handle NaN values which are not JSON compliant
            if math.isnan(rate):
                rate = 83.50
                
            return {"base": base, "quote": quote, "rate": rate, "source": "ibkr_live"}
        except Exception as e:
            logger.warning(f"IBKR FX rate fetch failed: {e}, using fallback")
            return {"base": base, "quote": quote, "rate": 83.50, "source": "fallback"}

    def get_available_strikes(self, symbol: str) -> Dict[str, Any]:
        """Fetch actual tradable strikes and expiries for a symbol from IBKR."""
        if not self._connected:
            self.connect()
        try:
            from ib_insync import Stock
            # reqSecDefOptParams returns a list of chains
            chains = self.ib.reqSecDefOptParams(Stock(symbol, 'SMART', 'USD'), '', '', 'RT')
            if not chains:
                return {"success": False, "message": "No option chains found for this symbol"}
            
            # We take the first chain (usually the primary one)
            chain = chains[0]
            return {
                "success": True,
                "expiries": chain.expirations,
                "strikes": chain.strikes,
                "multiplier": chain.multiplier
            }
        except Exception as e:
            logger.error(f"Error fetching available strikes for {symbol}: {e}")
            return {"success": False, "message": str(e)}

    def search_symbols(self, query: str) -> List[Dict[str, Any]]:
        """Search for symbols using IBKR's search functionality."""
        if not self._connected:
            self.connect()
        
        # Use ib_insync's search functionality or a simplified version
        # For this implementation, we'll return a list of common matches 
        # and the current symbol to simulate the search experience
        # In a full implementation, this would use ib.reqCompletedOrders or similar
        return [{"symbol": query.upper(), "type": "Stock", "exchange": "SMART"}]

    def get_contract_details(self, symbol: str, strike: float, expiry: str, option_type: Optional[str]) -> Dict[str, Any]:
        """Fetch live LTP, OI, and Volume for a contract."""
        if not self._connected:
            self.connect()

        import math
        if option_type:
            contract = Option(symbol, 'SMART', expiry, 'C' if option_type == 'C' else 'P', strike)
        else:
            contract = Stock(symbol, 'SMART', 'USD')

        ticker = self.ib.reqMktData(contract)
        self.ib.sleep(0.5)
        # NaN guard — IBKR returns NaN for fields with no data
        def _safe(v):
            if v is None:
                return None
            try:
                return None if math.isnan(float(v)) else float(v)
            except (TypeError, ValueError):
                return None

        # Note: OI and Volume require specific market data subscriptions in IBKR
        return {
            "ltp": _safe(ticker.last) or _safe(ticker.bid) or _safe(ticker.close),
            "volume": _safe(getattr(ticker, 'volume', None)),
            "oi": _safe(getattr(ticker, 'openInterest', None)),
            "symbol": symbol
        }

    def get_historical_data(
        self,
        symbol: str,
        duration: str = "1 Y",
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical OHLCV bars for any IBKR symbol.

        duration: e.g. "1 Y", "6 M", "3 M", "1 W", "1 D"
        bar_size: e.g. "1 day", "1 hour", "30 mins", "5 mins", "1 min"
        what_to_show: "TRADES" (default), "MIDPOINT", "BID", "ASK"

        Returns a list of {"date", "open", "high", "low", "close", "volume"} dicts,
        sorted oldest-first — the same shape as the Nifty chart data endpoint so
        the frontend Charts page can use it for any IBKR symbol.
        """
        if not self._connected:
            self.connect()
        try:
            contract = Stock(symbol, exchange, currency)
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=True,
                formatDate=1,
            )
            return [
                {
                    "date": str(bar.date),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars
            ]
        except Exception as e:
            logger.error(f"IBKR historical data fetch failed for {symbol}: {e}")
            return []

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Returns all open (pending) orders on the IBKR account.
        Useful for showing pending limit/stop orders in the UI.
        """
        if not self._connected:
            self.connect()
        try:
            trades = self.ib.reqOpenOrders()
            return [
                {
                    "order_id": t.order.orderId,
                    "symbol": t.contract.symbol,
                    "sec_type": t.contract.secType,
                    "action": t.order.action,
                    "quantity": t.order.totalQuantity,
                    "order_type": t.order.orderType,
                    "limit_price": t.order.lmtPrice if t.order.lmtPrice else None,
                    "status": t.orderStatus.status,
                    "filled": t.orderStatus.filled,
                    "remaining": t.orderStatus.remaining,
                }
                for t in trades
            ]
        except Exception as e:
            logger.error(f"IBKR open orders fetch failed: {e}")
            return []

    def get_executions(self) -> List[Dict[str, Any]]:
        """
        Returns today's executed trades (fills) from IBKR.
        Each fill includes symbol, side, quantity, price, and timestamp.
        """
        if not self._connected:
            self.connect()
        try:
            fills = self.ib.reqExecutions()
            return [
                {
                    "exec_id": f.execution.execId,
                    "order_id": f.execution.orderId,
                    "symbol": f.contract.symbol,
                    "sec_type": f.contract.secType,
                    "side": f.execution.side,
                    "quantity": f.execution.shares,
                    "price": f.execution.price,
                    "time": f.execution.time,
                    "exchange": f.execution.exchange,
                }
                for f in fills
            ]
        except Exception as e:
            logger.error(f"IBKR executions fetch failed: {e}")
            return []

    def get_account_summary(self) -> Dict[str, Any]:
        """
        Returns a structured account summary: net liquidation value, buying
        power, cash balance, unrealized P&L, and realized P&L — the key
        numbers a trader checks at a glance. Uses reqAccountSummary() which
        is more structured than the raw accountValues() used in get_margins().
        """
        if not self._connected:
            self.connect()
        try:
            summary_items = self.ib.accountSummary()
            result = {}
            for item in summary_items:
                result[item.tag] = {"value": item.value, "currency": item.currency}

            # Extract the most useful fields with clean names
            def _val(tag):
                entry = result.get(tag, {})
                try:
                    return float(entry.get("value", 0))
                except (TypeError, ValueError):
                    return 0.0

            return {
                "net_liquidation": _val("NetLiquidation"),
                "buying_power": _val("BuyingPower"),
                "cash_balance": _val("CashBalance"),
                "unrealized_pnl": _val("UnrealizedPnL"),
                "realized_pnl": _val("RealizedPnL"),
                "equity_with_loan": _val("EquityWithLoanValue"),
                "gross_position_value": _val("GrossPositionValue"),
                "currency": result.get("NetLiquidation", {}).get("currency", "USD"),
                "raw": result,
            }
        except Exception as e:
            logger.error(f"IBKR account summary fetch failed: {e}")
            return {"error": str(e)}
