from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import ask_question
from tools.prediction_model import (
    DEFAULT_PREDICTION_SEASON,
    DEFAULT_START_SEASON,
    DEFAULT_TRAIN_END_SEASON,
    predict_scheduled_game,
    walk_forward_backtest,
)

app = FastAPI(title="Sports Talk Agent API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str


class PredictionRequest(BaseModel):
    team_a: str
    team_b: str
    season: int = DEFAULT_PREDICTION_SEASON


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/ask")
def ask_question_route(payload: AskRequest):
    return {"answer": ask_question(payload.question)}


@app.post("/predict")
def predict_route(payload: PredictionRequest):
    try:
        return predict_scheduled_game(payload.team_a, payload.team_b, season=payload.season)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/prediction/backtest")
def prediction_backtest(
    start_season: int = DEFAULT_START_SEASON,
    end_season: int = DEFAULT_TRAIN_END_SEASON,
    include_predictions: bool = False,
):
    try:
        result = walk_forward_backtest(start_season=start_season, end_season=end_season)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not include_predictions:
        result.pop("predictions", None)
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
