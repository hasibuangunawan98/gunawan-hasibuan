#!/usr/bin/env python3
import argparse
import json
from collections import Counter
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
SPORTS_PRIORS_PATH = ROOT / "assets" / "sports-priors.json"
DEFAULT_SNAPSHOT_PATH = ROOT / "data" / "polymarket-sports-live.json"
DEFAULT_AUTO_LOG_PATH = ROOT / "data" / "ranked-auto-forecasts.jsonl"
DEFAULT_DASHBOARD_PATH = ROOT / "data" / "live-locks-dashboard.html"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; polymarket-forecast-bot/1.0)",
    "Accept": "application/json",
}
SPORTS_LIKE_TERMS = [
    " vs ",
    " vs. ",
    " matchup",
    " grand prix",
    " race",
    " fight",
    " bout",
    " playoffs",
    " qualify",
    " advance",
    " beat the ",
]
ENDGAME_SPORTS = {"soccer", "basketball", "hockey", "american-football", "baseball", "rugby", "handball", "volleyball"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp(value: float, low: float = 0.01, high: float = 0.99) -> float:
    return max(low, min(high, round(value, 4)))


def load_sports_priors() -> Dict[str, Any]:
    with SPORTS_PRIORS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def format_pct(value: Optional[float], signed: bool = False) -> str:
    if value is None:
        return "n/a"
    if signed:
        return f"{value * 100:+.1f}%"
    return f"{value * 100:.1f}%"


def normalize_text(value: str) -> str:
    lowered = value.lower().strip()
    pieces = []
    prev_space = False
    for ch in lowered:
        if ch.isalnum():
            pieces.append(ch)
            prev_space = False
        else:
            if not prev_space:
                pieces.append(" ")
                prev_space = True
    return " ".join("".join(pieces).split())


def fetch_json(url: str) -> Any:
    request = Request(url, headers=HTTP_HEADERS)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_json_string(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_yes_price(market: Dict[str, Any]) -> Optional[float]:
    outcomes = parse_json_string(market.get("outcomes"))
    outcome_prices = parse_json_string(market.get("outcomePrices"))
    if isinstance(outcomes, list) and isinstance(outcome_prices, list) and len(outcomes) == len(outcome_prices):
        for outcome, price in zip(outcomes, outcome_prices):
            if str(outcome).strip().lower() == "yes":
                parsed = safe_float(price)
                if parsed is not None:
                    return clamp(parsed, 0.0, 1.0)
    last_trade = safe_float(market.get("lastTradePrice"))
    if last_trade is not None and 0 <= last_trade <= 1:
        return round(last_trade, 4)
    return None


def canonicalize_sport(sport_input: str, priors: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    requested = sport_input.strip().lower()
    sports = priors["sports"]
    if requested in sports:
        return requested, sports[requested]

    for sport_key, sport_data in sports.items():
        aliases = [a.lower() for a in sport_data.get("aliases", [])]
        if requested in aliases:
            return sport_key, sport_data

    supported = ", ".join(sorted(sports.keys()))
    raise SystemExit(f"Unsupported sport: {sport_input}. Supported sports: {supported}")


def get_profile(sport_key: str, sport_data: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    profiles = sport_data.get("profiles", {})
    profile = profiles.get(profile_name)
    if not profile:
        supported = ", ".join(sorted(profiles.keys()))
        raise SystemExit(f"Unsupported profile '{profile_name}' for sport '{sport_key}'. Supported profiles: {supported}")
    return profile


def analyze_sports_market(args: argparse.Namespace) -> Dict[str, Any]:
    priors = load_sports_priors()
    sport_key, sport_data = canonicalize_sport(args.sport, priors)
    profile = get_profile(sport_key, sport_data, args.profile)

    base_yes = profile.get("favorite_win")
    if base_yes is None:
        raise SystemExit("This profile does not define favorite_win, so it cannot be used for YES/NO analysis.")

    adjustments: List[str] = []
    prob = float(base_yes)
    implied = args.implied_prob if args.implied_prob is not None else None

    if args.favorite_status == "underdog":
        prob = 1 - prob
        adjustments.append("YES side is treated as the underdog, so the profile prior is inverted.")

    if args.home_advantage:
        prob += 0.03 if args.favorite_status == "favorite" else -0.03
        adjustments.append("Applied home-advantage adjustment (+/-3 points).")

    if args.injury_impact:
        prob += args.injury_impact
        direction = "toward" if args.injury_impact >= 0 else "against"
        adjustments.append(f"Applied injury/availability adjustment {direction} YES side ({args.injury_impact * 100:+.1f} points).")

    if args.form_impact:
        prob += args.form_impact
        direction = "toward" if args.form_impact >= 0 else "against"
        adjustments.append(f"Applied form/momentum adjustment {direction} YES side ({args.form_impact * 100:+.1f} points).")

    if args.schedule_impact:
        prob += args.schedule_impact
        direction = "toward" if args.schedule_impact >= 0 else "against"
        adjustments.append(f"Applied schedule/rest adjustment {direction} YES side ({args.schedule_impact * 100:+.1f} points).")

    prob = clamp(prob)
    no_prob = clamp(1 - prob)

    diff = None if implied is None else round(prob - implied, 4)
    if diff is None:
        view = "no pricing check"
    elif abs(diff) < 0.03:
        view = "no edge"
    elif abs(diff) < 0.08:
        view = "possible edge"
    else:
        view = "candidate mispricing"

    confidence = "medium"
    if args.ambiguity_high or args.info_quality == "low":
        confidence = "low"
    elif args.info_quality == "high" and len(adjustments) <= 3 and not args.ambiguity_high:
        confidence = "high"

    why_yes: List[str] = []
    why_no: List[str] = []

    if args.favorite_status == "favorite":
        why_yes.append("YES side starts from the favorite profile prior.")
        why_no.append("Even favorites lose often enough that overconfidence is dangerous.")
    else:
        why_yes.append("YES side can still be live if the market underrates matchup-specific variance.")
        why_no.append("YES side starts from the underdog side of the prior profile.")

    if args.home_advantage:
        if args.favorite_status == "favorite":
            why_yes.append("Home advantage supports the YES side.")
        else:
            why_no.append("Home advantage supports the opposing side.")

    if args.injury_impact > 0:
        why_yes.append("Injury/availability news improves the YES case.")
    elif args.injury_impact < 0:
        why_no.append("Injury/availability news hurts the YES case.")

    if args.form_impact > 0:
        why_yes.append("Recent form/momentum is favorable to YES.")
    elif args.form_impact < 0:
        why_no.append("Recent form/momentum is unfavorable to YES.")

    if args.schedule_impact > 0:
        why_yes.append("Rest/schedule setup helps the YES side.")
    elif args.schedule_impact < 0:
        why_no.append("Rest/schedule setup hurts the YES side.")

    if args.ambiguity_high:
        why_no.append("Market wording or resolution ambiguity lowers reliability.")

    update_triggers = [
        "Lineup/injury news materially changes before the event.",
        "Market price moves sharply without corresponding public evidence.",
        "Weather/venue/map-pool/surface information changes the matchup context.",
    ]

    return {
        "market": args.market,
        "category": "sports",
        "sport": sport_key,
        "aliases": sport_data.get("aliases", []),
        "profile": args.profile,
        "supported_profiles": sorted(sport_data.get("profiles", {}).keys()),
        "common_inputs": sport_data.get("common_inputs", []),
        "yes_probability": prob,
        "no_probability": no_prob,
        "confidence": confidence,
        "market_implied_probability": implied,
        "difference_vs_implied": diff,
        "view": view,
        "prior_notes": profile.get("notes"),
        "adjustments": adjustments,
        "why_yes": why_yes,
        "why_no": why_no,
        "update_triggers": update_triggers,
        "info_quality": args.info_quality,
        "ambiguity_high": args.ambiguity_high,
    }


def build_detection_fields(event: Optional[Dict[str, Any]], market: Optional[Dict[str, Any]]) -> List[str]:
    fields: List[str] = []
    if event:
        for key in ["title", "slug", "ticker", "seriesSlug", "category", "subcategory", "gameStatus"]:
            value = event.get(key)
            if value:
                fields.append(str(value))
        for series in event.get("series", []) or []:
            for key in ["title", "slug", "ticker"]:
                value = series.get(key)
                if value:
                    fields.append(str(value))
        for tag in event.get("tags", []) or []:
            for key in ["label", "slug"]:
                value = tag.get(key)
                if value:
                    fields.append(str(value))
    if market:
        for key in ["question", "slug", "category", "sportsMarketType", "gameId"]:
            value = market.get(key)
            if value:
                fields.append(str(value))
    return [field for field in fields if field]


def classify_live_market(event: Optional[Dict[str, Any]], market: Optional[Dict[str, Any]], priors: Dict[str, Any]) -> Dict[str, Any]:
    raw_fields = build_detection_fields(event, market)
    normalized_fields = [normalize_text(field) for field in raw_fields if field]
    joined = " | ".join(normalized_fields)

    best_sport: Optional[str] = None
    best_score = 0
    best_hits: List[str] = []

    for sport_key, sport_data in priors["sports"].items():
        terms = [sport_key] + sport_data.get("aliases", [])
        score = 0
        hits: List[str] = []
        for term in terms:
            normalized_term = normalize_text(term)
            if not normalized_term:
                continue
            exact_hit = any(field == normalized_term for field in normalized_fields)
            word_hit = any(f" {normalized_term} " in f" {field} " for field in normalized_fields)
            contains_hit = normalized_term in joined
            if exact_hit:
                score += 8
                hits.append(term)
            elif word_hit:
                score += 5
                hits.append(term)
            elif contains_hit:
                score += 3
                hits.append(term)
        if score > best_score:
            best_sport = sport_key
            best_score = score
            best_hits = sorted(set(hits))

    corpus = f" {joined} "
    sports_like = any(term in corpus for term in SPORTS_LIKE_TERMS)
    if event and event.get("gameStatus"):
        sports_like = True
    if market and (market.get("sportsMarketType") or market.get("gameId") or market.get("teamAID") or market.get("teamBID")):
        sports_like = True

    if best_sport and best_score >= 3:
        if best_score >= 8:
            confidence = "high"
        elif best_score >= 5:
            confidence = "medium"
        else:
            confidence = "low"
        return {
            "is_sports": True,
            "sport": best_sport,
            "confidence": confidence,
            "score": best_score,
            "hits": best_hits,
        }

    if sports_like:
        return {
            "is_sports": True,
            "sport": "unknown-sport",
            "confidence": "low",
            "score": 1,
            "hits": ["sports-like wording or game metadata"],
        }

    return {
        "is_sports": False,
        "sport": None,
        "confidence": "none",
        "score": 0,
        "hits": [],
    }


def flatten_live_event(event: Dict[str, Any], priors: Dict[str, Any], include_unknown: bool = True) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    markets = event.get("markets", []) or []
    for market in markets:
        detection = classify_live_market(event, market, priors)
        if not detection["is_sports"]:
            continue
        if detection["sport"] == "unknown-sport" and not include_unknown:
            continue

        implied_yes = extract_yes_price(market)
        series = event.get("series", []) or []
        series_titles = [s.get("title") for s in series if s.get("title")]
        series_tickers = [s.get("ticker") for s in series if s.get("ticker")]
        item = {
            "event_id": event.get("id"),
            "event_title": event.get("title"),
            "event_slug": event.get("slug"),
            "market_id": market.get("id"),
            "market_question": market.get("question"),
            "market_slug": market.get("slug"),
            "sport": detection["sport"],
            "detection_confidence": detection["confidence"],
            "detection_hits": detection["hits"],
            "series_slug": event.get("seriesSlug"),
            "series_titles": series_titles,
            "series_tickers": series_tickers,
            "event_end_date": event.get("endDate"),
            "market_end_date": market.get("endDate"),
            "volume": market.get("volumeNum") or safe_float(market.get("volume")),
            "liquidity": market.get("liquidityNum") or safe_float(market.get("liquidity")),
            "last_trade_price": safe_float(market.get("lastTradePrice")),
            "best_bid": safe_float(market.get("bestBid")),
            "best_ask": safe_float(market.get("bestAsk")),
            "implied_yes_probability": implied_yes,
            "sports_market_type": market.get("sportsMarketType"),
            "line": market.get("line"),
            "game_status": event.get("gameStatus"),
            "live": event.get("live"),
            "url": f"https://polymarket.com/event/{event.get('slug')}" if event.get("slug") else None,
        }
        items.append(item)
    return items


def fetch_live_events(per_page: int, pages: int, closed: bool = False) -> List[Dict[str, Any]]:
    all_events: List[Dict[str, Any]] = []
    for page in range(pages):
        params = {
            "closed": str(closed).lower(),
            "limit": per_page,
            "offset": page * per_page,
            "order": "endDate",
            "ascending": "true",
        }
        url = f"{GAMMA_API_BASE}/events?{urlencode(params)}"
        payload = fetch_json(url)
        if not isinstance(payload, list) or not payload:
            break
        all_events.extend(payload)
        if len(payload) < per_page:
            break
    return all_events


def build_live_snapshot(events: List[Dict[str, Any]], priors: Dict[str, Any], include_unknown: bool) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for event in events:
        items.extend(flatten_live_event(event, priors, include_unknown=include_unknown))

    unique_items: List[Dict[str, Any]] = []
    seen_market_ids = set()
    for item in items:
        market_id = item.get("market_id")
        if market_id in seen_market_ids:
            continue
        seen_market_ids.add(market_id)
        unique_items.append(item)

    unique_items.sort(
        key=lambda item: (
            item.get("sport") or "",
            item.get("market_end_date") or "",
            -(item.get("volume") or 0),
        )
    )

    counts = Counter(item.get("sport") or "unknown-sport" for item in unique_items)
    return {
        "generated_at": utc_now(),
        "source": f"{GAMMA_API_BASE}/events",
        "ordering": {"order": "endDate", "ascending": True, "closed": False},
        "items": unique_items,
        "counts_by_sport": dict(sorted(counts.items())),
        "total_items": len(unique_items),
    }


def save_snapshot(snapshot: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)


def extract_slug_from_ref(ref: str) -> str:
    ref = ref.strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        parsed = urlparse(ref)
        parts = [part for part in parsed.path.split("/") if part]
        if not parts:
            raise SystemExit(f"Could not extract slug from URL: {ref}")
        return parts[-1]
    return ref


def fetch_market_by_slug(slug: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    market_url = f"{GAMMA_API_BASE}/markets?{urlencode({'slug': slug})}"
    markets = fetch_json(market_url)
    if isinstance(markets, list) and markets:
        market = markets[0]
        event = None
        events = market.get("events") or []
        if events:
            event = events[0]
        return market, event

    event_url = f"{GAMMA_API_BASE}/events?{urlencode({'slug': slug})}"
    events = fetch_json(event_url)
    if isinstance(events, list) and events:
        event = events[0]
        markets = event.get("markets") or []
        market = markets[0] if markets else None
        return market, event

    return None, None


def print_markdown_report(result: Dict[str, Any]) -> None:
    print("### Market")
    print(f"- Restated market: {result['market']}")
    print(f"- Category: {result['category']} / {result['sport']}")
    print(f"- Prior profile: {result['profile']}")
    print()
    print("### Estimate")
    print(f"- YES probability: {format_pct(result['yes_probability'])}")
    print(f"- NO probability: {format_pct(result['no_probability'])}")
    print(f"- Confidence: {result['confidence']}")
    print()
    print("### Why YES")
    if result["why_yes"]:
        for item in result["why_yes"]:
            print(f"- {item}")
    else:
        print("- No strong YES case identified yet.")
    print()
    print("### Why NO")
    if result["why_no"]:
        for item in result["why_no"]:
            print(f"- {item}")
    else:
        print("- No strong NO case identified yet.")
    print()
    print("### Pricing check")
    print(f"- Current market implied probability: {format_pct(result['market_implied_probability'])}")
    diff = result["difference_vs_implied"]
    print(f"- Difference vs estimate: {format_pct(diff, signed=True) if diff is not None else 'n/a'}")
    print(f"- View: {result['view']}")
    print()
    print("### Adjustments")
    if result["adjustments"]:
        for item in result["adjustments"]:
            print(f"- {item}")
    else:
        print(f"- No manual adjustments. Using prior notes: {result['prior_notes']}")
    print()
    print("### Sport inputs to check")
    if result["common_inputs"]:
        for item in result["common_inputs"]:
            print(f"- {item}")
    else:
        print("- No sport-specific inputs listed.")
    print()
    print("### What would change the forecast")
    for item in result["update_triggers"]:
        print(f"- {item}")


def handle_sports(args: argparse.Namespace) -> None:
    result = analyze_sports_market(args)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_markdown_report(result)


def handle_list_sports(_: argparse.Namespace) -> None:
    priors = load_sports_priors()
    for sport_key in sorted(priors["sports"].keys()):
        sport_data = priors["sports"][sport_key]
        aliases = ", ".join(sport_data.get("aliases", [])) or "-"
        profiles = ", ".join(sorted(sport_data.get("profiles", {}).keys())) or "-"
        print(f"- {sport_key}")
        print(f"  aliases: {aliases}")
        print(f"  profiles: {profiles}")


def handle_sync_live_sports(args: argparse.Namespace) -> None:
    priors = load_sports_priors()
    events = fetch_live_events(per_page=args.per_page, pages=args.pages, closed=args.closed)
    snapshot = build_live_snapshot(events, priors, include_unknown=args.include_unknown)
    output_path = Path(args.output) if args.output else DEFAULT_SNAPSHOT_PATH
    save_snapshot(snapshot, output_path)

    if args.json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        return

    print(f"Saved live sports snapshot to: {output_path}")
    print(f"Generated at: {snapshot['generated_at']}")
    print(f"Total sports-like markets found: {snapshot['total_items']}")
    print("Counts by sport:")
    for sport, count in snapshot["counts_by_sport"].items():
        print(f"- {sport}: {count}")
    print("\nSample markets:")
    for item in snapshot["items"][: min(10, len(snapshot["items"]))]:
        print(
            f"- [{item['sport']}] {item.get('market_question') or item.get('event_title')}"
            f" | implied_yes={format_pct(item.get('implied_yes_probability'))}"
            f" | end={item.get('market_end_date') or item.get('event_end_date')}"
        )


def inspect_live_market_payload(ref: str, priors: Dict[str, Any]) -> Dict[str, Any]:
    slug = extract_slug_from_ref(ref)
    market, event = fetch_market_by_slug(slug)
    if not market and not event:
        raise SystemExit(f"No market or event found for reference: {ref}")

    detection = classify_live_market(event, market, priors)
    return {
        "ref": ref,
        "slug": slug,
        "detected_sport": detection["sport"],
        "detection_confidence": detection["confidence"],
        "detection_hits": detection["hits"],
        "event_title": event.get("title") if event else None,
        "event_slug": event.get("slug") if event else None,
        "series_slug": event.get("seriesSlug") if event else None,
        "market_question": market.get("question") if market else None,
        "market_slug": market.get("slug") if market else None,
        "implied_yes_probability": extract_yes_price(market or {}),
        "last_trade_price": safe_float((market or {}).get("lastTradePrice")),
        "best_bid": safe_float((market or {}).get("bestBid")),
        "best_ask": safe_float((market or {}).get("bestAsk")),
        "market_end_date": (market or {}).get("endDate"),
        "sports_market_type": (market or {}).get("sportsMarketType"),
        "line": (market or {}).get("line"),
        "game_status": (event or {}).get("gameStatus"),
        "live": (event or {}).get("live"),
        "url": f"https://polymarket.com/event/{event.get('slug')}" if event and event.get("slug") else None,
    }


def infer_profile_from_implied(implied_yes: Optional[float]) -> str:
    if implied_yes is None:
        return "default"
    distance = abs(implied_yes - 0.5)
    if distance >= 0.18:
        return "heavy_favorite"
    if distance <= 0.08:
        return "balanced_match"
    return "default"


def infer_favorite_status_from_implied(implied_yes: Optional[float]) -> str:
    if implied_yes is None:
        return "favorite"
    return "favorite" if implied_yes >= 0.5 else "underdog"


def auto_forecast_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if not 0 <= args.anchor_to_market <= 1:
        raise SystemExit("--anchor-to-market must be between 0 and 1.")

    priors = load_sports_priors()
    inspected = inspect_live_market_payload(args.ref, priors)
    detected_sport = args.sport or inspected.get("detected_sport")
    if not detected_sport or detected_sport == "unknown-sport":
        raise SystemExit("Could not confidently detect sport for this market. Re-run with --sport <sport> to override.")

    sport_key, sport_data = canonicalize_sport(detected_sport, priors)
    implied_yes = inspected.get("implied_yes_probability")
    profile_name = args.profile or infer_profile_from_implied(implied_yes)
    favorite_status = args.favorite_status or infer_favorite_status_from_implied(implied_yes)
    profile = get_profile(sport_key, sport_data, profile_name)

    base_yes = profile.get("favorite_win")
    if base_yes is None:
        raise SystemExit("Selected sport profile does not define favorite_win.")

    forecast_yes = float(base_yes)
    adjustments: List[str] = [f"Base profile '{profile_name}' selected from implied-market context."]

    if favorite_status == "underdog":
        forecast_yes = 1 - forecast_yes
        adjustments.append("YES side inferred as underdog from market pricing, so prior is inverted.")
    else:
        adjustments.append("YES side inferred as favorite/even side from market pricing.")

    if args.home_advantage:
        forecast_yes += 0.03 if favorite_status == "favorite" else -0.03
        adjustments.append("Applied home-advantage adjustment (+/-3 points).")

    if args.injury_impact:
        forecast_yes += args.injury_impact
        direction = "toward" if args.injury_impact >= 0 else "against"
        adjustments.append(f"Applied injury/availability adjustment {direction} YES side ({args.injury_impact * 100:+.1f} points).")

    if args.form_impact:
        forecast_yes += args.form_impact
        direction = "toward" if args.form_impact >= 0 else "against"
        adjustments.append(f"Applied form/momentum adjustment {direction} YES side ({args.form_impact * 100:+.1f} points).")

    if args.schedule_impact:
        forecast_yes += args.schedule_impact
        direction = "toward" if args.schedule_impact >= 0 else "against"
        adjustments.append(f"Applied schedule/rest adjustment {direction} YES side ({args.schedule_impact * 100:+.1f} points).")

    if implied_yes is not None and args.anchor_to_market > 0:
        anchored = ((1 - args.anchor_to_market) * forecast_yes) + (args.anchor_to_market * implied_yes)
        adjustments.append(f"Anchored forecast {args.anchor_to_market * 100:.0f}% toward market implied probability.")
        forecast_yes = anchored

    forecast_yes = clamp(forecast_yes)
    forecast_no = clamp(1 - forecast_yes)
    diff = None if implied_yes is None else round(forecast_yes - implied_yes, 4)

    if diff is None:
        view = "no pricing check"
    elif abs(diff) < 0.03:
        view = "no edge"
    elif abs(diff) < 0.08:
        view = "possible edge"
    else:
        view = "candidate mispricing"

    confidence = "medium"
    if inspected.get("detection_confidence") == "low" or args.info_quality == "low":
        confidence = "low"
    elif args.info_quality == "high" and inspected.get("detection_confidence") in {"medium", "high"}:
        confidence = "high"

    why_yes: List[str] = []
    why_no: List[str] = []
    if favorite_status == "favorite":
        why_yes.append("YES side is being treated as the favorite or near-favorite from current market pricing.")
        why_no.append("Favorites still lose often enough that implied price can overstate certainty.")
    else:
        why_yes.append("YES side is being treated as the underdog, which can still create value if the market overreacts.")
        why_no.append("YES side starts from the underdog side of the chosen prior.")

    if args.injury_impact > 0:
        why_yes.append("Injury or availability context improves the YES case.")
    elif args.injury_impact < 0:
        why_no.append("Injury or availability context hurts the YES case.")
    if args.form_impact > 0:
        why_yes.append("Recent form/momentum supports the YES case.")
    elif args.form_impact < 0:
        why_no.append("Recent form/momentum weakens the YES case.")
    if args.schedule_impact > 0:
        why_yes.append("Schedule/rest setup supports YES.")
    elif args.schedule_impact < 0:
        why_no.append("Schedule/rest setup hurts YES.")

    if not why_yes:
        why_yes.append("The initial edge comes mainly from the chosen prior/profile rather than strong manual adjustments.")
    if not why_no:
        why_no.append("This remains a heuristic forecast and may miss lineup, injury, or live context.")

    return {
        "reference": inspected,
        "sport": sport_key,
        "profile": profile_name,
        "favorite_status": favorite_status,
        "prior_notes": profile.get("notes"),
        "common_inputs": sport_data.get("common_inputs", []),
        "yes_probability": forecast_yes,
        "no_probability": forecast_no,
        "market_implied_probability": implied_yes,
        "difference_vs_implied": diff,
        "view": view,
        "confidence": confidence,
        "adjustments": adjustments,
        "why_yes": why_yes,
        "why_no": why_no,
        "anchor_to_market": args.anchor_to_market,
        "info_quality": args.info_quality,
    }


def auto_forecast_from_snapshot_item(
    item: Dict[str, Any],
    priors: Dict[str, Any],
    *,
    profile_override: Optional[str] = None,
    favorite_status_override: Optional[str] = None,
    info_quality: str = "medium",
    anchor_to_market: float = 0.25,
) -> Dict[str, Any]:
    if not 0 <= anchor_to_market <= 1:
        raise SystemExit("anchor_to_market must be between 0 and 1.")

    detected_sport = item.get("sport")
    if not detected_sport or detected_sport == "unknown-sport":
        raise SystemExit("Snapshot item does not map to a specific known sport.")

    sport_key, sport_data = canonicalize_sport(detected_sport, priors)
    implied_yes = item.get("implied_yes_probability")
    profile_name = profile_override or infer_profile_from_implied(implied_yes)
    favorite_status = favorite_status_override or infer_favorite_status_from_implied(implied_yes)
    profile = get_profile(sport_key, sport_data, profile_name)
    base_yes = profile.get("favorite_win")
    if base_yes is None:
        raise SystemExit("Selected sport profile does not define favorite_win.")

    forecast_yes = float(base_yes)
    adjustments: List[str] = [f"Base profile '{profile_name}' selected from implied-market context."]
    if favorite_status == "underdog":
        forecast_yes = 1 - forecast_yes
        adjustments.append("YES side inferred as underdog from market pricing, so prior is inverted.")
    else:
        adjustments.append("YES side inferred as favorite/even side from market pricing.")

    if implied_yes is not None and anchor_to_market > 0:
        forecast_yes = ((1 - anchor_to_market) * forecast_yes) + (anchor_to_market * implied_yes)
        adjustments.append(f"Anchored forecast {anchor_to_market * 100:.0f}% toward market implied probability.")

    forecast_yes = clamp(forecast_yes)
    forecast_no = clamp(1 - forecast_yes)
    diff = None if implied_yes is None else round(forecast_yes - implied_yes, 4)
    edge_abs = abs(diff) if diff is not None else 0.0
    volume = item.get("volume") or 0.0
    liquidity = item.get("liquidity") or 0.0
    score = round((edge_abs * 100) + min(float(liquidity) / 1000.0, 20) + min(float(volume) / 10000.0, 20), 4)

    if diff is None:
        view = "no pricing check"
    elif edge_abs < 0.03:
        view = "no edge"
    elif edge_abs < 0.08:
        view = "possible edge"
    else:
        view = "candidate mispricing"

    confidence = "medium"
    detection_conf = item.get("detection_confidence")
    if detection_conf == "low" or info_quality == "low":
        confidence = "low"
    elif detection_conf in {"medium", "high"} and info_quality == "high":
        confidence = "high"

    return {
        "market_id": item.get("market_id"),
        "market_question": item.get("market_question"),
        "market_slug": item.get("market_slug"),
        "event_title": item.get("event_title"),
        "event_slug": item.get("event_slug"),
        "url": item.get("url"),
        "sport": sport_key,
        "profile": profile_name,
        "favorite_status": favorite_status,
        "yes_probability": forecast_yes,
        "no_probability": forecast_no,
        "market_implied_probability": implied_yes,
        "difference_vs_implied": diff,
        "edge_abs": round(edge_abs, 4),
        "view": view,
        "confidence": confidence,
        "score": score,
        "volume": volume,
        "liquidity": liquidity,
        "prior_notes": profile.get("notes"),
        "common_inputs": sport_data.get("common_inputs", []),
        "detection_confidence": detection_conf,
        "detection_hits": item.get("detection_hits", []),
        "adjustments": adjustments,
    }


def load_snapshot(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_clock_minutes(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    digits = []
    current = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            current += ch
        else:
            if current:
                digits.append(current)
                current = ""
    if current:
        digits.append(current)
    if not digits:
        return None
    try:
        nums = [float(x) for x in digits]
    except ValueError:
        return None
    if ":" in text and len(nums) >= 2:
        return nums[0] + (nums[1] / 60.0)
    return nums[0]


def infer_minutes_remaining(item: Dict[str, Any]) -> Optional[float]:
    candidates = [
        item.get("clock"),
        item.get("time_remaining"),
        item.get("remaining"),
        item.get("gameClock"),
        item.get("game_clock"),
        item.get("status_detail"),
        item.get("game_status"),
        item.get("market_question"),
        item.get("event_title"),
    ]
    lowered = " | ".join(str(v) for v in candidates if v)
    lowered_l = lowered.lower()
    if "ft" in lowered_l or "final" in lowered_l:
        return 0.0
    minute = parse_clock_minutes(lowered)
    if minute is None:
        return None

    sport = item.get("sport")
    total_minutes = {
        "soccer": 90,
        "basketball": 48,
        "hockey": 60,
        "american-football": 60,
        "rugby": 80,
        "handball": 60,
        "volleyball": 100,
        "baseball": 54,
    }.get(sport)
    if total_minutes is None:
        return None

    if "remaining" in lowered_l or "left" in lowered_l or "to go" in lowered_l:
        return minute
    if minute > total_minutes + 5:
        return 0.0
    return max(0.0, total_minutes - minute)


def parse_score_from_text(text: str) -> Optional[Tuple[int, int]]:
    if not text:
        return None
    for sep in ["-", "–", ":"]:
        if sep in text:
            parts = text.split(sep)
            for i in range(len(parts) - 1):
                left_digits = "".join(ch for ch in parts[i] if ch.isdigit())
                right_digits = "".join(ch for ch in parts[i + 1] if ch.isdigit())
                if left_digits and right_digits:
                    try:
                        return int(left_digits), int(right_digits)
                    except ValueError:
                        continue
    return None


def infer_score_state(item: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    direct_pairs = [
        (item.get("home_score"), item.get("away_score")),
        (item.get("score_home"), item.get("score_away")),
    ]
    for left, right in direct_pairs:
        if left is not None and right is not None:
            try:
                return int(left), int(right)
            except (TypeError, ValueError):
                pass

    texts = [
        str(item.get("score") or ""),
        str(item.get("status_detail") or ""),
        str(item.get("market_question") or ""),
        str(item.get("event_title") or ""),
    ]
    for text in texts:
        parsed = parse_score_from_text(text)
        if parsed:
            return parsed
    return None


def compute_endgame_lock_probability(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sport = item.get("sport")
    if sport not in ENDGAME_SPORTS:
        return None
    remaining = infer_minutes_remaining(item)
    score = infer_score_state(item)
    implied = item.get("implied_yes_probability")
    if remaining is None or score is None or implied is None:
        return None

    left, right = score
    margin = abs(left - right)
    if margin <= 0:
        return None

    yes_is_favorite = implied >= 0.5
    leader_side = "yes" if yes_is_favorite else "no"
    rationale = [f"Late-game state detected with ~{remaining:.1f} minutes remaining.", f"Current score margin is {margin}."]
    probability: Optional[float] = None

    if sport == "soccer":
        if remaining <= 5 and margin >= 2:
            probability = 0.90 + min(0.07, max(0.0, (5 - remaining)) * 0.01)
            rationale.append("Soccer rule: 2+ goal lead inside the last ~5 minutes is treated as a strong lock.")
        elif remaining <= 3 and margin >= 1:
            probability = 0.88 + min(0.04, max(0.0, (3 - remaining)) * 0.01)
            rationale.append("Soccer rule: 1-goal lead inside the last ~3 minutes is elevated but slightly weaker.")
    elif sport == "basketball":
        if remaining <= 2 and margin >= 8:
            probability = 0.92 + min(0.05, max(0.0, (2 - remaining)) * 0.02)
            rationale.append("Basketball rule: multi-possession lead inside the last 2 minutes is close to locked.")
        elif remaining <= 1 and margin >= 6:
            probability = 0.90 + min(0.04, max(0.0, (1 - remaining)) * 0.02)
            rationale.append("Basketball rule: 6+ lead inside the final minute is treated as a high-confidence closeout spot.")
    elif sport == "american-football":
        if remaining <= 2 and margin >= 10:
            probability = 0.93
            rationale.append("American football rule: 10+ lead inside 2 minutes is a near-lock.")
        elif remaining <= 1 and margin >= 8:
            probability = 0.90
            rationale.append("American football rule: 8+ lead inside the final minute is a strong lock.")
    elif sport == "hockey":
        if remaining <= 3 and margin >= 2:
            probability = 0.91 + min(0.05, max(0.0, (3 - remaining)) * 0.015)
            rationale.append("Hockey rule: 2-goal lead late in the 3rd period is a strong lock state.")
    elif sport == "baseball":
        if remaining <= 3 and margin >= 2:
            probability = 0.90
            rationale.append("Baseball rule: late-inning 2+ run lead is treated as highly stable.")
    elif sport in {"rugby", "handball"}:
        if remaining <= 3 and margin >= 8:
            probability = 0.91
            rationale.append(f"{sport} rule: large lead with under 3 minutes left is near-locked.")
    elif sport == "volleyball":
        if remaining <= 3 and margin >= 4:
            probability = 0.90
            rationale.append("Volleyball rule: late set/game 4+ point lead is treated as near-locked.")

    if probability is None:
        return None

    probability = clamp(probability, 0.01, 0.99)
    edge = round(probability - implied, 4) if leader_side == "yes" else round((1 - probability) - implied, 4)
    rationale.append(f"Computed heuristic lock probability: {probability * 100:.1f}%.")

    return {
        "sport": sport,
        "minutes_remaining": round(remaining, 2),
        "score": {"left": left, "right": right, "margin": margin},
        "leader_side": leader_side,
        "win_probability": probability,
        "market_implied_probability": implied,
        "edge": edge,
        "rationale": rationale,
    }


def stable_market_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def append_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_recent_jsonl(path: Optional[Path], limit: int = 30) -> List[Dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]


def html_escape(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_dashboard_html(summary: Dict[str, Any], log_path: Optional[Path], snapshot_path: Path, output_path: Path, summary_path: Path, log_limit: int = 30) -> None:
    template_path = ROOT / "assets" / "dashboard.html"
    template = template_path.read_text(encoding="utf-8")
    top_items = summary.get("top", [])
    log_rows = load_recent_jsonl(log_path, limit=log_limit)

    def conf_pill(conf: str) -> str:
        conf_key = (conf or "unknown").lower()
        klass = "info"
        if conf_key == "high":
            klass = "good"
        elif conf_key == "medium":
            klass = "warn"
        elif conf_key == "low":
            klass = "bad"
        return f'<span class="pill {klass}">{html_escape(conf_key.title())}</span>'

    def top_cards_html() -> str:
        if not top_items:
            return '<div class="empty-state"><h3>No live locks found yet</h3><div class="footnote">The scanner is active, but no current live sports market matches the strict 90%+ endgame-lock rules.</div><ul><li>No suitable late-game state was detected</li><li>Score margin may still be too small</li><li>Too much time may still remain</li></ul></div>'
        parts = []
        for row in top_items:
            score = row.get("score")
            score_text = f"{score:.2f}" if isinstance(score, (int, float)) else "n/a"
            parts.append(
                "<article class=\"card\">"
                "<div class=\"card-top\">"
                f"<div><div class=\"title\">{html_escape(row.get('market_question') or 'Unknown market')}</div><div class=\"footnote\">{html_escape(row.get('sport') or 'unknown')}</div></div>"
                f"{conf_pill(str(row.get('confidence') or 'unknown'))}"
                "</div>"
                "<div class=\"stats\">"
                f"<div class=\"stat\"><small>Score</small><strong>{score_text}</strong></div>"
                f"<div class=\"stat\"><small>Edge</small><strong>{format_pct(row.get('difference_vs_implied'), signed=True)}</strong></div>"
                f"<div class=\"stat\"><small>View</small><strong>{html_escape(row.get('view') or 'n/a')}</strong></div>"
                "</div>"
                f"<a href=\"{html_escape(row.get('url') or '#')}\">{html_escape(row.get('url') or '#')}</a>"
                "</article>"
            )
        return "\n".join(parts)

    def log_rows_html() -> str:
        if not log_rows:
            return '<tr><td colspan="8">No log rows yet. Run auto-cycle first.</td></tr>'
        parts = []
        for row in log_rows:
            try:
                edge_abs = abs(float(row.get("difference_vs_implied") or 0.0))
            except (TypeError, ValueError):
                edge_abs = 0.0
            heat = "low"
            if edge_abs >= 0.12:
                heat = "high"
            elif edge_abs >= 0.05:
                heat = "medium"
            score_value = row.get('score') or 0
            parts.append(
                f"<tr data-time=\"{html_escape(row.get('logged_at') or '')}\" data-score=\"{html_escape(score_value)}\" data-edge=\"{html_escape(edge_abs)}\" data-confidence=\"{html_escape(str(row.get('confidence') or '').lower())}\">"
                f"<td>{html_escape(row.get('logged_at') or 'n/a')}</td>"
                f"<td>{html_escape(row.get('market_question') or 'n/a')}</td>"
                f"<td>{html_escape(row.get('sport') or 'n/a')}</td>"
                f"<td>{html_escape(row.get('score') or 'n/a')}</td>"
                f"<td>{html_escape(format_pct(row.get('difference_vs_implied'), signed=True))}</td>"
                f"<td>{html_escape(row.get('confidence') or 'n/a')}</td>"
                f"<td><span class=\"heat {heat}\">{html_escape(heat.upper())}</span></td>"
                f"<td><a href=\"{html_escape(row.get('url') or '#')}\">open</a></td>"
                "</tr>"
            )
        return "\n".join(parts)

    def edge_chart_html() -> str:
        points = []
        for idx, row in enumerate(log_rows[:20]):
            try:
                edge = abs(float(row.get("difference_vs_implied") or 0.0))
            except (TypeError, ValueError):
                edge = 0.0
            points.append((idx, edge))
        if not points:
            return '<div class="footnote">No edge history yet.</div>'
        width, height = 640, 220
        max_edge = max(edge for _, edge in points) or 1.0
        coords = []
        for idx, edge in points:
            x = 30 + (idx / max(len(points) - 1, 1)) * (width - 60)
            y = height - 30 - ((edge / max_edge) * (height - 60))
            coords.append((x, y))
        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#6ee7ff" />' for x, y in coords)
        return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Edge history chart"><line x1="30" y1="190" x2="610" y2="190" stroke="rgba(255,255,255,.15)" /><line x1="30" y1="30" x2="30" y2="190" stroke="rgba(255,255,255,.15)" /><polyline fill="none" stroke="#6ee7ff" stroke-width="3" points="{polyline}" />{circles}</svg>'

    def top_movers_html() -> str:
        if not log_rows:
            return '<div class="footnote">No recent movers yet.</div>'
        sortable = []
        for row in log_rows:
            try:
                edge = abs(float(row.get("difference_vs_implied") or 0.0))
            except (TypeError, ValueError):
                edge = 0.0
            sortable.append((edge, row))
        sortable.sort(key=lambda item: item[0], reverse=True)
        parts = []
        for _, row in sortable[:5]:
            parts.append(
                f'<div class="footnote" style="margin-top:10px;"><strong>{html_escape(row.get("market_question") or "n/a")}</strong><br>edge {format_pct(row.get("difference_vs_implied"), signed=True)} · score {html_escape(row.get("score") or "n/a")}</div>'
            )
        return "".join(parts)

    best_edge = "n/a"
    if log_rows:
        try:
            best_row = max(log_rows, key=lambda r: abs(float(r.get("difference_vs_implied") or 0.0)))
            best_edge = format_pct(best_row.get("difference_vs_implied"), signed=True)
        except (TypeError, ValueError):
            best_edge = "n/a"
    high_conf_count = sum(1 for row in log_rows if str(row.get("confidence") or "").lower() == "high")

    best_bet = top_items[0] if top_items else {}
    replacements = {
        "{{LAST_RUN}}": html_escape(summary.get("ran_at") or "No data"),
        "{{COUNT}}": html_escape(summary.get("count") or 0),
        "{{SPORT_FILTER}}": html_escape(summary.get("sport_filter") or "all sports"),
        "{{TOP_CARDS}}": top_cards_html(),
        "{{LOG_ROWS}}": log_rows_html(),
        "{{SUMMARY_PATH}}": html_escape(summary_path),
        "{{LOG_PATH}}": html_escape(log_path or "n/a"),
        "{{SNAPSHOT_PATH}}": html_escape(snapshot_path),
        "{{BEST_EDGE}}": html_escape(best_edge),
        "{{HIGH_CONF_COUNT}}": html_escape(high_conf_count),
        "{{RECENT_ROWS}}": html_escape(len(log_rows)),
        "{{EDGE_CHART}}": edge_chart_html(),
        "{{TOP_MOVERS}}": top_movers_html(),
        "{{BEST_BET_MARKET}}": html_escape(best_bet.get("market_question") or "No candidate yet"),
        "{{BEST_BET_EDGE}}": html_escape(format_pct(best_bet.get("difference_vs_implied"), signed=True)),
        "{{BEST_BET_SCORE}}": html_escape(best_bet.get("score") or "n/a"),
        "{{BEST_BET_SPORT}}": html_escape(best_bet.get("sport") or "n/a"),
    }

    rendered = template
    for old, new in replacements.items():
        rendered = rendered.replace(old, new)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")


def handle_inspect_live_market(args: argparse.Namespace) -> None:
    priors = load_sports_priors()
    payload = inspect_live_market_payload(args.ref, priors)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print("### Live market inspection")
    print(f"- Reference: {args.ref}")
    print(f"- Event: {payload['event_title']}")
    print(f"- Market: {payload['market_question']}")
    print(f"- Detected sport: {payload['detected_sport']}")
    print(f"- Detection confidence: {payload['detection_confidence']}")
    print(f"- Detection hits: {', '.join(payload['detection_hits']) if payload['detection_hits'] else 'n/a'}")
    print(f"- Implied YES probability: {format_pct(payload['implied_yes_probability'])}")
    print(f"- Last trade price: {payload['last_trade_price'] if payload['last_trade_price'] is not None else 'n/a'}")
    print(f"- Best bid / ask: {payload['best_bid'] if payload['best_bid'] is not None else 'n/a'} / {payload['best_ask'] if payload['best_ask'] is not None else 'n/a'}")
    print(f"- Market end date: {payload['market_end_date']}")
    print(f"- Live/game status: {payload['live']} / {payload['game_status']}")
    print(f"- URL: {payload['url']}")


def handle_auto_forecast_live(args: argparse.Namespace) -> None:
    payload = auto_forecast_payload(args)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    ref = payload["reference"]
    print("### Live market")
    print(f"- Reference: {ref['ref']}")
    print(f"- Event: {ref['event_title']}")
    print(f"- Market: {ref['market_question']}")
    print(f"- Detected sport: {payload['sport']}")
    print(f"- Detection confidence: {ref['detection_confidence']}")
    print(f"- Detection hits: {', '.join(ref['detection_hits']) if ref['detection_hits'] else 'n/a'}")
    print()
    print("### Forecast scaffold")
    print(f"- Profile: {payload['profile']}")
    print(f"- YES side treated as: {payload['favorite_status']}")
    print(f"- YES probability: {format_pct(payload['yes_probability'])}")
    print(f"- NO probability: {format_pct(payload['no_probability'])}")
    print(f"- Confidence: {payload['confidence']}")
    print()
    print("### Pricing check")
    print(f"- Current market implied probability: {format_pct(payload['market_implied_probability'])}")
    diff = payload['difference_vs_implied']
    print(f"- Difference vs forecast: {format_pct(diff, signed=True) if diff is not None else 'n/a'}")
    print(f"- View: {payload['view']}")
    print()
    print("### Why YES")
    for item in payload['why_yes']:
        print(f"- {item}")
    print()
    print("### Why NO")
    for item in payload['why_no']:
        print(f"- {item}")
    print()
    print("### Adjustments")
    for item in payload['adjustments']:
        print(f"- {item}")
    print()
    print("### Sport inputs to check next")
    for item in payload['common_inputs']:
        print(f"- {item}")
    print()
    print("### Notes")
    print(f"- Prior notes: {payload['prior_notes']}")
    print("- This is an initial heuristic forecast scaffold, not a guaranteed edge.")
    print("- Re-run with injury/form/schedule inputs for a sharper estimate.")


def run_rank_live_markets(args: argparse.Namespace) -> Dict[str, Any]:
    priors = load_sports_priors()
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists() or args.refresh:
        events = fetch_live_events(per_page=args.per_page, pages=args.pages, closed=args.closed)
        snapshot = build_live_snapshot(events, priors, include_unknown=args.include_unknown)
        save_snapshot(snapshot, snapshot_path)
    else:
        snapshot = load_snapshot(snapshot_path)

    items = snapshot.get("items", [])
    ranked: List[Dict[str, Any]] = []
    for item in items:
        sport = item.get("sport")
        if not sport or sport == "unknown-sport":
            continue
        if args.sport and sport != args.sport:
            continue
        if args.min_liquidity is not None and (item.get("liquidity") or 0) < args.min_liquidity:
            continue
        if args.min_volume is not None and (item.get("volume") or 0) < args.min_volume:
            continue
        if item.get("implied_yes_probability") is None:
            continue
        ranked.append(
            auto_forecast_from_snapshot_item(
                item,
                priors,
                profile_override=args.profile,
                favorite_status_override=args.favorite_status,
                info_quality=args.info_quality,
                anchor_to_market=args.anchor_to_market,
            )
        )

    ranked.sort(key=lambda row: (-row.get("score", 0), -(row.get("edge_abs", 0)), -(row.get("liquidity", 0)), -(row.get("volume", 0))))
    ranked = ranked[: args.limit]

    log_rows: List[Dict[str, Any]] = []
    if args.log_output:
        now = utc_now()
        for row in ranked:
            market_key = row.get("market_slug") or row.get("market_id") or row.get("event_slug") or row.get("market_question") or "unknown-market"
            log_rows.append(
                {
                    "logged_at": now,
                    "kind": "ranked-auto-forecast",
                    "market_key": market_key,
                    "log_id": stable_market_id(str(market_key) + now),
                    "market_id": row.get("market_id"),
                    "market_slug": row.get("market_slug"),
                    "event_title": row.get("event_title"),
                    "market_question": row.get("market_question"),
                    "url": row.get("url"),
                    "sport": row.get("sport"),
                    "profile": row.get("profile"),
                    "favorite_status": row.get("favorite_status"),
                    "yes_probability": row.get("yes_probability"),
                    "market_implied_probability": row.get("market_implied_probability"),
                    "difference_vs_implied": row.get("difference_vs_implied"),
                    "edge_abs": row.get("edge_abs"),
                    "score": row.get("score"),
                    "confidence": row.get("confidence"),
                    "view": row.get("view"),
                    "volume": row.get("volume"),
                    "liquidity": row.get("liquidity"),
                }
            )
        append_jsonl(Path(args.log_output), log_rows)

    return {
        "snapshot": str(snapshot_path),
        "count": len(ranked),
        "items": ranked,
        "log_output": args.log_output,
        "log_rows": log_rows,
    }


def handle_rank_live_markets(args: argparse.Namespace) -> None:
    result = run_rank_live_markets(args)
    ranked = result["items"]

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"Snapshot: {result['snapshot']}")
    print(f"Ranked markets: {len(ranked)}")
    for idx, row in enumerate(ranked, start=1):
        print(f"\n{idx}. [{row['sport']}] {row['market_question']}")
        print(f"   score={row['score']:.2f} | edge={format_pct(row['difference_vs_implied'], signed=True)} | implied={format_pct(row['market_implied_probability'])} | forecast={format_pct(row['yes_probability'])}")
        print(f"   confidence={row['confidence']} | view={row['view']} | liquidity={row['liquidity']} | volume={row['volume']}")
        print(f"   url={row['url']}")

    if result["log_output"]:
        print(f"\nSaved ranked auto-forecasts to log: {result['log_output']}")


def handle_find_live_locks(args: argparse.Namespace) -> None:
    result = run_find_live_locks(args)
    candidates = result["items"]

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"Snapshot: {result['snapshot']}")
    print(f"Late-game lock candidates: {len(candidates)}")
    for idx, row in enumerate(candidates, start=1):
        score = row["score"]
        print(f"\n{idx}. [{row['sport']}] {row['market_question']}")
        print(f"   score_state={score['left']}-{score['right']} | margin={score['margin']} | remaining≈{row['minutes_remaining']} min")
        print(f"   lock_probability={format_pct(row['win_probability'])} | market_implied={format_pct(row['market_implied_probability'])} | edge={format_pct(row['edge'], signed=True)}")
        print(f"   leader_side={row['leader_side']} | url={row['url']}")

    if result["log_output"]:
        print(f"\nSaved live lock candidates to log: {result['log_output']}")


def run_find_live_locks(args: argparse.Namespace) -> Dict[str, Any]:
    priors = load_sports_priors()
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists() or args.refresh:
        events = fetch_live_events(per_page=args.per_page, pages=args.pages, closed=args.closed)
        snapshot = build_live_snapshot(events, priors, include_unknown=args.include_unknown)
        save_snapshot(snapshot, snapshot_path)
    else:
        snapshot = load_snapshot(snapshot_path)

    candidates = []
    for item in snapshot.get("items", []):
        if args.sport and item.get("sport") != args.sport:
            continue
        state = compute_endgame_lock_probability(item)
        if not state:
            continue
        if state["win_probability"] < args.min_probability:
            continue
        candidates.append(
            {
                "market_id": item.get("market_id"),
                "market_question": item.get("market_question"),
                "event_title": item.get("event_title"),
                "url": item.get("url"),
                "sport": item.get("sport"),
                "minutes_remaining": state["minutes_remaining"],
                "score": state["score"],
                "leader_side": state["leader_side"],
                "win_probability": state["win_probability"],
                "market_implied_probability": state["market_implied_probability"],
                "edge": state["edge"],
                "rationale": state["rationale"],
            }
        )

    candidates.sort(key=lambda row: (-row["win_probability"], -row["score"]["margin"], row["minutes_remaining"]))
    candidates = candidates[: args.limit]

    log_rows = []
    if args.log_output:
        now = utc_now()
        for row in candidates:
            log_rows.append(
                {
                    "logged_at": now,
                    "kind": "live-endgame-lock",
                    "market_id": row.get("market_id"),
                    "market_question": row.get("market_question"),
                    "event_title": row.get("event_title"),
                    "url": row.get("url"),
                    "sport": row.get("sport"),
                    "minutes_remaining": row.get("minutes_remaining"),
                    "score": row.get("score"),
                    "leader_side": row.get("leader_side"),
                    "win_probability": row.get("win_probability"),
                    "market_implied_probability": row.get("market_implied_probability"),
                    "edge": row.get("edge"),
                }
            )
        append_jsonl(Path(args.log_output), log_rows)

    return {
        "snapshot": str(snapshot_path),
        "count": len(candidates),
        "items": candidates,
        "log_output": args.log_output,
        "log_rows": log_rows,
    }


def handle_auto_live_locks(args: argparse.Namespace) -> None:
    result = run_find_live_locks(args)
    summary = {
        "ran_at": utc_now(),
        "mode": "auto-live-locks",
        "snapshot": result["snapshot"],
        "count": result["count"],
        "sport_filter": args.sport,
        "top": result["items"][: args.summary_limit],
        "log_output": result["log_output"],
    }

    summary_path = Path(args.summary_output) if args.summary_output else None
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.dashboard_output and summary_path:
        build_dashboard_html(summary, Path(result["log_output"]) if result["log_output"] else None, Path(result["snapshot"]), Path(args.dashboard_output), summary_path, log_limit=args.dashboard_log_limit)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    print(f"Auto live-lock scan completed at {summary['ran_at']}")
    print(f"Snapshot: {summary['snapshot']}")
    print(f"Lock candidates: {summary['count']}")
    for idx, row in enumerate(summary["top"], start=1):
        score = row.get("score") or {}
        print(f"- {idx}. [{row.get('sport')}] {row.get('market_question')} | lock={format_pct(row.get('win_probability'))} | edge={format_pct(row.get('edge'), signed=True)} | remaining≈{row.get('minutes_remaining')} min | score={score.get('left')}-{score.get('right')}")
        print(f"  {row.get('url')}")
    if summary_path:
        print(f"Summary file: {summary_path}")
    if args.dashboard_output and summary_path:
        print(f"Dashboard file: {args.dashboard_output}")


def handle_auto_cycle(args: argparse.Namespace) -> None:
    result = run_rank_live_markets(args)
    ranked = result["items"]
    summary = {
        "ran_at": utc_now(),
        "mode": "auto-cycle",
        "snapshot": result["snapshot"],
        "count": result["count"],
        "sport_filter": args.sport,
        "top": [
            {
                "market_question": row.get("market_question"),
                "sport": row.get("sport"),
                "score": row.get("score"),
                "difference_vs_implied": row.get("difference_vs_implied"),
                "confidence": row.get("confidence"),
                "view": row.get("view"),
                "url": row.get("url"),
            }
            for row in ranked[: args.summary_limit]
        ],
        "log_output": result["log_output"],
    }

    summary_path = Path(args.summary_output) if args.summary_output else None
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.dashboard_output and summary_path:
        build_dashboard_html(summary, Path(result["log_output"]) if result["log_output"] else None, Path(result["snapshot"]), Path(args.dashboard_output), summary_path, log_limit=args.dashboard_log_limit)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    print(f"Auto cycle completed at {summary['ran_at']}")
    print(f"Snapshot: {summary['snapshot']}")
    print(f"Ranked markets: {summary['count']}")
    if summary["top"]:
        print("Top candidates:")
        for idx, row in enumerate(summary["top"], start=1):
            print(f"- {idx}. [{row['sport']}] {row['market_question']} | score={row['score']:.2f} | edge={format_pct(row['difference_vs_implied'], signed=True)} | confidence={row['confidence']}")
            print(f"  {row['url']}")
    else:
        print("Top candidates: none")

    if summary["log_output"]:
        print(f"Log file: {summary['log_output']}")
    if summary_path:
        print(f"Summary file: {summary_path}")
    if args.dashboard_output and summary_path:
        print(f"Dashboard file: {args.dashboard_output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lightweight prediction-market analysis bot scaffold")
    sub = parser.add_subparsers(dest="command", required=True)

    list_sports = sub.add_parser("list-sports", help="List all supported sports and profiles")
    list_sports.set_defaults(func=handle_list_sports)

    sports = sub.add_parser("sports", help="Analyze a sports-related YES/NO market")
    sports.add_argument("market", help="Restated market text")
    sports.add_argument("--sport", required=True, help="Sport key or alias. Run 'list-sports' to see all supported values.")
    sports.add_argument("--profile", default="default", help="Prior profile to use, usually default, heavy_favorite, or balanced_match")
    sports.add_argument("--favorite-status", choices=["favorite", "underdog"], default="favorite", help="Whether the YES side is the favorite or underdog")
    sports.add_argument("--home-advantage", action="store_true", help="Apply a simple home-advantage adjustment")
    sports.add_argument("--injury-impact", type=float, default=0.0, help="Add/subtract probability points for injuries or availability; use decimal form like -0.05")
    sports.add_argument("--form-impact", type=float, default=0.0, help="Add/subtract probability points for form or momentum; decimal form")
    sports.add_argument("--schedule-impact", type=float, default=0.0, help="Add/subtract probability points for travel/rest/schedule; decimal form")
    sports.add_argument("--implied-prob", type=float, help="Current market implied probability in decimal form, e.g. 0.57")
    sports.add_argument("--info-quality", choices=["low", "medium", "high"], default="medium")
    sports.add_argument("--ambiguity-high", action="store_true", help="Flag if market wording/resolution is ambiguous")
    sports.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    sports.set_defaults(func=handle_sports)

    sync_live = sub.add_parser("sync-live-sports", help="Fetch active Polymarket events, auto-detect sports markets, and save a live snapshot")
    sync_live.add_argument("--pages", type=int, default=5, help="How many event pages to fetch")
    sync_live.add_argument("--per-page", type=int, default=100, help="How many events to fetch per page")
    sync_live.add_argument("--closed", action="store_true", help="Fetch closed markets instead of open ones")
    sync_live.add_argument("--include-unknown", action="store_true", help="Keep sports-like markets that could not be mapped to a specific sport")
    sync_live.add_argument("--output", help=f"Output JSON file path (default: {DEFAULT_SNAPSHOT_PATH})")
    sync_live.add_argument("--json", action="store_true", help="Print full snapshot JSON after saving")
    sync_live.set_defaults(func=handle_sync_live_sports)

    inspect_live = sub.add_parser("inspect-live-market", help="Inspect a Polymarket market/event slug or URL and auto-detect its sport")
    inspect_live.add_argument("ref", help="Market slug, event slug, or full Polymarket URL")
    inspect_live.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    inspect_live.set_defaults(func=handle_inspect_live_market)

    auto_forecast = sub.add_parser("auto-forecast-live", help="Fetch a live Polymarket market by URL/slug, detect sport, and produce a heuristic forecast scaffold")
    auto_forecast.add_argument("ref", help="Market slug, event slug, or full Polymarket URL")
    auto_forecast.add_argument("--sport", help="Override detected sport if needed")
    auto_forecast.add_argument("--profile", help="Override profile instead of auto-selecting from implied price")
    auto_forecast.add_argument("--favorite-status", choices=["favorite", "underdog"], help="Override whether YES side should be treated as favorite or underdog")
    auto_forecast.add_argument("--home-advantage", action="store_true", help="Apply a simple home-advantage adjustment")
    auto_forecast.add_argument("--injury-impact", type=float, default=0.0, help="Add/subtract probability points for injuries or availability; use decimal form like -0.05")
    auto_forecast.add_argument("--form-impact", type=float, default=0.0, help="Add/subtract probability points for form or momentum; decimal form")
    auto_forecast.add_argument("--schedule-impact", type=float, default=0.0, help="Add/subtract probability points for travel/rest/schedule; decimal form")
    auto_forecast.add_argument("--anchor-to-market", type=float, default=0.25, help="Blend part of the forecast toward market implied probability, between 0 and 1")
    auto_forecast.add_argument("--info-quality", choices=["low", "medium", "high"], default="medium")
    auto_forecast.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    auto_forecast.set_defaults(func=handle_auto_forecast_live)

    rank_live = sub.add_parser("rank-live-markets", help="Rank live sports markets from a Polymarket snapshot using heuristic auto-forecast scoring")
    rank_live.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT_PATH), help="Path to an existing snapshot JSON file")
    rank_live.add_argument("--refresh", action="store_true", help="Refresh the snapshot before ranking")
    rank_live.add_argument("--pages", type=int, default=3, help="How many pages to fetch when refreshing")
    rank_live.add_argument("--per-page", type=int, default=100, help="How many events to fetch per page when refreshing")
    rank_live.add_argument("--closed", action="store_true", help="Use closed markets when refreshing")
    rank_live.add_argument("--include-unknown", action="store_true", help="Keep unknown-sport rows in refreshed snapshot, though they are not ranked")
    rank_live.add_argument("--sport", help="Filter rankings to a single sport key")
    rank_live.add_argument("--profile", help="Override profile for all ranked markets")
    rank_live.add_argument("--favorite-status", choices=["favorite", "underdog"], help="Override favorite/underdog handling for all ranked markets")
    rank_live.add_argument("--anchor-to-market", type=float, default=0.25, help="Blend part of the forecast toward market implied probability, between 0 and 1")
    rank_live.add_argument("--info-quality", choices=["low", "medium", "high"], default="medium")
    rank_live.add_argument("--min-liquidity", type=float, help="Minimum liquidity filter")
    rank_live.add_argument("--min-volume", type=float, help="Minimum volume filter")
    rank_live.add_argument("--limit", type=int, default=20, help="How many ranked markets to print")
    rank_live.add_argument("--log-output", default=str(DEFAULT_AUTO_LOG_PATH), help="Optional JSONL output path for ranked auto-forecast rows")
    rank_live.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    rank_live.set_defaults(func=handle_rank_live_markets)

    auto_cycle = sub.add_parser("auto-cycle", help="Refresh live markets, rank them, auto-log results, and optionally write a summary file")
    auto_cycle.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT_PATH), help="Snapshot JSON path")
    auto_cycle.add_argument("--pages", type=int, default=3, help="How many event pages to fetch")
    auto_cycle.add_argument("--per-page", type=int, default=100, help="How many events to fetch per page")
    auto_cycle.add_argument("--closed", action="store_true", help="Use closed markets instead of open ones")
    auto_cycle.add_argument("--include-unknown", action="store_true", help="Keep unknown-sport rows in refreshed snapshot, though they are not ranked")
    auto_cycle.add_argument("--sport", help="Filter rankings to a single sport key")
    auto_cycle.add_argument("--profile", help="Override profile for all ranked markets")
    auto_cycle.add_argument("--favorite-status", choices=["favorite", "underdog"], help="Override favorite/underdog handling for all ranked markets")
    auto_cycle.add_argument("--anchor-to-market", type=float, default=0.25, help="Blend part of the forecast toward market implied probability, between 0 and 1")
    auto_cycle.add_argument("--info-quality", choices=["low", "medium", "high"], default="medium")
    auto_cycle.add_argument("--min-liquidity", type=float, help="Minimum liquidity filter")
    auto_cycle.add_argument("--min-volume", type=float, help="Minimum volume filter")
    auto_cycle.add_argument("--limit", type=int, default=20, help="How many ranked markets to produce")
    auto_cycle.add_argument("--summary-limit", type=int, default=5, help="How many top candidates to include in the summary")
    auto_cycle.add_argument("--log-output", default=str(DEFAULT_AUTO_LOG_PATH), help="JSONL output path for ranked auto-forecast rows")
    auto_cycle.add_argument("--summary-output", default=str(ROOT / "data" / "auto-summary.json"), help="JSON summary output path")
    auto_cycle.add_argument("--dashboard-output", default=str(DEFAULT_DASHBOARD_PATH), help="Rendered dashboard HTML output path")
    auto_cycle.add_argument("--dashboard-log-limit", type=int, default=30, help="How many recent log rows to render into the dashboard")
    auto_cycle.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    auto_cycle.set_defaults(func=handle_auto_cycle, refresh=True)

    live_locks = sub.add_parser("find-live-locks", help="Find late-game live sports markets with very high heuristic win probability")
    live_locks.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT_PATH), help="Snapshot JSON path")
    live_locks.add_argument("--refresh", action="store_true", help="Refresh the snapshot before scanning")
    live_locks.add_argument("--pages", type=int, default=4, help="How many event pages to fetch")
    live_locks.add_argument("--per-page", type=int, default=100, help="How many events to fetch per page")
    live_locks.add_argument("--closed", action="store_true", help="Use closed markets instead of open ones")
    live_locks.add_argument("--include-unknown", action="store_true", help="Keep unknown-sport rows in refreshed snapshot")
    live_locks.add_argument("--sport", help="Optional single-sport filter")
    live_locks.add_argument("--min-probability", type=float, default=0.9, help="Minimum heuristic lock probability")
    live_locks.add_argument("--limit", type=int, default=20, help="How many candidates to print")
    live_locks.add_argument("--log-output", help="Optional JSONL output path for live-lock candidates")
    live_locks.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    live_locks.set_defaults(func=handle_find_live_locks)

    auto_live_locks = sub.add_parser("auto-live-locks", help="Refresh live markets, find very high-confidence endgame locks, and optionally build a dashboard snapshot")
    auto_live_locks.add_argument("--snapshot", default=str(ROOT / "data" / "live-locks-snapshot.json"), help="Snapshot JSON path")
    auto_live_locks.add_argument("--refresh", action="store_true", help="Refresh the snapshot before scanning")
    auto_live_locks.add_argument("--pages", type=int, default=4, help="How many event pages to fetch")
    auto_live_locks.add_argument("--per-page", type=int, default=100, help="How many events to fetch per page")
    auto_live_locks.add_argument("--closed", action="store_true", help="Use closed markets instead of open ones")
    auto_live_locks.add_argument("--include-unknown", action="store_true", help="Keep unknown-sport rows in refreshed snapshot")
    auto_live_locks.add_argument("--sport", help="Optional single-sport filter")
    auto_live_locks.add_argument("--min-probability", type=float, default=0.9, help="Minimum heuristic lock probability")
    auto_live_locks.add_argument("--limit", type=int, default=20, help="How many candidates to produce")
    auto_live_locks.add_argument("--summary-limit", type=int, default=10, help="How many top candidates to include in the summary")
    auto_live_locks.add_argument("--log-output", default=str(ROOT / "data" / "live-locks.jsonl"), help="JSONL output path for live-lock rows")
    auto_live_locks.add_argument("--summary-output", default=str(ROOT / "data" / "live-locks-summary.json"), help="JSON summary output path")
    auto_live_locks.add_argument("--dashboard-output", default=str(ROOT / "data" / "live-locks-dashboard.html"), help="Rendered dashboard HTML output path")
    auto_live_locks.add_argument("--dashboard-log-limit", type=int, default=30, help="How many recent log rows to render into the dashboard")
    auto_live_locks.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    auto_live_locks.set_defaults(func=handle_auto_live_locks)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
