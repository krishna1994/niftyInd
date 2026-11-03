"""
Broker Manager
A singleton manager that coordinates multiple broker integrations.
Provides a unified interface for portfolio aggregation and order routing.
"""
import logging
from typing import List, Dict, Any, Optional
from broker_base import BaseBroker
from zerodha_client import ZerodhaBroker
from ibkr_client import IBKRBroker

logger = logging.getLogger(__name__)

class BrokerManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrokerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        # Initialize supported brokers
        self.brokers: Dict[str, BaseBroker] = {
            "zerodha": ZerodhaBroker(),
            "ibkr": IBKRBroker(),
        }
        self._initialized = True
        logger.info("BrokerManager initialized with Zerodha and IBKR support")

    def get_broker(self, name: str) -> BaseBroker:
        broker = self.brokers.get(name.lower())
        if not broker:
            raise ValueError(f"Broker {name} is not supported.")
        return broker

    def get_all_statuses(self) -> Dict[str, Any]:
        """Get connection status for all integrated brokers."""
        statuses = {}
        for name, broker in self.brokers.items():
            try:
                statuses[name] = broker.get_connection_status()
            except Exception as e:
                statuses[name] = {"connected": False, "message": f"Error: {str(e)}"}
        return statuses

    def get_aggregated_portfolio(self) -> Dict[str, Any]:
        """
        Aggregates positions and holdings from all connected brokers.
        Provides a unified view of wealth across India and US markets.
        """
        import os
        from datetime import datetime
        aggregated_positions = []
        aggregated_holdings = []
        total_unrealized_pnl = 0.0
        
        # 1. Fetch from API-based brokers (Zerodha, IBKR)
        for name, broker in self.brokers.items():
            try:
                status = broker.get_connection_status()
                if status.get("connected"):
                    # Fetch Positions
                    positions = broker.get_positions()
                    logger.info(f"Broker {name} returned {len(positions)} positions")
                    for p in positions:
                        # Handle Zerodha specific field names (Kite API)
                        if name == "zerodha":
                            pos_data = {
                                "symbol": p.get("tradingsymbol"),
                                "quantity": p.get("quantity"),
                                "avg_cost": p.get("average_price", 0),
                                "market_price": p.get("last_price", 0),
                                "unrealized_pnl": p.get("pnl", 0),
                                "broker": name,
                                "market": "India"
                            }
                        else:
                            pos_data = {
                                "symbol": p.get("symbol"),
                                "quantity": p.get("quantity"),
                                "avg_cost": p.get("avg_cost", 0),
                                "market_price": p.get("market_price", 0),
                                "unrealized_pnl": p.get("unrealized_pnl", 0),
                                "broker": name,
                                "market": "US"
                            }
                        aggregated_positions.append(pos_data)
                        total_unrealized_pnl += pos_data["unrealized_pnl"]
                    
                    # Fetch Holdings
                    holdings = broker.get_holdings()
                    logger.info(f"Broker {name} returned {len(holdings)} holdings")
                    for h in holdings:
                        # Handle Zerodha specific field names (Kite API)
                        if name == "zerodha":
                            hold_data = {
                                "symbol": h.get("tradingsymbol"),
                                "quantity": h.get("quantity"),
                                "avg_cost": h.get("average_price", 0),
                                "market_price": h.get("last_price", 0),
                                "unrealized_pnl": h.get("pnl", 0),
                                "broker": name,
                                "market": "India"
                            }
                        else:
                            hold_data = {
                                "symbol": h.get("symbol"),
                                "quantity": h.get("quantity"),
                                "avg_cost": h.get("avg_cost", 0),
                                "market_price": h.get("market_price", 0),
                                "unrealized_pnl": h.get("unrealized_pnl", 0),
                                "broker": name,
                                "market": "US"
                            }
                        aggregated_holdings.append(hold_data)
                        total_unrealized_pnl += hold_data["unrealized_pnl"]
                else:
                    logger.warning(f"Broker {name} is not connected, skipping data")
            except Exception as e:
                logger.error(f"Error fetching data from {name}: {e}", exc_info=True)

        # 2. Fetch manual eToro holdings
        try:
            from etoro_analysis import get_portfolio_with_analysis
            etoro_data = get_portfolio_with_analysis()
            for h in etoro_data.get("holdings", []):
                if h.get("success"):
                    hold_data = {
                        "symbol": h["symbol"],
                        "quantity": h["quantity"],
                        "avg_cost": h["entry_price"],
                        "market_price": h["spot"],
                        "unrealized_pnl": h["pnl"],
                        "broker": "etoro",
                        "market": "US"
                    }
                    aggregated_holdings.append(hold_data)
                    total_unrealized_pnl += h["pnl"]
        except Exception as e:
            logger.error(f"Error fetching eToro holdings: {e}")

        return {
            "positions": aggregated_positions,
            "holdings": aggregated_holdings,
            "summary": {
                "total_assets": len(aggregated_positions) + len(aggregated_holdings),
                "total_unrealized_pnl": round(total_unrealized_pnl, 2),
                "market_split": {
                    "India": len([p for p in aggregated_positions if p["market"] == "India"]) + 
                             len([h for h in aggregated_holdings if h["market"] == "India"]),
                    "US": len([p for p in aggregated_positions if p["market"] == "US"]) + 
                          len([h for h in aggregated_holdings if h["market"] == "US"])
                }
            },
            "timestamp": datetime.now().isoformat()
        }

    def route_order(self, broker_name: str, order_details: Dict[str, Any]) -> Dict[str, Any]:
        """Routes an order to the specified broker."""
        broker = self.get_broker(broker_name)
        return broker.place_order(order_details)

# Singleton instance
broker_manager = BrokerManager()