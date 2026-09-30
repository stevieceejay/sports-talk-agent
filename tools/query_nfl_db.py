"""Read-only JSON query tools for nfl.db."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "nfl.db"
ALLOWED_OBJECTS = frozenset({
    "v_season_team",
    "v_team_game",
    "v_explosive_season",
    "v_player_game_stats",
    "v_team_game_stats",
})
STAT_METRICS = frozenset({
    "passing_attempts", "completions", "passing_yards", "passing_tds",
    "interceptions_thrown", "sacks_taken", "rushing_attempts", "rushing_yards",
    "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds",
    "defensive_sacks", "defensive_interceptions", "forced_fumbles",
})
POSITION_GROUPS = {
    "quarterback": ("QB",),
    "running_back": ("RB",),
    "receiver": ("WR", "TE"),
    "defense": ("DL", "LB", "DB"),
}
_OBJECT_REFERENCE = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_READ_ONLY_START = re.compile(r"^\s*(?:select|with|explain\s+query\s+plan)\b", re.IGNORECASE)


def _safe_query(query: str) -> dict[str, Any]:
    """Execute one approved read-only query and return JSON-safe rows."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty SQL string")
    if not _READ_ONLY_START.match(query):
        raise ValueError("only SELECT, WITH, or EXPLAIN QUERY PLAN statements are allowed")
    if len([part for part in query.split(";") if part.strip()]) != 1:
        raise ValueError("exactly one SQL statement is allowed")

    if not DB_PATH.exists():
        return {"columns": [], "rows": [], "row_count": 0, "status": "empty"}

    referenced = {name.lower() for name in _OBJECT_REFERENCE.findall(query)}
    disallowed = sorted(referenced - ALLOWED_OBJECTS)
    if disallowed:
        raise ValueError(f"disallowed table/view reference(s): {', '.join(disallowed)}")
    if not referenced:
        raise ValueError("query must reference at least one approved NFL view")

    uri = f"{DB_PATH.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        available_views = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        }
        if referenced - available_views:
            return {"columns": [], "rows": [], "row_count": 0, "status": "empty"}
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        cursor = connection.execute(query)
        columns = [item[0] for item in cursor.description or ()]
        rows = [dict(row) for row in cursor.fetchall()]
    return {"columns": columns, "rows": rows, "row_count": len(rows), "status": "ok" if rows else "empty"}


def query_nfl_db(query: str) -> dict[str, Any]:
    """Run one read-only SQL query against the approved NFL views."""
    return _safe_query(query)


