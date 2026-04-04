#!/usr/bin/env python3
import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = ROOT / "assets" / "dashboard.html"
DEFAULT_SUMMARY = ROOT / "data" / "auto-summary.json"
DEFAULT_LOG = ROOT / "data" / "auto-log.jsonl"
DEFAULT_SNAPSHOT = ROOT / "data" / "auto-snapshot.json"
DEFAULT_OUTPUT = ROOT / "data" / "dashboard.html"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
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


def fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def fmt_signed_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def confidence_pill(conf: str) -> str:
    conf = (conf or "unknown").lower()
    if conf == "high":
        klass = "good"
    elif conf == "medium":
        klass = "warn"
    elif conf == "low":
        klass = "bad"
    else:
        klass = "info"
    return f'<span class="pill {klass}">{html.escape(conf.title())}</span>'


def build_top_cards(items: List[Dict[str, Any]]) -> str:
    if not items:
        return '<div class="empty-state"><h3>No live locks found yet</h3><div class="footnote">The scanner is active, but no current live sports market matches the strict 90%+ endgame-lock rules.</div><ul><li>No suitable late-game state was detected</li><li>Score margin may still be too small</li><li>Too much time may still remain</li></ul></div>'

    blocks = []
    for row in items:
        market = html.escape(str(row.get("market_question") or "Unknown market"))
        sport = html.escape(str(row.get("sport") or "unknown"))
        score = row.get("score")
        url = html.escape(str(row.get("url") or "#"))
        edge = fmt_signed_pct(row.get("difference_vs_implied"))
        blocks.append(
            f'''<article class="card">
  <div class="card-top">
    <div>
      <div class="title">{market}</div>
      <div class="footnote">{sport}</div>
    </div>
    {confidence_pill(str(row.get("confidence") or "unknown"))}
  </div>
  <div class="stats">
    <div class="stat"><small>Score</small><strong>{score if score is not None else 'n/a'}</strong></div>
    <div class="stat"><small>Edge</small><strong>{edge}</strong></div>
    <div class="stat"><small>View</small><strong>{html.escape(str(row.get("view") or 'n/a'))}</strong></div>
  </div>
  <a href="{url}">{url}</a>
</article>'''
        )
    return "\n".join(blocks)


def build_log_rows(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="8">No log rows yet. Run auto-cycle first.</td></tr>'

    out = []
    for row in rows:
        conf = str(row.get('confidence') or 'n/a')
        heat = 'low'
        try:
            edge_abs = abs(float(row.get('difference_vs_implied') or 0.0))
            if edge_abs >= 0.12:
                heat = 'high'
            elif edge_abs >= 0.05:
                heat = 'medium'
        except (TypeError, ValueError):
            heat = 'low'
        out.append(
            f"<tr data-time=\"{html.escape(str(row.get('logged_at') or ''))}\" data-score=\"{html.escape(str(row.get('score') or 0))}\" data-edge=\"{html.escape(str(abs(float(row.get('difference_vs_implied') or 0.0))))}\" data-confidence=\"{html.escape(conf.lower())}\">"
            f"<td>{html.escape(str(row.get('logged_at') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('market_question') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('sport') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('score') or 'n/a'))}</td>"
            f"<td>{html.escape(fmt_signed_pct(row.get('difference_vs_implied')))}</td>"
            f"<td>{html.escape(conf)}</td>"
            f"<td><span class=\"heat {heat}\">{heat.upper()}</span></td>"
            f"<td><a href=\"{html.escape(str(row.get('url') or '#'))}\">open</a></td>"
            "</tr>"
        )
    return "\n".join(out)


def build_edge_chart(rows: List[Dict[str, Any]]) -> str:
    points = []
    for idx, row in enumerate(rows[:20]):
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
        coords.append((x, y, edge))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in coords)
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#6ee7ff" />' for x, y, _ in coords)
    return f'''<svg viewBox="0 0 {width} {height}" role="img" aria-label="Edge history chart">
  <line x1="30" y1="190" x2="610" y2="190" stroke="rgba(255,255,255,.15)" />
  <line x1="30" y1="30" x2="30" y2="190" stroke="rgba(255,255,255,.15)" />
  <polyline fill="none" stroke="#6ee7ff" stroke-width="3" points="{polyline}" />
  {circles}
</svg>'''


