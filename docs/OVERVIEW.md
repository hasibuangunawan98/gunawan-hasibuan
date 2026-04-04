# Repository Overview

This repository is an OpenClaw workspace used for:

- custom skill development
- dashboard experiments
- local automation tooling
- forecasting and market analysis workflows

## Main areas

### `skills/polymarket-btc-microtrend/`
A BTC-focused skill with:
- live websocket bridge
- premium dashboard assets
- local premium HTTP server
- strategy references

### `skills/polymarket-forecast/`
A forecasting-oriented skill with:
- market bots
- dashboard generation scripts
- forecasting references and rubrics
- sports priors assets

## Version-control approach

The repository keeps source, references, and important assets in Git.

Runtime data, snapshots, logs, and frequently changing generated outputs are excluded from normal tracking after the initial archival snapshot.
