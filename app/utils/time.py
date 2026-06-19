"""Unified time utilities for HyperAgent.

All timestamps stored in the database MUST be naive UTC.
This module is the single source of truth for time operations.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, func


def now() -> datetime:
    """Return current UTC time as a naive datetime (for storage in DB).

    Using a function (not a lambda) makes it picklable and usable
    as SQLAlchemy ``default=`` argument.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Convert any datetime to naive UTC. Returns None iff *dt* is None.

    If *dt* is already naive it's assumed to be UTC and returned as-is.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt  # already naive, assume UTC
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def serialize_utc(dt: datetime) -> str:
    """Serialize a naive-UTC datetime to ISO 8601 with ``Z`` suffix.

    Without the ``Z``, JavaScript parses the string as local time,
    shifting the displayed value by the timezone offset.
    """
    s = dt.isoformat()
    if dt.tzinfo is None:
        s += "Z"
    return s


def to_local(dt: datetime, tz_name: str = "Asia/Shanghai") -> datetime:
    """Convert a naive-UTC datetime to a timezone-aware datetime in *tz_name*."""
    import pytz

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(pytz.timezone(tz_name))


def utc_now_sql():
    """SQLAlchemy ``server_default`` / ``onupdate`` expression returning UTC.

    Usage::

        created_at = Column(DateTime, server_default=utc_now_sql())
        updated_at = Column(DateTime, server_default=utc_now_sql(), onupdate=utc_now_sql())
    """
    return func.datetime("now", type_=DateTime)
