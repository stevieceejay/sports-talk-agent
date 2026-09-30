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
    "home_win_probability",
    "away_win_probability",
    "actual_home_win",
    "baseline_home_win_probability",
    "training_through_season",
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
    print(f"Model: {result['model']}")
    print(f"Backtested games: {result['games_backtested']}")
    print(
        f"Accuracy: {metrics['accuracy']:.3f} | Brier: {metrics['brier_score']:.3f} "
        f"(home-rate baseline {metrics['baseline_brier_score']:.3f}) | "
        f"Log loss: {metrics['log_loss']:.3f}"
    )
    for fold in result["folds"]:
        print(
            f"{fold['test_season']}: n={fold['games']} accuracy={fold['accuracy']:.3f} "
            f"Brier={fold['brier_score']:.3f} baseline={fold['baseline_brier_score']:.3f}"
        )
    print(f"Per-game probabilities: {args.output}")


if __name__ == "__main__":
    main()
