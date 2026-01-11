"""Currency graph construction for FX decrossing.

Builds a bidirectional graph from directly observable pairs, enabling
pathfinding for cross-pair decomposition.
"""

import hashlib
from collections import defaultdict

from ..config.universe import get_base_currency, get_quote_currency, validate_pair
from .schemas import CurrencyEdge, CurrencyGraph, CurrencyNode


class CurrencyGraphBuilder:
    """Builds currency graph from available direct pairs.

    Takes a list of directly observable market pairs (e.g., EURUSD, GBPUSD)
    and constructs a bidirectional graph where:
    - Nodes = individual currencies (EUR, USD, GBP, etc.)
    - Edges = tradeable pairs (bidirectional: EUR<->USD from EURUSD)

    The graph is deterministic: same input pairs produce same graph structure
    regardless of order.
    """

    def __init__(self, direct_pairs: list[str]):
        """Initialize with list of directly observable pairs.

        Args:
            direct_pairs: List of currency pairs from market dataset (e.g., ['EURUSD', 'GBPUSD'])

        Raises:
            ValueError: If any pair is invalid format
        """
        # Validate and normalize all pairs to uppercase
        self.direct_pairs: list[str] = []
        for pair in direct_pairs:
            pair = pair.upper()
            if not validate_pair(pair):
                raise ValueError(f"Invalid pair format: {pair}")
            self.direct_pairs.append(pair)

    def build_graph(self) -> CurrencyGraph:
        """Build bidirectional currency graph.

        Algorithm:
        1. Extract all unique currencies from pairs
        2. Create bidirectional edges for each pair:
           - Forward: base -> quote (normal)
           - Reverse: quote -> base (inverted)
        3. Build adjacency list for O(1) neighbor lookup
        4. Compute deterministic version ID (hash)

        Returns:
            CurrencyGraph with nodes, edges, adjacency list, and version ID

        Example:
            Input: ['EURUSD', 'GBPUSD']
            Output:
                Nodes: EUR, GBP, USD
                Edges: EUR->USD, USD->EUR, GBP->USD, USD->GBP
                Adjacency: {EUR: [USD], USD: [EUR, GBP], GBP: [USD]}
        """
        # Step 1: Extract unique currencies
        currencies: set[str] = set()
        for pair in self.direct_pairs:
            base = get_base_currency(pair)
            quote = get_quote_currency(pair)
            currencies.add(base)
            currencies.add(quote)

        # Create nodes (sorted for determinism)
        nodes = [CurrencyNode(currency=curr) for curr in sorted(currencies)]

        # Step 2: Create bidirectional edges
        edges: list[CurrencyEdge] = []
        adjacency: dict[str, list[str]] = defaultdict(list)

        # Sort pairs for deterministic edge ordering
        for pair in sorted(self.direct_pairs):
            base = get_base_currency(pair)
            quote = get_quote_currency(pair)

            # Forward edge: base -> quote (using pair as-is)
            edges.append(
                CurrencyEdge(
                    from_currency=base,
                    to_currency=quote,
                    pair=pair,
                    is_inverted=False,
                )
            )
            adjacency[base].append(quote)

            # Reverse edge: quote -> base (using inverted rate)
            edges.append(
                CurrencyEdge(
                    from_currency=quote,
                    to_currency=base,
                    pair=pair,
                    is_inverted=True,
                )
            )
            adjacency[quote].append(base)

        # Sort adjacency lists for determinism
        adjacency_sorted = {
            curr: sorted(neighbors) for curr, neighbors in adjacency.items()
        }

        # Step 4: Compute deterministic version ID
        version_id = self._compute_version_id(nodes, edges)

        return CurrencyGraph(
            nodes=nodes,
            edges=edges,
            adjacency=adjacency_sorted,
            version_id=version_id,
        )

    def _compute_version_id(
        self, nodes: list[CurrencyNode], edges: list[CurrencyEdge]
    ) -> str:
        """Compute deterministic hash of graph structure.

        Uses SHA-256 hash of sorted node and edge representations.
        Ensures same input pairs produce same version ID regardless of order.

        Args:
            nodes: List of currency nodes
            edges: List of currency edges

        Returns:
            First 16 characters of SHA-256 hash (hex)
        """
        # Create deterministic string representation
        node_str = "|".join(sorted(node.currency for node in nodes))

        edge_strs = []
        for edge in sorted(
            edges,
            key=lambda e: (e.from_currency, e.to_currency, e.pair, e.is_inverted),
        ):
            edge_str = f"{edge.from_currency}->{edge.to_currency}:{edge.pair}:{edge.is_inverted}"
            edge_strs.append(edge_str)
        edges_str = "|".join(edge_strs)

        # Compute hash
        graph_repr = f"nodes:{node_str}|edges:{edges_str}"
        hash_bytes = hashlib.sha256(graph_repr.encode("utf-8")).hexdigest()

        # Return first 16 characters (64 bits)
        return hash_bytes[:16]
