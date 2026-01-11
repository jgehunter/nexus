"""Deterministic hashing utilities for reproducibility.

Used to generate unique identifiers for configurations and data versions.
"""

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_dict(data: dict[str, Any], algorithm: str = "sha256") -> str:
    """Compute deterministic hash of a dictionary.

    Args:
        data: Dictionary to hash (must be JSON-serializable)
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        Hex digest of the hash
    """
    # Sort keys for deterministic ordering
    json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
    hasher = hashlib.new(algorithm)
    hasher.update(json_str.encode("utf-8"))
    return hasher.hexdigest()


def hash_config(config: Any, algorithm: str = "sha256") -> str:
    """Compute hash of a configuration object.

    Works with Pydantic models and plain dictionaries.

    Args:
        config: Configuration object (Pydantic model or dict)
        algorithm: Hash algorithm to use

    Returns:
        Hex digest of the hash
    """
    if hasattr(config, "model_dump"):
        # Pydantic v2
        data = config.model_dump(mode="json")
    elif hasattr(config, "dict"):
        # Pydantic v1
        data = config.dict()
    elif isinstance(config, dict):
        data = config
    else:
        raise TypeError(f"Cannot hash config of type {type(config)}")

    return hash_dict(data, algorithm)


def hash_file(file_path: Path, algorithm: str = "sha256", chunk_size: int = 8192) -> str:
    """Compute hash of a file.

    Args:
        file_path: Path to file
        algorithm: Hash algorithm to use (default: sha256)
        chunk_size: Read chunk size in bytes

    Returns:
        Hex digest of the hash

    Raises:
        FileNotFoundError: If file does not exist
    """
    hasher = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def short_hash(full_hash: str, length: int = 8) -> str:
    """Get shortened version of a hash for display.

    Args:
        full_hash: Full hex digest
        length: Number of characters to keep

    Returns:
        Shortened hash string
    """
    return full_hash[:length]
