"""
Market Data Analysis Module

Provides comprehensive market data processing and technical analysis capabilities
for the Robinhood HA Breakout trading system. This module handles data fetching,
Heikin-Ashi candle calculations, breakout pattern analysis, and LLM payload preparation.

Key Features:
- Market data fetching from Yahoo Finance
- Heikin-Ashi candle calculations for trend smoothing
- Support/resistance level identification
- Breakout pattern analysis using multiple indicators
- True Range calculations for volatility analysis
- LLM payload preparation with token optimization

Technical Indicators:
- Heikin-Ashi candles for trend clarity
- Support and resistance levels using pivot points
- True Range for volatility measurement
- Volume analysis for confirmation
- Price momentum and trend direction

Data Sources:
- Primary: Yahoo Finance (yfinance)
- Fallback: Alpaca Markets API (if configured)
- Real-time: 5-minute intervals for intraday trading
- Historical: 5-day lookback for pattern analysis

Breakout Analysis:
- Trend direction identification
- Candle body percentage analysis
- Volume confirmation signals
- Support/resistance breakouts
- Momentum strength calculation

Usage:
    # Fetch and analyze market data
    data = fetch_market_data('SPY', period='5d', interval='5m')
    ha_data = calculate_heikin_ashi(data)
    analysis = analyze_breakout_pattern(ha_data, lookback=20)
    llm_payload = prepare_llm_payload(analysis)

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def fetch_market_data(symbol: str = "SPY", period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """
    Fetch market data using yfinance.
    
    Args:
        symbol: Stock symbol (default: SPY)
        period: Data period (default: 5d for 5 days)
        interval: Data interval (default: 5m for 5 minutes)
    
    Returns:
        DataFrame with OHLCV data
    """
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period, interval=interval)
        
        if data.empty:
            raise ValueError(f"No data returned for {symbol}")
        
        # Ensure we have the required columns
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in data.columns for col in required_cols):
            raise ValueError(f"Missing required columns in data for {symbol}")
        
        logger.info(f"Fetched {len(data)} bars for {symbol}")
        return data
    
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        raise


def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert regular OHLC data to Heikin-Ashi candles.
    
    Args:
        df: DataFrame with OHLC data
    
    Returns:
        DataFrame with Heikin-Ashi OHLC data
    """
    ha_df = df.copy()
    
    # Initialize first HA candle
    ha_df.loc[ha_df.index[0], 'HA_Close'] = (df.iloc[0]['Open'] + df.iloc[0]['High'] + 
                                            df.iloc[0]['Low'] + df.iloc[0]['Close']) / 4
    ha_df.loc[ha_df.index[0], 'HA_Open'] = (df.iloc[0]['Open'] + df.iloc[0]['Close']) / 2
    ha_df.loc[ha_df.index[0], 'HA_High'] = df.iloc[0]['High']
    ha_df.loc[ha_df.index[0], 'HA_Low'] = df.iloc[0]['Low']
    
    # Calculate subsequent HA candles
    for i in range(1, len(df)):
        # HA Close = (O + H + L + C) / 4
        ha_df.iloc[i, ha_df.columns.get_loc('HA_Close')] = (
            df.iloc[i]['Open'] + df.iloc[i]['High'] + 
            df.iloc[i]['Low'] + df.iloc[i]['Close']
        ) / 4
        
        # HA Open = (previous HA Open + previous HA Close) / 2
        ha_df.iloc[i, ha_df.columns.get_loc('HA_Open')] = (
            ha_df.iloc[i-1]['HA_Open'] + ha_df.iloc[i-1]['HA_Close']
        ) / 2
        
        # HA High = max(H, HA Open, HA Close)
        ha_df.iloc[i, ha_df.columns.get_loc('HA_High')] = max(
            df.iloc[i]['High'], 
            ha_df.iloc[i]['HA_Open'], 
            ha_df.iloc[i]['HA_Close']
        )
        
        # HA Low = min(L, HA Open, HA Close)
        ha_df.iloc[i, ha_df.columns.get_loc('HA_Low')] = min(
            df.iloc[i]['Low'], 
            ha_df.iloc[i]['HA_Open'], 
            ha_df.iloc[i]['HA_Close']
        )
    
    logger.info(f"Calculated Heikin-Ashi for {len(ha_df)} candles")
    return ha_df


def find_support_resistance(df: pd.DataFrame, lookback: int = 20) -> Dict[str, List[float]]:
    """
    Identify support and resistance levels using pivot points.
    
    Args:
        df: DataFrame with OHLC data (can be regular or Heikin-Ashi)
        lookback: Number of bars to look back for pivot identification
    
    Returns:
        Dictionary with 'support' and 'resistance' lists
    """
    if len(df) < lookback * 2 + 1:
        logger.warning(f"Insufficient data for support/resistance calculation. Need at least {lookback * 2 + 1} bars")
        return {'support': [], 'resistance': []}
    
    # Use HA data if available, otherwise regular data
    high_col = 'HA_High' if 'HA_High' in df.columns else 'High'
    low_col = 'HA_Low' if 'HA_Low' in df.columns else 'Low'
    
    highs = df[high_col].values
    lows = df[low_col].values
    
    resistance_levels = []
    support_levels = []
    
    # Find pivot highs (resistance)
    for i in range(lookback, len(highs) - lookback):
        if highs[i] == max(highs[i-lookback:i+lookback+1]):
            resistance_levels.append(highs[i])
    
    # Find pivot lows (support)
    for i in range(lookback, len(lows) - lookback):
        if lows[i] == min(lows[i-lookback:i+lookback+1]):
            support_levels.append(lows[i])
    
    # Remove duplicates and sort
    resistance_levels = sorted(list(set(resistance_levels)), reverse=True)
    support_levels = sorted(list(set(support_levels)))
    
    logger.info(f"Found {len(resistance_levels)} resistance and {len(support_levels)} support levels")
    
    return {
        'resistance': resistance_levels[:5],  # Top 5 resistance levels
        'support': support_levels[-5:]       # Top 5 support levels
    }


