import pytest

from app.ml.walk_forward import walk_forward_splits


class TestWalkForwardSplits:
    def test_no_temporal_leakage(self):
        """Every train index must be strictly less than every test index in the same fold."""
        splits = walk_forward_splits(n_samples=200, n_splits=5)
        for split in splits:
            assert split.train_idx.max() < split.test_idx.min()

    def test_splits_are_contiguous_and_expanding(self):
        splits = walk_forward_splits(n_samples=200, n_splits=5)
        for i in range(1, len(splits)):
            # each fold's training set is a superset of the previous fold's train+test
            assert splits[i].train_idx.max() > splits[i - 1].train_idx.max()

    def test_all_samples_eventually_covered_by_some_test_fold(self):
        splits = walk_forward_splits(n_samples=200, n_splits=5)
        all_test_idx = set()
        for split in splits:
            all_test_idx.update(split.test_idx.tolist())
        min_train_size = max(int(200 * 0.2), 30)
        # every index from min_train_size onward should appear in some test fold
        assert all_test_idx == set(range(min_train_size, 200))

    def test_raises_on_insufficient_samples(self):
        with pytest.raises(ValueError):
            walk_forward_splits(n_samples=10, n_splits=5)

    def test_raises_on_too_few_splits(self):
        with pytest.raises(ValueError):
            walk_forward_splits(n_samples=200, n_splits=1)
