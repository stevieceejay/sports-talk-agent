from agent import SportAgent


def main():
    agent = SportAgent()
    result = agent.run(
        "Analyze today's Monday Night Football game between the Bears and Eagles."
    )
    print(result)


if __name__ == "__main__":
    main()


