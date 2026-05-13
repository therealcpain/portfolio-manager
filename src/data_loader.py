"""
Data loader — Phase 3 implementation.
Loads market data from free sources (yfinance, FRED, CoinGecko).
Phase 1: returns placeholders with clear [LIVE DATA REQUIRED] markers.
Advisory only — no live trading.
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional
import warnings

PHASE = 1  # Increment as data sources are integrated


PLACEHOLDER = "[LIVE DATA REQUIRED]"


def get_price(ticker: str, as_of: Optional[date] = None) -> dict:
    """
    Fetch current or historical price for a ticker.
    Phase 1: returns placeholder. Phase 3: integrates yfinance.
    """
    if PHASE < 3:
        return {
            "ticker": ticker,
            "price": None,
            "as_of": str(as_of or date.today()),
            "source": PLACEHOLDER,
            "note": "Phase 3 will integrate yfinance for live/historical prices.",
        }

    # Phase 3 implementation:
    # import yfinance as yf
    # data = yf.Ticker(ticker).history(period="1d")
    # return {"ticker": ticker, "price": data["Close"].iloc[-1], ...}
    raise NotImplementedError("Phase 3 not yet implemented.")


def get_price_history(
    ticker: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    period: str = "1y",
) -> dict:
    """
    Fetch OHLCV price history.
    Phase 1: placeholder. Phase 3: yfinance integration.
    """
    if PHASE < 3:
        return {
            "ticker": ticker,
            "data": None,
            "start": str(start),
            "end": str(end),
            "period": period,
            "source": PLACEHOLDER,
        }
    raise NotImplementedError("Phase 3 not yet implemented.")


def get_macro_data(series_id: str) -> dict:
    """
    Fetch macro data from FRED (Federal Reserve Economic Data).
    Series examples: M2SL (M2 money supply), DFF (Fed funds rate), T10YIE (breakeven inflation).
    Phase 1: placeholder. Phase 3: FRED API integration.
    """
    if PHASE < 3:
        return {
            "series_id": series_id,
            "value": None,
            "date": PLACEHOLDER,
            "source": "FRED (Phase 3)",
            "note": f"FRED series {series_id} — requires FRED_API_KEY in .env",
        }
    raise NotImplementedError("Phase 3 not yet implemented.")


def get_crypto_price(coin_id: str) -> dict:
    """
    Fetch crypto price from CoinGecko (free tier).
    Phase 1: placeholder. Phase 3: CoinGecko API.
    """
    if PHASE < 3:
        return {
            "coin": coin_id,
            "price_usd": None,
            "market_cap": None,
            "source": "CoinGecko (Phase 3)",
            "note": PLACEHOLDER,
        }
    raise NotImplementedError("Phase 3 not yet implemented.")


def get_options_chain(ticker: str, expiry: Optional[str] = None) -> dict:
    """
    Fetch options chain data.
    Phase 4: requires paid data provider (TBD).
    """
    return {
        "ticker": ticker,
        "expiry": expiry,
        "data": None,
        "source": "[PAID DATA — Phase 4]",
        "note": "Options chain data requires paid provider. Phase 4 implementation.",
    }


def get_sentiment_data(asset: str) -> dict:
    """
    Fetch sentiment indicators.
    Phase 4: requires sentiment data provider.
    """
    return {
        "asset": asset,
        "fear_greed": None,
        "source": "[PAID DATA — Phase 4]",
        "note": "Sentiment feeds require Phase 4 integration.",
    }


def get_onchain_data(metric: str, asset: str = "bitcoin") -> dict:
    """
    Fetch on-chain blockchain data.
    Phase 4: Glassnode, Nansen, or Dune Analytics integration.
    """
    return {
        "asset": asset,
        "metric": metric,
        "value": None,
        "source": "[PAID DATA — Phase 4]",
        "note": "On-chain data requires Phase 4 integration.",
    }
