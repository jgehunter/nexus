"""Streaming PnL writer for memory-efficient simulation output.

Writes PnL attribution records incrementally to Parquet files instead of
accumulating in memory, enabling week-long simulations without memory exhaustion.
"""

import logging
import tempfile
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from ..shard.state import PnLAttributionRecord, TradePnLAttribution

logger = logging.getLogger(__name__)


class StreamingPnLWriter:
    """Writes PnL attribution records incrementally to Parquet.

    Buffers records in memory until a threshold is reached, then flushes
    to temporary Parquet files. On finalization, merges all temp files
    into the final output efficiently using DuckDB.

    This approach reduces peak memory usage from O(total_records) to
    O(buffer_size), enabling large simulations that would otherwise
    exhaust memory.

    Attributes:
        output_path: Final output Parquet file path
        buffer_size: Number of flattened rows to buffer before flush
    """

    def __init__(
        self,
        output_path: Path,
        buffer_size: int = 100000,
        temp_dir: Path | None = None,
    ) -> None:
        """Initialize streaming writer.

        Args:
            output_path: Path for final merged Parquet file
            buffer_size: Number of rows to buffer before flushing to disk (default 100k for efficiency)
            temp_dir: Directory for temporary files (default: system temp)
        """
        self.output_path = Path(output_path)
        self.buffer_size = buffer_size
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())

        self._buffer: list[dict] = []
        self._temp_files: list[Path] = []
        self._total_records_written = 0
        self._finalized = False

    def write_records(self, records: list[PnLAttributionRecord]) -> None:
        """Write batch of PnL records, flushing when buffer exceeds threshold.

        Args:
            records: List of PnLAttributionRecord objects

        Raises:
            RuntimeError: If writer has already been finalized
        """
        if self._finalized:
            raise RuntimeError("Cannot write to finalized StreamingPnLWriter")

        for record in records:
            for trade_attr in record.trade_attributions:
                self._buffer.append(self._flatten_attribution(record, trade_attr))

        if len(self._buffer) >= self.buffer_size:
            self._flush_buffer()

    def write_records_from_dicts(self, records: list[dict]) -> None:
        """Write pre-serialized PnL records (for cross-process transfer).

        Args:
            records: List of serialized record dicts with structure:
                     {"timestamp_ms": int, "trade_attributions": [dict, ...]}

        Raises:
            RuntimeError: If writer has already been finalized
        """
        if self._finalized:
            raise RuntimeError("Cannot write to finalized StreamingPnLWriter")

        for record in records:
            timestamp_ms = record["timestamp_ms"]
            for attr in record.get("trade_attributions", []):
                row = {"timestamp_ms": timestamp_ms, **attr}
                self._buffer.append(row)

        if len(self._buffer) >= self.buffer_size:
            self._flush_buffer()

    def _flatten_attribution(
        self,
        record: PnLAttributionRecord,
        trade_attr: TradePnLAttribution,
    ) -> dict:
        """Flatten a trade attribution to a single row dict.

        Args:
            record: Parent PnL attribution record
            trade_attr: Individual trade attribution

        Returns:
            Flattened dict suitable for Parquet row
        """
        return {
            "timestamp_ms": trade_attr.timestamp_ms,
            "event_type": trade_attr.event_type,
            "source_trade_id": trade_attr.source_trade_id,
            "pair": trade_attr.pair,
            "side": trade_attr.side,
            "qty": trade_attr.qty,
            "price": trade_attr.price,
            "native_currency": trade_attr.native_currency,
            "reporting_currency": trade_attr.reporting_currency,
            "fx_rate": trade_attr.fx_rate,
            "execution_pnl_native": trade_attr.execution_pnl_native,
            "inventory_pnl_native": trade_attr.inventory_pnl_native,
            "hedge_pnl_native": trade_attr.hedge_pnl_native,
            "unrealized_pnl_native": trade_attr.unrealized_pnl_native,
            "execution_pnl_reporting": trade_attr.execution_pnl_reporting,
            "inventory_pnl_reporting": trade_attr.inventory_pnl_reporting,
            "hedge_pnl_reporting": trade_attr.hedge_pnl_reporting,
            "unrealized_pnl_reporting": trade_attr.unrealized_pnl_reporting,
            "triggered_hedge": trade_attr.triggered_hedge,
            "hedge_allocation_pct": trade_attr.hedge_allocation_pct,
            # Metadata fields (extensible)
            "order_id": trade_attr.metadata.get("order_id"),
            "is_direct": trade_attr.metadata.get("is_direct"),
            "path": trade_attr.metadata.get("path"),
        }

    def _flush_buffer(self) -> None:
        """Flush buffer to a temporary Parquet file."""
        if not self._buffer:
            return

        # Generate unique temp file name
        temp_path = self.temp_dir / f"_pnl_temp_{uuid4().hex}.parquet"

        # Write buffer to Parquet
        table = pa.Table.from_pylist(self._buffer)
        pq.write_table(table, temp_path, compression="snappy")

        self._temp_files.append(temp_path)
        self._total_records_written += len(self._buffer)
        self._buffer.clear()

        logger.debug(
            f"Flushed {self._total_records_written} records to {len(self._temp_files)} temp files"
        )

    def finalize(self) -> Path:
        """Merge all temp files into final output and cleanup.

        Returns:
            Path to the final merged Parquet file

        Raises:
            RuntimeError: If writer has already been finalized
        """
        if self._finalized:
            return self.output_path

        # Flush any remaining buffer
        self._flush_buffer()

        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._temp_files:
            # No records written - create empty file with schema
            self._write_empty_file()
        elif len(self._temp_files) == 1:
            # Single temp file - just move it
            import shutil
            shutil.move(str(self._temp_files[0]), str(self.output_path))
        else:
            # Multiple temp files - merge efficiently
            self._merge_temp_files()

        # Cleanup temp files (in case merge created a copy)
        for temp_path in self._temp_files:
            if temp_path.exists():
                temp_path.unlink()

        self._finalized = True
        logger.info(
            f"Finalized PnL writer: {self._total_records_written} records "
            f"written to {self.output_path}"
        )

        return self.output_path

    def _write_empty_file(self) -> None:
        """Write an empty Parquet file with the correct schema."""
        empty_table = pa.table({
            "timestamp_ms": pa.array([], type=pa.int64()),
            "event_type": pa.array([], type=pa.string()),
            "source_trade_id": pa.array([], type=pa.string()),
            "pair": pa.array([], type=pa.string()),
            "side": pa.array([], type=pa.int64()),
            "qty": pa.array([], type=pa.float64()),
            "price": pa.array([], type=pa.float64()),
            "native_currency": pa.array([], type=pa.string()),
            "reporting_currency": pa.array([], type=pa.string()),
            "fx_rate": pa.array([], type=pa.float64()),
            "execution_pnl_native": pa.array([], type=pa.float64()),
            "inventory_pnl_native": pa.array([], type=pa.float64()),
            "hedge_pnl_native": pa.array([], type=pa.float64()),
            "unrealized_pnl_native": pa.array([], type=pa.float64()),
            "execution_pnl_reporting": pa.array([], type=pa.float64()),
            "inventory_pnl_reporting": pa.array([], type=pa.float64()),
            "hedge_pnl_reporting": pa.array([], type=pa.float64()),
            "unrealized_pnl_reporting": pa.array([], type=pa.float64()),
            "triggered_hedge": pa.array([], type=pa.bool_()),
            "hedge_allocation_pct": pa.array([], type=pa.float64()),
            "order_id": pa.array([], type=pa.string()),
            "is_direct": pa.array([], type=pa.bool_()),
            "path": pa.array([], type=pa.string()),
        })
        pq.write_table(empty_table, self.output_path)

    def _merge_temp_files(self) -> None:
        """Merge multiple temp files into final output using DuckDB.

        Uses DuckDB for efficient streaming merge without loading all
        data into memory.
        """
        from ...core.data.duck import get_connection

        with get_connection(":memory:") as conn:
            # Build paths list for read_parquet
            paths_str = ", ".join(f"'{p}'" for p in self._temp_files)

            # Copy merged data to final output, ordered by timestamp
            conn.execute(f"""
                COPY (
                    SELECT * FROM read_parquet([{paths_str}])
                    ORDER BY timestamp_ms
                )
                TO '{self.output_path}'
                (FORMAT PARQUET, COMPRESSION SNAPPY)
            """)

    @property
    def records_written(self) -> int:
        """Total number of records written (including buffer)."""
        return self._total_records_written + len(self._buffer)

    @property
    def temp_file_count(self) -> int:
        """Number of temporary files created."""
        return len(self._temp_files)

    def __enter__(self) -> "StreamingPnLWriter":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - finalize if not already done."""
        if not self._finalized:
            self.finalize()


def merge_pnl_files(input_paths: list[Path], output_path: Path) -> Path:
    """Merge multiple PnL Parquet files into one.

    Utility function for merging per-pair temp files into final output.

    Args:
        input_paths: List of Parquet files to merge
        output_path: Path for merged output file

    Returns:
        Path to merged file
    """
    from ...core.data.duck import get_connection

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_paths:
        # Write empty file
        empty_table = pa.table({})
        pq.write_table(empty_table, output_path)
        return output_path

    valid_paths = [p for p in input_paths if Path(p).exists()]

    if not valid_paths:
        empty_table = pa.table({})
        pq.write_table(empty_table, output_path)
        return output_path

    with get_connection(":memory:") as conn:
        paths_str = ", ".join(f"'{p}'" for p in valid_paths)
        conn.execute(f"""
            COPY (
                SELECT * FROM read_parquet([{paths_str}])
                ORDER BY timestamp_ms
            )
            TO '{output_path}'
            (FORMAT PARQUET, COMPRESSION SNAPPY)
        """)

    return output_path
