#!/usr/bin/env python3
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
SUMMARY = DATA / 'summary.json'
OUT = DATA / 'polymarket-live.json'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; polymarket-realtime/1.0)', 'Accept': 'application/json'}


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def fetch_json(url: str):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=20) as resp:
        return json.load(resp)


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def extract_live(summary):
    best = summary.get('best_setup') or {}
    signals = summary.get('signals') or []
    top = [s for s in signals[:8] if s.get('url')]
    items = []
    for s in top:
        items.append({
            'question': s.get('question'),
            'url': s.get('url'),
            'implied_yes_probability': s.get('implied_yes_probability'),
            'action': s.get('action'),
            'bias': s.get('bias'),
            'confidence': s.get('confidence'),
            'model_score': s.get('model_score'),
            'resolution_source': s.get('resolution_source') or {},
        })
    return {'best': best, 'items': items}


def build_payload(prev):
    summary = load_json(SUMMARY, {})
    live = extract_live(summary)
    deltas = []
    prev_map = {x.get('question'): x for x in (prev.get('items') or [])}
    for item in live['items']:
        q = item.get('question')
        old = prev_map.get(q, {})
        new_p = safe_float(item.get('implied_yes_probability'))
        old_p = safe_float(old.get('implied_yes_probability'))
        delta = None if new_p is None or old_p is None else round(new_p - old_p, 4)
        item['delta_probability'] = delta
        if delta is not None and abs(delta) >= 0.03:
            deltas.append({'question': q, 'delta_probability': delta, 'new_probability': new_p})
    return {
        'updated_at': now_iso(),
        'status': 'live-ish',
        'best': live['best'],
        'items': live['items'],
        'significant_moves': deltas,
    }


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    prev = load_json(OUT, {})
    while True:
        try:
            payload = build_payload(prev)
            OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            prev = payload
        except Exception:
            pass
        time.sleep(5)


if __name__ == '__main__':
    main()
