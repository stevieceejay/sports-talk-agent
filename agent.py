from importlib import import_module
from tools.sports_tools import get_team_info
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return None

load_dotenv()

try:
    OpenAI = import_module("openai").OpenAI
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "The 'openai' package is required. Install it with: pip install openai"
    ) from exc


class SportAgent:
    def __init__(self):
        self.instructions = """
        You are a sports analysis agent.

        Your job is to analyze sports matchups using:
        - recent performance
        - team statistics
        - injuries
        - matchup characteristics
        - situational factors

        Explain your reasoning clearly.
        Do not invent statistics or sources.
        If you do not know, say you do not know.
        """

        self.tools = [
    {
        "type": "function",
        "name": "get_team_info",
        "description": "Gets basic information about a sports team, including sport type and status.",
        "parameters": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "The name of the sports team to retrieve information for."
                }
            },
            "required": ["team"]
        }
    }
]


        

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to your shell or .env file."
            )

        self.client = OpenAI(api_key=api_key)

    def run(self, task):
        response = self.client.responses.create(
            model="gpt-5.6",
            instructions=self.instructions,
            input=str(task),
        )
        return response.output_text


if __name__ == "__main__":
    agent = SportAgent()
    task = "Analyze the matchup between Team A and Team B."
    result = agent.run(task)
    print(result)
