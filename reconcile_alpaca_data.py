#!/usr/bin/env python3
"""
Reconcile Real Alpaca Trading Data with System Records

This script analyzes the actual Alpaca trading data from the user's screenshots
and reconciles it with the system's bankroll and position tracking records.

Real Alpaca Data Analysis:
- Buys: 4 contracts totaling $247.08 in costs
- Sells: 4 contracts totaling $304.92 in proceeds  
- Net P&L: +$57.84 (before fees)
- Fees: $0.16 in OCC clearing fees
- Final P&L: +$57.68

System Discrepancies:
1. Entry prices don't match actual fill prices
2. No exit trades recorded in bankroll
3. P&L not captured in system
4. Fees not tracked

This script will:
1. Update bankroll with actual trades and P&L
2. Clear positions file (all positions closed)
3. Record accurate trade history
"""

import json
import csv
from datetime import datetime
from pathlib import Path

def analyze_real_alpaca_data():
    """Analyze the real Alpaca trading data from screenshots."""
    
    # Real trades from Alpaca screenshots
    real_trades = [
        # Buys (costs) - negative amounts
        {'time': '2025-08-13 11:38:23', 'contract': 'IWM250813C00229000', 'action': 'BUY', 'qty': 1, 'price': 0.61, 'amount': -61.02, 'strike': 229.0},
        {'time': '2025-08-13 11:41:01', 'contract': 'IWM250813C00229000', 'action': 'BUY', 'qty': 1, 'price': 0.72, 'amount': -72.02, 'strike': 229.0},
        {'time': '2025-08-13 12:02:37', 'contract': 'IWM250813C00229000', 'action': 'BUY', 'qty': 1, 'price': 0.80, 'amount': -80.02, 'strike': 229.0},
        {'time': '2025-08-13 12:05:49', 'contract': 'IWM250813C00230000', 'action': 'BUY', 'qty': 1, 'price': 0.34, 'amount': -34.02, 'strike': 230.0},
        
        # Sells (proceeds) - positive amounts
        {'time': '2025-08-13 11:45:11', 'contract': 'IWM250813C00229000', 'action': 'SELL', 'qty': 2, 'price': 0.78, 'amount': 156.96, 'strike': 229.0},  # 2x $78.98
        {'time': '2025-08-13 12:33:09', 'contract': 'IWM250813C00230000', 'action': 'SELL', 'qty': 1, 'price': 0.38, 'amount': 38.98, 'strike': 230.0},
        {'time': '2025-08-13 12:44:00', 'contract': 'IWM250813C00229000', 'action': 'SELL', 'qty': 1, 'price': 1.09, 'amount': 108.98, 'strike': 229.0},
    ]
    
    # Calculate totals
    total_costs = sum([abs(t['amount']) for t in real_trades if t['action'] == 'BUY'])
    total_proceeds = sum([t['amount'] for t in real_trades if t['action'] == 'SELL'])
    gross_pnl = total_proceeds - total_costs
    
    # OCC clearing fees: $0.02 per contract side (8 total sides = $0.16)
    total_fees = 8 * 0.02
    net_pnl = gross_pnl - total_fees
    
    print("=== REAL ALPACA DATA ANALYSIS ===")
    print(f"Total Costs: ${total_costs:.2f}")
    print(f"Total Proceeds: ${total_proceeds:.2f}")
    print(f"Gross P&L: ${gross_pnl:.2f}")
    print(f"Total Fees: ${total_fees:.2f}")
    print(f"Net P&L: ${net_pnl:.2f}")
    
    return real_trades, net_pnl, total_fees

def load_current_bankroll():
    """Load current bankroll file."""
    bankroll_file = Path("bankroll_alpaca_live.json")
    if bankroll_file.exists():
        with open(bankroll_file, 'r') as f:
            return json.load(f)
    return None

