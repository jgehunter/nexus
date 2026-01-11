"""Tests for utility functions."""

from datetime import datetime, timezone

import pytest

from efxbt.util.time import (
    now_ms,
    ms_to_datetime,
    datetime_to_ms,
    date_str_to_ms,
    ms_to_date_str,
    ms_to_file_date,
)
from efxbt.util.hashing import hash_dict, hash_config, short_hash
from efxbt.core.config.universe import (
    validate_pair,
    get_base_currency,
    get_quote_currency,
    invert_pair,
    normalize_pair,
)


class TestTimeUtils:
    """Tests for time utility functions."""

    def test_now_ms_returns_positive_int(self) -> None:
        """now_ms returns a positive integer."""
        ts = now_ms()
        assert isinstance(ts, int)
        assert ts > 0

    def test_ms_to_datetime_conversion(self) -> None:
        """ms_to_datetime converts correctly."""
        # 2024-01-01 00:00:00 UTC
        ts_ms = 1704067200000
        dt = ms_to_datetime(ts_ms)

        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 0
        assert dt.tzinfo == timezone.utc

    def test_datetime_to_ms_conversion(self) -> None:
        """datetime_to_ms converts correctly."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts_ms = datetime_to_ms(dt)

        assert ts_ms == 1704067200000

    def test_roundtrip_conversion(self) -> None:
        """Roundtrip conversion preserves timestamp."""
        original_ms = 1704067200000
        dt = ms_to_datetime(original_ms)
        back_ms = datetime_to_ms(dt)

        assert back_ms == original_ms

    def test_date_str_to_ms(self) -> None:
        """date_str_to_ms converts date string to start of day."""
        ts_ms = date_str_to_ms("2024-01-01")
        assert ts_ms == 1704067200000

    def test_ms_to_date_str(self) -> None:
        """ms_to_date_str formats timestamp as date string."""
        date_str = ms_to_date_str(1704067200000)
        assert date_str == "2024-01-01"

    def test_ms_to_file_date(self) -> None:
        """ms_to_file_date formats timestamp as YYYYMMDD."""
        file_date = ms_to_file_date(1704067200000)
        assert file_date == "20240101"


class TestHashingUtils:
    """Tests for hashing utility functions."""

    def test_hash_dict_deterministic(self) -> None:
        """hash_dict produces deterministic results."""
        data = {"a": 1, "b": 2}
        hash1 = hash_dict(data)
        hash2 = hash_dict(data)

        assert hash1 == hash2

    def test_hash_dict_different_for_different_data(self) -> None:
        """hash_dict produces different results for different data."""
        hash1 = hash_dict({"a": 1})
        hash2 = hash_dict({"a": 2})

        assert hash1 != hash2

    def test_hash_dict_key_order_independent(self) -> None:
        """hash_dict is independent of key order."""
        hash1 = hash_dict({"a": 1, "b": 2})
        hash2 = hash_dict({"b": 2, "a": 1})

        assert hash1 == hash2

    def test_short_hash(self) -> None:
        """short_hash truncates correctly."""
        full = "abcdef1234567890"
        short = short_hash(full, length=8)

        assert short == "abcdef12"
        assert len(short) == 8


class TestUniverseUtils:
    """Tests for currency universe utilities."""

    def test_validate_pair_valid(self) -> None:
        """validate_pair accepts valid pairs."""
        assert validate_pair("EURUSD") is True
        assert validate_pair("USDJPY") is True
        assert validate_pair("GBPCHF") is True

    def test_validate_pair_invalid(self) -> None:
        """validate_pair rejects invalid pairs."""
        assert validate_pair("EUR/USD") is False
        assert validate_pair("EURUSD1") is False
        assert validate_pair("EUR") is False
        assert validate_pair("eurusd") is False
        assert validate_pair("") is False

    def test_get_base_currency(self) -> None:
        """get_base_currency extracts base currency."""
        assert get_base_currency("EURUSD") == "EUR"
        assert get_base_currency("USDJPY") == "USD"

    def test_get_quote_currency(self) -> None:
        """get_quote_currency extracts quote currency."""
        assert get_quote_currency("EURUSD") == "USD"
        assert get_quote_currency("USDJPY") == "JPY"

    def test_get_currency_invalid_pair(self) -> None:
        """get_base/quote_currency raises for invalid pair."""
        with pytest.raises(ValueError):
            get_base_currency("invalid")
        with pytest.raises(ValueError):
            get_quote_currency("invalid")

    def test_invert_pair(self) -> None:
        """invert_pair inverts currencies correctly."""
        assert invert_pair("EURUSD") == "USDEUR"
        assert invert_pair("USDJPY") == "JPYUSD"

    def test_normalize_pair(self) -> None:
        """normalize_pair handles various formats."""
        assert normalize_pair("eurusd") == "EURUSD"
        assert normalize_pair("EUR/USD") == "EURUSD"
        assert normalize_pair("EUR-USD") == "EURUSD"
        assert normalize_pair("EUR_USD") == "EURUSD"

    def test_normalize_pair_invalid(self) -> None:
        """normalize_pair raises for invalid input."""
        with pytest.raises(ValueError):
            normalize_pair("invalid")
        with pytest.raises(ValueError):
            normalize_pair("EU/USD")
