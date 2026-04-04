#!/usr/bin/env python3
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_entries(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL in {path} line {line_no}: {exc}")
    return entries


def save_entries(path: Path, entries: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def normalize_probability(value: float) -> float:
    if math.isnan(value) or value < 0 or value > 1:
        raise SystemExit("Probability values must be between 0 and 1.")
    return round(value, 4)


def find_entry(entries: List[Dict[str, Any]], market_id: str) -> Dict[str, Any]:
    for entry in entries:
        if entry.get("market_id") == market_id:
            return entry
    raise SystemExit(f"No market found with market_id={market_id!r}")


def cmd_add(args: argparse.Namespace) -> None:
    path = Path(args.log)
    entries = load_entries(path)
    if any(e.get("market_id") == args.market_id for e in entries):
        raise SystemExit(f"market_id already exists: {args.market_id}")

    entry = {
        "market_id": args.market_id,
        "market_text": args.market_text,
        "forecast_time": utc_now(),
        "resolution_date": args.resolution_date,
        "yes_probability": normalize_probability(args.yes_probability),
        "no_probability": round(1 - normalize_probability(args.yes_probability), 4),
        "market_implied_probability": normalize_probability(args.market_implied_probability)
        if args.market_implied_probability is not None
        else None,
        "confidence": args.confidence,
        "rationale": args.rationale,
        "tags": args.tags or [],
        "status": "open",
        "outcome": None,
        "resolved_at": None,
    }
    entries.append(entry)
    save_entries(path, entries)
    print(f"Added forecast for {args.market_id}")


def cmd_resolve(args: argparse.Namespace) -> None:
    path = Path(args.log)
    entries = load_entries(path)
    entry = find_entry(entries, args.market_id)
    entry["status"] = "resolved"
    entry["outcome"] = args.outcome
    entry["resolved_at"] = utc_now()
    save_entries(path, entries)
    print(f"Resolved {args.market_id} as {args.outcome}")


def brier_score(prob_yes: float, outcome: str) -> float:
    actual = 1.0 if outcome == "yes" else 0.0
    return round((prob_yes - actual) ** 2, 6)


def bucket_for(prob_yes: float) -> str:
    lower = int(prob_yes * 10) * 10
    upper = min(lower + 10, 100)
    return f"{lower:02d}-{upper:02d}%"


def cmd_stats(args: argparse.Namespace) -> None:
    path = Path(args.log)
    entries = load_entries(path)
    if not entries:
        print("No entries yet.")
        return

    resolved = [e for e in entries if e.get("status") == "resolved" and e.get("outcome") in {"yes", "no"}]
    print(f"Total forecasts: {len(entries)}")
    print(f"Resolved forecasts: {len(resolved)}")
    if not resolved:
        print("No resolved forecasts yet.")
        return

    scores = [brier_score(float(e["yes_probability"]), e["outcome"]) for e in resolved]
    avg_brier = sum(scores) / len(scores)
    print(f"Average Brier score: {avg_brier:.4f}")

    by_confidence: Dict[str, List[float]] = defaultdict(list)
    by_bucket: Dict[str, List[float]] = defaultdict(list)

    for entry, score in zip(resolved, scores):
        by_confidence[entry.get("confidence", "unknown")].append(score)
        by_bucket[bucket_for(float(entry["yes_probability"]))].append(score)

    print("\nBy confidence:")
    for confidence in sorted(by_confidence):
        vals = by_confidence[confidence]
        print(f"- {confidence}: n={len(vals)}, avg_brier={sum(vals)/len(vals):.4f}")

    print("\nBy probability bucket:")
    for bucket in sorted(by_bucket):
        vals = by_bucket[bucket]
        print(f"- {bucket}: n={len(vals)}, avg_brier={sum(vals)/len(vals):.4f}")


def cmd_show(args: argparse.Namespace) -> None:
    path = Path(args.log)
    entries = load_entries(path)
    if args.market_id:
        entry = find_entry(entries, args.market_id)
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return

    selected = entries[-args.limit :] if args.limit else entries
    for entry in selected:
        print(
            json.dumps(
                {
                    "market_id": entry.get("market_id"),
                    "yes_probability": entry.get("yes_probability"),
                    "confidence": entry.get("confidence"),
                    "status": entry.get("status"),
                    "outcome": entry.get("outcome"),
                    "market_text": entry.get("market_text"),
                },
                ensure_ascii=False,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple prediction-market forecast logger and backtester")
    parser.add_argument("--log", default="forecast-log.jsonl", help="Path to JSONL log file")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Add a new forecast")
    add.add_argument("market_id")
    add.add_argument("market_text")
    add.add_argument("yes_probability", type=float)
    add.add_argument("--market-implied-probability", type=float)
    add.add_argument("--confidence", choices=["low", "medium", "high"], default="medium")
    add.add_argument("--resolution-date")
    add.add_argument("--rationale", default="")
    add.add_argument("--tags", nargs="*", default=[])
    add.set_defaults(func=cmd_add)

    resolve = sub.add_parser("resolve", help="Resolve an existing forecast")
    resolve.add_argument("market_id")
    resolve.add_argument("outcome", choices=["yes", "no"])
    resolve.set_defaults(func=cmd_resolve)

    stats = sub.add_parser("stats", help="Show backtest statistics")
    stats.set_defaults(func=cmd_stats)

    show = sub.add_parser("show", help="Show recent forecasts or a specific entry")
    show.add_argument("market_id", nargs="?")
    show.add_argument("--limit", type=int, default=10)
    show.set_defaults(func=cmd_show)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
