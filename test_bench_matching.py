from pr_sentinel.bench.run_benchmark import _matches, score_item, BenchmarkItem


def test_matches_same_file_close_line():
    assert _matches({"file": "a.py", "line": 12}, {"file": "a.py", "line": 14})


def test_matches_fails_different_file():
    assert not _matches({"file": "a.py", "line": 12}, {"file": "b.py", "line": 12})


def test_matches_fails_far_line():
    assert not _matches({"file": "a.py", "line": 12}, {"file": "a.py", "line": 40})


def test_score_item_counts_tp_fn_fp():
    item = BenchmarkItem(
        id="p1", diff_path="x.diff", intent="",
        known_issues=[{"file": "a.py", "line": 10}, {"file": "b.py", "line": 5}],
        clean=False,
    )
    result = {
        "review": {
            "findings": [
                {"file": "a.py", "line": 11},   # matches issue 1
                {"file": "c.py", "line": 1},     # false positive
            ],
            "cost_usd": 0.01,
        },
        "latency_ms": 100,
    }
    row = score_item(item, result)
    assert row["true_positives"] == 1
    assert row["false_negatives"] == 1
    assert row["false_positives"] == 1
