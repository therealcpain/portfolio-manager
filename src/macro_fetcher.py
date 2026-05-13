"""
macro_fetcher.py — Fully automated macro + market data fetcher.

Pulls real data from yfinance, BLS (no key), and FRED (optional key).
Writes a populated macro_snapshot.yaml so the daily loop has no manual fields.

Usage:
    from macro_fetcher import fetch_and_write_macro_snapshot
    snapshot = fetch_and_write_macro_snapshot()

    # or as a script
    python src/macro_fetcher.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

OUTPUT_PATH = ROOT_DIR / "data" / "manual_inputs" / "macro_snapshot.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_env() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Market data — yfinance
# ---------------------------------------------------------------------------

_YF_MAP = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "GLD": "GLD",
    "MSTR": "MSTR",
    "NVDA": "NVDA",
    "COIN": "COIN",
    "IBIT": "IBIT",
    "URNM": "URNM",
    "TLT": "TLT",
    "HYG": "HYG",
    "LQD": "LQD",
    "AGG": "AGG",
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
    "US10Y": "^TNX",
    "US2Y": "^IRX",
    "US5Y": "^FVX",
    "US30Y": "^TYX",
    "GC_FUTURES": "GC=F",
}


def _fetch_yfinance() -> dict:
    import yfinance as yf
    from datetime import date, timedelta

    today = date.today()
    start_ytd = today.replace(month=1, day=1)
    start_20d = today - timedelta(days=30)
    start_5d  = today - timedelta(days=8)

    prices, r1, r5, r20, ytd_ret = {}, {}, {}, {}, {}

    for name, sym in _YF_MAP.items():
        try:
            ticker = yf.Ticker(sym)
            fast = ticker.fast_info
            prices[name] = round(float(fast.last_price), 4)

            hist = ticker.history(start=start_ytd, end=today + timedelta(days=1), interval="1d")["Close"]
            hist = hist.dropna()
            if len(hist) >= 2:
                r1[name]     = round((hist.iloc[-1] / hist.iloc[-2] - 1) * 100, 2)
                ytd_ret[name] = round((hist.iloc[-1] / hist.iloc[0] - 1) * 100, 2)
            hist_5d = hist[hist.index >= str(start_5d)]
            if len(hist_5d) >= 2:
                r5[name] = round((hist_5d.iloc[-1] / hist_5d.iloc[0] - 1) * 100, 2)
            hist_20d = hist[hist.index >= str(start_20d)]
            if len(hist_20d) >= 2:
                r20[name] = round((hist_20d.iloc[-1] / hist_20d.iloc[0] - 1) * 100, 2)
        except Exception:
            prices.setdefault(name, None)

    return {
        "prices": prices,
        "returns_1d": r1,
        "returns_5d": r5,
        "returns_20d": r20,
        "returns_ytd": ytd_ret,
    }


# ---------------------------------------------------------------------------
# BLS public API — CPI and unemployment (no key required)
# ---------------------------------------------------------------------------

def _bls_series(series_id: str, years: int = 2) -> list[dict]:
    today = date.today()
    payload = json.dumps({
        "seriesid": [series_id],
        "startyear": str(today.year - years),
        "endyear": str(today.year),
    }).encode()
    req = urllib.request.Request(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        data=payload,
        headers={"Content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    rows = data["Results"]["series"][0]["data"]
    return [row for row in rows if row.get("value", "-") != "-"]


def _yoy(rows: list[dict]) -> Optional[float]:
    if len(rows) < 13:
        return None
    curr = float(rows[0]["value"])
    prev = float(rows[12]["value"])
    return round((curr / prev - 1) * 100, 2)


def _fetch_bls() -> dict:
    result = {}
    try:
        cpi = _bls_series("CUUR0000SA0")
        result["cpi_yoy_pct"] = _yoy(cpi)
        result["cpi_latest_index"] = float(cpi[0]["value"]) if cpi else None
        result["cpi_period"] = f"{cpi[0]['periodName']} {cpi[0]['year']}" if cpi else None
    except Exception:
        result["cpi_yoy_pct"] = None

    try:
        core = _bls_series("CUUR0000SA0L1E")
        result["core_cpi_yoy_pct"] = _yoy(core)
    except Exception:
        result["core_cpi_yoy_pct"] = None

    try:
        unemp = _bls_series("LNS14000000", years=1)
        result["unemployment_rate"] = float(unemp[0]["value"]) if unemp else None
        result["unemployment_period"] = f"{unemp[0]['periodName']} {unemp[0]['year']}" if unemp else None
    except Exception:
        result["unemployment_rate"] = None

    return result


# ---------------------------------------------------------------------------
# FRED — deep macro (optional key)
# ---------------------------------------------------------------------------

def _fetch_fred(api_key: str) -> dict:
    from fredapi import Fred
    fred = Fred(api_key=api_key)
    result = {}

    def get(series_id, idx=-1, divisor=1, decimals=2):
        s = fred.get_series(series_id)
        s = s.dropna()
        return round(float(s.iloc[idx]) / divisor, decimals)

    # Fed funds effective rate (daily series more current than monthly FEDFUNDS)
    result["fed_funds_rate"] = _safe(lambda: get("DFF"))

    # PCE inflation YoY
    try:
        pce = fred.get_series("PCEPI").dropna()
        if len(pce) >= 13:
            result["pce_yoy_pct"] = round((float(pce.iloc[-1]) / float(pce.iloc[-13]) - 1) * 100, 2)
    except Exception:
        result["pce_yoy_pct"] = None

    # M2 money supply (billions)
    result["m2_billions"] = _safe(lambda: get("M2SL"))

    # M2 YoY growth
    try:
        m2 = fred.get_series("M2SL").dropna()
        if len(m2) >= 13:
            result["m2_yoy_pct"] = round((float(m2.iloc[-1]) / float(m2.iloc[-13]) - 1) * 100, 2)
    except Exception:
        result["m2_yoy_pct"] = None

    # Fed balance sheet (billions)
    result["fed_balance_sheet_b"] = _safe(lambda: round(get("WALCL") / 1000, 1))

    # Real GDP growth (annualized QoQ)
    result["gdp_real_qoq_pct"] = _safe(lambda: get("A191RL1Q225SBEA"))

    # 10Y TIPS real yield
    result["real_rate_10y_tips"] = _safe(lambda: get("DFII10"))

    # ISM Manufacturing PMI (FRED doesn't carry ISM directly; use Chicago PMI as proxy)
    result["ism_manufacturing"] = _safe(lambda: get("CPMI"))

    # ISM Services — no direct FRED series; leave None and note
    result["ism_services"] = None

    # HY credit spread (option-adjusted, bps)
    result["hy_credit_spread_bps"] = _safe(lambda: round(get("BAMLH0A0HYM2") * 100, 0))

    # IG credit spread
    result["ig_credit_spread_bps"] = _safe(lambda: round(get("BAMLC0A0CM") * 100, 0))

    # Reverse repo balance (billions)
    result["rrp_balance_b"] = _safe(lambda: round(get("RRPONTSYD") / 1000, 1))

    return result


# ---------------------------------------------------------------------------
# Regime auto-classification — derived from fetched data
# ---------------------------------------------------------------------------

def _auto_classify_regime(mkt: dict, bls: dict, fred_data: dict) -> dict:
    prices = mkt.get("prices", {})
    r20    = mkt.get("returns_20d", {})

    vix  = prices.get("VIX", 20)
    spy_20d = r20.get("SPY", 0)
    btc_20d = r20.get("BTC", 0)
    dxy_ytd = mkt.get("returns_ytd", {}).get("DXY", 0)

    fed_funds   = fred_data.get("fed_funds_rate") or 4.5
    us10y       = prices.get("US10Y", 4.5)
    us2y        = prices.get("US2Y", 4.0)
    yield_spread = round(us10y - us2y, 2)
    cpi_yoy     = bls.get("cpi_yoy_pct") or 3.0
    core_cpi    = bls.get("core_cpi_yoy_pct") or 3.0
    unemp       = bls.get("unemployment_rate") or 4.0
    ism_mfg     = fred_data.get("ism_manufacturing") or 50
    hy_spread   = fred_data.get("hy_credit_spread_bps") or 350
    pce_yoy     = fred_data.get("pce_yoy_pct") or 3.0
    gdp         = fred_data.get("gdp_real_qoq_pct") or 2.0

    signals = []
    score   = 0  # positive = risk-on / growth, negative = risk-off / contraction

    # Growth signals
    if gdp >= 2.5:
        signals.append(f"GDP +{gdp}% — solid growth")
        score += 2
    elif gdp >= 0:
        signals.append(f"GDP +{gdp}% — soft landing territory")
        score += 1
    else:
        signals.append(f"GDP {gdp}% — contraction risk")
        score -= 2

    if ism_mfg and ism_mfg >= 50:
        signals.append(f"ISM Mfg {ism_mfg} — expansion")
        score += 1
    elif ism_mfg and ism_mfg < 50:
        signals.append(f"ISM Mfg {ism_mfg} — contraction")
        score -= 1

    # Inflation signals
    if core_cpi > 3.5:
        signals.append(f"Core CPI {core_cpi}% — above target, Fed constrained")
        score -= 1
    elif core_cpi < 2.5:
        signals.append(f"Core CPI {core_cpi}% — near target, Fed flexibility")
        score += 1
    else:
        signals.append(f"Core CPI {core_cpi}% — moderating")

    # Liquidity / rates
    if yield_spread > 0:
        signals.append(f"Yield curve {yield_spread:+.2f}% — normal (10Y > 2Y)")
        score += 1
    else:
        signals.append(f"Yield curve {yield_spread:+.2f}% — inverted")
        score -= 1

    if fed_funds > 4.0:
        signals.append(f"Fed funds {fed_funds}% — restrictive")
        score -= 1
    else:
        signals.append(f"Fed funds {fed_funds}% — moderating")
        score += 1

    # Risk appetite
    if vix < 15:
        signals.append(f"VIX {vix} — complacency / risk-on")
        score += 1
    elif vix > 25:
        signals.append(f"VIX {vix} — elevated fear")
        score -= 2
    else:
        signals.append(f"VIX {vix} — moderate")

    if hy_spread and hy_spread < 300:
        signals.append(f"HY spread {hy_spread}bps — tight, credit bullish")
        score += 1
    elif hy_spread and hy_spread > 500:
        signals.append(f"HY spread {hy_spread}bps — wide, stress signal")
        score -= 2

    # Market momentum
    if spy_20d > 3:
        signals.append(f"SPY +{spy_20d}% (20d) — bullish momentum")
        score += 1
    elif spy_20d < -5:
        signals.append(f"SPY {spy_20d}% (20d) — distribution")
        score -= 1

    # Determine regime label
    if score >= 5:
        regime = "RISK_ON_GROWTH"
        confidence = min(90, 60 + score * 3)
        rationale = f"Strong multi-factor bullish alignment. Score {score}/10."
    elif score >= 2:
        regime = "LATE_CYCLE_CAUTIOUS"
        confidence = min(75, 50 + score * 3)
        rationale = f"Growth intact but inflation and rates are headwinds. Score {score}/10."
    elif score >= 0:
        regime = "TRANSITIONAL"
        confidence = 45
        rationale = f"Mixed signals — data inconclusive. Score {score}/10."
    elif score >= -3:
        regime = "RISK_OFF_TIGHTENING"
        confidence = min(75, 50 + abs(score) * 3)
        rationale = f"Restrictive conditions dominating. Score {score}/10."
    else:
        regime = "DEFENSIVE_CONTRACTION"
        confidence = min(85, 55 + abs(score) * 3)
        rationale = f"Multiple contraction signals. Score {score}/10."

    return {
        "regime": regime,
        "confidence": int(confidence),
        "rationale": rationale,
        "signals": signals,
        "raw_score": score,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

@dataclass
class MacroSnapshot:
    as_of_date: str
    source: str

    # Market
    prices: dict = field(default_factory=dict)
    returns_1d: dict = field(default_factory=dict)
    returns_5d: dict = field(default_factory=dict)
    returns_20d: dict = field(default_factory=dict)
    returns_ytd: dict = field(default_factory=dict)

    # Rates
    us_10y_yield: Optional[float] = None
    us_2y_yield: Optional[float] = None
    us_5y_yield: Optional[float] = None
    us_30y_yield: Optional[float] = None
    yield_curve_2_10: Optional[float] = None
    real_rate_10y_tips: Optional[float] = None

    # Fed
    fed_funds_rate: Optional[float] = None
    fed_balance_sheet_b: Optional[float] = None

    # Inflation
    cpi_yoy_pct: Optional[float] = None
    core_cpi_yoy_pct: Optional[float] = None
    pce_yoy_pct: Optional[float] = None
    cpi_period: Optional[str] = None

    # Growth
    gdp_real_qoq_pct: Optional[float] = None
    ism_manufacturing: Optional[float] = None
    ism_services: Optional[float] = None

    # Employment
    unemployment_rate: Optional[float] = None
    unemployment_period: Optional[str] = None

    # Liquidity
    m2_billions: Optional[float] = None
    m2_yoy_pct: Optional[float] = None
    rrp_balance_b: Optional[float] = None

    # Credit
    hy_credit_spread_bps: Optional[float] = None
    ig_credit_spread_bps: Optional[float] = None

    # Regime (auto-classified)
    regime: Optional[str] = None
    regime_confidence: int = 0
    regime_rationale: Optional[str] = None
    regime_signals: list = field(default_factory=list)


def fetch_macro_snapshot(write: bool = True) -> MacroSnapshot:
    """
    Fetch all available macro data and return a MacroSnapshot.
    Writes macro_snapshot.yaml if write=True.
    """
    _load_env()

    today_str = date.today().isoformat()
    sources = []

    print("  Fetching market prices (yfinance)...")
    mkt = _safe(_fetch_yfinance, {"prices": {}, "returns_1d": {}, "returns_5d": {}, "returns_20d": {}, "returns_ytd": {}})
    sources.append("yfinance")

    print("  Fetching CPI and unemployment (BLS)...")
    bls = _safe(_fetch_bls, {})
    if bls:
        sources.append("BLS")

    fred_data = {}
    fred_key = os.environ.get("FRED_API_KEY", "")
    if fred_key:
        print("  Fetching macro indicators (FRED)...")
        fred_data = _safe(lambda: _fetch_fred(fred_key), {})
        if fred_data:
            sources.append("FRED")

    print("  Auto-classifying regime...")
    regime = _auto_classify_regime(mkt, bls, fred_data)

    prices = mkt.get("prices", {})

    snap = MacroSnapshot(
        as_of_date=today_str,
        source=", ".join(sources),
        prices=prices,
        returns_1d=mkt.get("returns_1d", {}),
        returns_5d=mkt.get("returns_5d", {}),
        returns_20d=mkt.get("returns_20d", {}),
        returns_ytd=mkt.get("returns_ytd", {}),

        us_10y_yield=prices.get("US10Y"),
        us_2y_yield=prices.get("US2Y"),
        us_5y_yield=prices.get("US5Y"),
        us_30y_yield=prices.get("US30Y"),
        yield_curve_2_10=round(
            (prices.get("US10Y") or 0) - (prices.get("US2Y") or 0), 2
        ) if prices.get("US10Y") and prices.get("US2Y") else None,
        real_rate_10y_tips=fred_data.get("real_rate_10y_tips"),

        fed_funds_rate=fred_data.get("fed_funds_rate"),
        fed_balance_sheet_b=fred_data.get("fed_balance_sheet_b"),

        cpi_yoy_pct=bls.get("cpi_yoy_pct"),
        core_cpi_yoy_pct=bls.get("core_cpi_yoy_pct"),
        pce_yoy_pct=fred_data.get("pce_yoy_pct"),
        cpi_period=bls.get("cpi_period"),

        gdp_real_qoq_pct=fred_data.get("gdp_real_qoq_pct"),
        ism_manufacturing=fred_data.get("ism_manufacturing"),
        ism_services=fred_data.get("ism_services"),

        unemployment_rate=bls.get("unemployment_rate"),
        unemployment_period=bls.get("unemployment_period"),

        m2_billions=fred_data.get("m2_billions"),
        m2_yoy_pct=fred_data.get("m2_yoy_pct"),
        rrp_balance_b=fred_data.get("rrp_balance_b"),

        hy_credit_spread_bps=fred_data.get("hy_credit_spread_bps"),
        ig_credit_spread_bps=fred_data.get("ig_credit_spread_bps"),

        regime=regime["regime"],
        regime_confidence=regime["confidence"],
        regime_rationale=regime["rationale"],
        regime_signals=regime["signals"],
    )

    if write:
        _write_yaml(snap)

    return snap


def _write_yaml(snap: MacroSnapshot) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _f(v, suffix=""):
        if v is None:
            return "null"
        if isinstance(v, float):
            return f"{v:.2f}{suffix}"
        return str(v)

    lines = [
        f"# Auto-generated by macro_fetcher.py — {snap.as_of_date}",
        f"# Sources: {snap.source}",
        f"# Do not edit manually — re-run macro_fetcher.py to refresh",
        "",
        "metadata:",
        f"  as_of_date: \"{snap.as_of_date}\"",
        f"  source: \"{snap.source}\"",
        "",
        "fed:",
        f"  funds_rate: {_f(snap.fed_funds_rate)}",
        f"  balance_sheet_b: {_f(snap.fed_balance_sheet_b)}",
        "",
        "rates:",
        f"  us_10y_yield: {_f(snap.us_10y_yield)}",
        f"  us_2y_yield: {_f(snap.us_2y_yield)}",
        f"  us_5y_yield: {_f(snap.us_5y_yield)}",
        f"  us_30y_yield: {_f(snap.us_30y_yield)}",
        f"  yield_curve_2_10: {_f(snap.yield_curve_2_10)}",
        f"  real_rate_10y_tips: {_f(snap.real_rate_10y_tips)}",
        "",
        "inflation:",
        f"  cpi_yoy_pct: {_f(snap.cpi_yoy_pct)}",
        f"  core_cpi_yoy_pct: {_f(snap.core_cpi_yoy_pct)}",
        f"  pce_yoy_pct: {_f(snap.pce_yoy_pct)}",
        f"  cpi_period: \"{snap.cpi_period or 'unknown'}\"",
        "",
        "growth:",
        f"  gdp_real_qoq_pct: {_f(snap.gdp_real_qoq_pct)}",
        f"  ism_manufacturing: {_f(snap.ism_manufacturing)}",
        f"  ism_services: {_f(snap.ism_services)}",
        "",
        "employment:",
        f"  unemployment_rate: {_f(snap.unemployment_rate)}",
        f"  unemployment_period: \"{snap.unemployment_period or 'unknown'}\"",
        "",
        "liquidity:",
        f"  m2_billions: {_f(snap.m2_billions)}",
        f"  m2_yoy_pct: {_f(snap.m2_yoy_pct)}",
        f"  rrp_balance_b: {_f(snap.rrp_balance_b)}",
        "",
        "credit:",
        f"  hy_credit_spread_bps: {_f(snap.hy_credit_spread_bps)}",
        f"  ig_credit_spread_bps: {_f(snap.ig_credit_spread_bps)}",
        "",
        "market:",
        f"  spy_price: {_f(snap.prices.get('SPY'))}",
        f"  qqq_price: {_f(snap.prices.get('QQQ'))}",
        f"  btc_price: {_f(snap.prices.get('BTC'))}",
        f"  eth_price: {_f(snap.prices.get('ETH'))}",
        f"  gld_price: {_f(snap.prices.get('GLD'))}",
        f"  vix: {_f(snap.prices.get('VIX'))}",
        f"  dxy: {_f(snap.prices.get('DXY'))}",
        "",
        "returns_1d:",
    ]
    for k, v in snap.returns_1d.items():
        lines.append(f"  {k}: {_f(v)}")

    lines += ["", "returns_20d:"]
    for k, v in snap.returns_20d.items():
        lines.append(f"  {k}: {_f(v)}")

    lines += ["", "returns_ytd:"]
    for k, v in snap.returns_ytd.items():
        lines.append(f"  {k}: {_f(v)}")

    lines += [
        "",
        "# Auto-classified from fetched data — no manual input needed",
        "manual_regime_assessment:",
        f"  regime: \"{snap.regime}\"",
        f"  confidence: {snap.regime_confidence}",
        f"  rationale: \"{snap.regime_rationale}\"",
        "  signals:",
    ]
    for sig in snap.regime_signals:
        lines.append(f"    - \"{sig}\"")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n")
    print(f"  Written: {OUTPUT_PATH}")


if __name__ == "__main__":
    print("Fetching macro snapshot...")
    snap = fetch_macro_snapshot(write=True)
    print(f"\nRegime: {snap.regime} (confidence: {snap.regime_confidence}%)")
    print(f"Rationale: {snap.regime_rationale}")
    print(f"\nKey data points:")
    print(f"  SPY: ${snap.prices.get('SPY', 'N/A')}   BTC: ${snap.prices.get('BTC', 'N/A')}   GLD: ${snap.prices.get('GLD', 'N/A')}")
    print(f"  VIX: {snap.prices.get('VIX')}   DXY: {snap.prices.get('DXY')}")
    print(f"  10Y: {snap.us_10y_yield}%   2Y: {snap.us_2y_yield}%   Spread: {snap.yield_curve_2_10}%")
    print(f"  CPI YoY: {snap.cpi_yoy_pct}%   Core CPI: {snap.core_cpi_yoy_pct}%   PCE: {snap.pce_yoy_pct}%")
    print(f"  Unemployment: {snap.unemployment_rate}%   GDP: {snap.gdp_real_qoq_pct}%")
    print(f"  Fed Funds: {snap.fed_funds_rate}%   M2 growth: {snap.m2_yoy_pct}%")
    print(f"  HY Spread: {snap.hy_credit_spread_bps}bps")
