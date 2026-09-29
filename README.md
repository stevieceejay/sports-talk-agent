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
- `db/` – local NFL database and table definitions for season/team data
- `tools/sports_tools.py` – mock sports data tool for team metadata while live sources are unavailable
- `tools/query_nfl_db.py` – read-only SQL tool for querying approved NFL views
- `.env` – optional local environment configuration for secrets

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
python -m pip install openai python-dotenv
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
- Kept the tool output as mock data until a real sports-data source is connected

## Notes

- Keep API keys out of source control.
- Use a local `.env` file or shell environment variables for configuration.
- The current tool is intentionally mocked; live sports records, injuries, statistics, and schedules are unavailable until a real provider is connected.
- This project is structured for iterative improvement and expansion as real data sources are added.
