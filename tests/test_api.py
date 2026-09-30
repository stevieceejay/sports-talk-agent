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
