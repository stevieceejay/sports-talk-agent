import os
from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY is not set")

client = OpenAI(api_key=api_key)


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

    def run(self, task):
        response = client.responses.create(
            model="gpt-4o-mini",  # or another valid model in your account
            instructions=self.instructions,
            input=str(task),
        )
        return response.output_text