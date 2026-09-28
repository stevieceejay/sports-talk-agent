from agent import SportAgent  # type: ignore[attr-defined]

agent = SportAgent()

result = agent.run(
    "Analyze todays monday night football game between bears and eagles."
)
print(result)