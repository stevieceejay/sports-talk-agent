from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

try:
    OpenAI = import_module("openai").OpenAI
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "The 'openai' package is required. Install it with: pip install openai"
    ) from exc

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
            model="gpt-5.6",  
            instructions=self.instructions,
            input=task,
        )
        return response.output_text


if __name__ == "__main__":
    agent = SportAgent()
    task = "Analyze the matchup between Team A and Team B."
    result = agent.run(task)
    print(result)