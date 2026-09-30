import sqlite3

import tools.query_nfl_db as query_nfl_db
from scripts.create_nfl_db import seed_schedule_data
from scripts.create_nfl_db import schedule_records_from_csv


def test_seed_schedule_data_inserts_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "nfl.db"
    records = [
        {
            "season": 2025,
            "team": "Los Angeles Rams",
            "week": 1,
            "game_date": "2025-09-07",
            "opponent": "Detroit Lions",
            "venue": "home",
            "points_for": 20,
            "points_against": 24,
            "result": "L",
        },
        {
            "season": 2025,
            "team": "Los Angeles Rams",
            "week": 2,
            "game_date": "2025-09-14",
            "opponent": "Arizona Cardinals",
            "venue": "away",
            "points_for": 27,
            "points_against": 17,
            "result": "W",
        },
    ]

    inserted = seed_schedule_data(output_path=db_path, records=records)
    monkeypatch.setattr(query_nfl_db, "DB_PATH", db_path)

    assert inserted == 2
    schedule = query_nfl_db.get_team_schedule("Los Angeles Rams", season=2025)
    assert schedule["row_count"] == 2
    assert schedule["rows"][0]["opponent"] == "Detroit Lions"


def test_get_team_schedule_refuses_empty_data(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE team_game (
                game_id TEXT, season INTEGER, week INTEGER, game_date TEXT,
                team TEXT, opponent TEXT, venue TEXT, points_for INTEGER,
                points_against INTEGER, result TEXT
            );
            CREATE VIEW v_team_game AS SELECT * FROM team_game;
            """
        )
    monkeypatch.setattr(query_nfl_db, "DB_PATH", db_path)
    schedule = query_nfl_db.get_team_schedule("No Team", season=2025)
    assert schedule["row_count"] == 0
    assert schedule["status"] == "empty"


def test_get_team_recent_games_can_filter_requested_season(tmp_path, monkeypatch):
    records = [
        {"season": 2025, "team": "Los Angeles Rams", "week": 1, "game_date": "2025-09-07",
         "opponent": "Detroit Lions", "venue": "home", "points_for": 20, "points_against": 24, "result": "L"},
        {"season": 2026, "team": "Los Angeles Rams", "week": 1, "game_date": "2026-09-13",
         "opponent": "Detroit Lions", "venue": "home", "points_for": 27, "points_against": 24, "result": "W"},
    ]
    db_path = tmp_path / "seasons.db"
    seed_schedule_data(output_path=db_path, records=records)
    monkeypatch.setattr(query_nfl_db, "DB_PATH", db_path)

    games = query_nfl_db.get_team_recent_games("Los Angeles Rams", season=2025)

    assert games["row_count"] == 1
    assert games["rows"][0]["season"] == 2025


def test_schedule_feed_maps_full_season_rows_without_fabricating_scores():
    feed = """game_id,season,game_type,week,gameday,away_team,away_score,home_team,home_score
2026_01_DAL_AT_PHI,2026,REG,1,2026-09-10,DAL,,PHI,
2025_01_GB_AT_PHI,2025,REG,1,2025-09-04,GB,20,PHI,24
2026_01_DAL_AT_PHI,2026,PRE,1,2026-08-01,DAL,,PHI,
"""

    records = schedule_records_from_csv(feed, season=2026)

    assert len(records) == 2
    assert records[0]["team"] == "Dallas Cowboys"
    assert records[0]["opponent"] == "Philadelphia Eagles"
    assert records[0]["points_for"] is None
    assert records[0]["result"] is None


def test_seed_migrates_old_score_columns_and_preserves_other_tables(tmp_path):
    db_path = tmp_path / "existing.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE season_team (season INTEGER, team TEXT, games INTEGER, wins INTEGER,
                losses INTEGER, points_for INTEGER, points_against INTEGER, PRIMARY KEY (season, team));
            INSERT INTO season_team VALUES (2025, 'Keep Me', 1, 1, 0, 21, 7);
            CREATE TABLE team_game (game_id TEXT, season INTEGER, week INTEGER, game_date TEXT,
                team TEXT, opponent TEXT, venue TEXT, points_for INTEGER NOT NULL DEFAULT 0,
                points_against INTEGER NOT NULL DEFAULT 0, result TEXT, PRIMARY KEY (game_id, team));
            CREATE VIEW v_team_game AS SELECT * FROM team_game;
            """
        )
    seed_schedule_data(output_path=db_path, records=[
        {"game_id": "game-1", "season": 2026, "week": 1, "team": "Dallas Cowboys",
         "opponent": "Philadelphia Eagles", "venue": "away", "points_for": None,
         "points_against": None, "result": None},
    ])

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT team FROM season_team").fetchone() == ("Keep Me",)
        assert connection.execute("SELECT points_for FROM team_game").fetchone() == (None,)
