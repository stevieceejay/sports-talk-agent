from openai import OpenAI
imoprt os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class SportAgent: 

    def __init__(self):
        self.instructions = """you are a sports analysis agent.

        Your job is to analyze sports matchups using:
        -recent performance
        -team statistics
        -injuries
        -matchup characteristics
        -situational factors

        Explain your reasoning clearly.
        So not invent statistics or information. If you don't know, say you don't know.
        So not invent sources.
        """


    def run(self, task):
        response = client.responses.create(
            model="gpt-5.6",
            instructions=self.instructions,
            input=task
        )
        return response.output_text