from fastapi import FastAPI
from pydantic import BaseModel

from agent import ask_question

app = FastAPI(title="Sports Talk Agent API")


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/ask")
def ask_question_route(payload: AskRequest):
    return {"answer": ask_question(payload.question)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
