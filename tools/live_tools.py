"""Live sports-context tools using public read-only endpoints."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any
from urllib import parse, request


USER_AGENT = "sports-talk-agent/1.0"
DB_PATH = Path(__file__).resolve().parents[1] / "db" / "nfl.db"
NFL_ODDS_ENDPOINT = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"
NFL_ODDS_SOURCE_URL = "https://the-odds-api.com/sports-odds-data/nfl-odds.html"


def _fetch_json(url: str, timeout: int = 20) -> Any:
    """Fetch and decode JSON from a public endpoint."""
    try:
        req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read()
        return json.loads(body.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network guardrail
        return {"status": "error", "error": str(exc)}


def _normalize_team_name(team: str) -> str:
    team = (team or "").strip()
    if not team:
        raise ValueError("team must not be empty")
    return team


def _team_matches(candidate: str, requested: str) -> bool:
    candidate_value = " ".join((candidate or "").lower().split())
    requested_value = " ".join((requested or "").lower().split())
    return bool(requested_value) and (
        candidate_value == requested_value
        or requested_value in candidate_value
        or candidate_value in requested_value
    )


def _initialize_spread_storage(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS nfl_spread (
            event_id TEXT NOT NULL,
            commence_time TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            bookmaker_key TEXT NOT NULL,
            bookmaker TEXT NOT NULL,
            outcome_team TEXT NOT NULL,
            spread_point REAL NOT NULL,
            price REAL,
            market_last_update TEXT,
            fetched_at TEXT NOT NULL,
            source_url TEXT NOT NULL,
            PRIMARY KEY (event_id, bookmaker_key, outcome_team)
        );

        CREATE VIEW IF NOT EXISTS v_nfl_spread AS
        SELECT event_id, commence_time, home_team, away_team, bookmaker_key,
               bookmaker, outcome_team, spread_point, price,
               market_last_update, fetched_at, source_url
        FROM nfl_spread;
        """
    )


def _store_spread_rows(
    rows: list[dict[str, Any]],
    db_path: Path | str | None = None,
) -> int:
    if not rows:
        return 0

    target = Path(db_path) if db_path is not None else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        _initialize_spread_storage(connection)
        connection.executemany(
            """
            INSERT INTO nfl_spread (
                event_id, commence_time, home_team, away_team,
                bookmaker_key, bookmaker, outcome_team, spread_point,
                price, market_last_update, fetched_at, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, bookmaker_key, outcome_team) DO UPDATE SET
                commence_time = excluded.commence_time,
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                bookmaker = excluded.bookmaker,
                spread_point = excluded.spread_point,
                price = excluded.price,
                market_last_update = excluded.market_last_update,
                fetched_at = excluded.fetched_at,
                source_url = excluded.source_url
            """,
            [
                (
                    row["event_id"],
                    row["commence_time"],
                    row["home_team"],
                    row["away_team"],
                    row["bookmaker_key"],
                    row["bookmaker"],
                    row["outcome_team"],
                    row["spread_point"],
                    row.get("price"),
                    row.get("market_last_update"),
                    row["fetched_at"],
                    row["source_url"],
                )
                for row in rows
            ],
        )
    return len(rows)


