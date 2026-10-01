"""Reproducible, leakage-safe NFL home-win probability model."""

from __future__ import annotations

import re
import sqlite3
from itertools import groupby
from math import log
from pathlib import Path
from statistics import mean
from typing import Any

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from tools.query_nfl_db import DB_PATH

DEFAULT_START_SEASON = 2021
DEFAULT_TRAIN_END_SEASON = 2025
DEFAULT_PREDICTION_SEASON = 2026
ROLLING_WINDOW = 5
MODEL_NAME = "standard-scaled-logistic-regression"
MODEL_PARAMETERS = {
    "C": 0.2,
    "max_iter": 1000,
    "random_state": 42,
    "solver": "lbfgs",
}
CALIBRATION_PARAMETERS = {
    "C": 1.0,
    "max_iter": 1000,
    "random_state": 42,
    "solver": "lbfgs",
}
FEATURE_NAMES = (
    "home_win_pct_last_5",
    "away_win_pct_last_5",
    "home_point_diff_last_5",
    "away_point_diff_last_5",
    "home_points_for_last_5",
    "away_points_for_last_5",
    "home_points_against_last_5",
    "away_points_against_last_5",
    "home_games_before",
    "away_games_before",
    "week",
)


def _read_games(
    start_season: int,
    end_season: int,
    db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"NFL database does not exist: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT game_id, season, week, game_date, team AS home_team,
                       opponent AS away_team, points_for AS home_points,
                       points_against AS away_points
                FROM v_team_game
                WHERE venue = 'home' AND season BETWEEN ? AND ?
                ORDER BY season, week, game_date, game_id
                """,
                (int(start_season), int(end_season)),
            ).fetchall()
    except sqlite3.OperationalError as error:
        raise ValueError("Schedule view is not initialized; import NFL schedules first.") from error
    return [dict(row) for row in rows]


def _form(team: str, history: dict[str, list[tuple[float, float, float]]]) -> tuple[float, float, float, float, int]:
    games = history.get(team, [])[-ROLLING_WINDOW:]
    if not games:
        return 0.5, 0.0, 0.0, 0.0, 0
    return (
        mean(game[0] for game in games),
        mean(game[1] for game in games),
        mean(game[2] for game in games),
        mean(game[1] - game[2] for game in games),
        len(games),
    )


def _features(
    home_team: str,
    away_team: str,
    week: int,
    history: dict[str, list[tuple[float, float, float]]],
) -> list[float]:
    home_win, home_points, home_against, home_diff, home_games = _form(home_team, history)
    away_win, away_points, away_against, away_diff, away_games = _form(away_team, history)
    return [
        home_win,
        away_win,
        home_diff,
        away_diff,
        home_points,
        away_points,
        home_against,
        away_against,
        float(home_games),
        float(away_games),
        float(week),
    ]


def build_feature_rows(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build pregame features; all games in a week share only prior-week results."""
    home_games = [
        game for game in games
        if game.get("venue", "home") == "home"
        and game.get("home_points") is not None
        and game.get("away_points") is not None
    ]
    home_games.sort(key=lambda game: (
        int(game["season"]), int(game["week"]), game.get("game_date") or "", game["game_id"]
    ))
    histories: dict[str, list[tuple[float, float, float]]] = {}
    rows: list[dict[str, Any]] = []

    for _, week_iter in groupby(home_games, key=lambda game: (int(game["season"]), int(game["week"]))):
        week_games = list(week_iter)
        for game in week_games:
            home_points = int(game["home_points"])
            away_points = int(game["away_points"])
            if home_points == away_points:
                continue
            rows.append({
                "game_id": game["game_id"],
                "season": int(game["season"]),
                "week": int(game["week"]),
                "game_date": game.get("game_date"),
                "home_team": game["home_team"],
                "away_team": game["away_team"],
                "features": _features(
                    game["home_team"], game["away_team"], int(game["week"]), histories
                ),
                "home_win": int(home_points > away_points),
            })
        for game in week_games:
            home_points = int(game["home_points"])
            away_points = int(game["away_points"])
            if home_points == away_points:
                home_win = 0.5
            else:
                home_win = float(home_points > away_points)
            histories.setdefault(game["home_team"], []).append(
                (home_win, float(home_points), float(away_points))
            )
            histories.setdefault(game["away_team"], []).append(
                (1.0 - home_win, float(away_points), float(home_points))
            )
    return rows


def _new_model() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(**MODEL_PARAMETERS)),
    ])


