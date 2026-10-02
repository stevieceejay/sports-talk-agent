import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from tools.live_tools import (
    get_live_nfl_spread,
    get_live_nfl_standings,
    get_team_news,
    get_weather_for_city,
)
from tools.query_nfl_db import (
    get_explosive_plays,
    get_explosive_summary,
    get_matchup_snapshot,
    get_player_game_stats,
    get_player_stat_leaders,
    get_scheme_fit,
    get_team_game_log,
    get_team_game_stats,
    get_team_rankings,
    get_team_recent_games,
    get_team_recent_plays,
    get_team_record_vs_opponent,
    get_team_schedule,
    get_team_season_rollup,
    get_team_stat_leaders,
    query_nfl_db,
)
from tools.search_tools import search_web
from tools.sports_tools import get_team_info
from tools.prediction_model import predict_scheduled_game
from tools.prediction_model import predict_scheduled_game


class SportAgent:
    DEFAULT_SEASON = 2026
    SEASON_AWARE_TOOLS = {
        "get_player_game_stats",
        "get_player_stat_leaders",
        "get_team_game_stats",
        "get_team_stat_leaders",
        "get_team_schedule",
        "get_team_game_log",
        "get_team_recent_games",
        "get_team_recent_plays",
        "get_team_season_rollup",
        "get_team_rankings",
        "get_matchup_snapshot",
        "get_team_record_vs_opponent",
        "get_explosive_plays",
        "get_explosive_summary",
        "get_live_nfl_standings",
        "predict_scheduled_game",
    }

    def __init__(self):
        load_dotenv()
        self.client = OpenAI()
        self.model = "gpt-5.6"
        self.tool_priority = [
            "query_nfl_db",
            "get_player_stat_leaders",
            "get_team_stat_leaders",
            "get_player_game_stats",
            "get_team_game_stats",
            "get_team_schedule",
            "get_team_game_log",
            "get_team_recent_games",
            "get_matchup_snapshot",
            "get_team_rankings",
            "get_team_season_rollup",
            "get_live_nfl_standings",
            "get_live_nfl_spread",
            "get_weather_for_city",
            "get_team_news",
            "search_web",
        ]
        self.instructions = """
You are a sports analysis agent.

Use this tool selection order for every question:
1. Prefer local database tools for structured facts such as team records, schedules, season summaries, rankings, recent games, matchup history, and per-game player/team statistics. For statistical questions, query the local database before any web search; search is permitted only when database results are empty.
2. If the question is about current or live context, use live tools for weather, standings, team news, and NFL point spreads.
3. If the database and live tools do not have the answer, use a web search or external search tool as a last resort.
4. If no reliable source provides the answer, say that the information is unavailable and do not guess.

Analyze matchups using only information supplied by tools or the user.
Consider recent performance, team statistics, injuries, matchup characteristics, and situational factors when that data is available.
Clearly distinguish facts from opinions. Never invent data or sources.
When a tool returns no rows or empty results, do not keep retrying the same tool with different guesses.
Stop and explain that the requested data is unavailable in the current dataset or sources.
Unless the user specifies another season or explicitly asks for all-time/all-seasons data, use the 2026 season. Never silently substitute an older season for a 2026 request.
For a team-specific player leader question, filter the player leaderboard to that team; do not substitute a league-wide leader. For quarterbacks use position_group=quarterback and passing stats; for running backs use position_group=running_back and rushing stats; for receivers use position_group=receiver and receiving stats; for defensive leaders use position_group=defense and defensive sacks, interceptions, or forced_fumbles. Explain the stat total, games counted, team, and season using the database result.
For matchup win probabilities, always use predict_scheduled_game. Report home_win_probability and away_win_probability as the selected raw-model estimates, not guarantees. The Platt-calibrated fields are experimental candidates and calibration_applied is false; do not present those candidates as selected probabilities. Never invent a probability or substitute web search for a failed model prediction.
For a game prediction, use predict_scheduled_game and report its home/away probabilities as model estimates, not guarantees. Do not invent a probability if no scheduled matchup or model data is available.
For a current NFL point spread, always use get_live_nfl_spread. Report the provider, bookmaker count, consensus spread, and fetched_at timestamp. A point spread is betting-market data, not the prediction model's win probability. If the live spread source is unavailable, say so and do not substitute a guessed line or generic web-search snippet.
""".strip()

        self.tools = [
            {
                "type": "function",
                "name": "get_team_info",
                "description": "Get the available information for a sports team.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {
                            "type": "string",
                            "description": "The full or common name of the team.",
                        }
                    },
                    "required": ["team"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "query_nfl_db",
                "description": "Run a read-only SQL query against approved NFL views for schedules, season rollups, player and team game stats, and explosive plays.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A single read-only SQL SELECT/WITH query against approved NFL views, including v_player_game_stats and v_team_game_stats.",
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_player_game_stats",
                "description": "Get a player's per-game passing, rushing, receiving, sack, interception, and forced-fumble stats, including listed position and position group.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                        "limit": {"type": "integer"},
                    },
                    "required": ["player", "season", "limit"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_game_stats",
                "description": "Get a team's per-game passing, rushing, receiving, sack, interception, and forced-fumble stats from the local database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                        "limit": {"type": "integer"},
                    },
                    "required": ["team", "season", "limit"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_player_stat_leaders",
                "description": "Rank players by a supported season total, optionally filtered to a team and position group.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stat": {"type": "string", "enum": [
                            "passing_attempts", "completions", "passing_yards", "passing_tds",
                            "interceptions_thrown", "sacks_taken", "rushing_attempts", "rushing_yards",
                            "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds",
                            "defensive_sacks", "defensive_interceptions", "forced_fumbles",
                        ]},
                        "season": {"type": ["integer", "null"]},
                        "limit": {"type": "integer"},
                        "team": {
                            "type": "string",
                            "nullable": True,
                            "description": "Specific team name or nickname; use null for a league-wide leader.",
                        },
                        "position_group": {"type": "string", "enum": [
                            "quarterback", "running_back", "receiver", "defense",
                        ], "nullable": True, "description": "Role filter, or null for all positions."},
                    },
                    "required": ["stat", "season", "limit", "team", "position_group"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_stat_leaders",
                "description": "Rank teams by a supported season total such as passing yards, rushing yards, sacks, or interceptions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stat": {"type": "string", "enum": [
                            "passing_attempts", "completions", "passing_yards", "passing_tds",
                            "interceptions_thrown", "sacks_taken", "rushing_attempts", "rushing_yards",
                            "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds",
                            "defensive_sacks", "defensive_interceptions", "forced_fumbles",
                        ]},
                        "season": {"type": ["integer", "null"]},
                        "limit": {"type": "integer"},
                    },
                    "required": ["stat", "season", "limit"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "predict_scheduled_game",
                "description": "Return reproducible home and away win probabilities for a scheduled matchup using the backtested historical model.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team_a": {"type": "string"},
                        "team_b": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["team_a", "team_b", "season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_season_rollup",
                "description": "Return season-level team totals for a specific team, including wins, losses, points, and point differential.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["team", "season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_recent_games",
                "description": "Return recent game history for a team from v_team_game.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "limit": {"type": "integer"},
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["team", "limit", "season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_explosive_summary",
                "description": "Return explosive play summaries across teams for a given season or all seasons.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_explosive_plays",
                "description": "Fetch explosive-play totals by team for a season or across all seasons.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_recent_plays",
                "description": "Return recent game history for a team from the database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "limit": {"type": "integer"},
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["team", "limit", "season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_rankings",
                "description": "Return season rankings across teams ordered by wins and point differential.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "season": {"type": ["integer", "null"]},
                        "limit": {"type": "integer"},
                    },
                    "required": ["season", "limit"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_matchup_snapshot",
                "description": "Return a lightweight season snapshot for two teams from the database, including record and scoring data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team_a": {"type": "string"},
                        "team_b": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["team_a", "team_b", "season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_record_vs_opponent",
                "description": "Return a team's game history against a specific opponent from the database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "opponent": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["team", "opponent", "season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_game_log",
                "description": "Return the recent game log for a team, including opponent, venue, score, and result.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                        "limit": {"type": "integer"},
                    },
                    "required": ["team", "season", "limit"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_schedule",
                "description": "Return scheduled and completed games for a team; scores and results are present only when reported by the data source.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["team", "season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_weather_for_city",
                "description": "Fetch current or near-term weather for a city using a public no-key weather API.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "date_value": {"type": "string", "nullable": True},
                    },
                    "required": ["city", "date_value"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_live_nfl_standings",
                "description": "Return current NFL standings from the ESPN live standings feed for a season.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "season": {"type": ["integer", "null"]},
                    },
                    "required": ["season"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_team_news",
                "description": "Return the most recent ESPN news headlines for a team.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["team", "limit"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_live_nfl_spread",
                "description": "Fetch current NFL point spreads for a matchup from a structured live odds provider and save the returned bookmaker lines to the local database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team_a": {
                            "type": "string",
                            "description": "Full or common name of the first NFL team.",
                        },
                        "team_b": {
                            "type": "string",
                            "description": "Full or common name of the second NFL team.",
                        },
                    },
                    "required": ["team_a", "team_b"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_scheme_fit",
                "description": "Fetch scheme-vs-scheme data for one NFL team: man coverage rate, zone coverage rate, blitz rate, base front, and personnel-grouping tendency.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {
                            "type": "string",
                            "description": "Team abbreviation, e.g. 'WAS'",
                        },
                        "season": {
                            "type": "integer",
                            "description": "e.g. 2026",
                        },
                        "side": {
                            "type": "string",
                            "enum": ["offense", "defense"],
                            "description": "Which side of the ball to pull scheme data for",
                        },
                    },
                    "required": ["team", "season", "side"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "search_web",
                "description": "Use a public web search tool as a last resort when the database and live tools do not contain the needed answer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A targeted search query when local and live sports sources are insufficient.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of search result entries to return.",
                        },
                    },
                    "required": ["query", "max_results"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def _execute_tool(self, name, arguments):
        if name == "get_team_info":
            return get_team_info(**arguments)
        if name == "query_nfl_db":
            return query_nfl_db(**arguments)
        if name == "get_player_game_stats":
            return get_player_game_stats(**arguments)
        if name == "get_team_game_stats":
            return get_team_game_stats(**arguments)
        if name == "get_player_stat_leaders":
            return get_player_stat_leaders(**arguments)
        if name == "get_team_stat_leaders":
            return get_team_stat_leaders(**arguments)
        if name == "predict_scheduled_game":
            return predict_scheduled_game(**arguments)
        if name == "predict_scheduled_game":
            return predict_scheduled_game(**arguments)
        if name == "get_team_season_rollup":
            return get_team_season_rollup(**arguments)
        if name == "get_team_recent_games":
            return get_team_recent_games(**arguments)
        if name == "get_explosive_summary":
            return get_explosive_summary(**arguments)
        if name == "get_explosive_plays":
            return get_explosive_plays(**arguments)
        if name == "get_team_recent_plays":
            return get_team_recent_plays(**arguments)
        if name == "get_team_rankings":
            return get_team_rankings(**arguments)
        if name == "get_matchup_snapshot":
            return get_matchup_snapshot(**arguments)
        if name == "get_team_record_vs_opponent":
            return get_team_record_vs_opponent(**arguments)
        if name == "get_team_game_log":
            return get_team_game_log(**arguments)
        if name == "get_team_schedule":
            return get_team_schedule(**arguments)
        if name == "get_weather_for_city":
            return get_weather_for_city(**arguments)
        if name == "get_live_nfl_standings":
            return get_live_nfl_standings(**arguments)
        if name == "get_team_news":
            return get_team_news(**arguments)
        if name == "get_live_nfl_spread":
            return get_live_nfl_spread(**arguments)
        if name == "get_scheme_fit":
            return get_scheme_fit(**arguments)
        if name == "search_web":
            return search_web(**arguments)
        raise ValueError(f"Unknown tool requested: {name}")

    def _is_stat_question(self, task: str) -> bool:
        terms = (
            "stat", "passing", "passer", "quarterback", "rushing", "rusher", "running back",
            "receiving", "receiver", "wide receiver", "tight end", "defense", "defensive back",
            "linebacker", "safety", "yards", "touchdown", "interception", "sack", "fumble",
            "completion", "reception", "targets",
        )
        lower = task.lower()
        return any(term in lower for term in terms)

    def _is_prediction_question(self, task: str) -> bool:
        lower = task.lower()
        return any(term in lower for term in (
            "predict", "prediction", "probability", "probabilities", "win chance", "win probability",
            "odds of winning", "who will win", "who wins", "will win",
        ))

    def _is_spread_question(self, task: str) -> bool:
        lower = task.lower()
        return any(term in lower for term in (
            "point spread", "betting spread", "current spread", "live spread",
            "latest spread", "cover the spread", "favorite by", "underdog by",
        ))

    def _season_for_question(self, task: str) -> int | None:
        year = re.search(r"\b(?:19|20)\d{2}\b", task)
        if year:
            return int(year.group())
        normalized = task.lower().replace("-", " ")
        if any(phrase in normalized for phrase in ("all time", "all seasons", "every season", "career")):
            return None
        if any(phrase in normalized for phrase in (
            "last season", "previous season", "prior season", "last year", "previous year", "prior year",
        )):
            return self.DEFAULT_SEASON - 1
        return self.DEFAULT_SEASON

    def _database_first_tools(self, task: str) -> list[dict]:
        if self._is_spread_question(task):
            return [tool for tool in self.tools if tool["name"] == "get_live_nfl_spread"]
        if self._is_prediction_question(task):
            return [tool for tool in self.tools if tool["name"] == "predict_scheduled_game"]
        if not self._is_stat_question(task):
            return self.tools
        database_tools = {
            "get_player_game_stats",
            "get_team_game_stats",
            "get_player_stat_leaders",
            "get_team_stat_leaders",
        }
        return [tool for tool in self.tools if tool["name"] in database_tools]

    def _tool_priority_hint(self, task: str) -> str:
        lower = task.lower()
        ordered = list(self.tool_priority)

        if any(word in lower for word in ["weather", "rain", "snow", "temperature", "forecast", "wind"]):
            ordered = ["get_weather_for_city", *[name for name in ordered if name != "get_weather_for_city"]]
        if any(word in lower for word in ["standings", "rankings", "wins", "losses", "record", "league"]):
            ordered = ["get_live_nfl_standings", "get_team_rankings", *[name for name in ordered if name not in {"get_live_nfl_standings", "get_team_rankings"}]]
        if any(word in lower for word in ["schedule", "next week", "next weekend", "opponent", "play", "game", "matchup"]):
            ordered = ["get_team_schedule", "get_team_game_log", "get_matchup_snapshot", *[name for name in ordered if name not in {"get_team_schedule", "get_team_game_log", "get_matchup_snapshot"}]]
        if any(word in lower for word in ["news", "injury", "breaking", "headlines", "rumor"]):
            ordered = ["get_team_news", *[name for name in ordered if name != "get_team_news"]]
        if self._is_spread_question(task):
            ordered = ["get_live_nfl_spread", *[name for name in ordered if name != "get_live_nfl_spread"]]
        if any(word in lower for word in ["search", "latest", "current", "recent", "unknown", "unavailable", "what happened"]):
            ordered = [*ordered, "search_web"]

        if self._is_stat_question(task):
            stat_tools = [
                "get_player_game_stats",
                "get_team_game_stats",
                "get_player_stat_leaders",
                "get_team_stat_leaders",
                "query_nfl_db",
            ]
            if any(word in lower for word in ["leader", "lead", "most", "top", "highest", "rank"]):
                stat_tools = [
                    "get_player_stat_leaders",
                    "get_team_stat_leaders",
                    "get_player_game_stats",
                    "get_team_game_stats",
                    "query_nfl_db",
                ]
            ordered = [*stat_tools, *[name for name in ordered if name not in stat_tools]]
        if self._is_prediction_question(task):
            ordered = ["predict_scheduled_game", *[name for name in ordered if name != "predict_scheduled_game"]]

        return ", ".join(ordered)

    def run(self, task):
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")

        task_text = task.strip()
        prediction_question = self._is_prediction_question(task_text)
        spread_question = self._is_spread_question(task_text)
        database_first = self._is_stat_question(task_text) or prediction_question or spread_question
        requested_season = self._season_for_question(task_text)
        priority_hint = self._tool_priority_hint(task_text)
        response = self.client.responses.create(
            model=self.model,
            instructions=f"{self.instructions}\n\nTool priority for this request: {priority_hint}\nPrefer these tools in order before resorting to search or abstaining.",
            input=task_text,
            tools=self._database_first_tools(task_text),
            tool_choice="required" if database_first else "auto",
        )
        search_fallback_active = False

        for _ in range(8):
            calls = [
                item for item in response.output if item.type == "function_call"
            ]

            if not calls:
                if not response.output_text:
                    raise RuntimeError("The model returned no final text.")
                return response.output_text

            tool_outputs = []
            tool_results = []

            for call in calls:
                print(f"TOOL CALLED: {call.name}")

                try:
                    arguments = json.loads(call.arguments)
                    if call.name in self.SEASON_AWARE_TOOLS and "season" in arguments:
                        arguments["season"] = requested_season
                    print(f"ARGUMENTS: {json.dumps(arguments)}")
                    result = self._execute_tool(call.name, arguments)
                    tool_results.append(result)
                    output = json.dumps(result)
                except Exception as exc:
                    tool_results.append({"error": str(exc)})
                    output = json.dumps({"error": str(exc)})

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )

            database_empty = bool(tool_results) and all(
                isinstance(result, dict)
                and result.get("row_count") == 0
                and isinstance(result.get("rows"), list)
                and len(result["rows"]) == 0
                for result in tool_results
            )
            if database_empty and not database_first:
                return (
                    "The requested NFL data is not available in the current database. "
                    "The tool returned no rows, so I stopped rather than guessing with repeated retries."
                )

            if database_first and database_empty and prediction_question:
                return "A model probability is unavailable because the local database returned no prediction data."

            if database_first and database_empty and not search_fallback_active:
                next_tools = [tool for tool in self.tools if tool["name"] == "search_web"]
                next_instructions = (
                    f"{self.instructions}\n\nThe local database returned no rows for this statistical question. "
                    "Use search_web once as a fallback; do not retry database tools."
                )
                next_tool_choice = "required"
                search_fallback_active = True
            elif database_first:
                next_tools = []
                next_instructions = (
                    f"{self.instructions}\n\nAnswer from the supplied tool results only. "
                    "Do not introduce unsupported statistics."
                )
                next_tool_choice = "none"
            else:
                next_tools = self.tools
                next_instructions = self.instructions
                next_tool_choice = "auto"

            response = self.client.responses.create(
                model=self.model,
                instructions=next_instructions,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=next_tools,
                tool_choice=next_tool_choice,
            )

        raise RuntimeError("The agent exceeded the maximum number of tool rounds.")


def ask_question(question: str) -> str:
    agent = SportAgent()
    return agent.run(question)


if __name__ == "__main__":
    task = "Use get_team_season_rollup for the Eagles and tell me what the tool returned."
    result = ask_question(task)
    print(result)

