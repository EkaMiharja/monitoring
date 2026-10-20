import math


def compute_stats(values, digits=3):
    clean = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        number = float(value)
        if math.isfinite(number):
            clean.append(number)

    if not clean:
        return {"min": None, "max": None, "avg": None, "count": 0}

    return {
        "min": round(min(clean), digits),
        "max": round(max(clean), digits),
        "avg": round(sum(clean) / len(clean), digits),
        "count": len(clean),
    }


def build_metric(series, unit, source, status="ok", error=None):
    values = [point.get("value") for point in series]
    return {
        "status": status,
        "unit": unit,
        "source": source,
        "error": error,
        "series": series,
        "stats": compute_stats(values),
    }
