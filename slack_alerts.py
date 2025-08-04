#!/usr/bin/env python3
"""
Additional Slack alert methods for position monitoring.
These will be integrated into the main SlackNotifier class.
"""

def send_profit_alert(self, symbol: str, strike: float, side: str, 
                     entry_premium: float, current_premium: float, 
                     pnl_percentage: float, total_pnl: float) -> bool:
    """Send profit target alert when position hits 15% gain."""
    if not self.enabled:
        return False
    
    payload = {
        "attachments": [{
            "color": "#36a64f",  # Green
            "title": "🎯 PROFIT TARGET HIT!",
            "text": f"{symbol} ${strike} {side} reached 15% profit target",
            "fields": [
                {
                    "title": "Position",
                    "value": f"{symbol} ${strike} {side}",
                    "short": True
                },
                {
                    "title": "Entry → Current",
                    "value": f"${entry_premium:.2f} → ${current_premium:.2f}",
                    "short": True
                },
                {
                    "title": "P&L",
                    "value": f"{pnl_percentage:+.1f}% (${total_pnl:+.0f})",
                    "short": True
                },
                {
                    "title": "Action",
                    "value": "Consider taking profits!",
                    "short": True
                }
            ],
            "footer": "Conservative Strategy: Take profits over maximizing gains"
        }]
    }
    
    return self._send_message(payload)

def send_stop_loss_alert(self, symbol: str, strike: float, side: str, 
                        entry_premium: float, current_premium: float, 
                        pnl_percentage: float, total_pnl: float) -> bool:
    """Send stop loss alert when position hits 25% loss."""
    if not self.enabled:
        return False
    
    payload = {
        "attachments": [{
            "color": "#ff0000",  # Red
            "title": "🛑 STOP LOSS TRIGGERED!",
            "text": f"{symbol} ${strike} {side} hit 25% stop loss",
            "fields": [
                {
                    "title": "Position",
                    "value": f"{symbol} ${strike} {side}",
                    "short": True
                },
                {
                    "title": "Entry → Current",
                    "value": f"${entry_premium:.2f} → ${current_premium:.2f}",
                    "short": True
                },
                {
                    "title": "P&L",
                    "value": f"{pnl_percentage:+.1f}% (${total_pnl:+.0f})",
                    "short": True
                },
                {
                    "title": "Action",
                    "value": "CLOSE POSITION to limit losses!",
                    "short": True
                }
            ],
            "footer": "Capital Protection Priority: Avoid larger losses"
        }]
    }
    
    return self._send_message(payload)

def send_eod_warning(self, symbol: str, strike: float, side: str, 
                    current_premium: float, pnl_percentage: float) -> bool:
    """Send end-of-day warning to close positions."""
    if not self.enabled:
        return False
    
    payload = {
        "attachments": [{
            "color": "#ff9500",  # Orange
            "title": "⏰ END OF DAY WARNING",
            "text": f"Close {symbol} ${strike} {side} by 3:45 PM ET",
            "fields": [
                {
                    "title": "Position",
                    "value": f"{symbol} ${strike} {side}",
                    "short": True
                },
                {
                    "title": "Current P&L",
                    "value": f"{pnl_percentage:+.1f}% (${current_premium:.2f})",
                    "short": True
                },
                {
                    "title": "Time Remaining",
                    "value": "~15 minutes until close",
                    "short": True
                },
                {
                    "title": "Action",
                    "value": "CLOSE to avoid overnight risk",
                    "short": True
                }
            ],
            "footer": "Avoid overnight gaps - close all positions by 3:45 PM ET"
        }]
    }
    
    return self._send_message(payload)
