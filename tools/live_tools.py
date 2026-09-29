"""Live sports-context tools using public read-only endpoints."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib import parse, request


USER_AGENT = "sports-talk-agent/1.0"


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