def build_top_movers(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return '<div class="footnote">No recent movers yet.</div>'
    ranked = sorted(rows, key=lambda r: abs(float(r.get("difference_vs_implied") or 0.0)), reverse=True)[:5]
    parts = []
    for row in ranked:
        parts.append(
            f'<div class="footnote" style="margin-top:10px;"><strong>{html.escape(str(row.get("market_question") or "n/a"))}</strong><br>'
            f'edge {fmt_signed_pct(row.get("difference_vs_implied"))} · score {html.escape(str(row.get("score") or "n/a"))}</div>'
        )
    return "".join(parts)


def build_dashboard(template: str, summary: Dict[str, Any], log_rows: List[Dict[str, Any]], summary_path: Path, log_path: Path, snapshot_path: Path) -> str:
    items = summary.get("top", [])
    best_edge = "n/a"
    if log_rows:
        try:
            best_edge = fmt_signed_pct(max(log_rows, key=lambda r: abs(float(r.get("difference_vs_implied") or 0.0))).get("difference_vs_implied"))
        except Exception:
            best_edge = "n/a"
    high_conf_count = sum(1 for row in log_rows if str(row.get("confidence") or "").lower() == "high")
    best_bet = items[0] if items else {}
    replacements = {
        "{{LAST_RUN}}": html.escape(str(summary.get("ran_at") or "No data")),
        "{{COUNT}}": html.escape(str(summary.get("count") or 0)),
        "{{SPORT_FILTER}}": html.escape(str(summary.get("sport_filter") or "all sports")),
        "{{TOP_CARDS}}": build_top_cards(items),
        "{{LOG_ROWS}}": build_log_rows(log_rows),
        "{{SUMMARY_PATH}}": html.escape(str(summary_path)),
        "{{LOG_PATH}}": html.escape(str(log_path)),
        "{{SNAPSHOT_PATH}}": html.escape(str(snapshot_path)),
        "{{BEST_EDGE}}": html.escape(best_edge),
        "{{HIGH_CONF_COUNT}}": html.escape(str(high_conf_count)),
        "{{RECENT_ROWS}}": html.escape(str(len(log_rows))),
        "{{EDGE_CHART}}": build_edge_chart(log_rows),
        "{{TOP_MOVERS}}": build_top_movers(log_rows),
        "{{BEST_BET_MARKET}}": html.escape(str(best_bet.get("market_question") or "No candidate yet")),
        "{{BEST_BET_EDGE}}": html.escape(fmt_signed_pct(best_bet.get("difference_vs_implied"))),
        "{{BEST_BET_SCORE}}": html.escape(str(best_bet.get("score") or "n/a")),
        "{{BEST_BET_SPORT}}": html.escape(str(best_bet.get("sport") or "n/a")),
    }

    output = template
    for old, new in replacements.items():
        output = output.replace(old, new)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Polymarket forecast dashboard HTML from summary/log files")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--log-limit", type=int, default=30)
    args = parser.parse_args()

    template_path = Path(args.template)
    summary_path = Path(args.summary)
    log_path = Path(args.log)
    snapshot_path = Path(args.snapshot)
    output_path = Path(args.output)

    template = template_path.read_text(encoding="utf-8")
    summary = load_json(summary_path)
    log_rows = load_jsonl(log_path, args.log_limit)
    dashboard = build_dashboard(template, summary, log_rows, summary_path, log_path, snapshot_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dashboard, encoding="utf-8")
    print(f"Dashboard written to: {output_path}")


if __name__ == "__main__":
    main()
