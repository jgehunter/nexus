"""Data schemas for currency graph structures.

These schemas define the graph representation used for pathfinding
in the decrossing pipeline.
"""

from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class CurrencyNode(BaseModel):
    """A single currency node in the graph.

    Represents a currency that can be traded (e.g., USD, EUR, GBP).
    """

    currency: Annotated[
        str,
        Field(
            min_length=3,
            max_length=3,
            pattern=r"^[A-Z]{3}$",
            description="3-letter currency code (e.g., USD, EUR)",
        ),
    ]

    @field_validator("currency")
    @classmethod
    def validate_currency_uppercase(cls, v: str) -> str:
        """Ensure currency is uppercase."""
        return v.upper()


class CurrencyEdge(BaseModel):
    """A directed edge representing a tradeable currency pair.

    An edge connects two currencies and represents the ability to trade
    between them using a specific market pair (which may need inversion).
    """

    from_currency: Annotated[
        str,
        Field(
            min_length=3,
            max_length=3,
            description="Source currency (e.g., EUR)",
        ),
    ]
    to_currency: Annotated[
        str,
        Field(
            min_length=3,
            max_length=3,
            description="Target currency (e.g., USD)",
        ),
    ]
    pair: Annotated[
        str,
        Field(
            min_length=6,
            max_length=6,
            description="Canonical market pair (e.g., EURUSD)",
        ),
    ]
    is_inverted: Annotated[
        bool,
        Field(
            description="True if rate needs inversion (e.g., USD->EUR via EURUSD requires 1/price)"
        ),
    ]

    @field_validator("from_currency", "to_currency")
    @classmethod
    def validate_currency_format(cls, v: str) -> str:
        """Ensure currency codes are 3-letter uppercase."""
        v = v.upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError(f"Invalid currency code: {v}")
        return v

    @field_validator("pair")
    @classmethod
    def validate_pair_format(cls, v: str) -> str:
        """Ensure pair is 6-letter uppercase."""
        v = v.upper()
        if len(v) != 6 or not v.isalpha():
            raise ValueError(f"Invalid pair format: {v}")
        return v


class CurrencyGraph(BaseModel):
    """Complete currency graph representation.

    A bidirectional graph where nodes are currencies and edges are
    tradeable pairs from the market dataset.
    """

    nodes: Annotated[
        list[CurrencyNode],
        Field(min_length=1, description="All currencies in the graph"),
    ]
    edges: Annotated[
        list[CurrencyEdge],
        Field(min_length=1, description="All tradeable pairs (bidirectional)"),
    ]
    adjacency: Annotated[
        dict[str, list[str]],
        Field(
            description="Adjacency list: currency -> list of neighbor currencies"
        ),
    ]
    version_id: Annotated[
        str,
        Field(
            min_length=1,
            description="Version ID (hash) for graph structure determinism",
        ),
    ]

    @field_validator("adjacency")
    @classmethod
    def validate_adjacency_keys(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        """Ensure adjacency keys are valid 3-letter currency codes."""
        for key in v.keys():
            if len(key) != 3 or not key.isalpha() or not key.isupper():
                raise ValueError(f"Invalid currency in adjacency list: {key}")
        return v


class CurrencyPath(BaseModel):
    """A path through the currency graph.

    Represents a decomposition route for a cross-pair trade.
    For example, EURGBP might decompose via EUR->USD->GBP.
    """

    currencies: Annotated[
        list[str],
        Field(
            min_length=2,
            description="Ordered list of currencies in path (e.g., ['EUR', 'USD', 'GBP'])",
        ),
    ]
    pairs: Annotated[
        list[str],
        Field(
            min_length=1,
            description="Ordered list of market pairs to traverse (e.g., ['EURUSD', 'GBPUSD'])",
        ),
    ]
    inversions: Annotated[
        list[bool],
        Field(
            min_length=1,
            description="Which pairs need rate inversion (same length as pairs)",
        ),
    ]

    @field_validator("currencies")
    @classmethod
    def validate_currencies(cls, v: list[str]) -> list[str]:
        """Ensure all currencies are 3-letter uppercase codes."""
        result = []
        for curr in v:
            curr = curr.upper()
            if len(curr) != 3 or not curr.isalpha():
                raise ValueError(f"Invalid currency in path: {curr}")
            result.append(curr)
        return result

    @field_validator("pairs")
    @classmethod
    def validate_pairs(cls, v: list[str]) -> list[str]:
        """Ensure all pairs are 6-letter uppercase codes."""
        result = []
        for pair in v:
            pair = pair.upper()
            if len(pair) != 6 or not pair.isalpha():
                raise ValueError(f"Invalid pair in path: {pair}")
            result.append(pair)
        return result

    def model_post_init(self, __context) -> None:
        """Validate that inversions length matches pairs length."""
        if len(self.inversions) != len(self.pairs):
            raise ValueError(
                f"Inversions length ({len(self.inversions)}) must match pairs length ({len(self.pairs)})"
            )
        if len(self.currencies) != len(self.pairs) + 1:
            raise ValueError(
                f"Currencies length ({len(self.currencies)}) must be pairs length + 1 ({len(self.pairs) + 1})"
            )
