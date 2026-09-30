from __future__ import annotations

import argparse
import csv
import gzip
import io
import sqlite3
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

OUTPUT = Path(__file__).resolve().parents[1] / "db" / "nfl.db"
SCHEDULE_SOURCE = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
PBP_SOURCE = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"
PLAYER_SOURCE = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"

TEAM_NAMES = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAC": "Jacksonville Jaguars",
    "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs",
    "LAC": "Los Angeles Chargers",
    "LA": "Los Angeles Rams",
    "LAR": "Los Angeles Rams",
    "LV": "Las Vegas Raiders",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE": "New England Patriots",
    "NO": "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "OAK": "Oakland Raiders",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SD": "San Diego Chargers",
    "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers",
    "STL": "St. Louis Rams",
    "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
    "WSH": "Washington Commanders",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS season_team (
    season INTEGER NOT NULL,
    team TEXT NOT NULL,
    games INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    points_for INTEGER NOT NULL DEFAULT 0,
    points_against INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season, team)
);

CREATE TABLE IF NOT EXISTS team_game (
    game_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_date TEXT,
    team TEXT NOT NULL,
    opponent TEXT NOT NULL,
    venue TEXT CHECK (venue IN ('home', 'away', 'neutral')),
    points_for INTEGER,
    points_against INTEGER,
    result TEXT CHECK (result IN ('W', 'L', 'T')),
    PRIMARY KEY (game_id, team)
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    game_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_date TEXT,
    team TEXT NOT NULL,
    opponent TEXT NOT NULL,
    player_id TEXT NOT NULL,
    player_name TEXT NOT NULL,
    position TEXT,
    position_group TEXT,
    passing_attempts INTEGER NOT NULL DEFAULT 0,
    completions INTEGER NOT NULL DEFAULT 0,
    passing_yards INTEGER NOT NULL DEFAULT 0,
    passing_tds INTEGER NOT NULL DEFAULT 0,
    interceptions_thrown INTEGER NOT NULL DEFAULT 0,
    sacks_taken INTEGER NOT NULL DEFAULT 0,
    rushing_attempts INTEGER NOT NULL DEFAULT 0,
    rushing_yards INTEGER NOT NULL DEFAULT 0,
    rushing_tds INTEGER NOT NULL DEFAULT 0,
    targets INTEGER NOT NULL DEFAULT 0,
    receptions INTEGER NOT NULL DEFAULT 0,
    receiving_yards INTEGER NOT NULL DEFAULT 0,
    receiving_tds INTEGER NOT NULL DEFAULT 0,
    defensive_sacks REAL NOT NULL DEFAULT 0,
    defensive_interceptions INTEGER NOT NULL DEFAULT 0,
    forced_fumbles INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (game_id, team, player_id)
);

CREATE TABLE IF NOT EXISTS team_game_stats (
    game_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_date TEXT,
    team TEXT NOT NULL,
    opponent TEXT NOT NULL,
    passing_attempts INTEGER NOT NULL DEFAULT 0,
    completions INTEGER NOT NULL DEFAULT 0,
    passing_yards INTEGER NOT NULL DEFAULT 0,
    passing_tds INTEGER NOT NULL DEFAULT 0,
    interceptions_thrown INTEGER NOT NULL DEFAULT 0,
    sacks_taken INTEGER NOT NULL DEFAULT 0,
    rushing_attempts INTEGER NOT NULL DEFAULT 0,
    rushing_yards INTEGER NOT NULL DEFAULT 0,
    rushing_tds INTEGER NOT NULL DEFAULT 0,
    targets INTEGER NOT NULL DEFAULT 0,
    receptions INTEGER NOT NULL DEFAULT 0,
    receiving_yards INTEGER NOT NULL DEFAULT 0,
    receiving_tds INTEGER NOT NULL DEFAULT 0,
    defensive_sacks REAL NOT NULL DEFAULT 0,
    defensive_interceptions INTEGER NOT NULL DEFAULT 0,
    forced_fumbles INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (game_id, team)
);

CREATE TABLE IF NOT EXISTS explosive_season (
    season INTEGER NOT NULL,
    team TEXT NOT NULL,
    explosive_plays INTEGER NOT NULL DEFAULT 0,
    explosive_passes INTEGER NOT NULL DEFAULT 0,
    explosive_runs INTEGER NOT NULL DEFAULT 0,
    explosive_yards INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season, team)
);

