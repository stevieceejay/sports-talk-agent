# sports-talk-agent

Python AI sports agent for matchup research, statistical analysis, and API-driven insights.

## Features

- Sports-focused analysis agent for matchup questions
- OpenAI-powered response generation using the Responses API
- Tool-calling support for team lookups via `get_team_info`
- Structured loop for handling function calls and tool results
- Environment-variable based API key setup
- Graceful validation for empty tasks and missing data

## Project structure

- `agent.py` – core sports agent logic, tool definitions, and OpenAI integration
- `app.py` – app entry point for running the agent
- `scripts/create_nfl_db.py` – creates the local SQLite database in the `db/` folder
- `scripts/backtest_win_model.py` – runs and exports the historical win-probability backtest
- `db/` – local NFL database and table definitions for season/team data
- `tools/prediction_model.py` – reproducible pregame win-probability model
- `tools/sports_tools.py` – mock sports data tool for team metadata while live sources are unavailable
- `tools/query_nfl_db.py` – read-only SQL tool for querying approved NFL views
- `.env` – optional local environment configuration for secrets

## NFL schedule data

Schedules and completed game scores are imported from the public
[nflverse games dataset](https://github.com/nflverse/nfldata/blob/master/data/games.csv).
Per-game passing, rushing, receiving, sack, interception, and forced-fumble statistics,
with QB/RB/WR/TE/defense position groups, come from
[nflverse play-by-play](https://github.com/nflverse/nflverse-data/releases/tag/pbp),
with canonical names from the [nflverse player catalog](https://github.com/nflverse/nflverse-data/releases/tag/players).
Import or refresh one season, including its available game stats:

```powershell
python -m scripts.create_nfl_db --season 2026
```

The importer replaces only that season's schedule and game-stat rows and
preserves other database tables. It stores upcoming scores as unknown. Omitting
`--season` refreshes schedules for all seasons in the schedule feed but does not
download play-by-play stats. Stat queries return an empty status when the local
database has no matching rows; the agent must not invent statistics.

Example questions include “Who leads the Cardinals in rushing yards this season?”,
“Which quarterback has the most passing yards?”, “Who leads receivers in catches?”,
and “Which defender has the most forced fumbles?”. These are covered by the
database tools and tests; a separate question database is not required.

## Historical model and backtest

Import the five completed seasons used for model training:

```powershell
python -m scripts.create_nfl_db --from-season 2021 --to-season 2025
```

This replaces only 2021–2025 schedule and stat rows and preserves the 2026 season.
The model is a scikit-learn logistic regression with pinned dependencies, fixed
parameters, and five-game rolling team form. Backtesting is expanding by season:
each test season is predicted using only earlier seasons, and same-week outcomes
are excluded from pregame features.

Run the backtest and export each held-out game's home/away probabilities:

```powershell
python -m scripts.backtest_win_model
```

The CSV report is written to `reports/win_probabilities_2022_2025.csv`. On the
current 2021–2025 data, 1,084 held-out predictions achieved 61.3% accuracy and a
0.231 Brier score, compared with 0.248 for the training-fold home-win-rate
baseline. These are historical results, not a guarantee of future performance.
The `/predict` API and agent prediction tool return probabilities for scheduled
matchups, defaulting to 2026 and training on 2021–2025.

## Current implementation notes

- The agent loads environment variables with `load_dotenv()`
- It creates an `OpenAI` client and sends tool definitions with the request
- It checks for function-call outputs and executes matching tools
- It loops through tool responses until a final text answer is returned
- It avoids inventing facts and clearly indicates when information is unavailable

## Setup

1. Create and activate a virtual environment if needed.
2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Set your OpenAI API key:

PowerShell:

```powershell
$env:OPENAI_API_KEY="your_key_here"
```

4. Run the app:

```bash
python app.py
```

## Important corrections and safeguards

- Fixed the earlier circular import issue by keeping the app and agent independent
- Replaced hardcoded secrets with environment-variable lookup
- Corrected the tool schema so `description`, `parameters`, and `required` are valid JSON-like structures
- Added validation to ensure the task input is a non-empty string
- Added guardrails to prevent empty tool responses or infinite tool loops
- NFL schedules, completed scores, and available per-game player/team statistics
	are loaded from nflverse; live weather, standings, and news use live tools.

## Notes

- Keep API keys out of source control.
- Use a local `.env` file or shell environment variables for configuration.
- Season summaries, injuries, and advanced statistics beyond the imported PBP
	counting stats still require their own populated data sources.
- This project is structured for iterative improvement and expansion as real data sources are added.
