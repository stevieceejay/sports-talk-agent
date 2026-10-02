import sqlite3

from tools import live_tools
from tools.live_tools import (
    get_live_nfl_spread,
    get_live_nfl_standings,
    get_team_news,
    get_weather_for_city,
)


def test_live_tools_are_callable():
    assert callable(get_weather_for_city)
    assert callable(get_live_nfl_standings)
    assert callable(get_team_news)
    assert callable(get_live_nfl_spread)


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


def test_live_spread_requires_api_key(monkeypatch):
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)

    result = get_live_nfl_spread("Seattle Seahawks", "San Francisco 49ers")

    assert result["status"] == "unavailable"
    assert result["stored_rows"] == 0
    assert "THE_ODDS_API_KEY" in result["error"]


def test_live_spread_is_returned_and_persisted(monkeypatch, tmp_path):
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key")
    monkeypatch.setattr(
        live_tools,
        "_fetch_json",
        lambda url: [
            {
                "id": "sea-sf-2026",
                "commence_time": "2026-10-11T20:05:00Z",
                "home_team": "Seattle Seahawks",
                "away_team": "San Francisco 49ers",
                "bookmakers": [
                    {
                        "key": "book-a",
                        "title": "Book A",
                        "last_update": "2026-10-01T20:00:00Z",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": "Seattle Seahawks", "price": -110, "point": -2.5},
                                    {"name": "San Francisco 49ers", "price": -110, "point": 2.5},
                                ],
                            }
                        ],
                    },
                    {
                        "key": "book-b",
                        "title": "Book B",
                        "last_update": "2026-10-01T20:02:00Z",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": "Seattle Seahawks", "price": -105, "point": -3.0},
                                    {"name": "San Francisco 49ers", "price": -115, "point": 3.0},
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    )
    db_path = tmp_path / "nfl.db"

    result = get_live_nfl_spread("Seahawks", "49ers", db_path=db_path)

    assert result["status"] == "ok"
    assert result["consensus_home_spread"] == -2.75
    assert result["consensus_away_spread"] == 2.75
    assert result["bookmaker_count"] == 2
    assert result["stored_rows"] == 4
    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT bookmaker, outcome_team, spread_point FROM v_nfl_spread ORDER BY bookmaker, outcome_team"
        ).fetchall()
    assert len(stored) == 4
    assert ("Book A", "Seattle Seahawks", -2.5) in stored
