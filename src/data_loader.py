"""
Data loader — Phase 2 implementation.
Pulls real historical price data from yfinance (free).
Macro data from FRED (requires FRED_API_KEY in .env, optional).
Advisory only — no live trading.
"""

from __future__ import annotations
import warnings
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

ROOT_DIR = Path(__file__).parent.parent
CACHE_DIR = ROOT_DIR / "data" / "processed"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Ticker map: portfolio IDs → yfinance symbols
TICKER_MAP = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "MSTR": "MSTR",
    "GLD": "GLD",
    "SLV": "SLV",
    "URNM": "URNM",
    "IBIT": "IBIT",
    "COIN": "COIN",
    "CLSK": "CLSK",
    "NVDA": "NVDA",
    "SMH": "SMH",
    "XLE": "XLE",
    "COPX": "COPX",
    "NEE": "NEE",
    "MSFT": "MSFT",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "AGG": "AGG",
    "TLT": "TLT",
    "STRC_PROXY": "^IRX",  # 3-month T-bill as STRC proxy
    "DXY": "DX-Y.NYB",
    "GC": "GC=F",  # Gold futures
    "CL": "CL=F",  # WTI Crude futures
}


def _yf_download(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Download OHLCV from yfinance with SSL warning suppression."""
    import yfinance as yf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = yf.download(ticker, start=str(start), end=str(end), progress=False, auto_adjust=True)
    return df


def get_price_series(
    ticker: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    period_years: int = 2,
) -> pd.Series:
    """
    Return a daily closing price series for a ticker.
    Caches results to data/processed/ to avoid re-downloading.
    """
    yf_ticker = TICKER_MAP.get(ticker, ticker)
    end = end or date.today()
    start = start or (end - timedelta(days=period_years * 365))

    cache_path = CACHE_DIR / f"prices_{yf_ticker.replace('/', '_').replace('^', '').replace('=', '')}_{start}_{end}.parquet"

    if cache_path.exists():
        return pd.read_parquet(cache_path)["Close"].squeeze()

    df = _yf_download(yf_ticker, start, end)
    if df.empty:
        return pd.Series(dtype=float, name=ticker)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.to_parquet(cache_path)
    return df["Close"].squeeze().rename(ticker)


def get_price_history_multi(
    tickers: list[str],
    start: Optional[date] = None,
    end: Optional[date] = None,
    period_years: int = 2,
) -> pd.DataFrame:
    """Return a DataFrame of closing prices for multiple tickers."""
    end = end or date.today()
    start = start or (end - timedelta(days=period_years * 365))
    series = {}
    for ticker in tickers:
        s = get_price_series(ticker, start, end)
        if not s.empty:
            series[ticker] = s
    if not series:
        return pd.DataFrame()
    df = pd.DataFrame(series)
    df.index = pd.to_datetime(df.index)
    df = df.ffill()
    return df


def get_current_price(ticker: str) -> float:
    """Get the most recent closing price."""
    s = get_price_series(ticker, end=date.today(), period_years=0)
    if s.empty:
        return 0.0
    return float(s.iloc[-1])


def get_risk_free_rate() -> float:
    """
    Get the current annualized risk-free rate from 3-month T-bill (^IRX).
    Returns as a decimal (e.g., 0.045 for 4.5%).
    """
    s = get_price_series("STRC_PROXY", period_years=0)
    if s.empty:
        return 0.045  # fallback
    rate_pct = float(s.iloc[-1])
    return rate_pct / 100.0


def get_macro_series(series_id: str) -> pd.Series:
    """
    Fetch macro data from FRED API.
    Requires FRED_API_KEY env var. Returns empty series if unavailable.
    Common series: M2SL, DFF, T10YIE, UNRATE, CPIAUCSL, GDP
    """
    if not FRED_API_KEY:
        return pd.Series(dtype=float, name=series_id)

    try:
        import requests
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
            f"&sort_order=desc&limit=100"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json().get("observations", [])
        values = {obs["date"]: float(obs["value"]) for obs in data if obs["value"] != "."}
        s = pd.Series(values)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:
        return pd.Series(dtype=float, name=series_id)


def prices_to_returns(prices: pd.Series) -> pd.Series:
    """Convert price series to daily percentage returns."""
    return prices.pct_change().dropna()


def prices_to_cumulative_returns(prices: pd.Series, base: float = 1.0) -> pd.Series:
    """Convert price series to cumulative return series starting at `base`."""
    normalized = prices / prices.iloc[0] * base
    return normalized
