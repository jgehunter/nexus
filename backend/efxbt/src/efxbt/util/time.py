"""Timestamp utilities for millisecond-precision epoch timestamps.

All timestamps in the backtester are int64 milliseconds since Unix epoch (UTC).
"""

from datetime import datetime, timezone


def now_ms() -> int:
    """Get current time as milliseconds since Unix epoch (UTC).

    Returns:
        Current timestamp in milliseconds
    """
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def ms_to_datetime(timestamp_ms: int) -> datetime:
    """Convert milliseconds timestamp to datetime.

    Handles both millisecond (13 digits) and microsecond (16 digits) timestamps,
    auto-detecting based on magnitude.

    Args:
        timestamp_ms: Timestamp in milliseconds (or microseconds) since Unix epoch

    Returns:
        UTC datetime object
    """
    # Handle microsecond timestamps (16 digits) by converting to milliseconds
    if timestamp_ms > 9999999999999:  # More than 13 digits
        timestamp_ms = timestamp_ms // 1000
    return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)


def datetime_to_ms(dt: datetime) -> int:
    """Convert datetime to milliseconds timestamp.

    Args:
        dt: Datetime object (timezone-aware or naive, assumes UTC if naive)

    Returns:
        Timestamp in milliseconds since Unix epoch
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def date_str_to_ms(date_str: str, fmt: str = "%Y-%m-%d") -> int:
    """Convert date string to start-of-day milliseconds timestamp.

    Args:
        date_str: Date string (e.g., "2024-01-15")
        fmt: Date format string (default: "%Y-%m-%d")

    Returns:
        Timestamp in milliseconds for start of day (00:00:00 UTC)
    """
    dt = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
    return datetime_to_ms(dt)


def ms_to_date_str(timestamp_ms: int, fmt: str = "%Y-%m-%d") -> str:
    """Convert milliseconds timestamp to date string.

    Args:
        timestamp_ms: Timestamp in milliseconds since Unix epoch
        fmt: Output format string (default: "%Y-%m-%d")

    Returns:
        Formatted date string
    """
    dt = ms_to_datetime(timestamp_ms)
    return dt.strftime(fmt)


def ms_to_file_date(timestamp_ms: int) -> str:
    """Convert milliseconds timestamp to file date format (YYYYMMDD).

    Args:
        timestamp_ms: Timestamp in milliseconds since Unix epoch

    Returns:
        Date string in YYYYMMDD format
    """
    return ms_to_date_str(timestamp_ms, "%Y%m%d")