CREATE TABLE IF NOT EXISTS injuries (
    injury_id INTEGER PRIMARY KEY,
    season INTEGER NOT NULL,
    team TEXT NOT NULL,
    player_name TEXT NOT NULL,
    position TEXT,
    status TEXT NOT NULL,
    injury TEXT,
    practice_status TEXT,
    report_date TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE VIEW IF NOT EXISTS v_season_team AS
SELECT season, team, games, wins, losses, points_for, points_against,
       points_for - points_against AS point_differential
FROM season_team;

CREATE VIEW IF NOT EXISTS v_team_game AS
SELECT game_id, season, week, game_date, team, opponent, venue,
       points_for, points_against, result
FROM team_game;

CREATE VIEW IF NOT EXISTS v_player_game_stats AS
SELECT * FROM player_game_stats;

CREATE VIEW IF NOT EXISTS v_team_game_stats AS
SELECT * FROM team_game_stats;

CREATE VIEW IF NOT EXISTS v_explosive_season AS
SELECT season, team, explosive_plays, explosive_passes, explosive_runs,
       explosive_yards
FROM explosive_season;

CREATE VIEW IF NOT EXISTS v_injuries AS
SELECT injury_id, season, team, player_name, position, status, injury,
       practice_status, report_date, is_active
FROM injuries;
"""


def _initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    columns = {row[1]: row for row in connection.execute("PRAGMA table_info(team_game)")}
    schedule_scores_required = columns.get("points_for", (None, None, None, 0))[3] or columns.get(
        "points_against", (None, None, None, 0)
    )[3]
    if schedule_scores_required:
        connection.execute("DROP VIEW IF EXISTS v_team_game")
        connection.execute(
            """
            CREATE TABLE team_game_new (
                game_id TEXT NOT NULL,
                season INTEGER NOT NULL,
                week INTEGER NOT NULL,
                game_date TEXT,
                team TEXT NOT NULL,
                opponent TEXT NOT NULL,
                venue TEXT CHECK (venue IN ('home', 'away', 'neutral')),
                points_for INTEGER,
                points_against INTEGER,
                result TEXT CHECK (result IN ('W', 'L', 'T')),
                PRIMARY KEY (game_id, team)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO team_game_new
            SELECT game_id, season, week, game_date, team, opponent, venue,
                   points_for, points_against, result
            FROM team_game
            """
        )
        connection.execute("DROP TABLE team_game")
        connection.execute("ALTER TABLE team_game_new RENAME TO team_game")
        connection.execute(
            """
            CREATE VIEW v_team_game AS
            SELECT game_id, season, week, game_date, team, opponent, venue,
                   points_for, points_against, result
            FROM team_game
            """
        )

    migrations = {
        "player_game_stats": {
            "position": "TEXT",
            "position_group": "TEXT",
            "forced_fumbles": "INTEGER NOT NULL DEFAULT 0",
        },
        "team_game_stats": {"forced_fumbles": "INTEGER NOT NULL DEFAULT 0"},
    }
    changed_stat_schema = False
    for table, columns_to_add in migrations.items():
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, declaration in columns_to_add.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
                changed_stat_schema = True
    if changed_stat_schema:
        connection.execute("DROP VIEW IF EXISTS v_player_game_stats")
        connection.execute("DROP VIEW IF EXISTS v_team_game_stats")
        connection.execute("CREATE VIEW v_player_game_stats AS SELECT * FROM player_game_stats")
        connection.execute("CREATE VIEW v_team_game_stats AS SELECT * FROM team_game_stats")


def schedule_records_from_csv(contents: str, season: int | None = None) -> list[dict[str, Any]]:
    """Convert nflverse game rows into one schedule row per participating team."""
    reader = csv.DictReader(io.StringIO(contents))
    required = {"game_id", "season", "game_type", "week", "gameday", "away_team", "away_score", "home_team", "home_score"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("Schedule source is missing required nflverse columns")

    records = []
    for game in reader:
        game_season = int(game["season"])
        if season is not None and game_season != int(season):
            continue
        if game["game_type"] not in {"REG", "POST"}:
            continue

        away_team = game["away_team"].strip().upper()
        home_team = game["home_team"].strip().upper()
        away_score = int(game["away_score"]) if game["away_score"].strip() else None
        home_score = int(game["home_score"]) if game["home_score"].strip() else None
        for team_code, opponent_code, venue, points_for, points_against in (
            (away_team, home_team, "away", away_score, home_score),
            (home_team, away_team, "home", home_score, away_score),
        ):
            result = None
            if points_for is not None and points_against is not None:
                result = "W" if points_for > points_against else "L" if points_for < points_against else "T"
            records.append(
                {
                    "game_id": game["game_id"],
                    "season": game_season,
                    "week": int(game["week"]),
                    "game_date": game["gameday"] or None,
                    "team": TEAM_NAMES.get(team_code, team_code),
                    "opponent": TEAM_NAMES.get(opponent_code, opponent_code),
                    "venue": venue,
                    "points_for": points_for,
                    "points_against": points_against,
                    "result": result,
                }
            )
    if not records:
        raise ValueError(f"No regular-season or postseason schedule rows found for season {season}.")
    return records


def seed_schedule_data(
    output_path: Path | str = OUTPUT,
    records: list[dict[str, Any]] | None = None,
) -> int:
    """Replace imported schedule seasons without deleting unrelated database data."""
    if not records:
        raise ValueError("records must contain at least one schedule row")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    seasons = sorted({int(row["season"]) for row in records})

    with sqlite3.connect(target) as connection:
        _initialize_database(connection)
        placeholders = ", ".join("?" for _ in seasons)
        connection.execute(f"DELETE FROM team_game WHERE season IN ({placeholders})", seasons)
        connection.executemany(
            """
            INSERT INTO team_game (
                game_id, season, week, game_date, team, opponent, venue,
                points_for, points_against, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.get("game_id") or f"{row['season']}_{row['week']}_{row['team']}_{row['opponent']}",
                    int(row["season"]),
                    int(row["week"]),
                    row.get("game_date"),
                    row["team"],
                    row["opponent"],
                    row.get("venue", "neutral"),
                    row.get("points_for"),
                    row.get("points_against"),
                    row.get("result"),
                )
                for row in records
            ],
        )
    return len(records)


