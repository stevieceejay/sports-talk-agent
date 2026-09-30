import sqlite3

from tools.prediction_model import (
    FEATURE_NAMES,
    build_feature_rows,
    predict_scheduled_game,
    walk_forward_backtest,
)


def _game(game_id, season, week, home, away, home_points, away_points):
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "game_date": f"{season}-09-{week:02d}",
        "venue": "home",
        "home_team": home,
        "away_team": away,
        "home_points": home_points,
        "away_points": away_points,
    }


def _create_model_db(path):
    games = []
    teams = ("Alpha", "Bravo", "Charlie", "Delta")
    for season in range(2021, 2026):
        for week in range(1, 9):
            home = teams[(week - 1) % len(teams)]
            away = teams[week % len(teams)]
            if week % 2:
                home_points, away_points = 24 + week, 10 + week
            else:
                home_points, away_points = 10 + week, 24 + week
            games.append(_game(f"{season}-{week}", season, week, home, away, home_points, away_points))
    games.append({
        "game_id": "2026-upcoming",
        "season": 2026,
        "week": 1,
        "game_date": "2026-09-10",
        "venue": "home",
        "home_team": "Alpha",
        "away_team": "Bravo",
        "home_points": None,
        "away_points": None,
    })
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE team_game (
                game_id TEXT, season INTEGER, week INTEGER, game_date TEXT,
                team TEXT, opponent TEXT, venue TEXT, points_for INTEGER,
                points_against INTEGER, result TEXT
            )"""
        )
        connection.executemany(
            "INSERT INTO team_game VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    game["game_id"], game["season"], game["week"], game["game_date"],
                    game["home_team"], game["away_team"], game["venue"],
                    game["home_points"], game["away_points"], None,
                )
                for game in games
            ],
        )
        connection.execute("CREATE VIEW v_team_game AS SELECT * FROM team_game")


def test_same_week_results_never_leak_into_pregame_features():
    games = [
        _game("w1-a", 2021, 1, "Alpha", "Bravo", 21, 10),
        _game("w1-b", 2021, 1, "Charlie", "Delta", 10, 21),
        _game("w2", 2021, 2, "Alpha", "Charlie", 17, 14),
    ]

    rows = build_feature_rows(games)
    week_one = [row for row in rows if row["week"] == 1]
    week_two = next(row for row in rows if row["week"] == 2)

    assert all(row["features"][FEATURE_NAMES.index("home_games_before")] == 0 for row in week_one)
    assert week_two["features"][FEATURE_NAMES.index("home_win_pct_last_5")] == 1
    assert week_two["features"][FEATURE_NAMES.index("away_win_pct_last_5")] == 0


def test_walk_forward_backtest_is_deterministic_and_returns_probabilities(tmp_path):
    db_path = tmp_path / "model.db"
    _create_model_db(db_path)

    first = walk_forward_backtest(2021, 2025, db_path=db_path)
    second = walk_forward_backtest(2021, 2025, db_path=db_path)

    assert first["test_seasons"] == [2022, 2023, 2024, 2025]
    assert first["games_backtested"] == 32
    assert first["metrics"] == second["metrics"]
    assert all(0 <= row["home_win_probability"] <= 1 for row in first["predictions"])
    assert first["metrics"]["brier_score"] >= 0


def test_prediction_uses_historical_games_for_scheduled_matchup(tmp_path):
    db_path = tmp_path / "model.db"
    _create_model_db(db_path)

    prediction = predict_scheduled_game("Alpha", "Bravo", season=2026, db_path=db_path)

    assert prediction["status"] == "ok"
    assert prediction["training_seasons"] == [2021, 2025]
    assert prediction["home_team"] == "Alpha"
    assert 0 <= prediction["home_win_probability"] <= 1
    assert abs(prediction["home_win_probability"] + prediction["away_win_probability"] - 1) < 1e-12
