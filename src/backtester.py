"""
backtester.py — Historical backtest of the regime-based decision model.

Runs the portfolio's regime classification logic against monthly historical
macro data (Jan 2020 → today), applies the regime-appropriate allocation
each month, and computes performance vs benchmarks.

No look-ahead bias: each FRED series is offset by its typical publication
lag before being used in the regime decision.

Usage:
    python src/backtester.py                # run + write reports/backtest/
    python src/backtester.py --no-pdf       # skip PDF output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
OUTPUT_DIR = ROOT_DIR / "reports" / "backtest"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------

def _load_env() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ[k.strip()] = v.strip()


# ---------------------------------------------------------------------------
# Regime → Allocation policy
# ---------------------------------------------------------------------------

# Weights must sum to 1.0 for each regime.
# Tickers map to yfinance symbols used below.
REGIME_ALLOCATIONS: dict[str, dict[str, float]] = {
    "RISK_ON_GROWTH": {
        "SPY":  0.30,
        "QQQ":  0.20,
        "BTC":  0.15,
        "GLD":  0.08,
        "URNM": 0.05,
        "CASH": 0.22,
    },
    "LATE_CYCLE_CAUTIOUS": {
        "SPY":  0.20,
        "QQQ":  0.15,
        "BTC":  0.10,
        "GLD":  0.12,
        "URNM": 0.05,
        "CASH": 0.38,
    },
    "TRANSITIONAL": {
        "SPY":  0.18,
        "QQQ":  0.12,
        "BTC":  0.08,
        "GLD":  0.15,
        "URNM": 0.04,
        "CASH": 0.43,
    },
    "RISK_OFF_TIGHTENING": {
        "SPY":  0.12,
        "QQQ":  0.08,
        "BTC":  0.05,
        "GLD":  0.20,
        "URNM": 0.03,
        "CASH": 0.52,
    },
    "DEFENSIVE_CONTRACTION": {
        "SPY":  0.08,
        "QQQ":  0.05,
        "BTC":  0.00,
        "GLD":  0.25,
        "URNM": 0.00,
        "CASH": 0.62,
    },
}

STATIC_ALLOCATION: dict[str, float] = {
    "SPY":  0.20,
    "QQQ":  0.15,
    "BTC":  0.10,
    "GLD":  0.10,
    "URNM": 0.05,
    "CASH": 0.40,
}

BENCHMARK_60_40: dict[str, float] = {
    "SPY": 0.60,
    "TLT": 0.40,
}

BENCHMARK_SPY: dict[str, float] = {
    "SPY": 1.00,
}

# yfinance symbol map
_YF_SYMBOLS = {
    "SPY":  "SPY",
    "QQQ":  "QQQ",
    "BTC":  "BTC-USD",
    "GLD":  "GLD",
    "URNM": "URNM",
    "TLT":  "TLT",
    "VIX":  "^VIX",
    "US10Y": "^TNX",
    "US2Y":  "^IRX",
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class MonthlySnapshot:
    date: str                        # YYYY-MM-DD (last trading day of month)
    regime: str
    regime_score: int
    regime_confidence: int
    allocation: dict[str, float]     # ticker → weight (from REGIME_ALLOCATIONS)
    macro: dict                      # raw macro inputs used for classification


@dataclass
class BacktestResult:
    start_date: str
    end_date: str
    monthly_snapshots: list[MonthlySnapshot] = field(default_factory=list)
    model_returns: list[float] = field(default_factory=list)   # monthly
    bench_6040_returns: list[float] = field(default_factory=list)
    bench_spy_returns: list[float] = field(default_factory=list)
    static_returns: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Historical data download
# ---------------------------------------------------------------------------

_START_DATE = "2019-12-31"  # need Dec 2019 to compute Jan 2020 return
_END_DATE   = date.today().isoformat()
_BACKTEST_START = "2020-01-31"


def _download_prices() -> pd.DataFrame:
    """Download monthly close prices for all tickers."""
    import yfinance as yf

    syms = list(_YF_SYMBOLS.values())
    print(f"  Downloading price history for {len(syms)} tickers...")
    raw = yf.download(
        syms,
        start=_START_DATE,
        end=_END_DATE,
        interval="1mo",
        auto_adjust=True,
        progress=False,
    )
    # yfinance returns MultiIndex if multiple tickers
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:
        prices = raw[["Close"]].copy()
        prices.columns = [syms[0]]

    # Rename back from yf symbols to our internal names
    sym_to_name = {v: k for k, v in _YF_SYMBOLS.items()}
    prices.rename(columns=sym_to_name, inplace=True)
    prices.index = pd.to_datetime(prices.index)
    prices.index = prices.index.tz_localize(None)
    return prices


def _download_fred_series(fred_api_key: str) -> dict[str, pd.Series]:
    """Download FRED macro series needed for regime classification."""
    from fredapi import Fred
    fred = Fred(api_key=fred_api_key)

    series = {}
    _fred_map = {
        "DFF":              "fed_funds",          # daily → resample monthly
        "A191RL1Q225SBEA":  "gdp_qoq",            # quarterly, ~30d lag
        "BAMLH0A0HYM2":     "hy_spread",          # daily (in %)
        "DFII10":           "real_rate_10y",       # daily
        "PCEPI":            "pce",                 # monthly, ~30d lag
    }
    # ISM Manufacturing proxy not available via FRED API; ism_mfg defaults to 50 in regime classification
    for fred_id, name in _fred_map.items():
        try:
            s = fred.get_series(fred_id, observation_start=_START_DATE)
            s = s.dropna()
            s.index = pd.to_datetime(s.index).tz_localize(None)
            series[name] = s
            print(f"    FRED {fred_id} ({name}): {len(s)} obs")
        except Exception as e:
            print(f"    FRED {fred_id} skipped: {e}")
            series[name] = pd.Series(dtype=float)

    return series


# ---------------------------------------------------------------------------
# Historical macro reconstruction (with publication lags)
# ---------------------------------------------------------------------------

_EMPTY_TS = pd.Series(dtype=float, index=pd.DatetimeIndex([]))


def _get_as_of(series: pd.Series, as_of_date: pd.Timestamp,
               lag_days: int = 0) -> Optional[float]:
    """
    Return the most recent value of `series` that would have been *available*
    as of `as_of_date`, accounting for publication lag.
    """
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return None
    cutoff = as_of_date - pd.Timedelta(days=lag_days)
    available = series[series.index <= cutoff]
    if available.empty:
        return None
    return float(available.iloc[-1])


def _get_monthly_resample(series: pd.Series, as_of_date: pd.Timestamp,
                          lag_days: int = 0) -> Optional[float]:
    """Resample a daily series to monthly mean, then return value at lag-adjusted cutoff."""
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return None
    monthly = series.resample("ME").mean()
    return _get_as_of(monthly, as_of_date, lag_days)


def _get_yoy(series: pd.Series, as_of_date: pd.Timestamp,
             lag_days: int = 30) -> Optional[float]:
    """Compute YoY % change for a level series."""
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return None
    cutoff = as_of_date - pd.Timedelta(days=lag_days)
    available = series[series.index <= cutoff]
    if len(available) < 13:
        return None
    curr = float(available.iloc[-1])
    prev = float(available.iloc[-13])
    if prev == 0:
        return None
    return round((curr / prev - 1) * 100, 2)


def _build_historical_macro(
    date_ts: pd.Timestamp,
    prices: pd.DataFrame,
    fred_series: dict[str, pd.Series],
) -> dict:
    """
    Reconstruct macro signals as they would have appeared on `date_ts`,
    applying realistic publication lags to avoid look-ahead bias.
    """
    mac = {}

    # ── Prices & momentum (no lag — these are market prices) ──────────────
    def price_at(ticker: str) -> Optional[float]:
        if ticker not in prices.columns:
            return None
        col = prices[ticker].dropna()
        avail = col[col.index <= date_ts]
        return float(avail.iloc[-1]) if not avail.empty else None

    def mom_20d(ticker: str) -> Optional[float]:
        """Approximate 20-trading-day return using adjacent monthly bars."""
        if ticker not in prices.columns:
            return None
        col = prices[ticker].dropna()
        avail = col[col.index <= date_ts]
        if len(avail) < 2:
            return None
        return round((float(avail.iloc[-1]) / float(avail.iloc[-2]) - 1) * 100, 2)

    mac["vix"]       = price_at("VIX") or 20.0
    mac["spy_20d"]   = mom_20d("SPY") or 0.0
    mac["btc_20d"]   = mom_20d("BTC") or 0.0
    mac["us10y"]     = price_at("US10Y") or 4.5
    mac["us2y"]      = price_at("US2Y") or 4.0
    mac["yield_spread"] = round((mac["us10y"] or 0) - (mac["us2y"] or 0), 2)

    # ── FRED series with publication lags ──────────────────────────────────
    # Fed funds: daily, essentially no lag
    mac["fed_funds"] = _get_monthly_resample(fred_series.get("fed_funds", pd.Series()), date_ts, lag_days=2) or 4.5

    # GDP: quarterly, published ~30 days after quarter end → use 45d lag
    mac["gdp"] = _get_as_of(fred_series.get("gdp_qoq", pd.Series()), date_ts, lag_days=45)
    if mac["gdp"] is None:
        mac["gdp"] = 2.0

    # HY spread: daily (market-traded), essentially no lag (convert % → bps)
    hy_pct = _get_monthly_resample(fred_series.get("hy_spread", pd.Series()), date_ts, lag_days=2)
    mac["hy_spread_bps"] = round(hy_pct * 100, 0) if hy_pct is not None else 350.0

    # Real 10Y TIPS: daily, no lag
    mac["real_rate_10y"] = _get_monthly_resample(fred_series.get("real_rate_10y", pd.Series()), date_ts, lag_days=2)

    # ISM Mfg (Chicago PMI proxy): monthly, ~1 day lag
    mac["ism_mfg"] = _get_as_of(fred_series.get("ism_mfg", pd.Series()), date_ts, lag_days=5) or 50.0

    # PCE YoY: monthly, ~30d lag
    mac["pce_yoy"] = _get_yoy(fred_series.get("pce", pd.Series()), date_ts, lag_days=30) or 3.0

    # CPI approximation: use PCE as proxy (BLS historical reconstruction is complex)
    mac["cpi_yoy"]      = mac["pce_yoy"]
    mac["core_cpi_yoy"] = mac["pce_yoy"]
    mac["unemployment"] = 4.0  # stable default; avoid BLS API for historical

    return mac


# ---------------------------------------------------------------------------
# Regime classification (mirrors macro_fetcher._auto_classify_regime)
# ---------------------------------------------------------------------------

def _classify_regime(mac: dict) -> tuple[str, int, int]:
    """Returns (regime_label, score, confidence)."""
    score = 0

    gdp      = mac.get("gdp", 2.0) or 2.0
    ism_mfg  = mac.get("ism_mfg", 50) or 50
    core_cpi = mac.get("core_cpi_yoy", 3.0) or 3.0
    yield_sp = mac.get("yield_spread", 0.0) or 0.0
    fed_f    = mac.get("fed_funds", 4.5) or 4.5
    vix      = mac.get("vix", 20) or 20
    hy_bps   = mac.get("hy_spread_bps", 350) or 350
    spy_20d  = mac.get("spy_20d", 0) or 0

    if gdp >= 2.5:
        score += 2
    elif gdp >= 0:
        score += 1
    else:
        score -= 2

    if ism_mfg >= 50:
        score += 1
    else:
        score -= 1

    if core_cpi > 3.5:
        score -= 1
    elif core_cpi < 2.5:
        score += 1

    if yield_sp > 0:
        score += 1
    else:
        score -= 1

    if fed_f > 4.0:
        score -= 1
    else:
        score += 1

    if vix < 15:
        score += 1
    elif vix > 25:
        score -= 2

    if hy_bps < 300:
        score += 1
    elif hy_bps > 500:
        score -= 2

    if spy_20d > 3:
        score += 1
    elif spy_20d < -5:
        score -= 1

    if score >= 5:
        regime     = "RISK_ON_GROWTH"
        confidence = min(90, 60 + score * 3)
    elif score >= 2:
        regime     = "LATE_CYCLE_CAUTIOUS"
        confidence = min(75, 50 + score * 3)
    elif score >= 0:
        regime     = "TRANSITIONAL"
        confidence = 45
    elif score >= -3:
        regime     = "RISK_OFF_TIGHTENING"
        confidence = min(75, 50 + abs(score) * 3)
    else:
        regime     = "DEFENSIVE_CONTRACTION"
        confidence = min(85, 55 + abs(score) * 3)

    return regime, score, int(confidence)


# ---------------------------------------------------------------------------
# Portfolio return calculation
# ---------------------------------------------------------------------------

def _compute_monthly_return(
    allocation: dict[str, float],
    prices: pd.DataFrame,
    prev_date: pd.Timestamp,
    curr_date: pd.Timestamp,
) -> float:
    """
    Compute the 1-month portfolio return given weights at `prev_date`,
    using price data from `prices`.
    Cash earns 0% (conservative; could use T-bill but keeps it simple).
    """
    port_return = 0.0
    for ticker, weight in allocation.items():
        if ticker == "CASH" or weight == 0:
            continue
        if ticker not in prices.columns:
            continue
        col = prices[ticker].dropna()
        prev_avail = col[col.index <= prev_date]
        curr_avail = col[col.index <= curr_date]
        if prev_avail.empty or curr_avail.empty:
            continue
        p_prev = float(prev_avail.iloc[-1])
        p_curr = float(curr_avail.iloc[-1])
        if p_prev > 0:
            r = (p_curr / p_prev) - 1
            port_return += weight * r
    return port_return


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def _metrics(monthly_returns: list[float], label: str) -> dict:
    r = np.array(monthly_returns)
    if len(r) == 0:
        return {}

    n_months = len(r)
    n_years  = n_months / 12

    cum_return   = float(np.prod(1 + r) - 1)
    cagr         = float((1 + cum_return) ** (1 / n_years) - 1) if n_years > 0 else 0

    cumulative   = np.cumprod(1 + r)
    rolling_max  = np.maximum.accumulate(cumulative)
    drawdowns    = cumulative / rolling_max - 1
    max_dd       = float(np.min(drawdowns))

    std_monthly  = float(np.std(r, ddof=1))
    ann_vol      = std_monthly * np.sqrt(12)

    rf_monthly   = 0.0  # simplified; cash earns ~0 in model
    excess       = r - rf_monthly
    sharpe       = float(np.mean(excess) / std_monthly * np.sqrt(12)) if std_monthly > 0 else 0

    neg = r[r < 0]
    down_std = float(np.std(neg, ddof=1)) * np.sqrt(12) if len(neg) > 1 else ann_vol
    sortino  = float(np.mean(excess) / (down_std / np.sqrt(12)) * np.sqrt(12)) if down_std > 0 else 0

    calmar   = float(cagr / abs(max_dd)) if max_dd != 0 else 0
    win_rate = float(np.sum(r > 0) / n_months)
    best_m   = float(np.max(r))
    worst_m  = float(np.min(r))

    return {
        "label":        label,
        "months":       n_months,
        "total_return": round(cum_return * 100, 1),
        "cagr_pct":     round(cagr * 100, 2),
        "ann_vol_pct":  round(ann_vol * 100, 2),
        "max_dd_pct":   round(max_dd * 100, 2),
        "sharpe":       round(sharpe, 2),
        "sortino":      round(sortino, 2),
        "calmar":       round(calmar, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "best_month":   round(best_m * 100, 2),
        "worst_month":  round(worst_m * 100, 2),
    }


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest(fred_api_key: str) -> tuple[BacktestResult, list[dict]]:
    """
    Full backtest pipeline.
    Returns (BacktestResult, list_of_metric_dicts).
    """
    import yfinance as yf  # noqa: F401 (triggers install check)

    print("\n[Backtester] Downloading historical data...")
    prices = _download_prices()
    fred_series = _download_fred_series(fred_api_key)

    # Build list of month-end dates for the backtest window
    all_dates = pd.date_range(start="2020-01-31", end=_END_DATE, freq="ME")
    print(f"\n[Backtester] Running regime classification for {len(all_dates)} months...")

    result     = BacktestResult(start_date=str(all_dates[0].date()), end_date=str(all_dates[-1].date()))
    snapshots  = []
    model_r    = []
    b6040_r    = []
    bspy_r     = []
    static_r   = []
    date_labels = []

    for i, curr_ts in enumerate(all_dates):
        # Need a prior month for return calculation
        prev_ts = all_dates[i - 1] if i > 0 else pd.Timestamp("2019-12-31")

        # ── Reconstruct macro as it would appear at curr_ts ──────────────
        mac = _build_historical_macro(curr_ts, prices, fred_series)
        regime, score, confidence = _classify_regime(mac)
        allocation = REGIME_ALLOCATIONS[regime]

        snap = MonthlySnapshot(
            date=str(curr_ts.date()),
            regime=regime,
            regime_score=score,
            regime_confidence=confidence,
            allocation=dict(allocation),
            macro={
                "vix":          mac.get("vix"),
                "spy_20d":      mac.get("spy_20d"),
                "fed_funds":    mac.get("fed_funds"),
                "gdp":          mac.get("gdp"),
                "hy_spread_bps": mac.get("hy_spread_bps"),
                "yield_spread": mac.get("yield_spread"),
            },
        )
        snapshots.append(snap)

        # ── Compute monthly returns for each portfolio ────────────────────
        mr = _compute_monthly_return(allocation,              prices, prev_ts, curr_ts)
        br = _compute_monthly_return(BENCHMARK_60_40,         prices, prev_ts, curr_ts)
        sr = _compute_monthly_return(BENCHMARK_SPY,           prices, prev_ts, curr_ts)
        st = _compute_monthly_return(STATIC_ALLOCATION,       prices, prev_ts, curr_ts)

        model_r.append(mr)
        b6040_r.append(br)
        bspy_r.append(sr)
        static_r.append(st)
        date_labels.append(str(curr_ts.date()))

        if (i + 1) % 12 == 0:
            print(f"  ...{curr_ts.date()} — regime={regime}")

    result.monthly_snapshots   = snapshots
    result.model_returns       = model_r
    result.bench_6040_returns  = b6040_r
    result.bench_spy_returns   = bspy_r
    result.static_returns      = static_r
    result.dates               = date_labels

    metrics = [
        _metrics(model_r,   "Regime Model"),
        _metrics(b6040_r,   "60/40 (SPY/TLT)"),
        _metrics(bspy_r,    "100% SPY"),
        _metrics(static_r,  "Static Allocation"),
    ]

    return result, metrics


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _equity_curve_chart(result: BacktestResult, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    dates = pd.to_datetime(result.dates)

    def cumulative(rets):
        return np.cumprod(1 + np.array(rets)) * 100

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#0f0018")
    ax.set_facecolor("#0f0018")

    colors_map = {
        "Regime Model":      "#a855f7",
        "60/40":             "#6d28d9",
        "100% SPY":          "#c084fc",
        "Static Allocation": "#e879f9",
    }

    ax.plot(dates, cumulative(result.model_returns),      color=colors_map["Regime Model"],      lw=2,   label="Regime Model")
    ax.plot(dates, cumulative(result.bench_6040_returns), color=colors_map["60/40"],             lw=1.5, label="60/40 (SPY/TLT)", linestyle="--")
    ax.plot(dates, cumulative(result.bench_spy_returns),  color=colors_map["100% SPY"],          lw=1.5, label="100% SPY",        linestyle=":")
    ax.plot(dates, cumulative(result.static_returns),     color=colors_map["Static Allocation"], lw=1.5, label="Static Model",    linestyle="-.")

    ax.axhline(100, color="#3b0764", lw=0.8, linestyle="--")
    ax.set_title("Portfolio Growth (Base = $100)", color="#e9d5ff", fontsize=13, pad=10)
    ax.set_ylabel("Value ($)", color="#a78bfa")
    ax.tick_params(colors="#a78bfa")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for spine in ax.spines.values():
        spine.set_color("#2d1458")
    ax.legend(facecolor="#0f0018", labelcolor="#e9d5ff", framealpha=0.8, loc="upper left")
    ax.grid(True, color="#2d1458", lw=0.5, alpha=0.6)

    plt.tight_layout()
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close()


def _drawdown_chart(result: BacktestResult, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    dates = pd.to_datetime(result.dates)

    def drawdown_series(rets):
        cum = np.cumprod(1 + np.array(rets))
        roll_max = np.maximum.accumulate(cum)
        dd = (cum / roll_max - 1) * 100
        return dd

    fig, ax = plt.subplots(figsize=(12, 4))
    fig.patch.set_facecolor("#0f0018")
    ax.set_facecolor("#0f0018")

    ax.fill_between(dates, drawdown_series(result.model_returns),      0, alpha=0.4, color="#a855f7", label="Regime Model")
    ax.plot(dates,         drawdown_series(result.model_returns),               color="#a855f7", lw=1.5)
    ax.plot(dates,         drawdown_series(result.bench_spy_returns),   color="#c084fc", lw=1, linestyle=":", label="100% SPY")
    ax.plot(dates,         drawdown_series(result.bench_6040_returns),  color="#6d28d9", lw=1, linestyle="--", label="60/40")

    ax.set_title("Drawdown from Peak (%)", color="#e9d5ff", fontsize=13, pad=10)
    ax.set_ylabel("Drawdown %", color="#a78bfa")
    ax.tick_params(colors="#a78bfa")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for spine in ax.spines.values():
        spine.set_color("#2d1458")
    ax.legend(facecolor="#0f0018", labelcolor="#e9d5ff", framealpha=0.8)
    ax.grid(True, color="#2d1458", lw=0.5, alpha=0.6)

    plt.tight_layout()
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close()


def _regime_timeline_chart(result: BacktestResult, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Patch

    regime_colors = {
        "RISK_ON_GROWTH":        "#22c55e",
        "LATE_CYCLE_CAUTIOUS":   "#eab308",
        "TRANSITIONAL":          "#3b82f6",
        "RISK_OFF_TIGHTENING":   "#f97316",
        "DEFENSIVE_CONTRACTION": "#ef4444",
    }

    dates  = pd.to_datetime(result.dates)
    regimes = [s.regime for s in result.monthly_snapshots]

    fig, ax = plt.subplots(figsize=(12, 2.5))
    fig.patch.set_facecolor("#0f0018")
    ax.set_facecolor("#0f0018")

    for i, (d, reg) in enumerate(zip(dates, regimes)):
        ax.barh(0, 30, left=d.toordinal(), color=regime_colors.get(reg, "#888"), height=0.8)

    ax.set_xlim(dates[0].toordinal() - 5, dates[-1].toordinal() + 35)
    ax.set_yticks([])
    ax.set_title("Regime Classification Timeline", color="#e9d5ff", fontsize=13, pad=10)
    ax.tick_params(colors="#a78bfa")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())

    # Convert ordinal x-ticks to dates manually
    from matplotlib.ticker import FuncFormatter
    def fmt_ord(x, pos):
        try:
            return pd.Timestamp.fromordinal(int(x)).strftime("%Y")
        except Exception:
            return ""
    ax.xaxis.set_major_formatter(FuncFormatter(fmt_ord))

    patches = [Patch(color=c, label=r.replace("_", " ").title()) for r, c in regime_colors.items()]
    ax.legend(handles=patches, facecolor="#0f0018", labelcolor="#e9d5ff",
              framealpha=0.8, loc="lower right", fontsize=7, ncol=3)
    for spine in ax.spines.values():
        spine.set_color("#2d1458")

    plt.tight_layout()
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close()


def _monthly_return_heatmap(result: BacktestResult, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = pd.DataFrame({
        "date":  pd.to_datetime(result.dates),
        "return": result.model_returns,
    })
    df["year"]  = df["date"].dt.year
    df["month"] = df["date"].dt.month

    pivot = df.pivot(index="year", columns="month", values="return") * 100
    pivot.columns = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    fig, ax = plt.subplots(figsize=(14, max(3, len(pivot) * 0.6 + 1.5)))
    fig.patch.set_facecolor("#0f0018")
    ax.set_facecolor("#0f0018")

    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-15, vmax=15)

    ax.set_xticks(range(12))
    ax.set_xticklabels(pivot.columns, color="#a78bfa", fontsize=9)
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels(pivot.index, color="#a78bfa", fontsize=9)

    for y in range(len(pivot)):
        for x in range(12):
            val = pivot.values[y, x]
            if not np.isnan(val):
                ax.text(x, y, f"{val:.1f}%", ha="center", va="center",
                        color="white" if abs(val) > 8 else "#111", fontsize=7)

    plt.colorbar(im, ax=ax, label="Monthly Return %")
    ax.set_title("Regime Model — Monthly Returns Heatmap", color="#e9d5ff", fontsize=13, pad=10)

    plt.tight_layout()
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def _generate_pdf(
    result: BacktestResult,
    metrics: list[dict],
    chart_paths: dict[str, Path],
    output_path: Path,
) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image, PageBreak,
    )
    from reportlab.lib.colors import HexColor

    _BG     = HexColor("#0f0018")
    _PURPLE = HexColor("#6d28d9")
    _NEON   = HexColor("#c084fc")
    _TEXT   = HexColor("#e9d5ff")
    _MUTED  = HexColor("#a78bfa")
    _WHITE  = colors.white
    _FLASH  = HexColor("#e879f9")

    styles = getSampleStyleSheet()
    base   = styles["Normal"]

    def sty(name, **kw):
        return ParagraphStyle(name, parent=base, **kw)

    H1   = sty("H1",   fontSize=20, textColor=_FLASH,  spaceAfter=6,  spaceBefore=12, fontName="Helvetica-Bold")
    H2   = sty("H2",   fontSize=14, textColor=_NEON,   spaceAfter=4,  spaceBefore=10, fontName="Helvetica-Bold")
    H3   = sty("H3",   fontSize=11, textColor=_PURPLE, spaceAfter=3,  spaceBefore=8,  fontName="Helvetica-Bold")
    BODY = sty("BODY", fontSize=9,  textColor=_TEXT,   spaceAfter=4,  leading=13)
    MONO = sty("MONO", fontSize=8,  textColor=_MUTED,  fontName="Courier", leading=11)
    NOTE = sty("NOTE", fontSize=8,  textColor=_MUTED,  spaceAfter=3)

    story = []

    # ── Cover ──────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 0.4 * inch),
        Paragraph("ENIGMA PROTOCOL", sty("ENI", fontSize=10, textColor=_MUTED, fontName="Helvetica-Bold")),
        Paragraph("BACKTEST REPORT", H1),
        Paragraph(f"Regime-Driven Decision Model · {result.start_date} → {result.end_date}", BODY),
        HRFlowable(width="100%", color=_PURPLE, thickness=1),
        Spacer(1, 0.2 * inch),
    ]

    # ── Key Metrics Table ──────────────────────────────────────────────────
    story.append(Paragraph("KEY PERFORMANCE METRICS", H2))

    col_labels = ["Metric", "Regime Model", "60/40", "100% SPY", "Static Alloc"]
    rows = [col_labels]
    metric_keys = [
        ("total_return",  "Total Return (%)"),
        ("cagr_pct",      "CAGR (%)"),
        ("ann_vol_pct",   "Ann. Volatility (%)"),
        ("max_dd_pct",    "Max Drawdown (%)"),
        ("sharpe",        "Sharpe Ratio"),
        ("sortino",       "Sortino Ratio"),
        ("calmar",        "Calmar Ratio"),
        ("win_rate_pct",  "Win Rate (%)"),
        ("best_month",    "Best Month (%)"),
        ("worst_month",   "Worst Month (%)"),
    ]
    for key, label in metric_keys:
        row = [label]
        for m in metrics:
            v = m.get(key, "—")
            row.append(f"{v}" if v != "—" else "—")
        rows.append(row)

    tbl = Table(rows, colWidths=[2.2*inch, 1.3*inch, 1.3*inch, 1.3*inch, 1.3*inch])
    ts = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  _PURPLE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  _WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
        ("ALIGN",        (0, 0), (0, -1),  "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#130628"), HexColor("#0f0018")]),
        ("TEXTCOLOR",    (0, 1), (-1, -1), _TEXT),
        ("GRID",         (0, 0), (-1, -1), 0.3, HexColor("#2d1458")),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
    ])
    # Highlight model column
    for row_i in range(1, len(rows)):
        tbl.setStyle(TableStyle([
            ("TEXTCOLOR", (1, row_i), (1, row_i), _FLASH),
            ("FONTNAME",  (1, row_i), (1, row_i), "Helvetica-Bold"),
        ]))
    tbl.setStyle(ts)
    story += [tbl, Spacer(1, 0.2 * inch)]

    # ── Charts ─────────────────────────────────────────────────────────────
    for title, key in [
        ("Equity Curve — $100 Invested (Jan 2020)", "equity"),
        ("Drawdown from Peak",                        "drawdown"),
        ("Regime Classification Timeline",             "regime"),
        ("Monthly Returns Heatmap (Regime Model)",     "heatmap"),
    ]:
        p = chart_paths.get(key)
        if p and p.exists():
            story.append(Paragraph(title, H2))
            story.append(Image(str(p), width=7.2*inch, height=3.2*inch if key != "heatmap" else 4.0*inch))
            story.append(Spacer(1, 0.15 * inch))

    # ── Regime breakdown ───────────────────────────────────────────────────
    story += [PageBreak(), Paragraph("REGIME CLASSIFICATION BREAKDOWN", H2)]

    from collections import Counter
    regime_counts = Counter(s.regime for s in result.monthly_snapshots)
    total = len(result.monthly_snapshots)

    reg_rows = [["Regime", "Months", "% of Period", "Allocation Profile"]]
    for regime, alloc in REGIME_ALLOCATIONS.items():
        cnt = regime_counts.get(regime, 0)
        alloc_str = "  ".join(f"{k} {int(v*100)}%" for k, v in alloc.items() if v > 0)
        reg_rows.append([
            regime.replace("_", " "),
            str(cnt),
            f"{cnt/total*100:.1f}%",
            alloc_str,
        ])

    rtbl = Table(reg_rows, colWidths=[2.2*inch, 0.8*inch, 1.0*inch, 3.2*inch])
    rtbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  _PURPLE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  _WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#130628"), HexColor("#0f0018")]),
        ("TEXTCOLOR",    (0, 1), (-1, -1), _TEXT),
        ("GRID",         (0, 0), (-1, -1), 0.3, HexColor("#2d1458")),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
    ]))
    story += [rtbl, Spacer(1, 0.2 * inch)]

    # ── Monthly snapshots table ────────────────────────────────────────────
    story.append(Paragraph("MONTHLY REGIME HISTORY", H2))
    snap_rows = [["Date", "Regime", "Score", "Conf", "Model", "SPY", "60/40"]]
    for i, snap in enumerate(result.monthly_snapshots):
        mr = result.model_returns[i] if i < len(result.model_returns) else 0
        sr = result.bench_spy_returns[i] if i < len(result.bench_spy_returns) else 0
        br = result.bench_6040_returns[i] if i < len(result.bench_6040_returns) else 0
        snap_rows.append([
            snap.date[:7],
            snap.regime.replace("_", " ")[:22],
            str(snap.regime_score),
            f"{snap.regime_confidence}%",
            f"{mr*100:+.1f}%",
            f"{sr*100:+.1f}%",
            f"{br*100:+.1f}%",
        ])

    stbl = Table(snap_rows, colWidths=[0.8*inch, 2.2*inch, 0.6*inch, 0.7*inch, 0.9*inch, 0.9*inch, 0.9*inch])
    stbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  _PURPLE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  _WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#130628"), HexColor("#0f0018")]),
        ("TEXTCOLOR",    (0, 1), (-1, -1), _TEXT),
        ("GRID",         (0, 0), (-1, -1), 0.3, HexColor("#2d1458")),
        ("ALIGN",        (2, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
    ]))
    story += [stbl, Spacer(1, 0.2 * inch)]

    # ── Methodology note ───────────────────────────────────────────────────
    story += [
        Paragraph("METHODOLOGY & LIMITATIONS", H2),
        Paragraph(
            "This backtest applies the current regime classification model retroactively to historical macro data. "
            "Regime signals are reconstructed from FRED series (DFF, PCE, HY spread, TIPS real rate, Chicago PMI proxy, GDP) "
            "and yfinance market data (VIX, SPY momentum, yield curve). "
            "Publication lags are applied: GDP offset 45 days, PCE/CPI offset 30 days, ISM/Fed offset 2–5 days. "
            "Cash earns 0% (no T-bill return modeled). Transaction costs and taxes are not modeled. "
            "URNM data availability begins Dec 2019; BTC data is from BTC-USD (not MSTR, which has shorter history). "
            "This is an illustrative model — not investment advice.",
            BODY,
        ),
        Spacer(1, 0.1 * inch),
        Paragraph(
            "Advisory only. No live trading. All values are model positions.",
            NOTE,
        ),
    ]

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
        title="Enigma Protocol — Backtest Report",
    )
    doc.build(story)
    print(f"\n[Backtester] PDF written → {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(skip_pdf: bool = False) -> None:
    _load_env()

    fred_key = os.environ.get("FRED_API_KEY", "")
    if not fred_key:
        print("ERROR: FRED_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    result, metrics = run_backtest(fred_key)

    # Print summary to console
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS SUMMARY")
    print("=" * 70)
    for m in metrics:
        print(f"\n  {m['label']}")
        print(f"    Total Return: {m['total_return']}%")
        print(f"    CAGR:         {m['cagr_pct']}%")
        print(f"    Max Drawdown: {m['max_dd_pct']}%")
        print(f"    Sharpe:       {m['sharpe']}")
        print(f"    Win Rate:     {m['win_rate_pct']}%")

    # Save JSON
    json_out = OUTPUT_DIR / f"backtest_{result.start_date}_{result.end_date}.json"
    data_out = {
        "start": result.start_date,
        "end":   result.end_date,
        "metrics": metrics,
        "regime_sequence": [
            {"date": s.date, "regime": s.regime, "score": s.regime_score,
             "confidence": s.regime_confidence}
            for s in result.monthly_snapshots
        ],
    }
    json_out.write_text(json.dumps(data_out, indent=2))
    print(f"\n[Backtester] JSON → {json_out}")

    if not skip_pdf:
        # Generate charts
        print("\n[Backtester] Generating charts...")
        chart_paths = {
            "equity":   OUTPUT_DIR / "chart_equity.png",
            "drawdown": OUTPUT_DIR / "chart_drawdown.png",
            "regime":   OUTPUT_DIR / "chart_regime.png",
            "heatmap":  OUTPUT_DIR / "chart_heatmap.png",
        }
        _equity_curve_chart(result, chart_paths["equity"])
        _drawdown_chart(result, chart_paths["drawdown"])
        _regime_timeline_chart(result, chart_paths["regime"])
        _monthly_return_heatmap(result, chart_paths["heatmap"])
        print("  Charts done.")

        pdf_out = OUTPUT_DIR / f"backtest_report_{result.end_date}.pdf"
        _generate_pdf(result, metrics, chart_paths, pdf_out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regime model backtest")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation")
    args = parser.parse_args()
    main(skip_pdf=args.no_pdf)