def ingest_schedule_data(
    season: int | None = None,
    output_path: Path | str = OUTPUT,
    source_url: str = SCHEDULE_SOURCE,
) -> int:
    """Download the trusted nflverse schedule feed and store its NFL game rows."""
    request = Request(source_url, headers={"User-Agent": "sports-talk-agent schedule importer"})
    with urlopen(request, timeout=30) as response:
        contents = response.read().decode("utf-8-sig")
    records = schedule_records_from_csv(contents, season=season)
    return seed_schedule_data(output_path=output_path, records=records)


STAT_FIELDS = (
    "passing_attempts",
    "completions",
    "passing_yards",
    "passing_tds",
    "interceptions_thrown",
    "sacks_taken",
    "rushing_attempts",
    "rushing_yards",
    "rushing_tds",
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "defensive_sacks",
    "defensive_interceptions",
    "forced_fumbles",
)


def _stat_value(play: dict[str, str], field: str) -> int:
    value = (play.get(field) or "").strip()
    return int(float(value)) if value else 0


def _stat_flag(play: dict[str, str], field: str) -> bool:
    return (play.get(field) or "").strip().lower() in {"1", "1.0", "true"}


def game_stats_from_pbp(
    contents: str,
    season: int,
    player_names: dict[str, str] | None = None,
    player_positions: dict[str, str] | None = None,
    player_position_groups: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aggregate nflverse play-by-play into per-player and per-team game lines."""
    reader = csv.DictReader(io.StringIO(contents))
    required = {
        "game_id", "season", "season_type", "week", "game_date", "posteam", "defteam",
        "pass_attempt", "complete_pass", "passing_yards", "pass_touchdown", "interception",
        "rush_attempt", "rushing_yards", "rush_touchdown", "passer_player_id",
        "passer_player_name", "receiver_player_id", "receiver_player_name", "rusher_player_id",
        "rusher_player_name", "sack", "sack_player_id", "sack_player_name",
        "half_sack_1_player_id", "half_sack_1_player_name", "half_sack_2_player_id",
        "half_sack_2_player_name", "interception_player_id", "interception_player_name",
        "fumble_forced", "forced_fumble_player_1_team", "forced_fumble_player_1_player_id",
        "forced_fumble_player_1_player_name", "forced_fumble_player_2_team",
        "forced_fumble_player_2_player_id", "forced_fumble_player_2_player_name",
    }
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("Play-by-play source is missing required nflverse columns")

    players: dict[tuple[str, str, str], dict[str, Any]] = {}
    teams: dict[tuple[str, str], dict[str, Any]] = {}

    def team_row(
        game_id: str,
        game_season: int,
        week: int,
        game_date: str | None,
        team_code: str,
        opponent_code: str,
    ) -> dict[str, Any]:
        team = TEAM_NAMES.get(team_code, team_code)
        opponent = TEAM_NAMES.get(opponent_code, opponent_code)
        key = (game_id, team)
        return teams.setdefault(
            key,
            {
                "game_id": game_id,
                "season": game_season,
                "week": week,
                "game_date": game_date,
                "team": team,
                "opponent": opponent,
                **{field: 0 for field in STAT_FIELDS},
            },
        )

    def player_row(
        game_id: str,
        game_season: int,
        week: int,
        game_date: str | None,
        team_code: str,
        opponent_code: str,
        player_id: str,
        player_name: str,
    ) -> dict[str, Any] | None:
        if not team_code or (not player_id and not player_name):
            return None
        team = TEAM_NAMES.get(team_code, team_code)
        opponent = TEAM_NAMES.get(opponent_code, opponent_code)
        stable_id = player_id or f"name:{player_name.lower()}"
        display_name = (player_names or {}).get(player_id, player_name) if player_id else player_name
        key = (game_id, team, stable_id)
        return players.setdefault(
            key,
            {
                "game_id": game_id,
                "season": game_season,
                "week": week,
                "game_date": game_date,
                "team": team,
                "opponent": opponent,
                "player_id": stable_id,
                "player_name": display_name or stable_id,
                "position": (player_positions or {}).get(player_id) if player_id else None,
                "position_group": (player_position_groups or {}).get(player_id) if player_id else None,
                **{field: 0 for field in STAT_FIELDS},
            },
        )

    for play in reader:
        game_season = int(play["season"])
        if game_season != int(season) or play["season_type"] not in {"REG", "POST"}:
            continue
        game_id = play["game_id"]
        offense_code = (play.get("posteam") or "").strip().upper()
        defense_code = (play.get("defteam") or "").strip().upper()
        if not game_id or not offense_code or not defense_code:
            continue

        week = int(play["week"])
        game_date = play.get("game_date") or None
        offense = team_row(game_id, game_season, week, game_date, offense_code, defense_code)
        defense = team_row(game_id, game_season, week, game_date, defense_code, offense_code)

        if _stat_flag(play, "pass_attempt"):
            completed = _stat_flag(play, "complete_pass")
            intercepted = _stat_flag(play, "interception")
            passing_yards = _stat_value(play, "passing_yards")
            passing_td = _stat_value(play, "pass_touchdown")
            is_sack = _stat_flag(play, "sack")
            offense["passing_attempts"] += int(not is_sack)
            offense["completions"] += int(completed)
            offense["passing_yards"] += passing_yards
            offense["passing_tds"] += passing_td
            offense["interceptions_thrown"] += int(intercepted)
            offense["sacks_taken"] += int(is_sack)

            passer = player_row(
                game_id, game_season, week, game_date, offense_code, defense_code,
                play.get("passer_player_id", "").strip(), play.get("passer_player_name", "").strip(),
            )
            if passer:
                passer["passing_attempts"] += int(not is_sack)
                passer["completions"] += int(completed)
                passer["passing_yards"] += passing_yards
                passer["passing_tds"] += passing_td
                passer["interceptions_thrown"] += int(intercepted)
                passer["sacks_taken"] += int(is_sack)

            receiver_id = play.get("receiver_player_id", "").strip()
            receiver_name = play.get("receiver_player_name", "").strip()
            if receiver_id and not intercepted:
                offense["targets"] += 1
                receiver = player_row(
                    game_id, game_season, week, game_date, offense_code, defense_code,
                    receiver_id, receiver_name,
                )
                if receiver:
                    receiver["targets"] += 1
                    if completed:
                        receiver["receptions"] += 1
                        receiver["receiving_yards"] += _stat_value(play, "receiving_yards")
                        receiver["receiving_tds"] += passing_td
            if completed:
                offense["receptions"] += 1
                offense["receiving_yards"] += _stat_value(play, "receiving_yards")
                offense["receiving_tds"] += passing_td

        if _stat_flag(play, "rush_attempt"):
            rushing_yards = _stat_value(play, "rushing_yards")
            rushing_td = _stat_value(play, "rush_touchdown")
            offense["rushing_attempts"] += 1
            offense["rushing_yards"] += rushing_yards
            offense["rushing_tds"] += rushing_td
            rusher = player_row(
                game_id, game_season, week, game_date, offense_code, defense_code,
                play.get("rusher_player_id", "").strip(), play.get("rusher_player_name", "").strip(),
            )
            if rusher:
                rusher["rushing_attempts"] += 1
                rusher["rushing_yards"] += rushing_yards
                rusher["rushing_tds"] += rushing_td

        if _stat_flag(play, "sack"):
            defense["defensive_sacks"] += 1
            credited_half_sack = False
            for id_field, name_field in (
                ("half_sack_1_player_id", "half_sack_1_player_name"),
                ("half_sack_2_player_id", "half_sack_2_player_name"),
            ):
                defender_id = play.get(id_field, "").strip()
                defender_name = play.get(name_field, "").strip()
                if defender_id or defender_name:
                    defender = player_row(
                        game_id, game_season, week, game_date, defense_code, offense_code,
                        defender_id, defender_name,
                    )
                    if defender:
                        defender["defensive_sacks"] += 0.5
                        credited_half_sack = True
            if not credited_half_sack:
                defender = player_row(
                    game_id, game_season, week, game_date, defense_code, offense_code,
                    play.get("sack_player_id", "").strip(), play.get("sack_player_name", "").strip(),
                )
                if defender:
                    defender["defensive_sacks"] += 1

        if _stat_flag(play, "interception"):
            defense["defensive_interceptions"] += 1
            interceptor = player_row(
                game_id, game_season, week, game_date, defense_code, offense_code,
                play.get("interception_player_id", "").strip(),
                play.get("interception_player_name", "").strip(),
            )
            if interceptor:
                interceptor["defensive_interceptions"] += 1

        if _stat_flag(play, "fumble_forced"):
            credited_teams = set()
            credited_players = set()
            for team_field, id_field, name_field in (
                ("forced_fumble_player_1_team", "forced_fumble_player_1_player_id", "forced_fumble_player_1_player_name"),
                ("forced_fumble_player_2_team", "forced_fumble_player_2_player_id", "forced_fumble_player_2_player_name"),
            ):
                defender_id = play.get(id_field, "").strip()
                defender_name = play.get(name_field, "").strip()
                if not defender_id and not defender_name:
                    continue
                defender_team = (play.get(team_field) or defense_code).strip().upper()
                if defender_team:
                    credited_teams.add(defender_team)
                player_key = defender_id or defender_name
                if player_key and player_key not in credited_players:
                    defender = player_row(
                        game_id, game_season, week, game_date, defender_team, offense_code,
                        defender_id, defender_name,
                    )
                    if defender:
                        defender["forced_fumbles"] += 1
                        credited_players.add(player_key)
            for defender_team in credited_teams or {defense_code}:
                forced_fumble_team = team_row(
                    game_id, game_season, week, game_date, defender_team, offense_code
                )
                forced_fumble_team["forced_fumbles"] += 1

    if not teams:
        raise ValueError(f"No regular-season or postseason play-by-play rows found for season {season}.")
    return list(players.values()), list(teams.values())


def seed_game_stats(
    player_records: list[dict[str, Any]],
    team_records: list[dict[str, Any]],
    output_path: Path | str = OUTPUT,
) -> tuple[int, int]:
    """Replace per-game player and team stats for the supplied seasons."""
    if not player_records or not team_records:
        raise ValueError("player_records and team_records must contain imported stats")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    seasons = sorted({int(row["season"]) for row in team_records})
    metadata_fields = ("game_id", "season", "week", "game_date", "team", "opponent")
    player_fields = (
        *metadata_fields, "player_id", "player_name", "position", "position_group", *STAT_FIELDS
    )
    team_fields = (*metadata_fields, *STAT_FIELDS)

    with sqlite3.connect(target) as connection:
        _initialize_database(connection)
        placeholders = ", ".join("?" for _ in seasons)
        connection.execute(f"DELETE FROM player_game_stats WHERE season IN ({placeholders})", seasons)
        connection.execute(f"DELETE FROM team_game_stats WHERE season IN ({placeholders})", seasons)
        connection.executemany(
            f"INSERT INTO player_game_stats ({', '.join(player_fields)}) VALUES ({', '.join('?' for _ in player_fields)})",
            [tuple(row.get(field, 0) for field in player_fields) for row in player_records],
        )
        connection.executemany(
            f"INSERT INTO team_game_stats ({', '.join(team_fields)}) VALUES ({', '.join('?' for _ in team_fields)})",
            [tuple(row.get(field, 0) for field in team_fields) for row in team_records],
        )
    return len(player_records), len(team_records)


def ingest_game_stats(
    season: int,
    output_path: Path | str = OUTPUT,
    source_url: str | None = None,
) -> tuple[int, int]:
    """Download one nflverse season's play-by-play and aggregate game stats."""
    url = source_url or PBP_SOURCE.format(season=int(season))
    request = Request(url, headers={"User-Agent": "sports-talk-agent stats importer"})
    with urlopen(request, timeout=60) as response:
        contents = gzip.decompress(response.read()).decode("utf-8-sig")
    name_request = Request(PLAYER_SOURCE, headers={"User-Agent": "sports-talk-agent player catalog"})
    with urlopen(name_request, timeout=60) as response:
        player_catalog = response.read().decode("utf-8-sig")
    player_names = player_names_from_csv(player_catalog)
    player_positions = player_positions_from_csv(player_catalog)
    player_position_groups = player_position_groups_from_csv(player_catalog)
    player_records, team_records = game_stats_from_pbp(
        contents,
        season=season,
        player_names=player_names,
        player_positions=player_positions,
        player_position_groups=player_position_groups,
    )
    return seed_game_stats(player_records, team_records, output_path=output_path)


def player_names_from_csv(contents: str) -> dict[str, str]:
    """Map nflverse GSIS player IDs to display names."""
    reader = csv.DictReader(io.StringIO(contents))
    if not reader.fieldnames or not {"gsis_id", "display_name"}.issubset(reader.fieldnames):
        raise ValueError("Player catalog is missing required nflverse columns")
    return {
        row["gsis_id"].strip(): row["display_name"].strip()
        for row in reader
        if row.get("gsis_id") and row.get("display_name")
    }


def player_positions_from_csv(contents: str) -> dict[str, str]:
    """Map nflverse GSIS player IDs to listed positions."""
    reader = csv.DictReader(io.StringIO(contents))
    if not reader.fieldnames or not {"gsis_id", "position"}.issubset(reader.fieldnames):
        raise ValueError("Player catalog is missing position columns")
    return {
        row["gsis_id"].strip(): row["position"].strip().upper()
        for row in reader
        if row.get("gsis_id") and row.get("position")
    }


def player_position_groups_from_csv(contents: str) -> dict[str, str]:
    """Map nflverse GSIS player IDs to source-defined position groups."""
    reader = csv.DictReader(io.StringIO(contents))
    if not reader.fieldnames or not {"gsis_id", "position_group"}.issubset(reader.fieldnames):
        raise ValueError("Player catalog is missing position-group columns")
    return {
        row["gsis_id"].strip(): row["position_group"].strip().upper()
        for row in reader
        if row.get("gsis_id") and row.get("position_group")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import NFL schedules and game statistics from nflverse.")
    parser.add_argument("--season", type=int, help="Import this season's schedule and per-game player/team stats.")
    args = parser.parse_args()
    count = ingest_schedule_data(season=args.season)
    if args.season is None:
        print(f"Imported {count // 2} games ({count} team schedule rows) into {OUTPUT}; pass --season to import game stats.")
        return
    player_count, team_count = ingest_game_stats(args.season)
    print(
        f"Imported {count // 2} games, {player_count} player-game rows, and "
        f"{team_count} team-game stat rows for {args.season} into {OUTPUT}"
    )


if __name__ == "__main__":
    main()
