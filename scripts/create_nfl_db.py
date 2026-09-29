from pathlib import Path
import sqlite3


OUTPUT = Path(__file__).resolve().parents[1] / "db" / "nfl.db"

SCHEMA = """
CREATE TABLE season_team (
    season INTEGER NOT NULL,
    team TEXT NOT NULL,
    games INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    points_for INTEGER NOT NULL DEFAULT 0,
    points_against INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season, team)
);

CREATE TABLE team_game (
    game_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_date TEXT,
    team TEXT NOT NULL,
    opponent TEXT NOT NULL,
    venue TEXT CHECK (venue IN ('home', 'away', 'neutral')),
    points_for INTEGER NOT NULL DEFAULT 0,
    points_against INTEGER NOT NULL DEFAULT 0,
    result TEXT CHECK (result IN ('W', 'L', 'T')),
    PRIMARY KEY (game_id, team)
);

CREATE TABLE explosive_season (
    season INTEGER NOT NULL,
    team TEXT NOT NULL,
    explosive_plays INTEGER NOT NULL DEFAULT 0,
    explosive_passes INTEGER NOT NULL DEFAULT 0,
    explosive_runs INTEGER NOT NULL DEFAULT 0,
    explosive_yards INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season, team)
);

CREATE TABLE injuries (
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

CREATE VIEW v_season_team AS
SELECT season, team, games, wins, losses, points_for, points_against,
       points_for - points_against AS point_differential
FROM season_team;

CREATE VIEW v_team_game AS
SELECT game_id, season, week, game_date, team, opponent, venue,
       points_for, points_against, result
FROM team_game;

CREATE VIEW v_explosive_season AS
SELECT season, team, explosive_plays, explosive_passes, explosive_runs,
       explosive_yards
FROM explosive_season;

CREATE VIEW v_injuries AS
SELECT injury_id, season, team, player_name, position, status, injury,
       practice_status, report_date, is_active
FROM injuries;
"""


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()
    with sqlite3.connect(OUTPUT) as connection:
        connection.executescript(SCHEMA)
    print(OUTPUT)


if __name__ == "__main__":
    main()
