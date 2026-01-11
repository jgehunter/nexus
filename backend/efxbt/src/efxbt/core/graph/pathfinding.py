"""Pathfinding algorithms for currency graph traversal.

Implements BFS-based shortest path finding with priority-based tie-breaking
for deterministic cross-pair decomposition.
"""

from collections import deque

from ..config.universe import get_base_currency, get_quote_currency
from .schemas import CurrencyEdge, CurrencyGraph, CurrencyPath


class PathFinder:
    """Finds optimal paths through currency graph.

    Uses BFS to find shortest paths, with deterministic tie-breaking
    based on currency priorities (USD > EUR > GBP > JPY > alphabetical).
    """

    def __init__(self, graph: CurrencyGraph, priority_currencies: list[str]):
        """Initialize pathfinder.

        Args:
            graph: Currency graph to search
            priority_currencies: Ordered list of priority currencies for tie-breaking
                                (e.g., ['USD', 'EUR', 'GBP', 'JPY'])
        """
        self.graph = graph
        self.priority_currencies = [c.upper() for c in priority_currencies]

        # Build priority map: currency -> index (lower index = higher priority)
        self._priority_map: dict[str, int] = {
            curr: idx for idx, curr in enumerate(self.priority_currencies)
        }

        # Build edge lookup for quick access: (from_curr, to_curr) -> CurrencyEdge
        self._edge_lookup: dict[tuple[str, str], CurrencyEdge] = {
            (edge.from_currency, edge.to_currency): edge for edge in graph.edges
        }

    def find_path(
        self,
        from_currency: str,
        to_currency: str,
        max_path_length: int = 3,
    ) -> CurrencyPath | None:
        """Find shortest path with priority-based tie-breaking.

        Algorithm:
        1. Use BFS to find all paths of minimum hop count
        2. If multiple equal-length paths exist:
           - Score by intermediate currencies (prefer higher priority)
           - Use alphabetical tie-breaker for equal priority
        3. Convert best path to CurrencyPath with pair information

        Args:
            from_currency: Start currency (e.g., 'EUR')
            to_currency: End currency (e.g., 'GBP')
            max_path_length: Maximum number of currencies in path (default 3)

        Returns:
            CurrencyPath or None if no path exists

        Example:
            find_path('EUR', 'GBP', max_path_length=3)
            -> CurrencyPath(
                currencies=['EUR', 'USD', 'GBP'],
                pairs=['EURUSD', 'GBPUSD'],
                inversions=[False, True]
            )
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        # Validate currencies exist in graph
        graph_currencies = {node.currency for node in self.graph.nodes}
        if from_currency not in graph_currencies:
            raise ValueError(f"Currency not in graph: {from_currency}")
        if to_currency not in graph_currencies:
            raise ValueError(f"Currency not in graph: {to_currency}")

        # Special case: same currency
        if from_currency == to_currency:
            return None

        # Step 1: BFS to find all shortest paths
        shortest_paths = self._bfs_all_shortest_paths(
            from_currency, to_currency, max_path_length
        )

        if not shortest_paths:
            return None

        # Step 2: Select best path using priority scoring
        best_path = self._select_best_path(shortest_paths)

        # Step 3: Convert to CurrencyPath with pair information
        return self._build_currency_path(best_path)

    def _bfs_all_shortest_paths(
        self,
        start: str,
        end: str,
        max_path_length: int,
    ) -> list[list[str]]:
        """Find all paths of minimum length using BFS.

        Args:
            start: Start currency
            end: End currency
            max_path_length: Maximum currencies in path

        Returns:
            List of currency paths (each path is list of currencies)
            Empty list if no path exists
        """
        # Queue contains paths (lists of currencies)
        queue: deque[list[str]] = deque([[start]])

        # Track the depth at which we first visited each currency
        # This allows us to find ALL shortest paths, not just one
        visited_at_depth: dict[str, int] = {start: 0}

        shortest_length: int | None = None
        all_paths: list[list[str]] = []

        while queue:
            path = queue.popleft()
            current = path[-1]
            current_depth = len(path) - 1

            # Prune if we've already found shorter paths to the destination
            if shortest_length is not None and current_depth >= shortest_length:
                continue

            # Prune if path exceeds max length
            if len(path) >= max_path_length:
                continue

            # Explore neighbors
            neighbors = self.graph.adjacency.get(current, [])
            for neighbor in neighbors:
                # Avoid cycles: don't revisit currencies in current path
                if neighbor in path:
                    continue

                new_path = path + [neighbor]
                new_depth = len(new_path) - 1

                # Check if we reached the destination
                if neighbor == end:
                    path_length = len(new_path)

                    # First path to destination sets the target length
                    if shortest_length is None:
                        shortest_length = path_length
                        all_paths.append(new_path)
                    # Additional paths of same length
                    elif path_length == shortest_length:
                        all_paths.append(new_path)
                    # Longer paths are not interesting (BFS guarantees we see shortest first)

                else:
                    # Continue searching
                    # Only enqueue if we haven't visited this node at a shallower depth
                    if neighbor not in visited_at_depth or visited_at_depth[neighbor] >= new_depth:
                        visited_at_depth[neighbor] = new_depth
                        queue.append(new_path)

        return all_paths

    def _select_best_path(self, paths: list[list[str]]) -> list[str]:
        """Select best path using priority-based scoring.

        Tie-breaking rules:
        1. Prefer paths through higher-priority intermediate currencies
           (USD > EUR > GBP > JPY > ...)
        2. For equal priority, prefer alphabetically earlier intermediate currencies

        Args:
            paths: List of equal-length currency paths

        Returns:
            Best path according to priority rules
        """
        if len(paths) == 1:
            return paths[0]

        def path_score(path: list[str]) -> tuple:
            """Compute sort key for path (lower is better).

            Score is based on intermediate currencies (exclude start and end).
            """
            # Extract intermediate currencies (exclude first and last)
            intermediates = path[1:-1] if len(path) > 2 else []

            # Priority score: sum of priority indices (lower is better)
            # Currencies not in priority list get high score (999)
            priority_score = sum(
                self._priority_map.get(curr, 999) for curr in intermediates
            )

            # Alphabetical tiebreaker (tuple of intermediate currencies)
            alpha_score = tuple(intermediates)

            return (priority_score, alpha_score)

        # Return path with minimum score
        return min(paths, key=path_score)

    def _build_currency_path(self, currency_list: list[str]) -> CurrencyPath:
        """Convert currency list to CurrencyPath with pair information.

        Args:
            currency_list: List of currencies in path (e.g., ['EUR', 'USD', 'GBP'])

        Returns:
            CurrencyPath with pairs and inversion flags

        Example:
            ['EUR', 'USD', 'GBP']
            -> CurrencyPath(
                currencies=['EUR', 'USD', 'GBP'],
                pairs=['EURUSD', 'GBPUSD'],
                inversions=[False, True]
            )
        """
        if len(currency_list) < 2:
            raise ValueError("Path must contain at least 2 currencies")

        pairs: list[str] = []
        inversions: list[bool] = []

        # For each consecutive pair of currencies, find the edge
        for i in range(len(currency_list) - 1):
            from_curr = currency_list[i]
            to_curr = currency_list[i + 1]

            # Look up the edge in our edge lookup
            edge = self._edge_lookup.get((from_curr, to_curr))
            if edge is None:
                raise ValueError(
                    f"No edge found from {from_curr} to {to_curr} in graph"
                )

            pairs.append(edge.pair)
            inversions.append(edge.is_inverted)

        return CurrencyPath(
            currencies=currency_list,
            pairs=pairs,
            inversions=inversions,
        )
