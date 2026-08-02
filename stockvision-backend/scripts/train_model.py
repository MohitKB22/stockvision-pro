"""
CLI entry point for training a model outside the API — same use case as
`POST /api/v1/models/train`, but scriptable/schedulable (e.g. from a cron job
or a CI pipeline step) without needing an auth token.

Usage:
    python3 scripts/train_model.py DEMO --task trend_classification --algorithm xgboost --trials 20 --splits 5
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, SessionLocal, engine
from app.domain.enums import ModelAlgorithm, ModelTask
from app.services.ml_service import MLService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbol", help="Stock ticker to train on (must already be loaded — see scripts/seed_data.py)")
    parser.add_argument("--task", choices=[t.value for t in ModelTask], default=ModelTask.TREND_CLASSIFICATION.value)
    parser.add_argument("--algorithm", choices=[a.value for a in ModelAlgorithm], default=ModelAlgorithm.XGBOOST.value)
    parser.add_argument("--trials", type=int, default=20, help="Optuna hyperparameter search trials")
    parser.add_argument("--splits", type=int, default=5, help="Walk-forward CV folds")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)  # harmless no-op if tables already exist
    db = SessionLocal()
    try:
        service = MLService(db)
        print(f"Training {args.algorithm} for {args.symbol.upper()} [{args.task}] "
              f"({args.trials} Optuna trials x {args.splits} walk-forward folds)...")
        model = service.train_for_symbol(
            symbol=args.symbol,
            task=ModelTask(args.task),
            algorithm=ModelAlgorithm(args.algorithm),
            n_optuna_trials=args.trials,
            n_walk_forward_splits=args.splits,
        )
        print(f"\nDone: {model.name} v{model.version} [{model.stage.value if hasattr(model.stage, 'value') else model.stage}]")
        print(f"Best hyperparameters: {model.hyperparameters}")
        print("Walk-forward metrics:")
        for k, v in model.metrics.items():
            print(f"  {k}: {v}")
        print("\nTop SHAP features:")
        for f in getattr(model, "_top_features", [])[:10]:
            print(f"  {f['feature']:20s} {f['mean_abs_shap']:.5f}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
