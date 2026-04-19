# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Run the bot locally: `python tonkkabot.py` (requires `BOT_TOKEN` in `bot.env` or the environment)
- Lint: `pylint *.py` — this is the only check CI runs; it must pass on `main`/`master` pushes and all PRs
- Local dev via Docker: `docker compose up --build` (mounts the repo into `/bot` so edits + `history.json` persist)
- Production-style run: `docker compose -f docker-compose.prod.yml up -d` (pulls `ghcr.io/fyysikkokilta/tonkkabot:latest`)
- Deploy on the host: `./update-deployment.sh` (git pull + prod compose pull + up)

The CI pipeline (`.github/workflows/ci.yml`) runs pylint on Python 3.12, then builds and pushes a Docker image to `ghcr.io/fyysikkokilta/tonkkabot` on pushes to `main`/`master`. There is no test suite.

## Environment

The bot reads the token from `BOT_TOKEN` (see `tonkkabot.py:19` and `bot.env.example`). The README mentions `TONKKA_BOT_TOKEN`, which is stale — use `BOT_TOKEN`.

## Architecture

Three-module Python Telegram bot. User-facing text is in Finnish; the concept "tönkkä" = the first day of the year the temperature at Helsinki-Vantaa airport (EFHK) reaches ≥20 °C.

- `tonkkabot.py` — entry point and all `CommandHandler`s (`/start`, `/history`, `/temperature`, `/forecast`). Built on `python-telegram-bot` v22.3 async API. `post_init` flushes queued updates (so the bot doesn't spam after downtime) and registers a daily midnight job that refreshes the tönkkä record for the new year. `concurrent_updates(False)` is intentional — handlers are not safe for parallel execution against the shared caches/history file.
- `data.py` — fetches from the FMI Open Data WFS API (`http://opendata.fmi.fi/wfs`). Two stored queries: `observations::weather::multipointcoverage` (history, takes `hourdelta`) and `forecast::harmonie::surface::point::multipointcoverage` (forecast, no `hourdelta`). Responses are XML; the parser extracts positions from `gmlcov:positions` and values from `gml:doubleOrNilReasonTupleList`, joins them into a DataFrame in `Europe/Helsinki` tz. A `TTLCache(ttl=60)` memoizes `fetch_data` so repeat commands within a minute don't hammer FMI. `record_possible_tonkka` is called on every successful fetch — it writes the year's first ≥20 °C observation to `history.json` (gitignored, persisted via the docker volume mount).
- `plots.py` — builds matplotlib/seaborn PNGs returned as `BytesIO`. Both `history` and `forecast` have their own `TTLCache(ttl=60)`, so the same plot isn't regenerated within 60s. The 20 °C "Pääpäivä" threshold is always drawn. Empty-DataFrame path renders a "Ei tietoja saatavilla" placeholder image rather than raising.

## Argument ranges (enforced in handlers)

- `/history [hours]` — 2–24, default 24. The fetch adds 2h of slack (`hourdelta=hours+2`).
- `/forecast [hours]` — 2–48, default 48. FMI Harmonie delivers ~50h, so the handler slices `iloc[0:hours+1]`.

Out-of-range or non-integer args send a Finnish error message and then still render the default plot.

## State and persistence

- `history.json` is the only persisted state (one entry per year: first temp ≥20 °C and its timestamp). It is written in-place with `open(..., "r+")` — beware of concurrent writes; the single-concurrency setting above is what keeps this safe.
- If `history.json` is missing, `check_history` creates an empty one on first call.
