"""Currency universe configuration and pair utilities."""

import re
from typing import Final

from .defaults import Defaults


# Regex pattern for validating currency pairs
PAIR_REGEX: Final[re.Pattern[str]] = re.compile(Defaults.PAIR_PATTERN)


def validate_pair(pair: str) -> bool:
    """Validate that a string is a valid currency pair.

    Args:
        pair: Currency pair string to validate

    Returns:
        True if valid (6 uppercase letters), False otherwise
    """
    return bool(PAIR_REGEX.match(pair))


def get_base_currency(pair: str) -> str:
    """Extract base currency from a pair.

    Args:
        pair: Currency pair in canonical form (e.g., EURUSD)

    Returns:
        Base currency (first 3 characters)

    Raises:
        ValueError: If pair is not valid
    """
    if not validate_pair(pair):
        raise ValueError(f"Invalid pair format: {pair}")
    return pair[:3]


def get_quote_currency(pair: str) -> str:
    """Extract quote currency from a pair.

    Args:
        pair: Currency pair in canonical form (e.g., EURUSD)

    Returns:
        Quote currency (last 3 characters)

    Raises:
        ValueError: If pair is not valid
    """
    if not validate_pair(pair):
        raise ValueError(f"Invalid pair format: {pair}")
    return pair[3:]


def invert_pair(pair: str) -> str:
    """Invert a currency pair.

    Args:
        pair: Currency pair in canonical form (e.g., EURUSD)

    Returns:
        Inverted pair (e.g., USDEUR)

    Raises:
        ValueError: If pair is not valid
    """
    if not validate_pair(pair):
        raise ValueError(f"Invalid pair format: {pair}")
    return pair[3:] + pair[:3]


def normalize_pair(pair: str) -> str:
    """Normalize a pair to uppercase canonical form.

    Args:
        pair: Currency pair string (may be lowercase or have separators)

    Returns:
        Normalized pair in uppercase without separators

    Raises:
        ValueError: If pair cannot be normalized to valid format
    """
    # Remove common separators and convert to uppercase
    normalized = pair.upper().replace("/", "").replace("-", "").replace("_", "")

    if not validate_pair(normalized):
        raise ValueError(f"Cannot normalize pair: {pair}")

    return normalized
