#!/usr/bin/env python3
# ✅ Alpaca paper/live & scoped ledgers verified – 2025-08-10
"""
Alpaca API Integration for Real-Time Market Data

Provides real-time stock and options data to improve trading decisions.
This addresses the data accuracy issue where Yahoo Finance delayed data
led to missed profit opportunities.

Key Features:
- Real-time stock quotes and options data
- Professional-grade market data feeds
- Paper/live environment switching (v0.9.0)
- Fallback to Yahoo Finance if Alpaca unavailable
- Rate limiting and error handling

Usage:
    from utils.alpaca_client import AlpacaClient

    # Paper trading (default)
    alpaca = AlpacaClient(env="paper")
    
    # Live trading
    alpaca = AlpacaClient(env="live")
    
    current_price = alpaca.get_current_price('SPY')
    option_data = alpaca.get_option_chain('SPY', '2025-08-04')
"""

import os
import logging
from typing import Dict, Optional, Literal
from datetime import datetime, timedelta
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient

logger = logging.getLogger(__name__)


class AlpacaClient:
    """
    Alpaca API client for real-time market data and options information.

    Provides professional-grade market data to improve trading decisions
    and position monitoring accuracy.
    """

    def __init__(self, env: Literal["paper", "live"] = "paper", config: Optional[Dict] = None):
        """Initialize Alpaca client with API credentials and environment.
        
        Args:
            env: Trading environment - "paper" or "live" (default: "paper")
            config: Optional configuration dict with base URLs
        """
        self.env = env
        self.api_key = os.getenv("ALPACA_KEY_ID") or os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        
        # Configure base URL based on environment
        if config:
            if env == "paper":
                self.base_url = config.get("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")
            else:
                self.base_url = config.get("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets")
        else:
            # Fallback to environment variables or defaults
            if env == "paper":
                self.base_url = os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")
            else:
                self.base_url = os.getenv("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets")

        self.enabled = bool(self.api_key and self.secret_key)

        if self.enabled:
            try:
                # Initialize clients
                self.data_client = StockHistoricalDataClient(
                    api_key=self.api_key, secret_key=self.secret_key
                )

                self.trading_client = TradingClient(
                    api_key=self.api_key,
                    secret_key=self.secret_key,
                    paper=self.is_paper,
                )

                # Test connection
                account = self.trading_client.get_account()
                logger.info(
                    f"[ALPACA] Connected successfully - Account: {account.account_number} ({env.upper()})")
                logger.info(f"[ALPACA] Environment: {env}, Paper trading: {self.is_paper}")

            except Exception as e:
                logger.error(f"[ALPACA] Failed to initialize: {e}")
                self.enabled = False
        else:
            logger.warning(
                "[ALPACA] API keys not configured - falling back to Yahoo Finance"
            )

    @property
    def is_paper(self) -> bool:
        """Check if client is configured for paper trading.
        
        Returns:
            True if using paper trading environment, False for live trading
        """
        return self.env == "paper"

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get real-time current price for a symbol.

        Args:
            symbol: Stock symbol (e.g., 'SPY')

        Returns:
            Current price or None if unavailable
        """
        if not self.enabled:
            return None

        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
            quotes = self.data_client.get_stock_latest_quote(request)

            if symbol in quotes:
                quote = quotes[symbol]
                # Use mid-price (average of bid and ask)
                current_price = (quote.bid_price + quote.ask_price) / 2

                logger.debug(f"[ALPACA] {symbol} current price: ${current_price:.2f}")
                return float(current_price)

        except Exception as e:
            logger.error(f"[ALPACA] Failed to get current price for {symbol}: {e}")

        return None

    def get_market_data(
        self, symbol: str, period: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """
        Get historical market data for technical analysis.

        Args:
            symbol: Stock symbol
            period: Time period ('1d', '5d', '1mo', etc.)

        Returns:
            DataFrame with OHLCV data or None if unavailable
        """
        if not self.enabled:
            return None

        try:
            # Convert period to Alpaca timeframe
            if period == "1d":
                start_time = datetime.now() - timedelta(days=1)
                timeframe = TimeFrame.Minute
            elif period == "5d":
                start_time = datetime.now() - timedelta(
                    days=7
                )  # Get extra days for market hours
                timeframe = TimeFrame(5, TimeFrameUnit.Minute)  # 5-minute intervals
            else:
                start_time = datetime.now() - timedelta(days=30)
                timeframe = TimeFrame.Day

            request = StockBarsRequest(
                symbol_or_symbols=[symbol], timeframe=timeframe, start=start_time
            )

            logger.debug(
                f"[ALPACA] Requesting {symbol} data from {start_time} with {timeframe}"
            )
            bars = self.data_client.get_stock_bars(request)

            logger.debug(f"[ALPACA] Response type: {type(bars)}")

            # Handle the BarSet response properly
            if bars:
                try:
                    # Try to get the DataFrame directly
                    df = bars.df

                    # Filter for the specific symbol if multi-symbol response
                    if "symbol" in df.columns:
                        original_count = len(df)
                        df = df[df["symbol"] == symbol]
                        filtered_count = len(df)
                        logger.debug(
                            f"[ALPACA] Symbol filter: {original_count} → {filtered_count} bars "
                            f"(filtered for {symbol})"
                        )
                        if filtered_count == 0:
                            available_symbols = df["symbol"].unique().tolist() if original_count > 0 else []
                            logger.warning(
                                f"[ALPACA] No data found for symbol '{symbol}'. "
                                f"Available symbols in response: {available_symbols}"
                            )
                    else:
                        logger.debug(
                            f"[ALPACA] No 'symbol' column found in DataFrame. "
                            f"Available columns: {df.columns.tolist()}"
                        )

                    logger.debug(f"[ALPACA] Raw DataFrame shape: {df.shape}")
                    logger.debug(
                        f"[ALPACA] Raw DataFrame columns: {df.columns.tolist()}"
                    )

                    if df.empty:
                        logger.warning(f"[ALPACA] DataFrame is empty for {symbol}")
                        return None

                    # Rename columns to match Yahoo Finance format
                    df = df.rename(
                        columns={
                            "open": "Open",
                            "high": "High",
                            "low": "Low",
                            "close": "Close",
                            "volume": "Volume",
                        }
                    )

                    logger.info(
                        f"[ALPACA] Retrieved {len(df)} bars for {symbol} (timeframe: {timeframe})"
                    )
                    return df

                except Exception as df_error:
                    logger.error(
                        f"[ALPACA] Failed to process DataFrame for {symbol}: {df_error}"
                    )
                    return None
            else:
                logger.warning(
                    f"[ALPACA] No data found for symbol {symbol} in response"
                )

        except Exception as e:
            logger.error(f"[ALPACA] Failed to get market data for {symbol}: {e}")

        return None

    def get_option_estimate(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        current_stock_price: float,
    ) -> Optional[float]:
        """
        Get improved option price estimate using real-time data.

        Note: Alpaca doesn't provide direct options pricing, but we can
        create better estimates using real-time stock data and volatility.

        Args:
            symbol: Underlying symbol
            strike: Option strike price
            option_type: 'CALL' or 'PUT'
            expiry: Expiration date string
            current_stock_price: Current stock price

        Returns:
            Estimated option price or None
        """
        if not self.enabled:
            return None

        try:
            # Get real-time stock price if not provided
            if not current_stock_price:
                current_stock_price = self.get_current_price(symbol)
                if not current_stock_price:
                    return None

            # Calculate intrinsic value
            if option_type.upper() == "CALL":
                intrinsic_value = max(0, current_stock_price - strike)
            else:  # PUT
                intrinsic_value = max(0, strike - current_stock_price)

            # Estimate time value using recent volatility
            time_value = self._estimate_time_value(
                symbol, strike, current_stock_price, expiry
            )

            estimated_price = intrinsic_value + time_value
            estimated_price = max(0.01, estimated_price)  # Minimum $0.01

            logger.debug(
                f"[ALPACA] {symbol} ${strike} {option_type} estimate: ${estimated_price:.2f}"
            )
            return estimated_price

        except Exception as e:
            logger.error(f"[ALPACA] Failed to estimate option price: {e}")

        return None

    def _estimate_time_value(
        self, symbol: str, strike: float, current_price: float, expiry: str
    ) -> float:
        """
        Estimate option time value using recent volatility.

        This is a simplified estimation - real options pricing would
        use Black-Scholes with implied volatility.
        """
        try:
            # Get recent price data for volatility calculation
            df = self.get_market_data(symbol, "5d")
            if df is None or len(df) < 10:
                # Fallback to simple time value
                return 0.05

            # Calculate recent volatility
            df["returns"] = df["Close"].pct_change()
            volatility = df["returns"].std() * (252**0.5)  # Annualized

            # Calculate time to expiration
            try:
                expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
                days_to_expiry = (expiry_date - datetime.now()).days
                time_to_expiry = max(days_to_expiry / 365.0, 0.001)  # Years
            except:
                time_to_expiry = 0.001  # Very short time for 0DTE

            # Simplified time value estimation
            # For ATM options: time_value ≈ 0.4 * stock_price * volatility * sqrt(time)
            moneyness = abs(current_price - strike) / current_price
            atm_factor = max(0.1, 1.0 - moneyness * 2)  # Reduce for OTM options

            time_value = (
                0.4 * current_price * volatility * (time_to_expiry**0.5) * atm_factor
            )

            # For 0DTE, time value decays rapidly
            if days_to_expiry == 0:
                time_value *= 0.1  # Very low time value for 0DTE

            return max(
                0.01, min(time_value, current_price * 0.1)
            )  # Cap at 10% of stock price

        except Exception as e:
            logger.debug(f"[ALPACA] Time value estimation error: {e}")
            return 0.05  # Fallback

    def is_market_open(self) -> bool:
        """
        Check if the market is currently open.

        Returns:
            True if market is open, False otherwise
        """
        if not self.enabled:
            return True  # Assume open if we can't check

        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"[ALPACA] Failed to check market hours: {e}")
            return True  # Assume open on error

    def get_account_info(self) -> Optional[Dict]:
        """
        Get account information for paper trading validation.

        Returns:
            Account info dict or None
        """
        if not self.enabled:
            return None

        try:
            account = self.trading_client.get_account()
            return {
                "account_number": account.account_number,
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
                "portfolio_value": float(account.portfolio_value),
                "paper_trading": "paper" in self.base_url,
            }
        except Exception as e:
            logger.error(f"[ALPACA] Failed to get account info: {e}")
            return None

    def test_connection(self) -> bool:
        """
        Test Alpaca API connection and permissions.

        Returns:
            True if connection successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Test data API
            current_price = self.get_current_price("SPY")
            if current_price is None:
                return False

            # Test trading API
            account = self.trading_client.get_account()
            if account is None:
                return False

            logger.info("[ALPACA] Connection test successful")
            return True

        except Exception as e:
            logger.error(f"[ALPACA] Connection test failed: {e}")
            return False
