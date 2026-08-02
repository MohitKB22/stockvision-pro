"""
Walk-forward validation splitter.

Design decision: we deliberately do NOT use sklearn's KFold/StratifiedKFold
for this domain. Randomly shuffled K-fold CV on time series data leaks future
information into the training set (a model trained partly on "future" rows
would look artificially good on a "past" validation fold). Every split
produced here has train indices strictly before test indices in time.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class WalkForwardSplit:
    train_idx: np.ndarray
    test_idx: np.ndarray
    fold: int


def walk_forward_splits(
    n_samples: int, n_splits: int = 5, min_train_size: int | None = None
) -> list[WalkForwardSplit]:
    """
    Expanding-window walk-forward splits.

    Fold i trains on rows [0, boundary_i) and tests on the next contiguous
    block [boundary_i, boundary_i+1). Each subsequent fold's training set
    *includes* all previous folds' test data (an expanding window), which
    mirrors how a live model would actually be retrained over time as new
    labeled data becomes available.
    """
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")

    min_train_size = min_train_size or max(int(n_samples * 0.2), 30)
    remaining = n_samples - min_train_size
    if remaining < n_splits:
        raise ValueError(
            f"Not enough samples ({n_samples}) for {n_splits} walk-forward "
            f"splits with a minimum training size of {min_train_size}."
        )

    fold_size = remaining // n_splits
    splits = []
    for fold in range(n_splits):
        train_end = min_train_size + fold * fold_size
        test_end = train_end + fold_size if fold < n_splits - 1 else n_samples
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(train_end, test_end)
        if len(test_idx) == 0:
            continue
        splits.append(WalkForwardSplit(train_idx=train_idx, test_idx=test_idx, fold=fold))
    return splits