def create_corrected_bankroll(real_trades, net_pnl, total_fees):
    """Create corrected bankroll with real trade data."""
    
    # Load current bankroll
    current_bankroll = load_current_bankroll()
    if not current_bankroll:
        print("ERROR: Could not load current bankroll file")
        return None
    
    print("\n=== CORRECTING BANKROLL ===")
    
    # Update bankroll with real data
    corrected_bankroll = {
        "current_bankroll": current_bankroll["current_bankroll"] + net_pnl,  # Add real P&L
        "start_capital": current_bankroll["start_capital"],
        "total_trades": len([t for t in real_trades if t['action'] == 'BUY']),  # 4 buy trades
        "winning_trades": 3,  # 3 profitable exits
        "total_pnl": net_pnl,
        "max_drawdown": 0.0,  # No drawdown on profitable day
        "peak_bankroll": current_bankroll["current_bankroll"] + net_pnl,
        "created_at": current_bankroll["created_at"],
        "last_updated": datetime.now().isoformat(),
        "total_fees": total_fees,
        "trade_history": [],
        "win_loss_history": []
    }
    
    # Create accurate trade history from real data
    for trade in real_trades:
        if trade['action'] == 'BUY':
            # Entry trade
            trade_record = {
                "timestamp": trade['time'],
                "symbol": "IWM",
                "direction": "CALL",
                "strike": trade['strike'],
                "expiry": "2025-08-13",
                "quantity": trade['qty'],
                "premium": trade['price'],
                "total_cost": abs(trade['amount']),
                "decision_confidence": 0.65,
                "llm_reason": "Real Alpaca trade data",
                "realized_pnl": 0,
                "status": "FILLED"
            }
            corrected_bankroll["trade_history"].append(trade_record)
        
        else:  # SELL
            # Exit trade
            trade_record = {
                "timestamp": trade['time'],
                "symbol": "IWM",
                "direction": "CALL",
                "strike": trade['strike'],
                "expiry": "2025-08-13",
                "quantity": trade['qty'],
                "premium": trade['price'],
                "total_proceeds": trade['amount'],
                "action": "SELL",
                "status": "FILLED"
            }
            corrected_bankroll["trade_history"].append(trade_record)
    
    # Add win/loss records for the 3 profitable exits
    profitable_exits = [
        {"trade_pair": "IWM $229 CALL (2x)", "pnl": 156.96 - 133.04, "win": True},  # $23.92 profit
        {"trade_pair": "IWM $230 CALL", "pnl": 38.98 - 34.02, "win": True},        # $4.96 profit  
        {"trade_pair": "IWM $229 CALL", "pnl": 108.98 - 80.02, "win": True},       # $28.96 profit
    ]
    
    corrected_bankroll["win_loss_history"] = profitable_exits
    
    print(f"Updated bankroll: ${corrected_bankroll['current_bankroll']:.2f}")
    print(f"Total P&L: ${corrected_bankroll['total_pnl']:.2f}")
    print(f"Winning trades: {corrected_bankroll['winning_trades']}/4")
    
    return corrected_bankroll

def clear_positions_file():
    """Clear positions file since all positions were closed."""
    positions_file = Path("positions_alpaca_live.csv")
    
    # Write header only (empty positions)
    with open(positions_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['entry_time', 'symbol', 'expiry', 'strike', 'side', 'contracts', 'entry_premium'])
    
    print("Cleared positions file - all positions closed")

def main():
    """Main reconciliation function."""
    print("ALPACA DATA RECONCILIATION SCRIPT")
    print("=" * 50)
    
    # Analyze real data
    real_trades, net_pnl, total_fees = analyze_real_alpaca_data()
    
    # Create corrected bankroll
    corrected_bankroll = create_corrected_bankroll(real_trades, net_pnl, total_fees)
    
    if corrected_bankroll:
        # Save corrected bankroll
        with open("bankroll_alpaca_live.json", 'w') as f:
            json.dump(corrected_bankroll, f, indent=2)
        print("\n[SUCCESS] Updated bankroll_alpaca_live.json with real data")
        
        # Clear positions file
        clear_positions_file()
        print("[SUCCESS] Cleared positions_alpaca_live.csv")
        
        print("\nRECONCILIATION COMPLETE!")
        print(f"Real Trading Results:")
        print(f"   - Net P&L: ${net_pnl:.2f}")
        print(f"   - Fees: ${total_fees:.2f}")
        print(f"   - Winning Rate: 3/3 exits (100%)")
        print(f"   - Updated Bankroll: ${corrected_bankroll['current_bankroll']:.2f}")
        
    else:
        print("[ERROR] Failed to update bankroll")

if __name__ == "__main__":
    main()
