#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_TEMPLATE = ROOT / "assets" / "dashboard.html"
DEFAULT_SUMMARY = DATA_DIR / "summary.json"
DEFAULT_DASHBOARD = DATA_DIR / "dashboard.html"
DEFAULT_LOG = DATA_DIR / "signals.jsonl"
DEFAULT_FAST_SUMMARY = DATA_DIR / "fast-summary.json"
DEFAULT_ALERT = DATA_DIR / "alert.json"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; btc-microtrend-bot/1.0)", "Accept": "application/json"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str) -> Any:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        return json.load(resp)


def try_fetch_json(url: str) -> Any:
    try:
        return fetch_json(url)
    except Exception:
        return None


def safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_polymarket_btc_markets(limit: int = 200) -> List[Dict[str, Any]]:
    data = try_fetch_json(f"{GAMMA_API_BASE}/events?active=true&closed=false&limit={limit}&offset=0") or []
    hits = []
    for event in data:
        text = f"{event.get('title','')} {event.get('description','')}".lower()
        if "bitcoin" in text or "btc" in text:
            hits.append(event)
    return hits


def classify_market_type(text: str) -> str:
    lowered = text.lower()
    if "hit $" in lowered or "hit " in lowered:
        return "deadline-level"
    if "by december" in lowered or "by september" in lowered or "by june" in lowered or "by march" in lowered or "by " in lowered:
        if "bitcoin" in lowered or "btc" in lowered:
            return "deadline-level"
    if "above" in lowered or "below" in lowered:
        return "level"
    if "up or down" in lowered or "higher or lower" in lowered:
        return "direction"
    if "will bitcoin be" in lowered or "btc be" in lowered:
        return "level"
    if "increase" in lowered or "decrease" in lowered or "rise" in lowered or "fall" in lowered:
        return "direction"
    return "unknown"


def detect_timeframe(text: str) -> Optional[str]:
    lowered = text.lower()
    if "5m" in lowered or "5 minute" in lowered or "5-min" in lowered or "next 5 minutes" in lowered:
        return "5m"
    if "15m" in lowered or "15 minute" in lowered or "15-min" in lowered or "next 15 minutes" in lowered:
        return "15m"
    return None


def classify_family(text: str) -> str:
    lowered = text.lower()
    if "hit $" in lowered or ("will bitcoin hit" in lowered):
        return "btc-price-target"
    if "microstrategy" in lowered or "mstr" in lowered:
        return "company-bitcoin"
    if "capital gains tax" in lowered or "trump" in lowered or "policy" in lowered:
        return "policy-crypto"
    if "el salvador" in lowered or "hold $1b" in lowered or "arkham" in lowered:
        return "treasury-holdings"
    return "other-btc"


def infer_horizon_bucket(text: str) -> str:
    lowered = text.lower()
    if "september" in lowered or "june" in lowered or "march" in lowered:
        return "medium"
    if "december 31, 2026" in lowered or "2027" in lowered:
        return "long"
    if "december 31" in lowered or "2025" in lowered:
        return "short"
    return "unknown"


def infer_resolution_source(text: str) -> Dict[str, Any]:
    lowered = text.lower()
    if "resolution source for this market is binance" in lowered or "binance 1 minute candle" in lowered or 'btc/usdt "high"' in lowered:
        return {"source_type": "binance-1m-high", "source_label": "Binance BTCUSDT 1m High", "signal_source": "binance-orderflow"}
    if "arkham" in lowered:
        return {"source_type": "arkham-holdings", "source_label": "Arkham holdings tracker", "signal_source": "event-tracker"}
    if "chainlink" in lowered or "oracle" in lowered:
        return {"source_type": "oracle", "source_label": "Oracle/Chainlink-style source", "signal_source": "oracle"}
    return {"source_type": "unspecified", "source_label": "Unspecified / market text", "signal_source": "generic"}


