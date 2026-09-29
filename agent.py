import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from tools.query_nfl_db import (
    get_explosive_summary,
    get_team_recent_games,
    get_team_season_rollup,
    query_nfl_db,
)
from tools.sports_tools import get_team_info


class SportAgent:
    def __init__(self):
        load_dotenv()
        self.client = OpenAI()
        self.model = "gpt-5.6"
        self.instructions = """
You are a sports analysis agent.

Analyze matchups using only information supplied by tools or the user.
Consider recent performance, team statistics, injuries, matchup
characteristics, and situational factors when that data is available.
Clearly distinguish facts from opinions. Never invent data or sources.
If required information is unavailable, say so.
When a tool returns no rows or empty results, do not keep retrying the same tool with different guesses.
Stop and explain that the requested data is unavailable in the current dataset.
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
        raise ValueError(f"Unknown tool requested: {name}")

    def run(self, task):
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")

        response = self.client.responses.create(
            model=self.model,
            instructions=self.instructions,
            input=task.strip(),
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


if __name__ == "__main__":
    agent = SportAgent()
    task = "Use get_team_season_rollup for the Eagles and tell me what the tool returned."
    result = agent.run(task)
    print(result)