def get_live_nfl_spread(
    team_a: str,
    team_b: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Fetch current NFL point spreads and persist the matching bookmaker lines."""
    team_a = _normalize_team_name(team_a)
    team_b = _normalize_team_name(team_b)
    api_key = (os.getenv("THE_ODDS_API_KEY") or "").strip()
    if not api_key:
        return {
            "team_a": team_a,
            "team_b": team_b,
            "provider": "The Odds API",
            "source_url": NFL_ODDS_SOURCE_URL,
            "status": "unavailable",
            "spreads": [],
            "stored_rows": 0,
            "error": "THE_ODDS_API_KEY is not configured.",
        }

    url = NFL_ODDS_ENDPOINT + "?" + parse.urlencode(
        {
            "apiKey": api_key,
            "regions": "us",
            "markets": "spreads",
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
    )
    payload = _fetch_json(url)
    if isinstance(payload, dict) and payload.get("status") == "error":
        return {
            "team_a": team_a,
            "team_b": team_b,
            "provider": "The Odds API",
            "source_url": NFL_ODDS_SOURCE_URL,
            "status": "unavailable",
            "spreads": [],
            "stored_rows": 0,
            "error": payload.get("error"),
        }
    if not isinstance(payload, list):
        return {
            "team_a": team_a,
            "team_b": team_b,
            "provider": "The Odds API",
            "source_url": NFL_ODDS_SOURCE_URL,
            "status": "unavailable",
            "spreads": [],
            "stored_rows": 0,
            "error": "The odds provider returned an unexpected response.",
        }

    fetched_at = datetime.now(timezone.utc).isoformat()
    matching_event: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    for event in payload:
        home_team = event.get("home_team") or ""
        away_team = event.get("away_team") or ""
        requested_teams_match = (
            _team_matches(home_team, team_a) and _team_matches(away_team, team_b)
        ) or (
            _team_matches(home_team, team_b) and _team_matches(away_team, team_a)
        )
        if not requested_teams_match:
            continue

        matching_event = event
        for bookmaker in event.get("bookmakers") or []:
            for market in bookmaker.get("markets") or []:
                if market.get("key") != "spreads":
                    continue
                for outcome in market.get("outcomes") or []:
                    point = outcome.get("point")
                    if not outcome.get("name") or point is None:
                        continue
                    rows.append(
                        {
                            "event_id": event.get("id") or f"{away_team}-{home_team}-{event.get('commence_time')}",
                            "commence_time": event.get("commence_time") or "unknown",
                            "home_team": home_team,
                            "away_team": away_team,
                            "bookmaker_key": bookmaker.get("key") or bookmaker.get("title") or "unknown",
                            "bookmaker": bookmaker.get("title") or bookmaker.get("key") or "Unknown",
                            "outcome_team": outcome["name"],
                            "spread_point": float(point),
                            "price": outcome.get("price"),
                            "market_last_update": market.get("last_update") or bookmaker.get("last_update"),
                            "fetched_at": fetched_at,
                            "source_url": NFL_ODDS_SOURCE_URL,
                        }
                    )
        break

    if matching_event is None or not rows:
        return {
            "team_a": team_a,
            "team_b": team_b,
            "provider": "The Odds API",
            "source_url": NFL_ODDS_SOURCE_URL,
            "status": "empty",
            "spreads": [],
            "stored_rows": 0,
            "message": "No current spread was found for this NFL matchup.",
        }

    stored_rows = _store_spread_rows(rows, db_path=db_path)
    home_team = matching_event["home_team"]
    away_team = matching_event["away_team"]
    home_points = [row["spread_point"] for row in rows if row["outcome_team"] == home_team]
    away_points = [row["spread_point"] for row in rows if row["outcome_team"] == away_team]
    return {
        "provider": "The Odds API",
        "source_url": NFL_ODDS_SOURCE_URL,
        "status": "ok",
        "event_id": matching_event.get("id"),
        "commence_time": matching_event.get("commence_time"),
        "home_team": home_team,
        "away_team": away_team,
        "consensus_home_spread": median(home_points) if home_points else None,
        "consensus_away_spread": median(away_points) if away_points else None,
        "bookmaker_count": len({row["bookmaker_key"] for row in rows}),
        "spreads": rows,
        "stored_rows": stored_rows,
        "fetched_at": fetched_at,
    }


def get_weather_for_city(city: str, date_value: str | None = None) -> dict[str, Any]:
    """Fetch weather for a city using Open-Meteo without requiring an API key."""
    city = (city or "").strip()
    if not city:
        raise ValueError("city must not be empty")

    if date_value is None:
        date_value = date.today().isoformat()

    location = _fetch_json(
        "https://geocoding-api.open-meteo.com/v1/search?"
        + parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
    )
    results = location.get("results") or []
    if not results:
        return {"city": city, "date": date_value, "status": "not_found", "forecast": []}

    place = results[0]
    lat = place.get("latitude")
    lon = place.get("longitude")
    daily = "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
    forecast = _fetch_json(
        "https://api.open-meteo.com/v1/forecast?"
        + parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "daily": daily,
                "timezone": "auto",
                "start_date": date_value,
                "end_date": date_value,
            }
        )
    )

    daily_data = (forecast.get("daily") or {}).get("time") or []
    values = (forecast.get("daily") or {})
    return {
        "city": city,
        "date": date_value,
        "country": place.get("country"),
        "admin1": place.get("admin1"),
        "latitude": lat,
        "longitude": lon,
        "status": "ok",
        "forecast": {
            "date": daily_data[0] if daily_data else date_value,
            "high_f": None if not values.get("temperature_2m_max") else round((values["temperature_2m_max"][0] * 9 / 5) + 32, 1),
            "low_f": None if not values.get("temperature_2m_min") else round((values["temperature_2m_min"][0] * 9 / 5) + 32, 1),
            "precipitation_chance_pct": values.get("precipitation_probability_max", [None])[0],
            "weather_code": values.get("weather_code", [None])[0],
        },
    }


def get_live_nfl_standings(season: int | None = None) -> dict[str, Any]:
    """Fetch current NFL standings from ESPN in a lightweight, read-only format."""
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/standings"
    payload = _fetch_json(url)
    if isinstance(payload, dict) and payload.get("status") == "error":
        return {
            "source": "ESPN",
            "season": season or "current",
            "status": "unavailable",
            "teams": [],
            "error": payload.get("error"),
        }

    records: list[dict[str, Any]] = []
    for division in (payload.get("children") or []):
        for team in (division.get("standings", {}).get("entries") or []):
            team_name = team.get("team", {}).get("displayName") or team.get("team", {}).get("shortName")
            if not team_name:
                continue
            stats = team.get("stats") or []
            by_name = {item.get("name"): item.get("value") for item in stats if item.get("name")}
            records.append(
                {
                    "team": team_name,
                    "division": division.get("name"),
                    "wins": by_name.get("wins"),
                    "losses": by_name.get("losses"),
                    "ties": by_name.get("ties"),
                    "points_for": by_name.get("pointsFor"),
                    "points_against": by_name.get("pointsAgainst"),
                    "winning_pct": by_name.get("winPct"),
                }
            )

    return {
        "source": "ESPN",
        "season": season or payload.get("season", {}).get("year") or "current",
        "status": "ok" if records else "empty",
        "teams": records[:20],
    }


def get_team_news(team: str, limit: int = 3) -> dict[str, Any]:
    """Fetch the latest team news from ESPN for a given club."""
    team_name = _normalize_team_name(team)
    slug = team_name.lower().replace(" ", "-")
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{slug}/news"
    payload = _fetch_json(url)
    if isinstance(payload, dict) and payload.get("status") == "error":
        return {
            "team": team_name,
            "source": "ESPN",
            "status": "unavailable",
            "articles": [],
            "error": payload.get("error"),
        }

    articles = payload.get("articles") or []
    clipped = []
    for article in articles[: max(1, int(limit))]:
        clipped.append(
            {
                "headline": article.get("headline"),
                "description": article.get("description"),
                "published": article.get("published"),
                "source": article.get("source", {}).get("name") if isinstance(article.get("source"), dict) else None,
                "url": article.get("links", {}).get("web", {}).get("href") if isinstance(article.get("links"), dict) else None,
            }
        )

    return {
        "team": team_name,
        "source": "ESPN",
        "status": "ok" if clipped else "empty",
        "articles": clipped,
    }
