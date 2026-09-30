import csv
import io
import sqlite3

import tools.query_nfl_db as query_nfl_db
from scripts.create_nfl_db import (
    game_stats_from_pbp,
    player_position_groups_from_csv,
    seed_game_stats,
)


PBP_FIELDS = (
    "game_id", "season", "season_type", "week", "game_date", "posteam", "defteam",
    "pass_attempt", "complete_pass", "passing_yards", "pass_touchdown", "interception",
    "rush_attempt", "rushing_yards", "rush_touchdown", "receiving_yards", "passer_player_id",
    "passer_player_name", "receiver_player_id", "receiver_player_name", "rusher_player_id",
    "rusher_player_name", "sack", "sack_player_id", "sack_player_name",
    "half_sack_1_player_id", "half_sack_1_player_name", "half_sack_2_player_id",
    "half_sack_2_player_name", "interception_player_id", "interception_player_name",
    "fumble_forced", "forced_fumble_player_1_team", "forced_fumble_player_1_player_id",
    "forced_fumble_player_1_player_name", "forced_fumble_player_2_team",
    "forced_fumble_player_2_player_id", "forced_fumble_player_2_player_name",
)


def _play(**values):
    row = {field: "" for field in PBP_FIELDS}
    row.update({
        "game_id": "2026_01_NE_BUF",
        "season": "2026",
        "season_type": "REG",
        "week": "1",
        "game_date": "2026-09-13",
        "posteam": "NE",
        "defteam": "BUF",
        "pass_attempt": "0",
        "complete_pass": "0",
        "pass_touchdown": "0",
        "interception": "0",
        "rush_attempt": "0",
        "rush_touchdown": "0",
        "sack": "0",
        "fumble_forced": "0",
    })
    row.update(values)
    return row


