from tools.live_tools import get_live_nfl_standings, get_team_news, get_weather_for_city


def test_live_tools_are_callable():
    assert callable(get_weather_for_city)
    assert callable(get_live_nfl_standings)
    assert callable(get_team_news)


def test_weather_request_has_expected_shape():
    result = get_weather_for_city("Chicago", "2026-09-29")
    assert isinstance(result, dict)
    assert result["city"] == "Chicago"
    assert "forecast" in result
    assert result["status"] in {"ok", "not_found"}


def test_standings_request_has_expected_shape():
    result = get_live_nfl_standings(2026)
    assert isinstance(result, dict)
    assert result["source"] == "ESPN"
    assert "teams" in result


def test_team_news_request_has_expected_shape():
    result = get_team_news("Eagles", limit=2)
    assert isinstance(result, dict)
    assert result["team"] == "Eagles"
    assert "articles" in result
