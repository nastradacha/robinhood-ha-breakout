#!/usr/bin/env python3
"""
Sync Alpaca Account Balance with System Bankroll

This script pulls your current Alpaca account balance and updates
the system's bankroll tracking file to match.
"""

import os
import json
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

def sync_alpaca_balance(paper=False):
    """Sync Alpaca account balance with system bankroll."""
    
    # Load environment variables
    load_dotenv()
    
    # Get API credentials
    api_key = os.getenv('ALPACA_API_KEY') or os.getenv('ALPACA_KEY_ID')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    
    if not api_key or not secret_key:
        print("[ERROR] Alpaca API credentials not found in .env file")
        return
    
    try:
        # Initialize Alpaca client
        client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper
        )
        
        # Get current account info
        account = client.get_account()
        current_balance = float(account.cash)
        
        env_suffix = "paper" if paper else "live"
        bankroll_file = f"bankroll_alpaca_{env_suffix}.json"
        
        print(f"[SYNC] Syncing Alpaca {env_suffix.upper()} account balance...")
        print(f"[BALANCE] Current Alpaca balance: ${current_balance:.2f}")
        
        # Load existing bankroll data
        try:
            with open(bankroll_file, 'r') as f:
                bankroll_data = json.load(f)
        except FileNotFoundError:
            print(f"[NEW] Creating new bankroll file: {bankroll_file}")
            bankroll_data = {
                "current_balance": 0.0,
                "start_capital": current_balance,
                "total_trades": 0,
                "total_pnl": 0.0,
                "trades": []
            }
        
        # Update balance
        old_balance = bankroll_data.get("current_balance", 0.0)
        old_bankroll = bankroll_data.get("current_bankroll", 0.0)
        balance_change = current_balance - old_balance
        
        bankroll_data["current_balance"] = current_balance
        
        # Update current_bankroll to match account balance for deposits
        if balance_change > 0:
            bankroll_data["current_bankroll"] = current_balance
            print(f"[BANKROLL] Updated trading bankroll to: ${current_balance:.2f}")
        
        # If this is a deposit (positive change), update start capital
        if balance_change > 0:
            bankroll_data["start_capital"] = current_balance
            print(f"[CAPITAL] Updated start capital to: ${current_balance:.2f}")
        
        # Save updated bankroll
        with open(bankroll_file, 'w') as f:
            json.dump(bankroll_data, f, indent=2)
        
        print(f"[SUCCESS] Bankroll sync complete!")
        print(f"[OLD] Old balance: ${old_balance:.2f}")
        print(f"[NEW] New balance: ${current_balance:.2f}")
        print(f"[CHANGE] Change: ${balance_change:+.2f}")
        print(f"[FILE] Updated file: {bankroll_file}")
        
        return current_balance
        
    except Exception as e:
        print(f"[ERROR] Error syncing balance: {e}")
        return None

if __name__ == "__main__":
    print("Alpaca Balance Sync Utility")
    print("=" * 40)
    
    # Sync live account balance
    balance = sync_alpaca_balance(paper=False)
    
    if balance:
        print(f"\n[SUCCESS] Your system bankroll is now synced with Alpaca.")
        print(f"[BALANCE] Current balance: ${balance:.2f}")
    else:
        print(f"\n[ERROR] Failed to sync balance. Check your API credentials.")