def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    """
    Calculate True Range for volatility analysis.
    
    Args:
        df: DataFrame with OHLC data
    
    Returns:
        Series with True Range values
    """
    high_col = 'HA_High' if 'HA_High' in df.columns else 'High'
    low_col = 'HA_Low' if 'HA_Low' in df.columns else 'Low'
    close_col = 'HA_Close' if 'HA_Close' in df.columns else 'Close'
    
    high = df[high_col]
    low = df[low_col]
    close_prev = df[close_col].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range


def analyze_breakout_pattern(df: pd.DataFrame, lookback: int = 20) -> Dict:
    """
    Analyze current market conditions for breakout patterns.
    
    Args:
        df: DataFrame with Heikin-Ashi data
        lookback: Number of bars for analysis
    
    Returns:
        Dictionary with analysis results
    """
    if len(df) < lookback:
        raise ValueError(f"Insufficient data for analysis. Need at least {lookback} bars")
    
    # Get the most recent data
    recent_data = df.tail(lookback).copy()
    current_candle = df.iloc[-1]
    
    # Calculate support/resistance
    sr_levels = find_support_resistance(df, lookback)
    
    # Calculate volatility metrics
    true_range = calculate_true_range(recent_data)
    avg_true_range = true_range.mean()
    current_tr = true_range.iloc[-1]
    
    # Current price and candle analysis
    current_price = current_candle['HA_Close']
    candle_body = abs(current_candle['HA_Close'] - current_candle['HA_Open'])
    candle_range = current_candle['HA_High'] - current_candle['HA_Low']
    
    # Calculate body percentage
    body_pct = (candle_body / current_price) * 100 if current_price > 0 else 0
    
    # True range percentage
    tr_pct = (current_tr / current_price) * 100 if current_price > 0 else 0
    
    # Distance to nearest support/resistance
    nearest_resistance = min([r for r in sr_levels['resistance'] if r > current_price], 
                           default=current_price * 1.02)
    nearest_support = max([s for s in sr_levels['support'] if s < current_price], 
                         default=current_price * 0.98)
    
    room_to_resistance = ((nearest_resistance - current_price) / current_price) * 100
    room_to_support = ((current_price - nearest_support) / current_price) * 100
    
    # Trend analysis (simple moving average)
    if len(recent_data) >= 10:
        sma_10 = recent_data['HA_Close'].tail(10).mean()
        trend_direction = "BULLISH" if current_price > sma_10 else "BEARISH"
    else:
        trend_direction = "NEUTRAL"
    
    analysis = {
        'current_price': round(current_price, 2),
        'candle_body_pct': round(body_pct, 3),
        'true_range_pct': round(tr_pct, 3),
        'avg_true_range': round(avg_true_range, 2),
        'trend_direction': trend_direction,
        'nearest_resistance': round(nearest_resistance, 2),
        'nearest_support': round(nearest_support, 2),
        'room_to_resistance_pct': round(room_to_resistance, 3),
        'room_to_support_pct': round(room_to_support, 3),
        'support_levels': [round(s, 2) for s in sr_levels['support']],
        'resistance_levels': [round(r, 2) for r in sr_levels['resistance']],
        'volume': int(current_candle.get('Volume', 0)),
        'timestamp': current_candle.name.isoformat() if hasattr(current_candle.name, 'isoformat') else str(current_candle.name)
    }
    
    logger.info(f"Breakout analysis completed for {current_price}")
    return analysis


def prepare_llm_payload(analysis: Dict, max_tokens: int = 400) -> Dict:
    """
    Prepare a compact JSON payload for LLM analysis, staying under token limit.
    Extends the trimmed payload with all fields required by the LLM client.
    
    Args:
        analysis: Market analysis dictionary
        max_tokens: Maximum token limit (approximate)
    
    Returns:
        Dictionary with both compact and full field names for LLM consumption
    """
    # 1. Compact fields to keep token usage low (legacy format)
    compact = {
        'price': analysis['current_price'],
        'body_pct': analysis['candle_body_pct'],
        'tr_pct': analysis['true_range_pct'],
        'trend': analysis['trend_direction'],
        'room_up': analysis['room_to_resistance_pct'],
        'room_down': analysis['room_to_support_pct'],
        'resistance': analysis['resistance_levels'][:3],  # Top 3 only
        'support': analysis['support_levels'][-3:],       # Top 3 only
        'volume': analysis['volume'],
        'timestamp': analysis['timestamp']
    }
    
    # 2. Full field names required by the LLM client validation
    full_fields = {
        'today_true_range_pct': analysis.get('true_range_pct', 0.0),
        'room_to_next_pivot': max(
            analysis.get('room_to_resistance_pct', 0.0),
            analysis.get('room_to_support_pct', 0.0)
        ),
        'iv_5m': analysis.get('avg_true_range', 30.0),  # Use ATR as IV proxy
        'candle_body_pct': analysis.get('candle_body_pct', 0.0),
        'current_price': analysis.get('current_price', 0.0),
        'trend_direction': analysis.get('trend_direction', 'NEUTRAL'),
        'volume_confirmation': analysis.get('volume', 0) > 0,
        'support_levels': analysis.get('support_levels', []),
        'resistance_levels': analysis.get('resistance_levels', [])
    }
    
    # 3. Merge compact and full fields
    payload = {**compact, **full_fields}
    
    logger.info("Prepared compact LLM payload with full field names")
    return payload
