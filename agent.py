import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from tools.live_tools import get_live_nfl_standings, get_team_news, get_weather_for_city
from tools.query_nfl_db import (
    get_explosive_plays,
    get_explosive_summary,
    get_matchup_snapshot,
    get_scheme_fit,
    get_team_game_log,
    get_team_rankings,
    get_team_recent_games,
    get_team_recent_plays,
    get_team_record_vs_opponent,
    get_team_schedule,
    get_team_season_rollup,
    query_nfl_db,
)
from tools.search_tools import search_web
from tools.sports_tools import get_team_info


class SportAgent:
    def __init__(self):
        load_dotenv()
        self.client = OpenAI()
        self.model = "gpt-5.6"
        self.tool_priority = [
            "query_nfl_db",
            "get_team_schedule",
            "get_team_game_log",
            "get_team_recent_games",
            "get_matchup_snapshot",
            "get_team_rankings",
            "get_team_season_rollup",
            "get_live_nfl_standings",
            "get_weather_for_city",
            "get_team_news",
            "search_web",
        ]
        self.instructions = """
You are a sports analysis agent.

Use this tool selection order for every question:
1. Prefer local database tools for structured facts such as team records, schedules, season summaries, rankings, recent games, and matchup history.
2. If the question is about current or live context, use live tools for weather, standings, and team news.
3. If the database and live tools do not have the answer, use a web search or external search tool as a last resort.
4. If no reliable source provides the answer, say that the information is unavailable and do not guess.

Analyze matchups using only information supplied by tools or the user.
Consider recent performance, team statistics, injuries, matchup characteristics, and situational factors when that data is available.
Clearly distinguish facts from opinions. Never invent data or sources.
When a tool returns no rows or empty results, do not keep retrying the same tool with different guesses.
Stop and explain that the requested data is unavailable in the current dataset or sources.
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
                "description": "Run a read-only SQL query against the approved NFL database views for season rollups, game data, and explosive plays.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A single read-only SQL SELECT/WITH query against v_season_team, v_team_game, or v_explosive_season.",
                        }
                    },
                    "required": ["query"],
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
                        "season": {"type": "integer", "nullable": True},
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
                    },
                    "required": ["team", "limit"],
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
                        "season": {"type": "integer", "nullable": True},
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
                        "season": {"type": "integer", "nullable": True},
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
                    },
                    "required": ["team", "limit"],
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
                        "season": {"type": "integer", "nullable": True},
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
                        "season": {"type": "integer", "nullable": True},
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
                        "season": {"type": "integer", "nullable": True},
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
                        "season": {"type": "integer", "nullable": True},
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
                "description": "Return the schedule for a team, including opponent, venue, and game result.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "team": {"type": "string"},
                        "season": {"type": "integer", "nullable": True},
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
                        "season": {"type": "integer", "nullable": True},
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
                    "required": ["query"],
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
        if name == "get_scheme_fit":
            return get_scheme_fit(**arguments)
        if name == "search_web":
            return search_web(**arguments)
        raise ValueError(f"Unknown tool requested: {name}")

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
        if any(word in lower for word in ["search", "latest", "current", "recent", "unknown", "unavailable", "what happened"]):
            ordered = [*ordered, "search_web"]

        return ", ".join(ordered)

    def run(self, task):
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")

        task_text = task.strip()
        priority_hint = self._tool_priority_hint(task_text)
        response = self.client.responses.create(
            model=self.model,
            instructions=f"{self.instructions}\n\nTool priority for this request: {priority_hint}\nPrefer these tools in order before resorting to search or abstaining.",
            input=task_text,
            tools=self.tools,
        )

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
                print(f"ARGUMENTS: {call.arguments}")

                try:
                    arguments = json.loads(call.arguments)
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

            if all(
                isinstance(result, dict)
                and result.get("row_count") == 0
                and isinstance(result.get("rows"), list)
                and len(result["rows"]) == 0
                for result in tool_results
                if isinstance(result, dict)
            ):
                return (
                    "The requested NFL data is not available in the current database. "
                    "The tool returned no rows, so I stopped rather than guessing with repeated retries."
                )

            response = self.client.responses.create(
                model=self.model,
                instructions=self.instructions,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=self.tools,
            )

        raise RuntimeError("The agent exceeded the maximum number of tool rounds.")


def ask_question(question: str) -> str:
    agent = SportAgent()
    return agent.run(question)


if __name__ == "__main__":
    task = "Use get_team_season_rollup for the Eagles and tell me what the tool returned."
    result = ask_question(task)
    print(result)

