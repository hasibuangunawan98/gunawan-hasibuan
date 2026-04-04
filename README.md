# OpenClaw Workspace

![Repo Status](https://img.shields.io/badge/status-active-22c55e)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4)
![License](https://img.shields.io/badge/license-MIT-blue)

Personal OpenClaw workspace containing custom skills, dashboards, live market-data bridges, and forecasting experiments.

## Overview

This repository acts as a working OpenClaw home for:
- custom skill authoring
- BTC/Polymarket dashboard development
- local automation experiments
- market forecasting workflows
- documentation and references for iterative agent work

## Featured Skills

### Polymarket BTC Microtrend
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

### Polymarket Forecast
Path: `skills/polymarket-forecast/`

Includes:
- market forecasting skill
- dashboard generation scripts
- forecasting references and rubric
- sports priors and market-data tooling

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
├── docs/
│   └── OVERVIEW.md
├── skills/
│   ├── polymarket-btc-microtrend/
│   └── polymarket-forecast/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Git Strategy

This repository keeps source files, references, and important assets under version control.

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

### BTC premium cockpit components
Related runtime components in this repository:
- `skills/polymarket-btc-microtrend/scripts/btc_ws_bridge.py`
- `skills/polymarket-btc-microtrend/scripts/premium_server.py`

Desktop launchers were created locally on the machine, outside this repository.

## Documentation

Additional notes:
- `docs/OVERVIEW.md`
- `docs/ROADMAP.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`

## Suggested Future Improvements

- add screenshots or GIF previews of dashboards
- publish stable skills separately if needed
- add release tags for milestones
- split reproducible outputs and runtime artifacts even further

## Remote Repository

GitHub:
- <https://github.com/hasibuangunawan98/gunawan-hasibuan>