def extract_market_rows(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for event in events:
        for market in event.get("markets", []) or []:
            question = market.get("question") or event.get("title")
            description = market.get("description", "")
            text = f"{question} {description}"
            lowered = text.lower()
            timeframe = detect_timeframe(text)
            market_type = classify_market_type(text)
            valid_for_bot = (timeframe in {"5m", "15m"} and market_type in {"level", "direction"}) or market_type == "deadline-level"

            outcomes = market.get("outcomes")
            outcome_prices = market.get("outcomePrices")
            implied_yes = None
            try:
                outs = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
                prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                if isinstance(outs, list) and isinstance(prices, list):
                    for o, p in zip(outs, prices):
                        if str(o).strip().lower() == "yes":
                            implied_yes = safe_float(p)
                            break
            except Exception:
                pass

            resolution = infer_resolution_source(text)
            rows.append({
                "event_title": event.get("title"),
                "question": question,
                "description": description,
                "text": text,
                "contains_bitcoin": ("bitcoin" in lowered or "btc" in lowered),
                "timeframe": timeframe,
                "market_type": market_type,
                "family": classify_family(text),
                "horizon_bucket": infer_horizon_bucket(text),
                "valid_for_bot": valid_for_bot,
                "implied_yes_probability": implied_yes,
                "url": f"https://polymarket.com/event/{event.get('slug')}" if event.get("slug") else None,
                "resolution_source": resolution,
            })
    return rows


def fetch_binance_klines(interval: str, limit: int = 120) -> List[List[Any]]:
    data = try_fetch_json(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
    if data:
        return data
    return []


def synthetic_klines_from_spots(spots: List[float], limit: int = 120) -> List[List[Any]]:
    if not spots:
        return []
    out = []
    values = spots[-limit:]
    while len(values) < limit:
        values.insert(0, values[0])
    for price in values:
        out.append([None, None, None, None, price])
    return out


def fetch_kraken_spot() -> Optional[float]:
    data = try_fetch_json("https://api.kraken.com/0/public/Ticker?pair=XBTUSD")
    result = (data or {}).get("result") or {}
    for payload in result.values():
        last = payload.get("c") if isinstance(payload, dict) else None
        if isinstance(last, list) and last:
            return safe_float(last[0])
    return None


def fetch_bybit_spot() -> Optional[float]:
    data = try_fetch_json("https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT")
    rows = (((data or {}).get("result") or {}).get("list") or [])
    if rows:
        return safe_float(rows[0].get("lastPrice"))
    return None


def fetch_coingecko_spot() -> Optional[float]:
    data = try_fetch_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
    return safe_float(((data or {}).get("bitcoin") or {}).get("usd"))


def fetch_coinbase_spot() -> Optional[float]:
    data = try_fetch_json("https://api.coinbase.com/v2/prices/BTC-USD/spot")
    return safe_float(((data or {}).get("data") or {}).get("amount"))


def fetch_binance_spot() -> Optional[float]:
    data = try_fetch_json("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
    return safe_float((data or {}).get("price"))


def fetch_chainlink_anchor() -> Optional[float]:
    # keep a public anchor-style fallback chain; if a direct public Chainlink endpoint is unavailable, use consensus fallback.
    urls = [
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
        "https://api.coinbase.com/v2/prices/BTC-USD/spot",
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
    ]
    for url in urls:
        try:
            data = try_fetch_json(url)
            val = safe_float((data or {}).get("price"))
            if val is None:
                val = safe_float((((data or {}).get("data") or {}).get("amount")))
            if val is None:
                val = safe_float((((data or {}).get("bitcoin") or {}).get("usd")))
            if val is not None:
                return val
        except Exception:
            continue
    return None


def close_prices(klines: List[List[Any]]) -> List[float]:
    out = []
    for row in klines:
        val = safe_float(row[4] if len(row) > 4 else None)
        if val is not None:
            out.append(val)
    return out


def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    current = sum(values[:period]) / period
    for v in values[period:]:
        current = (v * k) + (current * (1 - k))
    return current


def pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return (b - a) / a


def extract_target_price(text: str) -> Optional[float]:
    lowered = text.lower().replace(',', '')
    if '$' not in lowered and 'k' not in lowered:
        return None
    tokens = lowered.replace('?', ' ').replace('.', ' ').split()
    for token in tokens:
        raw = token.replace('$', '').strip()
        if not raw:
            continue
        mult = 1.0
        if raw.endswith('k'):
            mult = 1000.0
            raw = raw[:-1]
        try:
            val = float(raw) * mult
            if val > 1000:
                return val
        except ValueError:
            continue
    return None


def signal_for_deadline_level(question: str, market_prob: Optional[float], spot: Optional[float], anchor: Optional[float], horizon_bucket: str = "unknown", family: str = "other-btc", resolution_source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source_type = (resolution_source or {}).get("source_type") or "unspecified"
    if source_type == "binance-1m-high":
        price = spot or anchor or 0.0
    elif source_type == "oracle":
        price = anchor or spot or 0.0
    else:
        price = spot or anchor or 0.0
    target = extract_target_price(question)
    if not target or price <= 0:
        return {
            "bias": "no-trade",
            "confidence": "low",
            "model_score": 0.0,
            "action": "insufficient-data",
            "distance_pct": None,
            "target_price": target,
            "regime": "unknown",
            "black_swan": False,
        }
    distance_pct = (target - price) / price
    horizon_mult = {"short": 0.7, "medium": 1.0, "long": 1.35, "unknown": 1.0}.get(horizon_bucket, 1.0)
    effective_distance = distance_pct / horizon_mult

    if family != "btc-price-target":
        return {
            "bias": "no-trade",
            "confidence": "low",
            "model_score": 0.0,
            "action": "unsupported-family",
            "distance_pct": round(distance_pct, 4),
            "target_price": target,
            "regime": "deadline-level",
            "black_swan": False,
        }

    if effective_distance <= 0:
        bias = "strong-bullish"
        confidence = "high"
        model_score = 0.97
        action = "watch-yes"
    elif effective_distance < 0.05:
        bias = "bullish"
        confidence = "medium"
        model_score = 0.74
        action = "watch-yes"
    elif effective_distance < 0.15:
        bias = "level-watch"
        confidence = "medium"
        model_score = 0.52
        action = "watch-level"
    else:
        bias = "bearish"
        confidence = "medium"
        model_score = 0.24
        action = "watch-no"
    if market_prob is not None:
        if bias in {"strong-bullish", "bullish"} and market_prob > 0.85:
            action = "skip-overpriced"
            confidence = "low"
        if bias == "bearish" and market_prob < 0.15:
            action = "skip-overpriced"
            confidence = "low"
    return {
        "bias": bias,
        "confidence": confidence,
        "model_score": round(model_score, 4),
        "action": action,
        "distance_pct": round(distance_pct, 4),
        "effective_distance_pct": round(effective_distance, 4),
        "target_price": target,
        "regime": "deadline-level",
        "black_swan": False,
    }


def signal_from_prices(prices: List[float], timeframe: str, market_prob: Optional[float], spot: Optional[float], anchor: Optional[float]) -> Dict[str, Any]:
    latest = prices[-1] if prices else 0.0
    e9 = ema(prices, 9) or latest
    e20 = ema(prices, 20) or latest
    chg_short = pct_change(prices[-4], latest) if len(prices) >= 4 else 0.0
    chg_mid = pct_change(prices[-12], latest) if len(prices) >= 12 else 0.0
    trend_score = 0.0
    if latest > e9: trend_score += 1.0
    if e9 > e20: trend_score += 1.0
    if chg_short > 0: trend_score += 1.0
    if chg_mid > 0: trend_score += 1.0

    divergence = abs(((spot or latest) - (anchor or latest)) / (anchor or latest)) if (anchor or latest) else 0.0
    blackswan = divergence > 0.008 or abs(chg_short) > 0.012 or abs(chg_mid) > 0.02
    regime = "trend" if abs(chg_mid) > 0.003 else "chop"

    if blackswan:
        bias = "no-trade"
        confidence = "low"
        model_score = 0.0
        action = "avoid"
    else:
        bull_score = trend_score / 4.0
        model_score = bull_score
        if bull_score >= 0.9:
            bias = "strong-bullish"
            confidence = "high"
            action = "watch-long"
        elif bull_score >= 0.7:
            bias = "bullish"
            confidence = "medium"
            action = "watch-long"
        elif bull_score <= 0.1:
            bias = "strong-bearish"
            confidence = "high"
            action = "watch-short"
        elif bull_score <= 0.3:
            bias = "bearish"
            confidence = "medium"
            action = "watch-short"
        else:
            bias = "neutral"
            confidence = "low"
            action = "wait"

    if market_prob is not None:
        if bias in {"strong-bullish", "bullish"} and market_prob > 0.82:
            confidence = "low"
            action = "skip-overpriced"
        if bias in {"strong-bearish", "bearish"} and market_prob < 0.18:
            confidence = "low"
            action = "skip-overpriced"

    return {
        "timeframe": timeframe,
        "latest_price": latest,
        "ema9": e9,
        "ema20": e20,
        "change_short": round(chg_short, 4),
        "change_mid": round(chg_mid, 4),
        "divergence_vs_anchor": round(divergence, 4),
        "regime": regime,
        "black_swan": blackswan,
        "bias": bias,
        "confidence": confidence,
        "model_score": round(model_score, 4),
        "action": action,
    }


def classify_status(action: str) -> Dict[str, str]:
    action = str(action or "")
    if action in {"watch-yes", "watch-no", "watch-long", "watch-short"}:
        return {"label": "actionable", "css": "status-actionable"}
    if action in {"skip-overpriced", "avoid", "insufficient-data", "unsupported-family"}:
        return {"label": "skip", "css": "status-skip"}
    if action in {"wait", "watch-level"}:
        return {"label": "wait", "css": "status-wait"}
    return {"label": "unknown", "css": "status-unknown"}


def load_order_book() -> Dict[str, Any]:
    """Muat data order book dari file JSON."""
    try:
        return json.loads(ORDER_BOOK.read_text(encoding='utf-8'))
    except Exception:
        return {"bids": [], "asks": []}

def load_recent_trades() -> List[Dict[str, Any]]:
    """Muat data trades terbaru dari file JSONL."""
    try:
        trades = []
        with TRADES_LOG.open('r', encoding='utf-8') as f:
            for line in f:
                trades.append(json.loads(line))
        return trades[-10:]  # Ambil 10 trades terbaru
    except Exception:
        return []

def render_dashboard(summary: Dict[str, Any], output_path: Path) -> None:
    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    best = summary.get("best_setup") or {}
    signals = summary.get("signals") or []
    
    # Muat data real-time
    order_book = load_order_book()
    recent_trades = load_recent_trades()

    if best:
        badge = "bull" if "bull" in str(best.get("bias")) else ("bear" if "bear" in str(best.get("bias")) else "neutral")
        best_html = f'<div class="card"><div><strong>{best.get("question","No setup")}</strong></div><div class="footnote">family={best.get("family","n/a")} · horizon={best.get("horizon_bucket","n/a")}</div><div style="margin-top:10px;"><span class="pill {badge}">{best.get("bias","n/a")}</span></div><div class="footnote" style="margin-top:10px;">confidence={best.get("confidence","n/a")} · action={best.get("action","n/a")} · distance={best.get("distance_pct","n/a")}</div></div>'
    else:
        best_html = '<div class="card"><strong>No setup yet</strong><div class="footnote">No valid BTC microtrend setup found yet.</div></div>'

    rows = []
    for s in signals:
        badge = "bull" if "bull" in str(s.get("bias")) else ("bear" if "bear" in str(s.get("bias")) else "neutral")
        status = classify_status(str(s.get("action", "")))
        rows.append(
            f"<tr data-family='{s.get('family','other-btc')}'><td>{s.get('question','n/a')}</td><td>{s.get('family','n/a')}</td><td><span class='pill {badge}'>{s.get('bias','n/a')}</span></td><td>{s.get('confidence','n/a')}</td><td>{s.get('implied_yes_probability','n/a')}</td><td>{s.get('distance_pct','n/a')}</td><td>{s.get('model_score','n/a')}</td><td>{s.get('action','n/a')}</td><td><span class='{status['css']}'>{status['label']}</span></td></tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='9'>No BTC target/deadline signals found.</td></tr>")

    alert_payload = summary.get("alert") or {}
    top_actionable = (alert_payload.get("top_actionable") or {})
    mode = str(alert_payload.get("alert_mode") or "idle")
    alert_text = (
        f"ACTIONABLE: {top_actionable.get('question', 'signal available')} · action={top_actionable.get('action', 'watch')} · confidence={top_actionable.get('confidence', 'n/a')}"
        if mode == "hard"
        else (
            f"SOFT ALERT: {top_actionable.get('question', 'candidate available')} · action={top_actionable.get('action', 'watch')} · confidence={top_actionable.get('confidence', 'n/a')}"
            if mode == "soft"
            else "No actionable BTC signal right now. Bot is still scanning on the fast/full schedule."
        )
    )
    alert_class = "good" if mode in {"hard", "soft"} else "idle"

    # Siapkan data order book untuk tabel
    order_book_rows = ""
    for bid, ask in zip(order_book.get("bids", [])[:10], order_book.get("asks", [])[:10]):
        order_book_rows += f"
        <tr>
            <td>{bid.get('price', 'N/A')}</td>
            <td>{bid.get('size', 'N/A')}</td>
            <td>{ask.get('size', 'N/A')}</td>
        </tr>
        "
    
    # Siapkan data trades untuk tabel
    trade_rows = ""
    for trade in recent_trades:
        trade_rows += f"
        <tr>
            <td>{trade.get('timestamp', 'N/A')}</td>
            <td>{trade.get('price', 'N/A')}</td>
            <td>{trade.get('size', 'N/A')}</td>
            <td>{trade.get('side', 'N/A')}</td>
        </tr>
        "
    
    # Siapkan data untuk grafik harga
    chart_labels = [trade.get('timestamp', '') for trade in recent_trades]
    chart_data = [trade.get('price', 0) for trade in recent_trades]
    
    replacements = {
        "{{LAST_RUN}}": str(summary.get("ran_at") or "n/a"),
        "{{BTC_SPOT}}": str(summary.get("btc_spot") or "n/a"),
        "{{CHAINLINK_SPOT}}": str(summary.get("chainlink_btc_usd") or "n/a"),
        "{{ACTIONABLE_COUNT}}": str(((summary.get("alert") or {}).get("actionable_count")) or 0),
        "{{ALERT_TEXT}}": alert_text,
        "{{ALERT_CLASS}}": alert_class,
        "{{BEST_SETUP}}": best_html,
        "{{REGIME}}": str(summary.get("regime") or "n/a"),
        "{{BLACKSWAN}}": str(summary.get("black_swan_status") or "n/a"),
        "{{VALID_MARKETS}}": str(((summary.get("market_universe") or {}).get("valid_markets")) or 0),
        "{{BEST_YES}}": str(((summary.get("best_yes_candidate") or {}).get("question")) or "none"),
        "{{BEST_NO}}": str(((summary.get("best_no_candidate") or {}).get("question")) or "none"),
        "{{NOTES}}": str(summary.get("notes") or "n/a"),
        "{{SIGNAL_ROWS}}": "\n".join(rows),
        "{{ORDER_BOOK_ROWS}}": order_book_rows,
        "{{TRADE_ROWS}}": trade_rows,
        "{{CHART_LABELS}}": json.dumps(chart_labels),
        "{{CHART_DATA}}": json.dumps(chart_data),
    }
    html = template
    for old, new in replacements.items():
        html = html.replace(old, new)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def inspect_btc_market_universe(limit: int = 200) -> Dict[str, Any]:
    events = fetch_polymarket_btc_markets(limit=limit)
    market_rows = extract_market_rows(events)
    valid = [row for row in market_rows if row.get("valid_for_bot")]
    invalid = [row for row in market_rows if not row.get("valid_for_bot")]
    return {
        "ran_at": utc_now(),
        "event_count": len(events),
        "market_count": len(market_rows),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "valid": valid[:50],
        "invalid": invalid[:50],
    }


def summarize_alert(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    actionable = [s for s in signals if str(s.get("action")) in {"watch-yes", "watch-no", "watch-long", "watch-short"}]
    soft_candidates = [
        s for s in signals
        if str(s.get("action")) in {"watch-level", "skip-overpriced"} and str(s.get("confidence")) in {"medium", "high"}
    ]
    top = actionable[0] if actionable else (soft_candidates[0] if soft_candidates else None)
    return {
        "ran_at": utc_now(),
        "actionable_count": len(actionable),
        "soft_count": len(soft_candidates),
        "top_actionable": top,
        "has_actionable": bool(top),
        "alert_mode": "hard" if actionable else ("soft" if soft_candidates else "idle"),
    }


def priority_rank(s: Dict[str, Any]) -> int:
    family = str(s.get("family") or "")
    question = str(s.get("question") or "").lower()
    score = 0
    if family == "btc-price-target":
        score += 4
    if "will bitcoin hit $" in question:
        score += 3
    if "september" in question or "december" in question or "2025" in question:
        score += 1
    return score


def run_scan(limit: int = 200) -> Dict[str, Any]:
    events = fetch_polymarket_btc_markets(limit=limit)
    market_rows = [row for row in extract_market_rows(events) if row.get("valid_for_bot")]
    spot_binance = fetch_binance_spot()
    spot_coinbase = fetch_coinbase_spot()
    spot_kraken = fetch_kraken_spot()
    spot_bybit = fetch_bybit_spot()
    spot_coingecko = fetch_coingecko_spot()
    chainlink_anchor = fetch_chainlink_anchor()
    spot_candidates = [x for x in [spot_binance, spot_coinbase, spot_kraken, spot_bybit, spot_coingecko, chainlink_anchor] if x is not None]
    btc_spot = sum(spot_candidates) / len(spot_candidates) if spot_candidates else None

    k5 = fetch_binance_klines("5m", 120)
    k15 = fetch_binance_klines("15m", 120)
    p5 = close_prices(k5)
    p15 = close_prices(k15)
    synthetic_prices = [x for x in [spot_binance, spot_coinbase, spot_kraken, spot_bybit, spot_coingecko, chainlink_anchor] if x is not None]
    if not p5:
        p5 = close_prices(synthetic_klines_from_spots(synthetic_prices or [btc_spot or chainlink_anchor or 0.0], 20))
    if not p15:
        p15 = close_prices(synthetic_klines_from_spots(synthetic_prices or [btc_spot or chainlink_anchor or 0.0], 20))
    base_signals = {
        "5m": signal_from_prices(p5, "5m", None, btc_spot, chainlink_anchor),
        "15m": signal_from_prices(p15, "15m", None, btc_spot, chainlink_anchor),
    }

    signals = []
    for row in market_rows:
        if row.get("market_type") == "deadline-level":
            base = signal_for_deadline_level(row.get("question", ""), row.get("implied_yes_probability"), btc_spot, chainlink_anchor, row.get("horizon_bucket") or "unknown", row.get("family") or "other-btc", row.get("resolution_source") or {})
        else:
            tf = row.get("timeframe") or "15m"
            base = dict(base_signals.get(tf) or base_signals["15m"])
        sig = {
            **row,
            **base,
        }
        signals.append(sig)

    def rank_key(s: Dict[str, Any]):
        conf_rank = {"high": 3, "medium": 2, "low": 1}.get(str(s.get("confidence")), 0)
        return (priority_rank(s), conf_rank, s.get("model_score", 0.0))

    signals.sort(key=rank_key, reverse=True)
    best = signals[0] if signals else None
    regime = base_signals["15m"]["regime"] if base_signals else "n/a"
    blackswan = "triggered" if any(s.get("black_swan") for s in base_signals.values()) else "clear"
    best_yes = next((s for s in signals if s.get("action") == "watch-yes"), None)
    best_no = next((s for s in signals if s.get("action") == "watch-no"), None)
    alert = summarize_alert(signals[:20])

    return {
        "ran_at": utc_now(),
        "btc_spot": btc_spot,
        "chainlink_btc_usd": chainlink_anchor,
        "exchange_spots": {
            "binance": spot_binance,
            "coinbase": spot_coinbase,
            "kraken": spot_kraken,
            "bybit": spot_bybit,
            "coingecko": spot_coingecko,
        },
        "market_universe": {
            "valid_markets": len(market_rows),
            "events_scanned": len(events),
        },
        "best_yes_candidate": best_yes,
        "best_no_candidate": best_no,
        "regime": regime,
        "black_swan_status": blackswan,
        "notes": "Bot now distinguishes between market resolution source and signal source. Binance-referenced markets are evaluated against Binance-style price context; oracle/event-tracker markets are separated so mismatched price logic is less likely.",
        "signals": signals[:20],
        "best_setup": best,
        "alert": alert,
    }


def append_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def handle_inspect_btc(args: argparse.Namespace) -> None:
    payload = inspect_btc_market_universe(limit=args.limit)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"Inspected at: {payload['ran_at']}")
    print(f"BTC events: {payload['event_count']}")
    print(f"BTC markets: {payload['market_count']}")
    print(f"Valid for bot: {payload['valid_count']}")
    print(f"Invalid/skipped: {payload['invalid_count']}")
    if payload['valid']:
        print("\nValid markets:")
        for row in payload['valid'][:10]:
            print(f"- [{row.get('timeframe')}] [{row.get('market_type')}] {row.get('question')}")
    if payload['invalid']:
        print("\nSkipped markets:")
        for row in payload['invalid'][:10]:
            tf = row.get('timeframe') or 'no-tf'
            mt = row.get('market_type') or 'unknown'
            print(f"- [{tf}] [{mt}] {row.get('question')}")


def handle_scan_btc(args: argparse.Namespace) -> None:
    summary = run_scan(limit=args.limit)
    alert = summarize_alert(summary.get("signals", []))
    log_output = getattr(args, "log_output", None)
    if log_output:
        append_jsonl(Path(log_output), summary.get("signals", []))
    if args.summary_output:
        Path(args.summary_output).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if getattr(args, "alert_output", None):
        Path(args.alert_output).write_text(json.dumps(alert, indent=2, ensure_ascii=False), encoding="utf-8")
    dashboard_output = getattr(args, "dashboard_output", None)
    if dashboard_output:
        render_dashboard(summary, Path(dashboard_output))
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return
    print(f"BTC scan completed at {summary['ran_at']}")
    print(f"BTC spot: {summary['btc_spot']}")
    print(f"Chainlink anchor: {summary['chainlink_btc_usd']}")
    print(f"Signals: {len(summary.get('signals', []))}")
    print(f"Actionable signals: {alert['actionable_count']}")
    best = summary.get("best_setup")
    if best:
        print(f"Best setup: [{best['timeframe']}] {best['question']} | {best['bias']} | confidence={best['confidence']} | action={best['action']}")
    else:
        print("Best setup: none")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Polymarket BTC microtrend bot")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect-btc", help="Inspect BTC-related Polymarket markets and classify which ones are valid for the bot")
    inspect.add_argument("--limit", type=int, default=200)
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(func=handle_inspect_btc)

    scan = sub.add_parser("scan-btc", help="Scan BTC-related Polymarket markets with 5m/15m microtrend logic")
    scan.add_argument("--limit", type=int, default=200)
    scan.add_argument("--log-output", default=str(DEFAULT_LOG))
    scan.add_argument("--summary-output", default=str(DEFAULT_SUMMARY))
    scan.add_argument("--dashboard-output", default=str(DEFAULT_DASHBOARD))
    scan.add_argument("--alert-output", default=str(DEFAULT_ALERT))
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=handle_scan_btc)

    auto = sub.add_parser("auto-btc", help="Alias for scan-btc automation mode")
    auto.add_argument("--limit", type=int, default=200)
    auto.add_argument("--log-output", default=str(DEFAULT_LOG))
    auto.add_argument("--summary-output", default=str(DEFAULT_SUMMARY))
    auto.add_argument("--dashboard-output", default=str(DEFAULT_DASHBOARD))
    auto.add_argument("--alert-output", default=str(DEFAULT_ALERT))
    auto.add_argument("--json", action="store_true")
    auto.set_defaults(func=handle_scan_btc)

    fast = sub.add_parser("fast-btc", help="Lightweight BTC scan for quick refresh cadence")
    fast.add_argument("--limit", type=int, default=40)
    fast.add_argument("--summary-output", default=str(DEFAULT_FAST_SUMMARY))
    fast.add_argument("--alert-output", default=str(DEFAULT_ALERT))
    fast.add_argument("--json", action="store_true")
    fast.set_defaults(func=handle_scan_btc)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
