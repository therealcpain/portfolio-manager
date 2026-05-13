"""
pdf_report.py — Generates a clean PDF from a DailyLoopResult.

Usage:
    from pdf_report import generate_pdf
    path = generate_pdf(result)   # returns Path to written PDF
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from daily_loop import DailyLoopResult

ROOT_DIR = Path(__file__).parent.parent

# Colour palette
_VOID    = "#000000"
_DARK    = "#0f0018"
_ARCANE  = "#130628"
_DIM     = "#2d1458"
_PURPLE  = "#6d28d9"
_GLOW    = "#a855f7"
_NEON    = "#c084fc"
_FLASH   = "#e879f9"
_TEXT    = "#e9d5ff"
_MUTED   = "#a78bfa"
_WHITE   = "#f5f3ff"
_GREEN   = "#22c55e"
_RED     = "#ef4444"
_AMBER   = "#f59e0b"
_GRAY    = "#6b7280"
_LGRAY   = "#f3f4f6"


def _hex(h: str):
    from reportlab.lib import colors
    return colors.HexColor(h)


def _pct_color(v: Optional[float]):
    if v is None:
        return _hex(_MUTED)
    return _hex(_GREEN) if v >= 0 else _hex(_RED)


def generate_pdf(result, output_path: Optional[Path] = None) -> Path:
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
        str(output_path),
        pagesize=letter,
        leftMargin=0.65*inch, rightMargin=0.65*inch,
        topMargin=0.6*inch, bottomMargin=0.6*inch,
    )

    W = 7.2 * inch  # usable width

    def sty(name="body", **kw):
        raw_color = kw.pop("color", _DARK)
        # Accept either a hex string or an already-converted Color object
        text_color = raw_color if not isinstance(raw_color, str) else _hex(raw_color)
        base = ParagraphStyle(name,
            fontName=kw.pop("font", "Helvetica"),
            fontSize=kw.pop("size", 9),
            textColor=text_color,
            leading=kw.pop("leading", 13),
            spaceBefore=kw.pop("sb", 0),
            spaceAfter=kw.pop("sa", 2),
            alignment=kw.pop("align", TA_LEFT),
        )
        for k, v in kw.items():
            setattr(base, k, v)
        return base

    S = {
        "title":    sty("t",  font="Helvetica-Bold", size=18, color=_WHITE, align=TA_CENTER, leading=22),
        "subtitle": sty("su", font="Helvetica",       size=9,  color=_NEON,  align=TA_CENTER),
        "section":  sty("s",  font="Helvetica-Bold", size=10, color=_PURPLE, sb=10, sa=4),
        "label":    sty("l",  font="Helvetica-Bold", size=8.5, color=_DARK),
        "body":     sty("b",  font="Helvetica",       size=8.5, color=_DARK, leading=13),
        "mono":     sty("m",  font="Courier",         size=8,   color=_DARK, leading=12),
        "muted":    sty("mu", font="Helvetica",       size=7.5, color=_GRAY),
        "disc":     sty("d",  font="Helvetica-Oblique", size=7, color=_GRAY, align=TA_CENTER, sb=6),
        "green":    sty("g",  font="Helvetica-Bold", size=8.5, color=_GREEN),
        "red":      sty("r",  font="Helvetica-Bold", size=8.5, color=_RED),
        "amber":    sty("a",  font="Helvetica-Bold", size=8.5, color=_AMBER),
        "regime":   sty("re", font="Helvetica-Bold", size=11,  color=_FLASH, align=TA_CENTER),
    }

    def P(text, style="body"): return Paragraph(str(text), S[style])
    def SP(h=6): return Spacer(1, h)
    def HR(): return HRFlowable(width="100%", thickness=0.4, color=_hex(_DIM), spaceAfter=6, spaceBefore=2)

    def header_table():
        data = [
            [P("ENIGMA CAPITAL", "title")],
            [P("DAILY INVESTMENT BRIEF", "subtitle")],
            [P(f"{date_str}  ·  ADVISORY ONLY  ·  NOT FINANCIAL ADVICE", "subtitle")],
        ]
        t = Table(data, colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), _hex(_DARK)),
            ("TOPPADDING",   (0,0),(-1,-1), 10),
            ("BOTTOMPADDING",(0,0),(-1,-1), 10),
            ("LEFTPADDING",  (0,0),(-1,-1), 16),
            ("RIGHTPADDING", (0,0),(-1,-1), 16),
        ]))
        return t

    def two_col(left_items, right_items, lw=3.4*inch):
        rw = W - lw - 0.2*inch
        left_t  = Table([[item] for item in left_items],  colWidths=[lw])
        right_t = Table([[item] for item in right_items], colWidths=[rw])
        for t in (left_t, right_t):
            t.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),
                                   ("RIGHTPADDING",(0,0),(-1,-1),0),
                                   ("TOPPADDING",(0,0),(-1,-1),1),
                                   ("BOTTOMPADDING",(0,0),(-1,-1),1)]))
        outer = Table([[left_t, right_t]], colWidths=[lw, rw])
        outer.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                                   ("LEFTPADDING",(0,0),(-1,-1),0),
                                   ("RIGHTPADDING",(0,0),(-1,-1),0)]))
        return outer

    def kv(label, value, val_style="body"):
        return Table([[P(label, "label"), P(str(value), val_style)]],
                     colWidths=[1.7*inch, W-1.7*inch],
                     style=[("VALIGN",(0,0),(-1,-1),"TOP"),
                            ("LEFTPADDING",(0,0),(-1,-1),0),
                            ("RIGHTPADDING",(0,0),(-1,-1),0),
                            ("TOPPADDING",(0,0),(-1,-1),1),
                            ("BOTTOMPADDING",(0,0),(-1,-1),1)])

    def section(text): return P(f"▸  {text}", "section")

    def price_table(ingest):
        rows = [
            [P("Ticker","label"), P("Price","label"), P("1d","label"),
             P("20d","label"), P("YTD","label")],
        ]
        show = [("SPY","SPY"), ("QQQ","QQQ"), ("BTC","BTC"), ("ETH","ETH"),
                ("GLD","GLD"), ("NVDA","NVDA"), ("MSTR","MSTR"), ("IBIT","IBIT")]
        prices   = ingest.prices       if ingest else {}
        r1       = ingest.returns_1d   if ingest else {}
        r20      = ingest.returns_20d  if ingest else {}
        ytd_ret  = ingest.returns_ytd  if ingest else {}
        for name, _ in show:
            p   = prices.get(name)
            d1  = r1.get(name)
            d20 = r20.get(name)
            dy  = ytd_ret.get(name)
            def fmt_pct(v):
                if v is None: return P("—","muted")
                s = f"{v:+.2f}%"
                return P(s, "green" if v >= 0 else "red")
            price_str = f"${p:,.2f}" if p else "—"
            rows.append([P(name,"label"), P(price_str,"body"), fmt_pct(d1), fmt_pct(d20), fmt_pct(dy)])

        t = Table(rows, colWidths=[0.9*inch, 1.3*inch, 1.1*inch, 1.1*inch, 1.1*inch])
        ts = TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), _hex(_ARCANE)),
            ("TEXTCOLOR",     (0,0),(-1,0), _hex(_NEON)),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [_hex(_WHITE), _hex(_LGRAY)]),
            ("GRID",          (0,0),(-1,-1), 0.3, _hex(_DIM)),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("FONTSIZE",      (0,0),(-1,-1), 8.5),
        ])
        t.setStyle(ts)
        return t

    def macro_table(ingest, snap):
        rows = [[P("Indicator","label"), P("Value","label"), P("Source","label")]]
        fields = []
        if snap:
            fields = [
                ("Fed Funds Rate",    snap.get("fed_funds_rate"),        "%"),
                ("10Y Yield",         snap.get("us_10y_yield"),           "%"),
                ("2Y Yield",          snap.get("us_2y_yield"),            "%"),
                ("Yield Curve 2-10",  snap.get("yield_curve_2_10"),       "%"),
                ("Real Rate (TIPS)",  snap.get("real_rate_10y_tips"),     "%"),
                ("CPI YoY",           snap.get("cpi_yoy_pct"),            "%"),
                ("Core CPI YoY",      snap.get("core_cpi_yoy_pct"),       "%"),
                ("PCE YoY",           snap.get("pce_yoy_pct"),            "%"),
                ("Unemployment",      snap.get("unemployment_rate"),       "%"),
                ("GDP (real QoQ)",    snap.get("gdp_real_qoq_pct"),       "%"),
                ("ISM Mfg",           snap.get("ism_manufacturing"),       ""),
                ("HY Spread",         snap.get("hy_credit_spread_bps"),   "bps"),
                ("M2 Growth YoY",     snap.get("m2_yoy_pct"),             "%"),
                ("VIX",               ingest.vix if ingest else None,     ""),
                ("DXY",               ingest.dxy if ingest else None,     ""),
            ]
        for label, val, suffix in fields:
            if val is None:
                continue
            try:
                val_f = float(val)
                val_str = f"{val_f:.2f}{suffix}"
            except (TypeError, ValueError):
                val_str = str(val)
            rows.append([P(label,"body"), P(val_str,"body"), P("FRED/BLS/yf","muted")])

        if len(rows) == 1:
            return None
        t = Table(rows, colWidths=[2.2*inch, 1.5*inch, 1.5*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), _hex(_ARCANE)),
            ("TEXTCOLOR",     (0,0),(-1,0), _hex(_NEON)),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [_hex(_WHITE), _hex(_LGRAY)]),
            ("GRID",          (0,0),(-1,-1), 0.3, _hex(_DIM)),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("FONTSIZE",      (0,0),(-1,-1), 8.5),
        ]))
        return t

    def regime_block(regime_result):
        if not regime_result:
            return []
        items = [
            P(regime_result.macro_regime.replace("_", " "), "regime"),
            SP(4),
            kv("Confidence", f"{regime_result.macro_confidence}%"),
            kv("Equity stance", regime_result.equity_stance),
            kv("BTC / Crypto", regime_result.btc_crypto_stance),
            kv("Gold", regime_result.gold_stance),
            SP(4),
            P(regime_result.macro_rationale, "body"),
        ]
        subs = regime_result.sub_assessments or []
        if subs:
            items.append(SP(6))
            sub_rows = [[P("Sub-regime","label"), P("Assessment","label"), P("Conf","label")]]
            for s in subs:
                sub_rows.append([P(getattr(s,"name",getattr(s,"dimension","?")),"body"), P(s.label,"body"), P(f"{s.confidence}%","body")])
            st = Table(sub_rows, colWidths=[1.6*inch, 3.2*inch, 0.8*inch])
            st.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,0), _hex(_DIM)),
                ("TEXTCOLOR",     (0,0),(-1,0), _hex(_NEON)),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [_hex(_WHITE), _hex(_LGRAY)]),
                ("GRID",          (0,0),(-1,-1), 0.3, _hex(_DIM)),
                ("TOPPADDING",    (0,0),(-1,-1), 3),
                ("BOTTOMPADDING", (0,0),(-1,-1), 3),
                ("LEFTPADDING",   (0,0),(-1,-1), 6),
                ("FONTSIZE",      (0,0),(-1,-1), 8.5),
            ]))
            items.append(st)
        return items

    def cio_block(cio):
        if not cio:
            return [P("CIO decision phase did not complete.", "muted")]
        items = []
        stance_style = "green" if "buy" in cio.final_stance.lower() or "overweight" in cio.final_stance.lower() \
                       else "red" if "sell" in cio.final_stance.lower() or "reduce" in cio.final_stance.lower() \
                       else "amber"
        items += [
            kv("Stance", cio.final_stance, stance_style),
            kv("Confidence", f"{cio.final_confidence}%"),
            kv("Allocation change", "Yes" if cio.allocation_change else "No"),
        ]
        # Summarise signals as rationale
        signals = getattr(cio, "signals", []) or []
        if signals:
            sig_text = " · ".join(
                s.get("signal", s.get("description", str(s)))[:80]
                for s in signals[:4]
            )
            items += [SP(4), P("<b>Key Signals</b>", "body"), P(sig_text, "body")]
        if cio.required_actions:
            items += [SP(4), P("<b>Required Actions</b>", "body")]
            for a in cio.required_actions:
                items.append(P(f"  • {a}", "body"))
        if cio.challenge_questions:
            items += [SP(4), P("<b>Challenge Questions</b>", "label")]
            for q in cio.challenge_questions:
                items.append(P(f"  ? {q}", "body"))
        if cio.next_review_trigger:
            items += [SP(4), kv("Next review", cio.next_review_trigger)]
        return items

    def memos_block(memos_result):
        if not memos_result or not memos_result.memos:
            return [P("No specialist memos — run with mock=False and a valid API key.", "muted")]
        items = []
        for memo in memos_result.memos:
            if not memo:
                continue
            # memos are stored as dicts
            m = memo if isinstance(memo, dict) else vars(memo)
            stance = m.get("stance", "")
            if stance in ("error", "skipped"):
                continue
            agent_label = m.get("agent", "?").replace("_", " ").title()
            conf = m.get("confidence", 0)
            items.append(P(f"<b>{agent_label}</b>  ({conf}% confidence  ·  {stance})", "body"))
            for pt in m.get("key_points", [])[:3]:
                items.append(P(f"  · {pt}", "body"))
            rec = m.get("recommendation", "")
            if rec:
                items.append(P(f"  → {rec}", "body"))
            dissent = m.get("dissent", "") or m.get("dissent_reason", "")
            if dissent and str(dissent).lower() not in ("no", "false", "none", ""):
                items.append(P(f"  ⚠ Dissent: {dissent}", "red"))
            items.append(SP(4))
        return items or [P("All specialists returned errors.", "muted")]

    def dissent_block(dissent):
        if not dissent:
            return [P("No dissent data.", "muted")]
        items = [
            kv("Groupthink alert", "YES" if dissent.groupthink_alert else "No",
               "red" if dissent.groupthink_alert else "body"),
            kv("Dissent suppressed", "YES" if dissent.dissent_suppressed else "No",
               "amber" if dissent.dissent_suppressed else "body"),
            kv("Sentiment", dissent.sentiment_state or "—"),
        ]
        if dissent.recommendations:
            items += [SP(4), P("<b>Recommendations</b>", "label")]
            for r in dissent.recommendations:
                items.append(P(f"  • {r}", "body"))
        return items

    def org_block(org):
        if not org:
            return [P("Org review did not complete.", "muted")]
        items = [
            kv("Complexity score", f"{org.complexity_score:.0f} / 100"),
            kv("Health score",     f"{org.health_score:.0f} / 100"),
            kv("Complexity breach", "YES" if org.complexity_breach else "No",
               "red" if org.complexity_breach else "body"),
        ]
        if org.alerts:
            items += [SP(4), P("<b>Alerts</b>", "label")]
            for a in org.alerts:
                items.append(P(f"  ⚠ {a}", "amber"))
        return items

    # ── Assemble story ─────────────────────────────────────────────────────
    story = []

    # Retrieve data objects
    ingest       = getattr(result, "ingest", None)
    regime_res   = getattr(result, "regime", None)
    memos_res    = getattr(result, "memos", None)
    dissent_res  = getattr(result, "dissent", None)
    cio_res      = getattr(result, "cio_decision", None)
    org_res      = getattr(result, "org_review", None)

    # Load raw snapshot for macro table
    snap_path = ROOT_DIR / "data" / "manual_inputs" / "macro_snapshot.yaml"
    snap_flat = {}
    if snap_path.exists():
        try:
            import yaml
            raw = yaml.safe_load(snap_path.read_text()) or {}
            # Flatten nested yaml into flat dict for display
            for yaml_section in ("fed", "rates", "inflation", "growth", "employment", "liquidity", "credit"):
                snap_flat.update(raw.get(yaml_section, {}))
            snap_flat["vix"] = raw.get("market", {}).get("vix")
            snap_flat["dxy"] = raw.get("market", {}).get("dxy")
        except Exception:
            pass

    # Header
    story += [header_table(), SP(14)]

    # ── REGIME ──
    story.append(KeepTogether([section("MACRO REGIME")] + regime_block(regime_res) + [SP(8)]))
    story.append(HR())

    # ── MARKETS ──
    story += [section("MARKET SNAPSHOT"), price_table(ingest), SP(8), HR()]

    # ── MACRO INDICATORS ──
    macro_t = macro_table(ingest, snap_flat)
    if macro_t:
        story += [section("MACRO INDICATORS"), macro_t, SP(8), HR()]

    # ── CIO DECISION ──
    story.append(KeepTogether([section("CIO DECISION")] + cio_block(cio_res) + [SP(8)]))
    story.append(HR())

    # ── SPECIALIST MEMOS ──
    story += [section("SPECIALIST MEMOS")] + memos_block(memos_res) + [SP(4), HR()]

    # ── DISSENT ──
    story.append(KeepTogether([section("DISSENT & ORG HEALTH")] + dissent_block(dissent_res) + [SP(8)]))

    # ── ORG HEALTH ──
    story += org_block(org_res)
    story += [SP(8), HR()]

    # ── DISCLAIMER ──
    story.append(P(
        "ADVISORY ONLY. All outputs are model recommendations requiring human review and approval before any action. "
        "Not financial advice. Not a registered investment adviser. Past performance is not indicative of future results.",
        "disc",
    ))

    doc.build(story)
    return output_path
