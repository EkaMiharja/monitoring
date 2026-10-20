def section(status="ok", source=None, error=None, **extra):
    payload = {"status": status, "source": source, "error": error}
    payload.update(extra)
    return payload


def unavailable(source, message):
    return section(status="unavailable", source=source, error=message)