def _probability_metrics(
    actual: list[int],
    probabilities: list[float],
    baseline: float | list[float],
) -> dict[str, float]:
    clipped = [min(max(value, 1e-8), 1.0 - 1e-8) for value in probabilities]
    baseline_predictions = [baseline] * len(actual) if isinstance(baseline, (int, float)) else baseline
    if len(baseline_predictions) != len(actual):
        raise ValueError("baseline probabilities must match the actual result count")
    return {
        "accuracy": float(accuracy_score(actual, [int(value >= 0.5) for value in clipped])),
        "brier_score": float(brier_score_loss(actual, clipped)),
        "log_loss": float(log_loss(actual, clipped, labels=[0, 1])),
        "expected_calibration_error": _expected_calibration_error(actual, clipped),
        "baseline_brier_score": float(brier_score_loss(actual, baseline_predictions)),
        "baseline_home_win_probability": float(mean(baseline_predictions)),
    }


def _logit(probability: float) -> float:
    bounded = min(max(probability, 1e-8), 1.0 - 1e-8)
    return log(bounded / (1.0 - bounded))


def _fit_platt_calibrator(
    raw_probabilities: list[float],
    actual: list[int],
) -> LogisticRegression | None:
    """Fit Platt scaling only when prior out-of-fold examples contain both classes."""
    if len(raw_probabilities) != len(actual) or len(set(actual)) < 2:
        return None
    calibrator = LogisticRegression(**CALIBRATION_PARAMETERS)
    calibrator.fit([[_logit(value)] for value in raw_probabilities], actual)
    return calibrator


def _apply_platt_calibration(
    calibrator: LogisticRegression | None,
    raw_probability: float,
) -> float:
    if calibrator is None:
        return raw_probability
    return float(calibrator.predict_proba([[_logit(raw_probability)]])[0, 1])


def _expected_calibration_error(
    actual: list[int],
    probabilities: list[float],
    bin_count: int = 10,
) -> float:
    if not actual:
        return 0.0
    bin_error = 0.0
    for bin_index in range(bin_count):
        lower = bin_index / bin_count
        upper = (bin_index + 1) / bin_count
        members = [
            index for index, probability in enumerate(probabilities)
            if lower <= probability < upper or (bin_index == bin_count - 1 and probability == 1.0)
        ]
        if members:
            mean_probability = mean(probabilities[index] for index in members)
            observed_rate = mean(actual[index] for index in members)
            bin_error += len(members) / len(actual) * abs(mean_probability - observed_rate)
    return float(bin_error)


