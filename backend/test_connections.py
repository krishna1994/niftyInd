"""
Broker Connection Diagnostic Tool
Tests Zerodha and IBKR connections independently to identify failure points.
"""
import logging
import os
from dotenv import load_dotenv
from broker_manager import broker_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_broker(name):
    print(f"\n--- Testing {name.upper()} Connection ---")
    try:
        broker = broker_manager.get_broker(name)
        status = broker.get_connection_status()
        print(f"Status: {status}")
        
        if status.get("connected"):
            print("✅ Connection Successful!")
            try:
                positions = broker.get_positions()
                print(f"Positions found: {len(positions)}")
            except Exception as e:
                print(f"❌ Failed to fetch positions: {e}")
        else:
            print(f"❌ Connection Failed: {status.get('message', 'No error message provided')}")
            
    except Exception as e:
        print(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    load_dotenv()
    print("Starting Broker Diagnostics...")
    
    # Test Zerodha
    test_broker("zerodha")
    
    # Test IBKR
    test_broker("ibkr")
    
    print("\nDiagnostics Complete.")