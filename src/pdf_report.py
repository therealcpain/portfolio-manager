"""
pdf_report.py — Portfolio-first PDF report generator.

Structure:
  1. Target allocation table (with deltas vs yesterday / 1wk / 1mo)
  2. Per-position rationale (why you own it, what changed, key risk)
  3. Dissent & challenge questions
  4. Macro context (only as it relates to the portfolio)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent

_DARK   = "#0f0018"
_ARCANE = "#130628"
_DIM    = "#2d1458"
_PURPLE = "#6d28d9"
_GLOW   = "#a855f7"
_NEON   = "#c084fc"
_FLASH  = "#e879f9"
_TEXT   = "#e9d5ff"
_MUTED  = "#a78bfa"
_WHITE  = "#f5f3ff"
_GREEN  = "#16a34a"
_RED    = "#dc2626"
_AMBER  = "#d97706"
_GRAY   = "#6b7280"
_LGRAY  = "#f3f4f6"
_MGRAY  = "#e5e7eb"


def generate_pdf(result, output_path=None) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    date_str = result.config.date or date.today().isoformat()
    if output_path is None:
        out_dir = ROOT_DIR / "reports" / "daily"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"daily_brief_{date_str}.pdf"

    doc = SimpleDocTemplate(
        str(output_path), pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.55*inch, bottomMargin=0.55*inch,
    )
    W = 7.3 * inch

    def C(h): return colors.HexColor(h)

    def sty(name, font="Helvetica", size=9, color=_DARK, leading=13,
            sb=0, sa=2, align=TA_LEFT, bold=False):
        f = f"Helvetica-Bold" if bold else font
        return ParagraphStyle(name, fontName=f, fontSize=size,
                              textColor=C(color), leading=leading,
                              spaceBefore=sb, spaceAfter=sa, alignment=align)

    S = {
        "h1":     sty("h1",  size=17, color=_WHITE,  align=TA_CENTER, leading=21, bold=True),
        "h1sub":  sty("h1s", size=8,  color=_NEON,   align=TA_CENTER),
        "sec":    sty("sec", size=10, color=_PURPLE,  bold=True, sb=10, sa=4),
        "pos":    sty("pos", size=9,  color=_DARK,    bold=True, sb=6, sa=2),
        "body":   sty("bod", size=8.5,color=_DARK,    leading=13),
        "small":  sty("sm",  size=7.5,color=_GRAY),
        "green":  sty("g",   size=8.5,color=_GREEN,   bold=True),
        "red":    sty("r",   size=8.5,color=_RED,     bold=True),
        "amber":  sty("a",   size=8.5,color=_AMBER,   bold=True),
        "regime": sty("re",  size=10, color=_FLASH,   bold=True, align=TA_CENTER),
        "disc":   sty("d",   size=7,  color=_GRAY,    align=TA_CENTER, sb=4),
        "label":  sty("lb",  size=8,  color=_DARK,    bold=True),
        "mono":   sty("mo",  font="Courier", size=8,  color=_DARK, leading=11),
        "q":      sty("q",   size=8.5,color=_PURPLE,  leading=13),
    }

    def P(t, s="body"): return Paragraph(str(t), S[s])
    def SP(h=6): return Spacer(1, h)
    def HR(c=_DIM): return HRFlowable(width="100%", thickness=0.4,
                                       color=C(c), spaceAfter=4, spaceBefore=2)
    def sec(t): return P(f"▸  {t}", "sec")

    # ── Pull data ────────────────────────────────────────────────────────────
    ingest          = getattr(result, "ingest", None)
    regime_res      = getattr(result, "regime", None)
    memos_res       = getattr(result, "memos", None)
    dissent_res     = getattr(result, "dissent", None)
    cio_res         = getattr(result, "cio_decision", None)
    org_res         = getattr(result, "org_review", None)
    regime_stab     = getattr(result, "_regime_stability", None)

    alloc_snap   = getattr(cio_res, "_allocation_snapshot", None)
    alloc_deltas = getattr(cio_res, "_allocation_deltas", [])

    # Load portfolio yaml for per-position theses
    import yaml
    portfolio_path = ROOT_DIR / "portfolio" / "current_portfolio.yaml"
    portfolio_yaml = {}
    all_positions_yaml = {}
    if portfolio_path.exists():
        portfolio_yaml = yaml.safe_load(portfolio_path.read_text()) or {}
        for bucket in ("core_structural", "tactical_strategic", "individual_equities",
                       "options_convexity", "experimental", "defensive_reserve"):
            for pos in portfolio_yaml.get(bucket, {}).get("positions", []):
                ticker = pos.get("ticker", "")
                if ticker:
                    all_positions_yaml[ticker] = pos

    # Load macro snapshot for context
    snap_path = ROOT_DIR / "data" / "manual_inputs" / "macro_snapshot.yaml"
    macro_snap = {}
    if snap_path.exists():
        raw_snap = yaml.safe_load(snap_path.read_text()) or {}
        for k in ("fed", "rates", "inflation", "growth", "employment", "liquidity", "credit"):
            macro_snap.update(raw_snap.get(k, {}))
        macro_snap["vix"]  = raw_snap.get("market", {}).get("vix")
        macro_snap["dxy"]  = raw_snap.get("market", {}).get("dxy")
        macro_snap["regime_signals"] = raw_snap.get(
            "manual_regime_assessment", {}).get("signals", [])

    # Build memo lookup by agent
    memo_lookup: dict[str, dict] = {}
    if memos_res:
        for m in memos_res.memos:
            if isinstance(m, dict):
                memo_lookup[m.get("agent", "")] = m

    # ── Header ───────────────────────────────────────────────────────────────
    regime_label = regime_res.macro_regime.replace("_", " ") if regime_res else "UNKNOWN"
    regime_conf  = regime_res.macro_confidence if regime_res else 0

    # Regime stability line
    if regime_stab:
        stab_label = regime_stab.status_label
        if regime_stab.pending_flip:
            stab_color = _AMBER
        elif regime_stab.days_at_regime >= 10:
            stab_color = _NEON
        else:
            stab_color = _MUTED
    else:
        stab_label = "Day 1"
        stab_color = _MUTED

    # Regime banner — two rows: regime name large, stability line below
    S["regime_big"] = sty("rb", size=14, color=_FLASH, bold=True, align=TA_CENTER, leading=18)
    S["regime_stab"] = sty("rs", size=8.5, color=stab_color, align=TA_CENTER, leading=12)

    hdr_data = [
        [P("PORTFOLIO BRIEF", "h1")],
        [P(f"<b>{regime_label}</b>  ·  {regime_conf}% confidence", "regime_big")],
        [P(stab_label, "regime_stab")],
        [P(f"{date_str}", "h1sub")],
    ]
    hdr = Table(hdr_data, colWidths=[W])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), C(_DARK)),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
        ("RIGHTPADDING",  (0,0),(-1,-1), 14),
    ]))

    story = [hdr, SP(12)]

    # ── Section 1: Target Allocation ─────────────────────────────────────────
    story.append(sec("TARGET ALLOCATION"))

    if alloc_deltas:
        action_colors = {
            "ADD":      _GREEN, "INITIATE": _GREEN, "RAISE": _GREEN,
            "TRIM":     _RED,   "EXIT":     _RED,   "REDUCE": _RED,
            "HOLD":     _DARK,
        }
        # Header row — white text on solid purple for readability
        hdr_cells = ["POSITION", "TARGET %", "vs 1d", "vs 1wk", "vs 1mo", "ACTION", "CONF"]
        rows = [[Paragraph(f"<b>{h}</b>", ParagraphStyle(
            f"th{i}", fontName="Helvetica-Bold", fontSize=8.5,
            textColor=colors.white, leading=11,
        )) for i, h in enumerate(hdr_cells)]]

        def fmt_delta(v):
            if v is None or abs(v) < 0.5: return P("—", "small")
            s = f"+{v:.1f}pp" if v > 0 else f"{v:.1f}pp"
            return P(s, "green" if v > 0 else "red")

        _REBALANCE_THRESHOLD_PCT = 5.0  # only flag action if drift exceeds this

        for d in alloc_deltas:
            action = d.action.upper()
            # Suppress action if all deltas are within tolerance (no drift data yet is OK)
            max_drift = max(
                abs(v) for v in [d.delta_1d, d.delta_1w, d.delta_1m] if v is not None
            ) if any(v is not None for v in [d.delta_1d, d.delta_1w, d.delta_1m]) else 0
            if action not in ("EXIT", "INITIATE") and max_drift < _REBALANCE_THRESHOLD_PCT and action not in ("ADD", "TRIM", "RAISE", "REDUCE"):
                display_action = "HOLD"
                act_style = "body"
            elif action not in ("EXIT", "INITIATE") and max_drift < _REBALANCE_THRESHOLD_PCT and action in ("ADD", "TRIM", "RAISE", "REDUCE"):
                display_action = f"HOLD*"   # CIO wanted action but drift < 5% threshold
                act_style = "small"
            else:
                display_action = action
                act_style = ("green" if action in ("ADD","INITIATE","RAISE")
                             else "red" if action in ("TRIM","EXIT","REDUCE") else "body")
            # Normalize cash label
            label = "CASH / STRC" if d.ticker in ("CASH", "STRC") else d.ticker
            rows.append([
                P(f"<b>{label}</b>", "body"),
                P(f"<b>{d.current_pct:.0f}%</b>", "body"),
                fmt_delta(d.delta_1d),
                fmt_delta(d.delta_1w),
                fmt_delta(d.delta_1m),
                P(display_action, act_style),
                P(f"{d.confidence}%" if d.confidence else "—", "small"),
            ])

        # Options row — always shown explicitly
        rows.append([
            P("OPTIONS", "small"),
            P("0%", "small"),
            P("—", "small"), P("—", "small"), P("—", "small"),
            P("NONE", "small"),
            P("—", "small"),
        ])

        col_w = [1.25*inch, 0.8*inch, 0.75*inch, 0.75*inch, 0.75*inch, 0.85*inch, 0.6*inch]
        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  C(_PURPLE)),   # solid purple header
            ("ROWBACKGROUNDS",(0,1),(-1,-2), [C(_WHITE), C(_LGRAY)]),
            ("BACKGROUND",    (0,-1),(-1,-1), C(_MGRAY)),   # options row greyed
            ("GRID",          (0,0),(-1,-1), 0.3, C(_MGRAY)),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 7),
            ("FONTSIZE",      (0,0),(-1,-1), 8.5),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        story += [t, SP(4)]

        # Legend
        story.append(P(
            "ADD = increase  ·  TRIM = reduce  ·  HOLD = no change  ·  "
            "EXIT = close position  ·  INITIATE = new  ·  HOLD* = CIO wanted action but drift <5% (within tolerance)  ·  "
            "pp = percentage points vs prior period",
            "small"
        ))
        story.append(SP(4))

        # Overall confidence
        conf = alloc_snap.overall_confidence if alloc_snap else 0
        conf_style = "green" if conf >= 70 else ("amber" if conf >= 50 else "red")
        story.append(P(f"Portfolio confidence: {conf}/100", conf_style))

    else:
        story.append(P("No allocation parsed from CIO output — run with mock=False.", "small"))

    story += [SP(8), HR()]

    # ── Section 2: Per-position rationale ────────────────────────────────────
    story.append(sec("WHY YOU OWN WHAT YOU OWN"))

    positions_to_show = alloc_deltas if alloc_deltas else []

    for d in positions_to_show:
        if d.ticker in ("CASH", "STRC"):
            continue

        # Get thesis from CIO raw text or portfolio yaml
        yaml_pos = all_positions_yaml.get(d.ticker, {})
        thesis   = yaml_pos.get("thesis", "")
        inv_cond = yaml_pos.get("invalidation", "")

        # Find specialist memos relevant to this ticker
        relevant_memos = []
        for agent, m in memo_lookup.items():
            pts = m.get("key_points", [])
            rec = m.get("recommendation", "")
            combined = " ".join(pts) + " " + rec
            if d.ticker.upper() in combined.upper():
                relevant_memos.append((agent, m.get("stance", "hold"), rec))

        # Build position block
        pos_items = [
            P(f"<b>{d.ticker}</b>  ·  {d.current_pct:.0f}% target  ·  {d.action}  ·  {d.confidence or '?'}% confidence", "pos"),
        ]
        if d.reason:
            pos_items.append(P(d.reason, "body"))
        if thesis:
            pos_items.append(P(f"Thesis: {thesis}", "body"))

        # Macro relevance for this position
        macro_relevance = _macro_relevance(d.ticker, macro_snap, regime_res)
        if macro_relevance:
            pos_items.append(P(f"Macro fit: {macro_relevance}", "body"))

        if inv_cond:
            pos_items.append(P(f"Invalidation: {inv_cond}", "small"))

        if relevant_memos:
            specialist_str = "  ·  ".join(
                f"{a.replace('_',' ').title()}: {s}" for a, s, _ in relevant_memos[:3]
            )
            pos_items.append(P(f"Specialists: {specialist_str}", "small"))

        pos_items.append(SP(4))
        story.append(KeepTogether(pos_items))

    # Cash / STRC rationale
    cash_delta = next((d for d in alloc_deltas if d.ticker in ("CASH","STRC")), None)
    if cash_delta:
        story.append(KeepTogether([
            P(f"<b>CASH / STRC</b>  ·  {cash_delta.current_pct:.0f}% target  ·  {cash_delta.action}", "pos"),
            P(f"Held in STRC or money market equivalent, earning yield while awaiting high-conviction deployment. "
              f"{'Reason: ' + cash_delta.reason if cash_delta.reason else 'Dry powder — no current high-conviction opportunity warrants full deployment.'}", "body"),
            SP(4),
        ]))

    # Options callout — always explicit
    story.append(KeepTogether([
        P("<b>OPTIONS / CONVEXITY</b>  ·  0% currently", "pos"),
        P("No options positions active. Options are reserved for asymmetric setups where the risk/reward "
          "justifies the premium decay. Current volatility environment does not present a compelling entry. "
          "Will revisit if VIX compresses further or a catalyst creates a defined-risk asymmetric trade.", "body"),
        SP(4),
    ]))

    story += [SP(4), HR()]

    # ── Bear case / contrarian view ───────────────────────────────────────────
    story.append(sec("IF THE BEARS ARE RIGHT"))

    bear_memo = memo_lookup.get("bear_case_analyst", {})
    risk_memo  = memo_lookup.get("risk_officer", {})

    bear_pts  = bear_memo.get("key_points", [])
    bear_rec  = bear_memo.get("recommendation", "")
    risk_pts  = risk_memo.get("key_points", [])

    if bear_pts or risk_pts:
        story.append(P(
            "The following represents the contrarian allocation the bear case analyst would recommend "
            "if their thesis is correct. It is not the CIO recommendation — it is the stress-test view "
            "you should hold in your head as a check on conviction.", "body"
        ))
        story.append(SP(4))
        if bear_pts:
            story.append(P("<b>Bear case analyst argues:</b>", "label"))
            for pt in bear_pts[:4]:
                story.append(P(f"  • {pt}", "body"))
        if bear_rec:
            story.append(SP(3))
            story.append(P(f"<b>Contrarian recommendation:</b> {bear_rec}", "body"))
        if risk_pts:
            story.append(SP(4))
            story.append(P("<b>Risk officer flags:</b>", "label"))
            for pt in risk_pts[:3]:
                story.append(P(f"  • {pt}", "body"))
    else:
        story.append(P(
            "Bear case memo not available in this run. In live mode, the bear_case_analyst "
            "and risk_officer specialists provide the contrarian stress-test view — what the portfolio "
            "should look like if the dominant thesis is wrong (more cash, less beta, gold over equities).",
            "body"
        ))

    story += [SP(6), HR()]

    # ── Section 3: What changed ───────────────────────────────────────────────
    changes = [d for d in alloc_deltas if d.delta_1d and abs(d.delta_1d) >= 0.5]
    if changes:
        story.append(sec("WHAT CHANGED TODAY"))
        for d in changes:
            direction = "increased" if d.delta_1d > 0 else "reduced"
            story.append(P(
                f"<b>{d.ticker}</b>: {direction} {abs(d.delta_1d):.1f}pp to {d.current_pct:.0f}% — {d.reason}",
                "body"
            ))
        story += [SP(6), HR()]

    # ── Section 4: CIO challenge questions ────────────────────────────────────
    if cio_res and cio_res.challenge_questions:
        story.append(sec("QUESTIONS FOR YOU"))
        for q in cio_res.challenge_questions:
            story.append(P(f"? {q}", "q"))
            story.append(SP(3))
        story += [SP(4), HR()]

    # ── Section 5: Dissent ────────────────────────────────────────────────────
    if dissent_res and (dissent_res.groupthink_alert or dissent_res.dissent_suppressed):
        story.append(sec("DISSENT FLAGS"))
        if dissent_res.groupthink_alert:
            story.append(P(f"⚠ Groupthink alert: {dissent_res.groupthink_reason or 'High consensus'}", "red"))
        if dissent_res.dissent_suppressed:
            story.append(P("⚠ Dissent suppressed — fewer than 2 dissenting voices recorded.", "amber"))
        story += [SP(4), HR()]

    # ── Section 6: Macro context (portfolio-relevant only) ───────────────────
    story.append(sec("MACRO CONTEXT"))
    story.append(P(
        f"Regime: <b>{regime_label}</b>  ({regime_conf}% confidence)  ·  "
        f"Equity stance: {regime_res.equity_stance if regime_res else '—'}",
        "body"
    ))
    story.append(SP(4))

    # Only show macro signals that are portfolio-relevant
    relevant_signals = _portfolio_relevant_signals(macro_snap, alloc_deltas)
    for sig in relevant_signals:
        story.append(P(f"• {sig}", "body"))

    story += [SP(8), HR()]

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(P(
        "ADVISORY ONLY — model recommendations requiring human review before any action. "
        "Not financial advice. Not a registered investment adviser.",
        "disc",
    ))

    doc.build(story)
    return output_path


# ---------------------------------------------------------------------------
# Helpers — portfolio-relevant macro signals
# ---------------------------------------------------------------------------

_TICKER_MACRO_MAP = {
    "BTC":  ["cpi_yoy_pct", "fed_funds_rate", "m2_yoy_pct", "hy_credit_spread_bps"],
    "MSTR": ["cpi_yoy_pct", "fed_funds_rate", "m2_yoy_pct"],
    "GLD":  ["cpi_yoy_pct", "real_rate_10y_tips", "fed_funds_rate", "dxy"],
    "SPY":  ["gdp_real_qoq_pct", "ism_manufacturing", "unemployment_rate", "hy_credit_spread_bps"],
    "QQQ":  ["gdp_real_qoq_pct", "ism_manufacturing", "us_10y_yield"],
    "NVDA": ["gdp_real_qoq_pct", "ism_manufacturing"],
    "URNM": ["gdp_real_qoq_pct"],
    "TLT":  ["us_10y_yield", "fed_funds_rate", "cpi_yoy_pct"],
    "COIN": ["cpi_yoy_pct", "fed_funds_rate"],
    "IBIT": ["cpi_yoy_pct", "fed_funds_rate", "m2_yoy_pct"],
}

_MACRO_LABELS = {
    "cpi_yoy_pct":        ("CPI YoY",          "%",   "BTC/GLD/MSTR: high inflation = scarcity demand"),
    "core_cpi_yoy_pct":   ("Core CPI YoY",      "%",   "Constrains Fed; hurts rate-sensitive positions"),
    "pce_yoy_pct":        ("PCE YoY",            "%",   "Fed's preferred inflation gauge"),
    "fed_funds_rate":     ("Fed Funds",           "%",   "Discount rate for all risk assets"),
    "us_10y_yield":       ("10Y Yield",           "%",   "Benchmark for equity valuations"),
    "us_2y_yield":        ("2Y Yield",            "%",   "Near-term rate expectations"),
    "yield_curve_2_10":   ("Yield Curve 2-10",   "%",   "Negative = recession signal"),
    "real_rate_10y_tips": ("Real Rate (TIPS)",   "%",   "Negative real rates = tailwind for BTC/GLD"),
    "gdp_real_qoq_pct":   ("GDP Real QoQ",       "%",   "SPY/QQQ earnings backdrop"),
    "ism_manufacturing":  ("ISM Mfg PMI",        "",    "Above 50 = expansion"),
    "unemployment_rate":  ("Unemployment",        "%",   "Labor market health"),
    "m2_yoy_pct":         ("M2 Growth YoY",      "%",   "Liquidity proxy; tailwind for BTC/GLD when high"),
    "hy_credit_spread_bps":("HY Spread",         "bps", "Credit stress indicator"),
    "dxy":                ("DXY",                "",    "Strong dollar = headwind for commodities/BTC"),
    "vix":                ("VIX",                "",    "Fear gauge"),
}


def _macro_relevance(ticker: str, macro_snap: dict, regime_res) -> str:
    relevant_keys = _TICKER_MACRO_MAP.get(ticker.upper(), [])
    parts = []
    for key in relevant_keys[:3]:
        val = macro_snap.get(key)
        if val is None:
            continue
        label, suffix, note = _MACRO_LABELS.get(key, (key, "", ""))
        try:
            parts.append(f"{label} {float(val):.2f}{suffix}")
        except (TypeError, ValueError):
            pass
    return "  ·  ".join(parts) if parts else ""


def _portfolio_relevant_signals(macro_snap: dict, deltas) -> list[str]:
    tickers = {d.ticker for d in deltas if d.ticker != "CASH"}
    seen_keys = set()
    signals = []
    for ticker in tickers:
        for key in _TICKER_MACRO_MAP.get(ticker, []):
            if key in seen_keys:
                continue
            seen_keys.add(key)
            val = macro_snap.get(key)
            if val is None:
                continue
            label, suffix, note = _MACRO_LABELS.get(key, (key, "", ""))
            try:
                signals.append(f"{label}: {float(val):.2f}{suffix} — {note}")
            except (TypeError, ValueError):
                pass
    return signals[:10]
