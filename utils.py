from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def utc_now():
    return datetime.now(timezone.utc)


def wib_now():
    return datetime.now(WIB)


def iso(dt=None):
    value = dt or utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def wib_iso(dt=None):
    """Timestamp ISO dengan offset WIB (+07:00)."""
    value = dt or wib_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=WIB)
    return value.astimezone(WIB).isoformat(timespec="seconds")


def parse_iso(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
