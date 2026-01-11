"""Unit tests for currency graph pathfinding."""

import pytest

from efxbt.core.graph.currency_graph import CurrencyGraphBuilder
from efxbt.core.graph.pathfinding import PathFinder


class TestPathFinder:
    """Tests for PathFinder class."""

    def test_find_direct_path(self):
        """Test pathfinding for directly connected currencies."""
        builder = CurrencyGraphBuilder(["EURUSD"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD", "EUR"])
        path = finder.find_path("EUR", "USD")

        assert path is not None
        assert path.currencies == ["EUR", "USD"]
        assert path.pairs == ["EURUSD"]
        assert path.inversions == [False]

    def test_find_indirect_path(self):
        """Test pathfinding through intermediate currency."""
        # Graph: EUR-USD-GBP (no direct EUR-GBP)
        builder = CurrencyGraphBuilder(["EURUSD", "GBPUSD"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD", "EUR", "GBP"])
        path = finder.find_path("EUR", "GBP")

        assert path is not None
        assert path.currencies == ["EUR", "USD", "GBP"]
        assert len(path.pairs) == 2
        assert "EURUSD" in path.pairs
        assert "GBPUSD" in path.pairs

    def test_prefer_direct_over_indirect(self):
        """Test that direct path is preferred over multi-hop path."""
        # Graph with both direct and indirect paths: EUR-GBP direct, EUR-USD-GBP indirect
        builder = CurrencyGraphBuilder(["EURUSD", "GBPUSD", "EURGBP"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])
        path = finder.find_path("EUR", "GBP")

        # Should choose direct path
        assert path is not None
        assert path.currencies == ["EUR", "GBP"]
        assert path.pairs == ["EURGBP"]

    def test_priority_tiebreaker_usd_preferred(self):
        """Test that USD is preferred over other currencies for equal-length paths."""
        # Graph with two equal-length paths: EUR-USD-JPY and EUR-GBP-JPY
        builder = CurrencyGraphBuilder(["EURUSD", "USDJPY", "EURGBP", "GBPJPY"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD", "EUR", "GBP", "JPY"])
        path = finder.find_path("EUR", "JPY")

        # Should prefer path through USD (higher priority than GBP)
        assert path is not None
        assert "USD" in path.currencies
        assert "GBP" not in path.currencies

    def test_priority_tiebreaker_alphabetical(self):
        """Test alphabetical tie-breaking for equal-priority currencies."""
        # Graph with two paths through equal-priority currencies
        builder = CurrencyGraphBuilder(["EURAUD", "AUDJPY", "EURCAD", "CADJPY"])
        graph = builder.build_graph()

        # AUD and CAD have same priority (not in priority list)
        finder = PathFinder(graph, priority_currencies=["USD", "EUR"])
        path = finder.find_path("EUR", "JPY")

        # Should prefer AUD over CAD (alphabetically earlier)
        assert path is not None
        assert "AUD" in path.currencies
        assert "CAD" not in path.currencies

    def test_no_path_exists(self):
        """Test that None is returned when no path exists."""
        # Two disconnected components: EUR-USD and GBP-JPY
        builder = CurrencyGraphBuilder(["EURUSD", "GBPJPY"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])
        path = finder.find_path("EUR", "GBP")

        assert path is None

    def test_avoid_cycles(self):
        """Test that pathfinding avoids cycles."""
        # Triangle: EUR-USD-GBP-EUR
        builder = CurrencyGraphBuilder(["EURUSD", "GBPUSD", "EURGBP"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])
        path = finder.find_path("EUR", "GBP")

        # Should find simple path without cycles
        assert path is not None
        # Path should not revisit any currency
        assert len(path.currencies) == len(set(path.currencies))

    def test_max_path_length_constraint(self):
        """Test that max_path_length constraint is respected."""
        # Long chain: EUR-USD-GBP-JPY-AUD
        builder = CurrencyGraphBuilder(["EURUSD", "GBPUSD", "GBPJPY", "AUDJPY"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])

        # With max_path_length=3, should find EUR-USD-GBP-JPY
        path = finder.find_path("EUR", "JPY", max_path_length=4)
        assert path is not None
        assert len(path.currencies) <= 4

        # With max_path_length=2, may not find path to JPY
        path_short = finder.find_path("EUR", "AUD", max_path_length=2)
        # Should either be None or length <= 2
        if path_short:
            assert len(path_short.currencies) <= 2

    def test_same_currency(self):
        """Test pathfinding from currency to itself."""
        builder = CurrencyGraphBuilder(["EURUSD"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])
        path = finder.find_path("EUR", "EUR")

        # Should return None for self-loop
        assert path is None

    def test_invalid_currency(self):
        """Test error handling for currencies not in graph."""
        builder = CurrencyGraphBuilder(["EURUSD"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])

        with pytest.raises(ValueError, match="Currency not in graph"):
            finder.find_path("EUR", "JPY")  # JPY not in graph

        with pytest.raises(ValueError, match="Currency not in graph"):
            finder.find_path("XXX", "USD")  # XXX not in graph

    def test_case_insensitive(self):
        """Test that pathfinding is case-insensitive."""
        builder = CurrencyGraphBuilder(["EURUSD"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])
        path = finder.find_path("eur", "usd")  # lowercase

        assert path is not None
        # Output should be uppercase
        assert all(c.isupper() for c in path.currencies)

    def test_inversion_flags(self):
        """Test that inversion flags are correctly set."""
        builder = CurrencyGraphBuilder(["EURUSD"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])

        # Forward direction: EUR -> USD (no inversion)
        path_forward = finder.find_path("EUR", "USD")
        assert path_forward.inversions == [False]

        # Reverse direction: USD -> EUR (inversion needed)
        path_reverse = finder.find_path("USD", "EUR")
        assert path_reverse.inversions == [True]

    def test_path_currencies_match_pairs(self):
        """Test that path currencies correctly correspond to pairs."""
        builder = CurrencyGraphBuilder(["EURUSD", "GBPUSD"])
        graph = builder.build_graph()

        finder = PathFinder(graph, priority_currencies=["USD"])
        path = finder.find_path("EUR", "GBP")

        # Path: EUR -> USD -> GBP
        # Pairs should connect consecutive currencies
        assert len(path.pairs) == len(path.currencies) - 1

        # Verify each pair connects consecutive currencies in path
        for i, pair in enumerate(path.pairs):
            from_curr = path.currencies[i]
            to_curr = path.currencies[i + 1]
            # Pair should involve both currencies (may be inverted)
            assert from_curr in pair or to_curr in pair
