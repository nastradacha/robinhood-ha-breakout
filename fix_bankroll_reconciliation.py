#!/usr/bin/env python3
"""
Manual Bankroll Reconciliation Script
Fixes bankroll_alpaca_live.json based on real Alpaca account data
"""

import json
import os
from datetime import datetime

def fix_bankroll_reconciliation():
    """Fix bankroll based on real Alpaca account data from Aug 13, 2025"""
    
    # Real Alpaca account data from user's screenshot
    real_account_data = {
        "cash_deposit": 150.00,
        "current_balance": 208.57,
        "net_pnl": 58.57,  # 208.57 - 150.00
        "day_trade_count": 3
    }
    
    # Real transactions from Alpaca (from user's screenshot)
    real_transactions = [
        # Buys (negative amounts)
        {"time": "11:38:23 AM", "symbol": "IWM250813C00229000", "type": "BUY", "qty": 1, "amount": -61.02},
        {"time": "12:02:37 PM", "symbol": "IWM250813C00229000", "type": "BUY", "qty": 1, "amount": -80.02},
        {"time": "12:05:49 PM", "symbol": "IWM250813C00230000", "type": "BUY", "qty": 1, "amount": -34.02},
        {"time": "11:41:01 AM", "symbol": "IWM250813C00229000", "type": "BUY", "qty": 1, "amount": -72.02},
        
        # Sells (positive amounts)
        {"time": "11:45:11 AM", "symbol": "IWM250813C00229000", "type": "SELL", "qty": 1, "amount": 78.98},
        {"time": "11:45:11 AM", "symbol": "IWM250813C00229000", "type": "SELL", "qty": 1, "amount": 78.98},
        {"time": "12:33:09 PM", "symbol": "IWM250813C00230000", "type": "SELL", "qty": 1, "amount": 38.98},
        {"time": "12:44:00 PM", "symbol": "IWM250813C00229000", "type": "SELL", "qty": 1, "amount": 108.98},
        
        # Fees (8 x $0.02 = $0.16 total)
        {"time": "Aug 13, 2025", "symbol": "OCC Clearing Fee", "type": "FEE", "qty": 8, "amount": -0.16}
    ]
    
    # Calculate totals
    total_buys = sum(t["amount"] for t in real_transactions if t["type"] == "BUY")
    total_sells = sum(t["amount"] for t in real_transactions if t["type"] == "SELL")
    total_fees = sum(t["amount"] for t in real_transactions if t["type"] == "FEE")
    
    print("=== ALPACA BANKROLL RECONCILIATION ===")
    print(f"Cash Deposit: ${real_account_data['cash_deposit']:.2f}")
    print(f"Total Buys: ${total_buys:.2f}")
    print(f"Total Sells: ${total_sells:.2f}")
    print(f"Total Fees: ${total_fees:.2f}")
    print(f"Net P&L: ${total_sells + total_buys + total_fees:.2f}")
    print(f"Expected Balance: ${real_account_data['cash_deposit'] + total_sells + total_buys + total_fees:.2f}")
    print(f"Actual Balance: ${real_account_data['current_balance']:.2f}")
    
    # Create corrected bankroll
    corrected_bankroll = {
        "current_bankroll": real_account_data["current_balance"],
        "start_capital": real_account_data["cash_deposit"],
        "total_trades": 4,  # 4 round-trip trades
        "winning_trades": 4,  # All were profitable
        "total_pnl": real_account_data["net_pnl"],
        "max_drawdown": 0.0,
        "peak_bankroll": real_account_data["current_balance"],
        "created_at": "2025-08-11T10:14:42.952134",
        "last_updated": datetime.now().isoformat(),
        "total_fees": abs(total_fees),
        "trade_history": [
            {
                "timestamp": "2025-08-13 11:38:23",
                "symbol": "IWM",
                "direction": "CALL",
                "strike": 229.0,
                "expiry": "2025-08-13",
                "quantity": 1,
                "premium": 0.61,
                "total_cost": 61.02,
                "decision_confidence": 0.65,
                "llm_reason": "Real Alpaca trade - reconciled",
                "realized_pnl": 17.96,  # 78.98 - 61.02
                "status": "CLOSED"
            },
            {
                "timestamp": "2025-08-13 11:41:01",
                "symbol": "IWM",
                "direction": "CALL",
                "strike": 229.0,
                "expiry": "2025-08-13",
                "quantity": 1,
                "premium": 0.72,
                "total_cost": 72.02,
                "decision_confidence": 0.65,
                "llm_reason": "Real Alpaca trade - reconciled",
                "realized_pnl": 6.96,  # 78.98 - 72.02
                "status": "CLOSED"
            },
            {
                "timestamp": "2025-08-13 12:02:37",
                "symbol": "IWM",
                "direction": "CALL",
                "strike": 229.0,
                "expiry": "2025-08-13",
                "quantity": 1,
                "premium": 0.80,
                "total_cost": 80.02,
                "decision_confidence": 0.65,
                "llm_reason": "Real Alpaca trade - reconciled",
                "realized_pnl": 28.96,  # 108.98 - 80.02
                "status": "CLOSED"
            },
            {
                "timestamp": "2025-08-13 12:05:49",
                "symbol": "IWM",
                "direction": "CALL",
                "strike": 230.0,
                "expiry": "2025-08-13",
                "quantity": 1,
                "premium": 0.34,
                "total_cost": 34.02,
                "decision_confidence": 0.65,
                "llm_reason": "Real Alpaca trade - reconciled",
                "realized_pnl": 4.96,  # 38.98 - 34.02
                "status": "CLOSED"
            }
        ],
        "win_loss_history": [
            {"trade_pair": "IWM $229 CALL #1", "pnl": 17.96, "win": True},
            {"trade_pair": "IWM $229 CALL #2", "pnl": 6.96, "win": True},
            {"trade_pair": "IWM $229 CALL #3", "pnl": 28.96, "win": True},
            {"trade_pair": "IWM $230 CALL", "pnl": 4.96, "win": True}
        ]
    }
    
    # Backup current file
    bankroll_file = "bankroll_alpaca_live.json"
    backup_file = f"bankroll_alpaca_live_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    if os.path.exists(bankroll_file):
        with open(bankroll_file, 'r') as f:
            old_data = json.load(f)
        with open(backup_file, 'w') as f:
            json.dump(old_data, f, indent=2)
        print(f"[OK] Backed up old bankroll to: {backup_file}")
    
    # Write corrected bankroll
    with open(bankroll_file, 'w') as f:
        json.dump(corrected_bankroll, f, indent=2)
    
    print(f"[OK] Updated {bankroll_file} with real Alpaca data")
    print(f"[OK] Corrected balance: ${corrected_bankroll['current_bankroll']:.2f}")
    print(f"[OK] Total P&L: ${corrected_bankroll['total_pnl']:.2f}")
    print(f"[OK] Win rate: {corrected_bankroll['winning_trades']}/{corrected_bankroll['total_trades']} (100%)")

if __name__ == "__main__":
    fix_bankroll_reconciliation()
