"""Unit tests for currency graph construction."""

import pytest

from efxbt.core.graph.currency_graph import CurrencyGraphBuilder
from efxbt.core.graph.schemas import CurrencyEdge, CurrencyNode


class TestCurrencyGraphBuilder:
    """Tests for CurrencyGraphBuilder."""

    def test_build_graph_simple(self):
        """Test basic graph construction with two pairs."""
        builder = CurrencyGraphBuilder(["EURUSD", "GBPUSD"])
        graph = builder.build_graph()

        # Check nodes
        currencies = {node.currency for node in graph.nodes}
        assert currencies == {"EUR", "USD", "GBP"}

        # Check edges (should have bidirectional for each pair)
        edge_tuples = {(e.from_currency, e.to_currency) for e in graph.edges}
        assert ("EUR", "USD") in edge_tuples
        assert ("USD", "EUR") in edge_tuples
        assert ("GBP", "USD") in edge_tuples
        assert ("USD", "GBP") in edge_tuples

        # Check adjacency
        assert "USD" in graph.adjacency["EUR"]
        assert "EUR" in graph.adjacency["USD"]
        assert "USD" in graph.adjacency["GBP"]
        assert "GBP" in graph.adjacency["USD"]

    def test_build_graph_bidirectional_edges(self):
        """Test that each pair creates both forward and reverse edges."""
        builder = CurrencyGraphBuilder(["EURUSD"])
        graph = builder.build_graph()

        # Should have 2 edges: EUR->USD and USD->EUR
        assert len(graph.edges) == 2

        # Check forward edge
        forward = [e for e in graph.edges if e.from_currency == "EUR" and e.to_currency == "USD"]
        assert len(forward) == 1
        assert forward[0].pair == "EURUSD"
        assert forward[0].is_inverted == False

        # Check reverse edge
        reverse = [e for e in graph.edges if e.from_currency == "USD" and e.to_currency == "EUR"]
        assert len(reverse) == 1
        assert reverse[0].pair == "EURUSD"
        assert reverse[0].is_inverted == True

    def test_build_graph_deterministic_version(self):
        """Test that graph version ID is deterministic regardless of input order."""
        builder1 = CurrencyGraphBuilder(["EURUSD", "GBPUSD", "USDJPY"])
        builder2 = CurrencyGraphBuilder(["USDJPY", "EURUSD", "GBPUSD"])  # Different order

        graph1 = builder1.build_graph()
        graph2 = builder2.build_graph()

        # Version IDs should be identical
        assert graph1.version_id == graph2.version_id

    def test_build_graph_complex(self):
        """Test graph with multiple interconnected currencies."""
        pairs = ["EURUSD", "GBPUSD", "USDJPY", "EURJPY"]
        builder = CurrencyGraphBuilder(pairs)
        graph = builder.build_graph()

        # Check nodes
        currencies = {node.currency for node in graph.nodes}
        assert currencies == {"EUR", "USD", "GBP", "JPY"}

        # Check total edges (4 pairs × 2 directions = 8 edges)
        assert len(graph.edges) == 8

        # Verify EUR has multiple neighbors
        assert set(graph.adjacency["EUR"]) == {"USD", "JPY"}

    def test_build_graph_invalid_pair(self):
        """Test that invalid pair format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid pair format"):
            builder = CurrencyGraphBuilder(["EUR"])  # Too short

        with pytest.raises(ValueError, match="Invalid pair format"):
            builder = CurrencyGraphBuilder(["EURUSD123"])  # Too long

    def test_build_graph_uppercase_normalization(self):
        """Test that lowercase pairs are normalized to uppercase."""
        builder = CurrencyGraphBuilder(["eurusd", "gbpusd"])
        graph = builder.build_graph()

        # All currencies should be uppercase
        for node in graph.nodes:
            assert node.currency.isupper()

        # All pair names should be uppercase
        for edge in graph.edges:
            assert edge.pair.isupper()

    def test_build_graph_empty_pairs(self):
        """Test behavior with empty pair list."""
        builder = CurrencyGraphBuilder([])

        # Empty graph should raise ValidationError (nodes and edges require min_length=1)
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            graph = builder.build_graph()

    def test_version_id_format(self):
        """Test that version ID is a valid hex string of correct length."""
        builder = CurrencyGraphBuilder(["EURUSD"])
        graph = builder.build_graph()

        # Version ID should be 16-character hex string
        assert len(graph.version_id) == 16
        assert all(c in "0123456789abcdef" for c in graph.version_id)

    def test_adjacency_sorted(self):
        """Test that adjacency lists are sorted for determinism."""
        builder = CurrencyGraphBuilder(["EURUSD", "EURGBP", "EURJPY"])
        graph = builder.build_graph()

        # EUR's neighbors should be sorted
        eur_neighbors = graph.adjacency.get("EUR", [])
        assert eur_neighbors == sorted(eur_neighbors)