def get_team_season_rollup(team: str, season: int | None = None) -> dict[str, Any]:
    """Fetch season-level team rollup data for a given team and optional season."""
    team = (team or "").strip()
    if not team:
        raise ValueError("team must not be empty")

    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT season, team, games, wins, losses, points_for, points_against, point_differential
        FROM v_season_team
        WHERE LOWER(team) = LOWER('{team.replace("'", "''")}')
        {season_clause}
        ORDER BY season DESC
    """.strip()
    return _safe_query(query)


def get_team_recent_games(
    team: str,
    limit: int = 5,
    season: int | None = None,
) -> dict[str, Any]:
    """Fetch recent game history for a team from the team_game view."""
    team = (team or "").strip()
    if not team:
        raise ValueError("team must not be empty")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT game_id, season, week, game_date, team, opponent, venue,
               points_for, points_against, result
        FROM v_team_game
        WHERE LOWER(team) = LOWER('{team.replace("'", "''")}')
        {season_clause}
        ORDER BY season DESC, week DESC
        LIMIT {int(limit)}
    """.strip()
    return _safe_query(query)


def get_explosive_summary(season: int | None = None) -> dict[str, Any]:
    """Fetch explosive-play summary data across teams for a season."""
    season_clause = "" if season is None else f"WHERE season = {int(season)}"
    query = f"""
        SELECT season, team, explosive_plays, explosive_passes, explosive_runs, explosive_yards
        FROM v_explosive_season
        {season_clause}
        ORDER BY explosive_plays DESC
    """.strip()
    return _safe_query(query)


def get_explosive_plays(season: int | None = None) -> dict[str, Any]:
    """Alias for explosive-play summary data across teams."""
    return get_explosive_summary(season=season)


def get_team_recent_plays(
    team: str,
    limit: int = 5,
    season: int | None = None,
) -> dict[str, Any]:
    """Alias for recent game history for a team."""
    return get_team_recent_games(team=team, limit=limit, season=season)


def get_team_rankings(season: int | None = None, limit: int = 10) -> dict[str, Any]:
    """Fetch team rankings from the season rollup view, ordered by point differential or win rate."""
    season_clause = "" if season is None else f"WHERE season = {int(season)}"
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    query = f"""
        SELECT season, team, wins, losses, points_for, points_against, point_differential
        FROM v_season_team
        {season_clause}
        ORDER BY wins DESC, point_differential DESC
        LIMIT {int(limit)}
    """.strip()
    return _safe_query(query)


def get_matchup_snapshot(team_a: str, team_b: str, season: int | None = None) -> dict[str, Any]:
    """Return a lightweight team-vs-team snapshot for two clubs from the season rollup view."""
    team_a = (team_a or "").strip()
    team_b = (team_b or "").strip()
    if not team_a or not team_b:
        raise ValueError("team_a and team_b must both be provided")

    season_filter = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT season, team, wins, losses, points_for, points_against, point_differential
        FROM v_season_team
        WHERE LOWER(team) IN (LOWER('{team_a.replace("'", "''")}'), LOWER('{team_b.replace("'", "''")}'))
        {season_filter}
        ORDER BY team ASC
    """.strip()
    return _safe_query(query)


def get_team_record_vs_opponent(team: str, opponent: str, season: int | None = None) -> dict[str, Any]:
    """Return a team's game history against one opponent from the game-level database view."""
    team = (team or "").strip()
    opponent = (opponent or "").strip()
    if not team:
        raise ValueError("team must not be empty")
    if not opponent:
        raise ValueError("opponent must not be empty")

    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT season, week, game_date, team, opponent, venue, points_for, points_against, result
        FROM v_team_game
        WHERE LOWER(team) = LOWER('{team.replace("'", "''")}')
          AND LOWER(opponent) = LOWER('{opponent.replace("'", "''")}')
        {season_clause}
        ORDER BY season DESC, week DESC
    """.strip()
    return _safe_query(query)


def get_team_game_log(team: str, season: int | None = None, limit: int = 10) -> dict[str, Any]:
    """Return the recent game log for a team, ordered from newest to oldest."""
    team = (team or "").strip()
    if not team:
        raise ValueError("team must not be empty")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT season, week, game_date, team, opponent, venue, points_for, points_against, result
        FROM v_team_game
        WHERE LOWER(team) = LOWER('{team.replace("'", "''")}')
        {season_clause}
        ORDER BY season DESC, week DESC
        LIMIT {int(limit)}
    """.strip()
    return _safe_query(query)


def has_team_schedule_rows(team: str, season: int | None = None) -> bool:
    """Return True when a team has at least one schedule row in the database."""
    team = (team or "").strip()
    if not team:
        return False
    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM v_team_game
        WHERE LOWER(team) = LOWER('{team.replace("'", "''")}')
        {season_clause}
    """.strip()
    payload = _safe_query(query)
    rows = payload.get("rows") or []
    if not rows:
        return False
    return int((rows[0].get("cnt") or 0)) > 0


def get_team_schedule(team: str, season: int | None = None) -> dict[str, Any]:
    """Return the full schedule for a team from the game-level database view."""
    team = (team or "").strip()
    if not team:
        raise ValueError("team must not be empty")

    if not has_team_schedule_rows(team, season=season):
        return {
            "team": team,
            "season": season,
            "status": "empty",
            "rows": [],
            "row_count": 0,
            "message": "No schedule data is available for this team in the current database.",
        }

    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT season, week, game_date, team, opponent, venue, points_for, points_against, result
        FROM v_team_game
        WHERE LOWER(team) = LOWER('{team.replace("'", "''")}')
        {season_clause}
        ORDER BY season ASC, week ASC
    """.strip()
    return _safe_query(query)


def get_player_game_stats(player: str, season: int | None = None, limit: int = 20) -> dict[str, Any]:
    """Return a player's per-game passing, rushing, receiving, and defensive stats."""
    player = (player or "").strip()
    if not player:
        raise ValueError("player must not be empty")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    escaped = player.replace("'", "''").lower()
    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
         SELECT game_id, season, week, game_date, team, opponent, player_id, player_name,
             position, position_group,
               passing_attempts, completions, passing_yards, passing_tds,
               interceptions_thrown, sacks_taken, rushing_attempts, rushing_yards,
               rushing_tds, targets, receptions, receiving_yards, receiving_tds,
               defensive_sacks, defensive_interceptions, forced_fumbles
        FROM v_player_game_stats
        WHERE (LOWER(player_name) LIKE '%{escaped}%' OR LOWER(player_id) LIKE '%{escaped}%')
        {season_clause}
        ORDER BY season DESC, week DESC, team ASC
        LIMIT {int(limit)}
    """.strip()
    return _safe_query(query)


def get_team_game_stats(team: str, season: int | None = None, limit: int = 20) -> dict[str, Any]:
    """Return a team's per-game offensive and defensive counting stats."""
    team = (team or "").strip()
    if not team:
        raise ValueError("team must not be empty")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    escaped = team.replace("'", "''")
    season_clause = "" if season is None else f"AND season = {int(season)}"
    query = f"""
        SELECT game_id, season, week, game_date, team, opponent,
               passing_attempts, completions, passing_yards, passing_tds,
               interceptions_thrown, sacks_taken, rushing_attempts, rushing_yards,
               rushing_tds, targets, receptions, receiving_yards, receiving_tds,
               defensive_sacks, defensive_interceptions, forced_fumbles
        FROM v_team_game_stats
        WHERE (LOWER(team) = LOWER('{escaped}') OR LOWER(team) LIKE LOWER('% {escaped}'))
        {season_clause}
        ORDER BY season DESC, week DESC
        LIMIT {int(limit)}
    """.strip()
    return _safe_query(query)


def get_player_stat_leaders(
    stat: str,
    season: int | None = None,
    limit: int = 10,
    team: str | None = None,
    position_group: str | None = None,
) -> dict[str, Any]:
    """Rank players by a supported season total, optionally limited by team or role."""
    stat = (stat or "").strip().lower()
    if stat not in STAT_METRICS:
        raise ValueError(f"stat must be one of: {', '.join(sorted(STAT_METRICS))}")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    if position_group is not None:
        position_group = position_group.strip().lower()
        if position_group not in POSITION_GROUPS:
            raise ValueError(f"position_group must be one of: {', '.join(POSITION_GROUPS)}")

    team_filter = (team or "").strip()
    if team_filter.lower() in {"", "all", "all teams", "any", "any team", "league", "nfl", "null"}:
        team_filter = ""

    filters = []
    if season is not None:
        filters.append(f"season = {int(season)}")
    if team_filter:
        escaped_team = team_filter.replace("'", "''")
        filters.append(
            f"(LOWER(team) = LOWER('{escaped_team}') "
            f"OR LOWER(team) LIKE LOWER('% {escaped_team}'))"
        )
    if position_group:
        group_values = ", ".join(f"'{group}'" for group in POSITION_GROUPS[position_group])
        filters.append(f"position_group IN ({group_values})")
    season_select = "season" if season is not None else "NULL AS season"
    team_select = ", team" if team_filter else ""
    position_select = ", position_group" if position_group else ""
    where_clause = "WHERE " + " AND ".join(filters) if filters else ""
    group_fields = ["player_id", "player_name"]
    if season is not None:
        group_fields.insert(0, "season")
    if team_filter:
        group_fields.append("team")
    if position_group:
        group_fields.append("position_group")
    query = f"""
        SELECT {season_select}, player_id, player_name{team_select}{position_select},
               SUM({stat}) AS total, COUNT(DISTINCT game_id) AS games
        FROM v_player_game_stats
        {where_clause}
        GROUP BY {', '.join(group_fields)}
        HAVING SUM({stat}) > 0
        ORDER BY total DESC, player_name ASC
        LIMIT {int(limit)}
    """.strip()
    return _safe_query(query)


def get_team_stat_leaders(stat: str, season: int | None = None, limit: int = 10) -> dict[str, Any]:
    """Rank teams by a supported per-game stat summed across the season."""
    stat = (stat or "").strip().lower()
    if stat not in STAT_METRICS:
        raise ValueError(f"stat must be one of: {', '.join(sorted(STAT_METRICS))}")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    season_select = "season" if season is not None else "NULL AS season"
    season_clause = "" if season is None else f"WHERE season = {int(season)}"
    group_fields = "season, team" if season is not None else "team"
    query = f"""
        SELECT {season_select}, team, SUM({stat}) AS total, COUNT(DISTINCT game_id) AS games
        FROM v_team_game_stats
        {season_clause}
        GROUP BY {group_fields}
        HAVING SUM({stat}) > 0
        ORDER BY total DESC, team ASC
        LIMIT {int(limit)}
    """.strip()
    return _safe_query(query)


def get_scheme_fit(team: str, season: int, side: str) -> dict[str, Any]:
    """Return scheme-fit data for a team and side of the ball using the local database.

    This is a placeholder for future scheme data. It provides a structured contract
    so the agent calls the tool in a specific, explicit way before estimating matchup fit.
    """
    team = (team or "").strip()
    if not team:
        raise ValueError("team must not be empty")
    side = (side or "").strip().lower()
    if side not in {"offense", "defense"}:
        raise ValueError("side must be 'offense' or 'defense'")

    return {
        "team": team,
        "season": int(season),
        "side": side,
        "data_status": "placeholder",
        "man_coverage_rate": None,
        "zone_coverage_rate": None,
        "blitz_rate": None,
        "base_front": None,
        "personnel_tendency": None,
        "message": (
            "Scheme-fit data is not yet populated in the database. "
            "This tool exists to enforce the required data contract before any matchup analysis."
        ),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="One read-only SQL query")
    args = parser.parse_args()
    print(json.dumps(query_nfl_db(args.query), indent=2))
