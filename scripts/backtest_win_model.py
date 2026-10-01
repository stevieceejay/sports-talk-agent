from __future__ import annotations

import argparse
import csv
from pathlib import Path

from tools.prediction_model import (
    DEFAULT_START_SEASON,
    DEFAULT_TRAIN_END_SEASON,
    walk_forward_backtest,
)

DEFAULT_REPORT = Path(__file__).resolve().parents[1] / "reports" / "win_probabilities_2022_2025.csv"
REPORT_FIELDS = (
    "game_id",
    "season",
    "week",
    "game_date",
    "home_team",
    "away_team",
    "raw_home_win_probability",
    "raw_away_win_probability",
    "home_win_probability",
    "away_win_probability",
    "calibrated_home_win_probability",
    "calibrated_away_win_probability",
    "actual_home_win",
    "baseline_home_win_probability",
    "training_through_season",
    "calibration_method",
    "calibration_training_games",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible NFL walk-forward win-probability backtest.")
    parser.add_argument("--start-season", type=int, default=DEFAULT_START_SEASON)
    parser.add_argument("--end-season", type=int, default=DEFAULT_TRAIN_END_SEASON)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    result = walk_forward_backtest(args.start_season, args.end_season)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(result["predictions"])

    metrics = result["metrics"]
    calibration_candidate = metrics["calibrated_candidate"]
    print(f"Model: {result['model']}")
    print(f"Backtested games: {result['games_backtested']}")
    print(
        f"Selected raw accuracy: {metrics['accuracy']:.3f} | "
        f"Brier: raw {metrics['brier_score']:.3f}, Platt candidate {calibration_candidate['brier_score']:.3f}, "
        f"baseline {metrics['baseline_brier_score']:.3f} | "
        f"Log loss: raw {metrics['log_loss']:.3f}, Platt candidate {calibration_candidate['log_loss']:.3f} | "
        f"ECE: raw {metrics['expected_calibration_error']:.3f}, "
        f"Platt candidate {calibration_candidate['expected_calibration_error']:.3f}"
    )
    for fold in result["folds"]:
        print(
            f"{fold['test_season']}: n={fold['games']} calibration={fold['calibration_method']} "
            f"accuracy={fold['accuracy']:.3f} Brier raw/candidate={fold['brier_score']:.3f}/"
            f"{fold['calibrated_brier_score']:.3f} ECE raw/candidate="
            f"{fold['expected_calibration_error']:.3f}/{fold['calibrated_ece']:.3f}"
        )
    if metrics["calibrated_folds_only"]:
        calibrated = metrics["calibrated_folds_only"]
        print(
            f"Platt-candidate folds only: n={calibrated['games']} "
            f"Brier={calibrated['brier_score']:.3f} ECE={calibrated['expected_calibration_error']:.3f}"
        )
    print(f"Calibration applied to selected predictions: {metrics['calibration_applied']}")
    print(f"Per-game probabilities: {args.output}")


if __name__ == "__main__":
    main()
