from agent import SportAgent


def main():
    agent = SportAgent()
    print("Ask the sports agent a question (type 'exit' to quit):")

    while True:
        question = input("\nQuestion: ").strip()
        if not question:
            print("Please enter a question.")
            continue
        if question.lower() in {"exit", "quit", "q"}:
            print("Goodbye.")
            break

        print("\nThinking...\n")
        result = agent.run(question)
        print(result)


if __name__ == "__main__":
    main()


