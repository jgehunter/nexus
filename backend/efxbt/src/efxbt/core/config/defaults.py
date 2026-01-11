"""Default values and constants for the backtester."""

from typing import Final


class Defaults:
    """Default configuration values used throughout the application."""

    # Version
    VERSION: Final[str] = "0.1.0"

    # Timestamp precision
    TIMESTAMP_UNIT: Final[str] = "ms"  # milliseconds

    # Currency pair validation
    PAIR_PATTERN: Final[str] = r"^[A-Z]{6}$"
    PAIR_LENGTH: Final[int] = 6

    # Side convention: +1 = buy base, -1 = sell base
    SIDE_BUY: Final[int] = 1
    SIDE_SELL: Final[int] = -1

    # Common currency pairs for validation
    MAJOR_PAIRS: Final[frozenset[str]] = frozenset({
        "EURUSD",
        "USDJPY",
        "GBPUSD",
        "USDCHF",
        "AUDUSD",
        "USDCAD",
        "NZDUSD",
    })

    # Dataset structure
    TRADES_SUBDIR: Final[str] = "trades"
    MARKET_SUBDIR: Final[str] = "market"
    META_FILENAME: Final[str] = "meta.json"

    # Date format for parquet files
    DATE_FORMAT: Final[str] = "%Y%m%d"  # YYYYMMDD
    DATE_DISPLAY_FORMAT: Final[str] = "%Y-%m-%d"  # YYYY-MM-DD

    # Numeric precision
    PRICE_DECIMALS: Final[int] = 5  # Standard FX pip precision
    QTY_DECIMALS: Final[int] = 2
