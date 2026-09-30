import json
from types import SimpleNamespace

from agent import SportAgent


def test_tool_priority_prefers_db_then_live_then_search():
    agent = SportAgent()
    assert agent._tool_priority_hint("Who do the Rams play next weekend?")
    assert agent._tool_priority_hint("Who do the Rams play next weekend?").startswith("get_team_schedule")
    assert "search_web" in agent._tool_priority_hint("Who do the Rams play next weekend?")


def test_search_tool_is_registered():
    agent = SportAgent()
    names = [tool["name"] for tool in agent.tools]
    assert "search_web" in names


def test_stats_questions_force_database_tools_before_search():
    agent = SportAgent()
    names = [tool["name"] for tool in agent._database_first_tools("Who leads in rushing yards?")]

    assert "get_player_stat_leaders" in names
    assert "get_team_game_stats" in names
    assert "search_web" not in names
    assert agent._tool_priority_hint("Who leads in rushing yards?").startswith("get_player_stat_leaders")


def test_function_schemas_require_every_property():
    agent = SportAgent()
    for tool in agent.tools:
        properties = set(tool["parameters"]["properties"])
        assert properties == set(tool["parameters"]["required"]), tool["name"]


def test_player_leader_tool_supports_role_groups_and_forced_fumbles():
    agent = SportAgent()
    tool = next(tool for tool in agent.tools if tool["name"] == "get_player_stat_leaders")
    properties = tool["parameters"]["properties"]

    assert properties["position_group"]["enum"] == ["quarterback", "running_back", "receiver", "defense"]
    assert "forced_fumbles" in properties["stat"]["enum"]


class FakeResponses:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


def _response(response_id, output=(), output_text=""):
    return SimpleNamespace(id=response_id, output=list(output), output_text=output_text)


def _function_call(name, arguments, call_id="call-1"):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=json.dumps(arguments),
        call_id=call_id,
    )


def test_stats_search_fallback_is_available_only_after_empty_database(monkeypatch):
    agent = SportAgent()
    responses = FakeResponses([
        _response("db", [_function_call("get_player_stat_leaders", {
            "stat": "rushing_yards", "season": 2026, "limit": 1,
        })]),
        _response("search", [_function_call("search_web", {
            "query": "2026 NFL rushing yards leaders", "max_results": 3,
        }, call_id="call-2")]),
        _response("answer", output_text="Search fallback answer."),
    ])
    agent.client.responses = responses
    monkeypatch.setattr("agent.get_player_stat_leaders", lambda **kwargs: {
        "status": "empty", "rows": [], "row_count": 0,
    })
    monkeypatch.setattr("agent.search_web", lambda **kwargs: {
        "status": "ok", "results": [{"snippet": "A source result"}],
    })

    answer = agent.run("Who leads in rushing yards in 2026?")

    tool_sets = [[tool["name"] for tool in call["tools"]] for call in responses.calls]
    assert answer == "Search fallback answer."
    assert "search_web" not in tool_sets[0]
    assert tool_sets[1] == ["search_web"]
    assert tool_sets[2] == []
    assert responses.calls[0]["tool_choice"] == "required"


def test_stats_success_does_not_offer_web_search(monkeypatch):
    agent = SportAgent()
    responses = FakeResponses([
        _response("db", [_function_call("get_player_stat_leaders", {
            "stat": "rushing_yards", "season": 2026, "limit": 1,
        })]),
        _response("answer", output_text="Database answer."),
    ])
    agent.client.responses = responses
    monkeypatch.setattr("agent.get_player_stat_leaders", lambda **kwargs: {
        "status": "ok", "rows": [{"player_name": "Player", "total": 99}], "row_count": 1,
    })

    assert agent.run("Who leads in rushing yards in 2026?") == "Database answer."
    assert [tool["name"] for tool in responses.calls[0]["tools"]].count("search_web") == 0
    assert responses.calls[1]["tools"] == []


def test_season_selection_defaults_to_2026_and_honors_historical_requests():
    agent = SportAgent()

    assert agent._season_for_question("Who leads in rushing yards?") == 2026
    assert agent._season_for_question("Who led in rushing yards in 2024?") == 2024
    assert agent._season_for_question("Who led last season?") == 2025
    assert agent._season_for_question("Who has the career rushing record?") is None


def test_tool_arguments_are_forced_to_the_question_season(monkeypatch):
    agent = SportAgent()
    responses = FakeResponses([
        _response("db", [_function_call("get_player_stat_leaders", {
            "stat": "rushing_yards", "season": 2025, "limit": 1,
        })]),
        _response("answer", output_text="Database answer."),
    ])
    agent.client.responses = responses
    captured = []

    def fake_leaders(**arguments):
        captured.append(arguments)
        return {"status": "ok", "rows": [{"player_name": "Player", "total": 99}], "row_count": 1}

    monkeypatch.setattr("agent.get_player_stat_leaders", fake_leaders)

    assert agent.run("Who leads in rushing yards?") == "Database answer."
    assert captured[0]["season"] == 2026


def test_explicit_historical_season_overrides_model_tool_argument(monkeypatch):
    agent = SportAgent()
    responses = FakeResponses([
        _response("db", [_function_call("get_player_stat_leaders", {
            "stat": "rushing_yards", "season": 2026, "limit": 1,
        })]),
        _response("answer", output_text="Historical database answer."),
    ])
    agent.client.responses = responses
    captured = []

    def fake_leaders(**arguments):
        captured.append(arguments)
        return {"status": "ok", "rows": [{"player_name": "Player", "total": 99}], "row_count": 1}

    monkeypatch.setattr("agent.get_player_stat_leaders", fake_leaders)

    assert agent.run("Who led in rushing yards in 2024?") == "Historical database answer."
    assert captured[0]["season"] == 2024


def test_prediction_question_requires_local_model_and_defaults_to_2026(monkeypatch):
    agent = SportAgent()
    responses = FakeResponses([
        _response("model", [_function_call("predict_scheduled_game", {
            "team_a": "Cardinals", "team_b": "Rams", "season": 2025,
        })]),
        _response("answer", output_text="Arizona has a 58% home win probability."),
    ])
    agent.client.responses = responses
    captured = []

    def fake_prediction(**arguments):
        captured.append(arguments)
        return {"status": "ok", "home_win_probability": 0.58, "away_win_probability": 0.42}

    monkeypatch.setattr("agent.predict_scheduled_game", fake_prediction)

    answer = agent.run("What are the win probabilities for the next Cardinals-Rams game?")

    first_tool_names = [tool["name"] for tool in responses.calls[0]["tools"]]
    assert answer == "Arizona has a 58% home win probability."
    assert first_tool_names == ["predict_scheduled_game"]
    assert responses.calls[0]["tool_choice"] == "required"
    assert responses.calls[1]["tools"] == []
    assert captured[0]["season"] == 2026


def test_prediction_model_error_does_not_fall_back_to_search(monkeypatch):
    agent = SportAgent()
    responses = FakeResponses([
        _response("model", [_function_call("predict_scheduled_game", {
            "team_a": "Cardinals", "team_b": "Rams", "season": 2026,
        })]),
        _response("answer", output_text="No scheduled matchup is available."),
    ])
    agent.client.responses = responses
    monkeypatch.setattr(
        "agent.predict_scheduled_game",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("No unplayed game is scheduled")),
    )

    assert agent.run("What is the win probability for the Cardinals-Rams game?") == "No scheduled matchup is available."
    assert [tool["name"] for tool in responses.calls[0]["tools"]] == ["predict_scheduled_game"]
    assert responses.calls[1]["tools"] == []
