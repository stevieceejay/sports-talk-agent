from fastapi import FastAPI
from pydantic import BaseModel

from agent import SportAgent

app = FastAPI(title="Sports Talk Agent API")


class AskRequest(BaseModel):
    question: str


def get_agent() -> SportAgent:
    return SportAgent()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/ask")
def ask_question(payload: AskRequest):
    agent = get_agent()
    return {"answer": agent.run(payload.question)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
