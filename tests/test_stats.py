from services.stats import build_metric, compute_stats


def test_compute_stats_ignores_invalid_values():
    stats = compute_stats([10, 20, None, "x", True, 30.5])
    assert stats == {"min": 10.0, "max": 30.5, "avg": 20.167, "count": 3}


def test_compute_stats_empty():
    assert compute_stats([]) == {"min": None, "max": None, "avg": None, "count": 0}


def test_build_metric_uses_same_samples():
    series = [{"t": "2026-10-20T10:00:00Z", "value": 5}, {"t": "2026-10-20T10:00:05Z", "value": 15}]
    metric = build_metric(series, "ms", "test")
    assert metric["status"] == "ok"
    assert metric["unit"] == "ms"
    assert metric["stats"]["count"] == 2
    assert metric["stats"]["avg"] == 10.0