def _fixture_csv():
    rows = [
        _play(
            pass_attempt="1", complete_pass="1", passing_yards="12", pass_touchdown="1",
            passer_player_id="qb1", passer_player_name="J.Maye",
            receiver_player_id="wr1", receiver_player_name="S.Diggs", receiving_yards="12",
        ),
        _play(
            rush_attempt="1", rushing_yards="7", rush_touchdown="1",
            rusher_player_id="rb1", rusher_player_name="J.Gibbs",
        ),
        _play(
            posteam="BUF", defteam="NE", pass_attempt="1", sack="1",
            passer_player_id="qb2", passer_player_name="J.Allen",
            sack_player_id="de1", sack_player_name="T.Groot",
        ),
        _play(
            posteam="BUF", defteam="NE", pass_attempt="1", interception="1",
            passer_player_id="qb2", passer_player_name="J.Allen",
            interception_player_id="cb1", interception_player_name="T.White",
        ),
        _play(
            posteam="BUF", defteam="NE", rush_attempt="1", rushing_yards="9",
            rusher_player_id="rb2", rusher_player_name="T.Other",
        ),
        _play(
            posteam="NE", defteam="BUF", fumble_forced="1",
            forced_fumble_player_1_team="BUF", forced_fumble_player_1_player_id="ff1",
            forced_fumble_player_1_player_name="T.Force",
        ),
        _play(
            posteam="BUF", defteam="BUF", fumble_forced="1",
            forced_fumble_player_1_team="NE", forced_fumble_player_1_player_id="ff2",
            forced_fumble_player_1_player_name="J.Force",
        ),
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PBP_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def test_game_stats_from_pbp_aggregates_player_and_team_lines():
    player_rows, team_rows = game_stats_from_pbp(
        _fixture_csv(), season=2026, player_names={"qb1": "Jacoby Brissett"},
        player_positions={"qb1": "QB", "rb1": "RB", "wr1": "WR"},
        player_position_groups={"qb1": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR", "ff1": "DB"},
    )

    players = {row["player_id"]: row for row in player_rows}
    teams = {row["team"]: row for row in team_rows}
    assert players["qb1"]["passing_yards"] == 12
    assert players["qb1"]["player_name"] == "Jacoby Brissett"
    assert players["qb1"]["position"] == "QB"
    assert players["qb1"]["position_group"] == "QB"
    assert players["qb1"]["passing_tds"] == 1
    assert players["wr1"]["receptions"] == 1
    assert players["rb1"]["rushing_yards"] == 7
    assert players["de1"]["defensive_sacks"] == 1
    assert players["cb1"]["defensive_interceptions"] == 1
    assert players["ff1"]["forced_fumbles"] == 1
    assert players["ff2"]["team"] == "New England Patriots"
    assert players["ff2"]["forced_fumbles"] == 1
    assert players["qb2"]["interceptions_thrown"] == 1
    assert teams["New England Patriots"]["rushing_yards"] == 7
    assert teams["Buffalo Bills"]["rushing_yards"] == 9
    assert teams["Buffalo Bills"]["forced_fumbles"] == 1
    assert teams["New England Patriots"]["forced_fumbles"] == 1
    assert teams["New England Patriots"]["defensive_interceptions"] == 1


def test_seeded_player_and_team_game_stats_are_readable(tmp_path, monkeypatch):
    player_rows, team_rows = game_stats_from_pbp(
        _fixture_csv(), season=2026, player_names={"qb1": "Jacoby Brissett"},
        player_positions={"qb1": "QB", "rb1": "RB", "wr1": "WR"},
        player_position_groups={"qb1": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR", "ff1": "DB"},
    )
    db_path = tmp_path / "nfl.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE season_team (season INTEGER, team TEXT, games INTEGER, wins INTEGER, "
            "losses INTEGER, points_for INTEGER, points_against INTEGER, PRIMARY KEY (season, team))"
        )
        connection.execute(
            "CREATE TABLE team_game (game_id TEXT NOT NULL, season INTEGER NOT NULL, week INTEGER NOT NULL, "
            "game_date TEXT, team TEXT NOT NULL, opponent TEXT NOT NULL, venue TEXT, points_for INTEGER, "
            "points_against INTEGER, result TEXT, PRIMARY KEY (game_id, team))"
        )

    counts = seed_game_stats(player_rows, team_rows, output_path=db_path)
    monkeypatch.setattr(query_nfl_db, "DB_PATH", db_path)

    player_stats = query_nfl_db.get_player_game_stats("Jacoby Brissett", season=2026)
    team_stats = query_nfl_db.get_team_game_stats("New England Patriots", season=2026)
    nickname_team_stats = query_nfl_db.get_team_game_stats("Patriots", season=2026)
    leaders = query_nfl_db.get_player_stat_leaders("rushing_yards", season=2026)
    team_filtered_leaders = query_nfl_db.get_player_stat_leaders(
        "rushing_yards", season=2026, team="New England Patriots"
    )
    nickname_filtered_leaders = query_nfl_db.get_player_stat_leaders(
        "rushing_yards", season=2026, team="Patriots", position_group="running_back"
    )
    running_back_leaders = query_nfl_db.get_player_stat_leaders(
        "rushing_yards", season=2026, position_group="running_back"
    )
    defensive_fumble_leaders = query_nfl_db.get_player_stat_leaders(
        "forced_fumbles", season=2026, position_group="defense"
    )
    team_leaders = query_nfl_db.get_team_stat_leaders("rushing_yards", season=2026)
    career_leaders = query_nfl_db.get_player_stat_leaders("rushing_yards")
    all_team_leaders = query_nfl_db.get_player_stat_leaders(
        "rushing_yards", season=2026, team="all", position_group="running_back"
    )
    null_team_leaders = query_nfl_db.get_player_stat_leaders(
        "rushing_yards", season=2026, team="null", position_group="running_back"
    )
    assert counts == (9, 2)
    assert player_stats["rows"][0]["passing_yards"] == 12
    assert team_stats["rows"][0]["rushing_yards"] == 7
    assert nickname_team_stats["row_count"] == 1
    assert leaders["rows"][0]["player_id"] == "rb2"
    assert team_filtered_leaders["rows"][0]["player_id"] == "rb1"
    assert team_filtered_leaders["rows"][0]["team"] == "New England Patriots"
    assert nickname_filtered_leaders["rows"][0]["player_id"] == "rb1"
    assert running_back_leaders["rows"][0]["player_id"] == "rb2"
    assert running_back_leaders["rows"][0]["position_group"] == "RB"
    assert defensive_fumble_leaders["rows"][0]["player_id"] == "ff1"
    assert team_leaders["rows"][0]["team"] == "Buffalo Bills"
    assert career_leaders["rows"][0]["season"] is None
    assert all_team_leaders["rows"][0]["player_id"] == "rb2"
    assert null_team_leaders["rows"][0]["player_id"] == "rb2"
    assert query_nfl_db.get_player_game_stats("Unknown Player", season=2026)["status"] == "empty"


def test_stat_leader_rejects_unapproved_column_name():
    try:
        query_nfl_db.get_player_stat_leaders("passing_yards; DROP TABLE player_game_stats")
    except ValueError as error:
        assert "stat must be one of" in str(error)
    else:
        raise AssertionError("unapproved stat field should be rejected")


def test_player_catalog_maps_position_groups():
    catalog = "gsis_id,display_name,position,position_group\nqb1,Example QB,QB,QB\nwr1,Example TE,TE,TE\n"

    assert player_position_groups_from_csv(catalog) == {"qb1": "QB", "wr1": "TE"}


def test_stat_query_returns_empty_if_stats_views_are_not_initialized(tmp_path, monkeypatch):
    db_path = tmp_path / "schedule-only.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE team_game (game_id TEXT)")
        connection.execute("CREATE VIEW v_team_game AS SELECT game_id FROM team_game")
    monkeypatch.setattr(query_nfl_db, "DB_PATH", db_path)

    assert query_nfl_db.get_player_game_stats("Jacoby Brissett", season=2026)["status"] == "empty"