from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ask_returns_answer(monkeypatch):
    monkeypatch.setattr(main, "ask_question", lambda q: "Mock answer for: " + q)

    response = client.post("/ask", json={"question": "Who will win?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Mock answer for: Who will win?"


def test_predict_returns_model_probabilities_and_defaults_to_2026(monkeypatch):
    calls = []

    def fake_prediction(team_a, team_b, season):
        calls.append((team_a, team_b, season))
        return {"home_win_probability": 0.62, "away_win_probability": 0.38}

    monkeypatch.setattr(main, "predict_scheduled_game", fake_prediction)

    response = client.post("/predict", json={"team_a": "Cardinals", "team_b": "Rams"})

    assert response.status_code == 200
    assert response.json()["home_win_probability"] == 0.62
    assert calls == [("Cardinals", "Rams", 2026)]


def test_predict_returns_validation_error_for_unscheduled_matchup(monkeypatch):
    def no_scheduled_game(*args, **kwargs):
        raise ValueError("No unplayed schedule entry found")

    monkeypatch.setattr(main, "predict_scheduled_game", no_scheduled_game)

    response = client.post("/predict", json={"team_a": "Cardinals", "team_b": "Rams"})

    assert response.status_code == 422
    assert response.json()["detail"] == "No unplayed schedule entry found"


def test_backtest_route_can_include_per_game_probabilities(monkeypatch):
    monkeypatch.setattr(main, "walk_forward_backtest", lambda **kwargs: {
        "games_backtested": 10,
        "metrics": {"brier_score": 0.22},
        "predictions": [{"game_id": "sample", "home_win_probability": 0.6}],
    })

    summary = client.get("/prediction/backtest")
    detailed = client.get("/prediction/backtest?include_predictions=true")

    assert summary.status_code == 200
    assert "predictions" not in summary.json()
    assert detailed.json()["predictions"][0]["home_win_probability"] == 0.6
