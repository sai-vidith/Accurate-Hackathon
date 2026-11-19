"""Trip times are local wall-clock strings 'YYYY-MM-DDTHH:MM' in the trip's own timezone."""
from datetime import datetime, timedelta

FMT = "%Y-%m-%dT%H:%M"


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip().replace(" ", "T")[:16]
    return datetime.strptime(value, FMT)


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime(FMT) if dt else None


def hm(dt: datetime | None) -> str:
    return dt.strftime("%H:%M") if dt else "—"


def add(dt: datetime, minutes: float) -> datetime:
    return dt + timedelta(minutes=round(minutes))


def minutes_between(a: datetime, b: datetime) -> int:
    return round((b - a).total_seconds() / 60)


def rfc3339(dt: datetime, offset: str) -> str:
    """Local time + offset like '+05:30' for Google APIs."""
    return dt.strftime("%Y-%m-%dT%H:%M:00") + offset
