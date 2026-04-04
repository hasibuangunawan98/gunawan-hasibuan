# OpenClaw Workspace

Personal OpenClaw workspace containing custom skills, dashboards, live data bridges, and forecasting experiments.

## Highlights

### 1) Polymarket BTC Microtrend
Path: `skills/polymarket-btc-microtrend/`

Includes:
- BTC microtrend skill logic
- live websocket bridge for BTC market data
- premium cockpit dashboards
- local premium HTTP server
- strategy references and supporting assets

Main files:
- `scripts/btc_bot.py`
- `scripts/btc_ws_bridge.py`
- `scripts/premium_server.py`
- `assets/premium_dashboard.html`
- `assets/premium_dashboard_v2.html`

### 2) Polymarket Forecast
Path: `skills/polymarket-forecast/`

Includes:
- market forecasting skill
- dashboard generation scripts
- forecasting references and rubric
- sports priors and market data tooling

Main files:
- `scripts/market_bot.py`
- `scripts/build_dashboard.py`
- `scripts/forecast_log.py`

## Repository Structure

```text
.
├── AGENTS.md
├── SOUL.md
├── USER.md
├── TOOLS.md
├── HEARTBEAT.md
├── skills/
│   ├── polymarket-btc-microtrend/
│   └── polymarket-forecast/
└── README.md
```

## Git Notes

This repository intentionally keeps source files, references, and key assets under version control.

Runtime/generated files are ignored after the initial full snapshot commit so the repository stays cleaner over time.

Examples of ignored content:
- temporary JSON snapshots
- generated logs
- local OpenClaw runtime state
- memory notes
- build artifacts
- frequently changing skill data outputs

## Local Usage

### Git basics
```powershell
git status
git log --oneline
git add .
git commit -m "your message"
git push
```

### Launching the BTC premium cockpit
Desktop launchers were created locally on the machine, outside this repository.

Related runtime components inside this repo:
- `skills/polymarket-btc-microtrend/scripts/btc_ws_bridge.py`
- `skills/polymarket-btc-microtrend/scripts/premium_server.py`

## Suggested Next Improvements

- add screenshots to this README
- add a dedicated docs folder
- split experimental/runtime data from reproducible outputs even further
- publish stable skills separately if needed

## Remote Repository

GitHub remote:
- <https://github.com/hasibuangunawan98/gunawan-hasibuan>
