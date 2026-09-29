import json
import os

from dotenv import load_dotenv
from openai import OpenAI

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
            }
        ]

    def _execute_tool(self, name, arguments):
        if name == "get_team_info":
            return get_team_info(**arguments)
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

            for call in calls:
                print(f"TOOL CALLED: {call.name}")
                print(f"ARGUMENTS: {call.arguments}")

                try:
                    arguments = json.loads(call.arguments)
                    result = self._execute_tool(call.name, arguments)
                    output = json.dumps(result)
                except Exception as exc:
                    output = json.dumps({"error": str(exc)})

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
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
    task = "use get_team_info to get information on the Eagles and Bears game Then tell me what information the tool returned."
    result = agent.run(task)
    print(result)