def walk_forward_backtest(
    start_season: int = DEFAULT_START_SEASON,
    end_season: int = DEFAULT_TRAIN_END_SEASON,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Compare raw probabilities with Platt candidates calibrated on prior OOF seasons."""
    if end_season <= start_season:
        raise ValueError("Backtest requires at least two seasons")
    games = _read_games(start_season, end_season, db_path=db_path)
    feature_rows = build_feature_rows(games)
    seasons = sorted({row["season"] for row in feature_rows})
    fold_results = []
    all_predictions = []
    prior_oof_probabilities: list[float] = []
    prior_oof_actual: list[int] = []

    for test_season in seasons:
        if test_season <= start_season:
            continue
        training = [row for row in feature_rows if row["season"] < test_season]
        testing = [row for row in feature_rows if row["season"] == test_season]
        if not training or not testing or len({row["home_win"] for row in training}) < 2:
            continue
        model = _new_model()
        model.fit([row["features"] for row in training], [row["home_win"] for row in training])
        raw_probabilities = model.predict_proba([row["features"] for row in testing])[:, 1].tolist()
        actual = [row["home_win"] for row in testing]
        baseline = mean(row["home_win"] for row in training)
        calibrator = _fit_platt_calibrator(prior_oof_probabilities, prior_oof_actual)
        calibration_method = "platt" if calibrator is not None else "uncalibrated_insufficient_prior_oof"
        calibrated_probabilities = [
            _apply_platt_calibration(calibrator, probability)
            for probability in raw_probabilities
        ]
        raw_metrics = _probability_metrics(actual, raw_probabilities, baseline)
        calibrated_metrics = _probability_metrics(actual, calibrated_probabilities, baseline)
        fold_results.append({
            "test_season": test_season,
            "games": len(testing),
            "calibration_method": calibration_method,
            "calibration_training_games": len(prior_oof_actual),
            "accuracy": raw_metrics["accuracy"],
            "raw_brier_score": raw_metrics["brier_score"],
            "calibrated_brier_score": calibrated_metrics["brier_score"],
            "brier_score": raw_metrics["brier_score"],
            "raw_log_loss": raw_metrics["log_loss"],
            "calibrated_log_loss": calibrated_metrics["log_loss"],
            "log_loss": raw_metrics["log_loss"],
            "raw_ece": raw_metrics["expected_calibration_error"],
            "calibrated_ece": calibrated_metrics["expected_calibration_error"],
            "expected_calibration_error": raw_metrics["expected_calibration_error"],
            "baseline_brier_score": raw_metrics["baseline_brier_score"],
            "baseline_home_win_probability": baseline,
        })
        all_predictions.extend({
            "game_id": row["game_id"],
            "season": row["season"],
            "week": row["week"],
            "game_date": row["game_date"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "raw_home_win_probability": float(raw_probability),
            "raw_away_win_probability": float(1.0 - raw_probability),
            "home_win_probability": float(raw_probability),
            "away_win_probability": float(1.0 - raw_probability),
            "calibrated_home_win_probability": float(calibrated_probability),
            "calibrated_away_win_probability": float(1.0 - calibrated_probability),
            "actual_home_win": row["home_win"],
            "baseline_home_win_probability": float(baseline),
            "training_through_season": test_season - 1,
            "calibration_method": calibration_method,
            "calibration_training_games": len(prior_oof_actual),
        } for row, raw_probability, calibrated_probability in zip(
            testing, raw_probabilities, calibrated_probabilities
        ))
        prior_oof_probabilities.extend(raw_probabilities)
        prior_oof_actual.extend(actual)

    if not all_predictions:
        raise ValueError(
            f"No walk-forward predictions could be made for {start_season}-{end_season}; "
            "import at least two seasons with completed game scores."
        )
    actual_all = [row["actual_home_win"] for row in all_predictions]
    raw_probabilities_all = [row["raw_home_win_probability"] for row in all_predictions]
    calibrated_probabilities_all = [row["calibrated_home_win_probability"] for row in all_predictions]
    overall_baseline = [row["baseline_home_win_probability"] for row in all_predictions]
    raw_overall = _probability_metrics(actual_all, raw_probabilities_all, overall_baseline)
    calibrated_overall = _probability_metrics(actual_all, calibrated_probabilities_all, overall_baseline)
    calibrated_predictions = [
        row for row in all_predictions if row["calibration_method"] == "platt"
    ]
    calibrated_only = None
    if calibrated_predictions:
        calibrated_only = _probability_metrics(
            [row["actual_home_win"] for row in calibrated_predictions],
            [row["calibrated_home_win_probability"] for row in calibrated_predictions],
            [row["baseline_home_win_probability"] for row in calibrated_predictions],
        )
        calibrated_only["games"] = len(calibrated_predictions)
    return {
        "model": MODEL_NAME,
        "model_parameters": MODEL_PARAMETERS.copy(),
        "feature_names": list(FEATURE_NAMES),
        "training_seasons": [start_season, end_season],
        "test_seasons": [row["test_season"] for row in fold_results],
        "games_backtested": len(all_predictions),
        "metrics": {
            **raw_overall,
            "selected_probability": "raw_model",
            "calibration_applied": False,
            "calibration_method": "platt_candidate",
            "calibrated_candidate": calibrated_overall,
            "calibrated_folds_only": calibrated_only,
        },
        "folds": fold_results,
        "predictions": all_predictions,
    }


def _team_matches(canonical: str, requested: str) -> bool:
    clean = lambda value: re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    canonical_name = clean(canonical)
    requested_name = clean(requested)
    return canonical_name == requested_name or canonical_name.endswith(f" {requested_name}")


def predict_scheduled_game(
    team_a: str,
    team_b: str,
    season: int = DEFAULT_PREDICTION_SEASON,
    start_season: int = DEFAULT_START_SEASON,
    train_through_season: int = DEFAULT_TRAIN_END_SEASON,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Predict a scheduled game's home-win probability using a model trained on prior seasons."""
    if not team_a.strip() or not team_b.strip():
        raise ValueError("team_a and team_b must both be provided")
    if season <= train_through_season:
        raise ValueError("Prediction season must be later than the training seasons")

    games = _read_games(start_season, season, db_path=db_path)
    completed = [
        game for game in games
        if game["home_points"] is not None and game["away_points"] is not None
    ]
    scheduled = [
        game for game in games
        if int(game["season"]) == season
        and (game["home_points"] is None or game["away_points"] is None)
        and (
            (_team_matches(game["home_team"], team_a) and _team_matches(game["away_team"], team_b))
            or (_team_matches(game["home_team"], team_b) and _team_matches(game["away_team"], team_a))
        )
    ]
    if not scheduled:
        raise ValueError(f"No unplayed {season} schedule entry found for {team_a} vs {team_b}.")
    target = scheduled[0]

    training_games = [
        game for game in completed if int(game["season"]) <= train_through_season
    ]
    training_rows = build_feature_rows(training_games)
    if len({row["home_win"] for row in training_rows}) < 2:
        raise ValueError("Historical data does not contain both home wins and away wins")

    calibration_probabilities: list[float] = []
    calibration_actual: list[int] = []
    for test_season in sorted({row["season"] for row in training_rows}):
        earlier_rows = [row for row in training_rows if row["season"] < test_season]
        held_out_rows = [row for row in training_rows if row["season"] == test_season]
        if not earlier_rows or not held_out_rows or len({row["home_win"] for row in earlier_rows}) < 2:
            continue
        fold_model = _new_model()
        fold_model.fit(
            [row["features"] for row in earlier_rows],
            [row["home_win"] for row in earlier_rows],
        )
        calibration_probabilities.extend(
            fold_model.predict_proba([row["features"] for row in held_out_rows])[:, 1].tolist()
        )
        calibration_actual.extend(row["home_win"] for row in held_out_rows)
    calibrator = _fit_platt_calibrator(calibration_probabilities, calibration_actual)

    model = _new_model()
    model.fit([row["features"] for row in training_rows], [row["home_win"] for row in training_rows])

    prior_games = [
        game for game in completed
        if (int(game["season"]), int(game["week"])) < (season, int(target["week"]))
    ]
    history_rows = build_feature_rows(prior_games)
    prior_games_by_id = {game["game_id"]: game for game in prior_games}
    histories: dict[str, list[tuple[float, float, float]]] = {}
    for row in history_rows:
        matching_game = prior_games_by_id[row["game_id"]]
        home_points = int(matching_game["home_points"])
        away_points = int(matching_game["away_points"])
        home_win = float(home_points > away_points) if home_points != away_points else 0.5
        histories.setdefault(matching_game["home_team"], []).append(
            (home_win, float(home_points), float(away_points))
        )
        histories.setdefault(matching_game["away_team"], []).append(
            (1.0 - home_win, float(away_points), float(home_points))
        )
    target_features = _features(
        target["home_team"], target["away_team"], int(target["week"]), histories
    )
    raw_home_probability = float(model.predict_proba([target_features])[0, 1])
    calibrated_home_probability = _apply_platt_calibration(calibrator, raw_home_probability)
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "training_seasons": [start_season, train_through_season],
        "training_games": len(training_rows),
        "calibration_method": "platt" if calibrator is not None else "uncalibrated_insufficient_oof",
        "calibration_training_games": len(calibration_actual),
        "calibration_applied": False,
        "season": season,
        "week": int(target["week"]),
        "game_date": target["game_date"],
        "home_team": target["home_team"],
        "away_team": target["away_team"],
        "raw_home_win_probability": raw_home_probability,
        "raw_away_win_probability": 1.0 - raw_home_probability,
        "home_win_probability": raw_home_probability,
        "away_win_probability": 1.0 - raw_home_probability,
        "calibrated_home_win_probability_candidate": calibrated_home_probability,
        "calibrated_away_win_probability_candidate": 1.0 - calibrated_home_probability,
        "note": (
            "Selected probabilities are raw logistic-model estimates; Platt calibration is shown as a candidate "
            "but not applied because it did not improve walk-forward scores. Probabilities are estimates, not guarantees."
        ),
    }
