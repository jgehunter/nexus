"""Shard engine orchestrator for per-(date, pair) simulation.

Integrates all shard components (timeline, market data, FIFO matching, PnL calculation,
hedge policies) into a cohesive simulation loop with full trade-level attribution and
multi-currency PnL tracking.
"""

from pathlib import Path

import numpy as np
from pydantic import BaseModel

from ...core.config.run_config import SimulationConfig
from ...core.data.schemas import DecrossedTradeRecord
from .fifo_matcher import FIFO_SLICE_DTYPE, FIFOMatcher
from .fx_converter import FXConverter
from .hedge_policy import create_hedge_policy
from .market_fetcher import MarketSnapshotFetcher
from .pnl_calculator import PnLCalculator, calculate_hedge_cost
from .state import FIFOSlice, PnLAttributionRecord, ShardState, TradePnLAttribution
from .timeline import build_timeline


class ShardResult(BaseModel):
    """Result of running a single shard simulation.

    Contains final state, PnL attribution records, and summary metrics.

    Attributes:
        pair: Currency pair
        date: Date (YYYYMMDD)
        final_state: Final shard state (for chaining to next day)
        pnl_records: List of PnL attribution records (one per event)
        metrics: Summary metrics dict
    """

    pair: str
    date: str
    final_state: ShardState
    pnl_records: list[PnLAttributionRecord]
    metrics: dict


class ShardEngine:
    """Orchestrates simulation for a single shard (pair + date).

    Integrates all components:
    - Timeline construction
    - Market data fetching (with FX rates)
    - FIFO matching (Numba-optimized)
    - PnL calculation (with currency conversion)
    - Hedge policy evaluation
    - Trade-level attribution
    """

    def __init__(
        self,
        pair: str,
        date: str,
        config: SimulationConfig,
        data_root: Path,
    ):
        """Initialize shard engine.

        Args:
            pair: Currency pair (e.g., "EURUSD")
            date: Date in YYYYMMDD format
            config: Simulation configuration
            data_root: Root data directory
        """
        self.pair = pair
        self.date = date
        self.config = config
        self.data_root = Path(data_root)

        # Initialize components
        self.market_fetcher = MarketSnapshotFetcher(pair, data_root, config)
        self.fifo_matcher = FIFOMatcher()
        self.fx_converter = FXConverter(config.reporting_currency)
        self.pnl_calculator = PnLCalculator(self.fx_converter)
        self.hedge_policy = create_hedge_policy(config.hedge_policy)

        # Get native currency for this pair
        self.native_currency = self.fx_converter.get_native_currency(pair)

    def run(
        self,
        client_trades: list[DecrossedTradeRecord],
        prior_state: ShardState | None = None,
    ) -> ShardResult:
        """Run simulation for this shard.

        Args:
            client_trades: List of client trades to simulate
            prior_state: Prior day's final state (for state chaining)

        Returns:
            ShardResult with final state, PnL records, and metrics

        Algorithm:
            1. Build decision timeline (client fills + sampling grid)
            2. Fetch all market snapshots (single DuckDB query with FX rates)
            3. Initialize state (from prior or fresh)
            4. Simulation loop:
               - Process client fills → calculate exec PnL → FIFO match → attribute
               - Evaluate hedge policy → execute hedges → attribute costs
               - Sample unrealized PnL → attribute to open slices
            5. Calculate metrics (internalization, time-to-close)
            6. Return results
        """
        # Step 1: Build timeline
        timeline = build_timeline(client_trades, self.config)

        if not timeline:
            # No events to process
            return self._empty_result(prior_state)

        # Step 2: Fetch ALL market snapshots (single DuckDB query)
        snapshots = self.market_fetcher.fetch_snapshots(timeline)

        # Step 3: Initialize state
        if prior_state:
            state = prior_state.model_copy(deep=True)
            # Restore FIFO queue to numpy array
            self.fifo_matcher.queue = self._state_to_numpy(prior_state.fifo_queue)
        else:
            state = ShardState(pair=self.pair, date=self.date)

        # Step 4: Simulation loop with trade-level attribution
        pnl_records: list[PnLAttributionRecord] = []
        hedge_trades: list[dict] = []
        recent_trades: list[DecrossedTradeRecord] = []  # Track for hedge attribution

        for point in timeline:
            snapshot = snapshots[point.timestamp_ms]
            event_attributions: list[TradePnLAttribution] = []

            # Process client fill
            if point.event_type == "client_fill":
                trade = point.client_trade
                recent_trades.append(trade)

                # Calculate execution PnL (native and reporting)
                exec_pnl_native, exec_pnl_reporting = self.pnl_calculator.calculate_execution_pnl(
                    trade.price,
                    snapshot.mid,
                    trade.qty,
                    trade.side,
                    self.pair,
                    snapshot.fx_rate,
                )

                # FIFO match with attribution
                match_result = self.fifo_matcher.process_fill(trade, snapshot, is_hedge=False)

                # Convert inventory PnL to reporting currency
                inv_pnl_native = match_result.inventory_pnl
                inv_pnl_reporting = self.pnl_calculator.convert_inventory_pnl(
                    inv_pnl_native, self.pair, snapshot.fx_rate
                )

                # Create attribution record for this trade
                trade_attribution = TradePnLAttribution(
                    timestamp_ms=trade.timestamp_ms,
                    event_type="client_fill",
                    source_trade_id=trade.source_trade_id,
                    pair=trade.pair,
                    native_currency=self.native_currency,
                    reporting_currency=self.config.reporting_currency,
                    fx_rate=snapshot.fx_rate,
                    metadata={
                        "order_id": trade.order_id,
                        "is_direct": trade.is_direct,
                        "path": trade.path,
                    },
                    execution_pnl_native=exec_pnl_native,
                    execution_pnl_reporting=exec_pnl_reporting,
                    inventory_pnl_native=inv_pnl_native,
                    inventory_pnl_reporting=inv_pnl_reporting,
                    matched_slices=[
                        {
                            "slice_source_trade_id": slice_id,
                            "matched_qty": qty,
                            "pnl": pnl
                        }
                        for slice_id, qty, pnl in match_result.matched_slices
                    ],
                )
                event_attributions.append(trade_attribution)

                # Update net position
                state.net_position += trade.qty * trade.side

            # Evaluate hedge policy
            hedge_trades_now = self.hedge_policy.evaluate(
                state, snapshot, self.config.hedge_policy_config
            )

            for hedge in hedge_trades_now:
                # Calculate hedge cost (in native currency)
                hedge_cost_native = calculate_hedge_cost(
                    hedge["side"], hedge["qty"], snapshot.spread
                )

                # Convert hedge cost to reporting currency
                hedge_cost_reporting = self.pnl_calculator.convert_inventory_pnl(
                    hedge_cost_native, self.pair, snapshot.fx_rate
                )

                # Attribute hedge cost to trades that triggered it
                hedge_allocations = self.pnl_calculator.attribute_hedge_cost_to_trades(
                    hedge_cost_native,
                    hedge_cost_reporting,
                    recent_trades,
                    state.net_position,
                )

                # FIFO match for hedge
                match_result_hedge = self.fifo_matcher.process_fill(
                    hedge, snapshot, is_hedge=True
                )

                # Convert hedge inventory PnL
                inv_pnl_hedge_native = match_result_hedge.inventory_pnl
                inv_pnl_hedge_reporting = self.pnl_calculator.convert_inventory_pnl(
                    inv_pnl_hedge_native, self.pair, snapshot.fx_rate
                )

                # Create attribution records for each trade that triggered hedge
                for trade_id, (alloc_native, alloc_reporting) in hedge_allocations.items():
                    source_trade = next(
                        (t for t in recent_trades if t.source_trade_id == trade_id), None
                    )
                    if source_trade:
                        hedge_attribution = TradePnLAttribution(
                            timestamp_ms=hedge["timestamp_ms"],
                            event_type="hedge_fill",
                            source_trade_id=trade_id,
                            pair=self.pair,
                            native_currency=self.native_currency,
                            reporting_currency=self.config.reporting_currency,
                            fx_rate=snapshot.fx_rate,
                            metadata={
                                "order_id": source_trade.order_id,
                                "is_direct": source_trade.is_direct,
                                "path": source_trade.path,
                            },
                            execution_pnl_native=0.0,
                            execution_pnl_reporting=0.0,
                            inventory_pnl_native=0.0,
                            inventory_pnl_reporting=0.0,
                            hedge_pnl_native=alloc_native,
                            hedge_pnl_reporting=alloc_reporting,
                            triggered_hedge=True,
                            hedge_allocation_pct=(
                                alloc_native / hedge_cost_native
                                if hedge_cost_native != 0 else 0
                            ),
                        )
                        event_attributions.append(hedge_attribution)

                # Attribute inventory PnL from hedge matching to source trades
                for slice_id, qty, pnl_native in match_result_hedge.matched_slices:
                    source_trade = next(
                        (t for t in recent_trades if t.source_trade_id == slice_id), None
                    )
                    if source_trade:
                        pnl_reporting = self.pnl_calculator.convert_inventory_pnl(
                            pnl_native, self.pair, snapshot.fx_rate
                        )

                        inv_attribution = TradePnLAttribution(
                            timestamp_ms=hedge["timestamp_ms"],
                            event_type="hedge_match",
                            source_trade_id=slice_id,
                            pair=self.pair,
                            native_currency=self.native_currency,
                            reporting_currency=self.config.reporting_currency,
                            fx_rate=snapshot.fx_rate,
                            metadata={
                                "order_id": source_trade.order_id,
                                "is_direct": source_trade.is_direct,
                                "path": source_trade.path,
                            },
                            execution_pnl_native=0.0,
                            execution_pnl_reporting=0.0,
                            inventory_pnl_native=pnl_native,
                            inventory_pnl_reporting=pnl_reporting,
                            hedge_pnl_native=0.0,
                            hedge_pnl_reporting=0.0,
                            matched_slices=[{
                                "slice_source_trade_id": slice_id,
                                "matched_qty": qty,
                                "pnl": pnl_native
                            }],
                        )
                        event_attributions.append(inv_attribution)

                # Update net position
                state.net_position += hedge["qty"] * hedge["side"]
                hedge_trades.append(hedge)

            # Sample unrealized PnL with per-slice attribution
            if point.event_type == "sample":
                slice_pnls = self.fifo_matcher.calculate_unrealized_pnl(snapshot.mid)

                for slice_id, unrealized_native in slice_pnls:
                    source_trade = next(
                        (t for t in recent_trades if t.source_trade_id == slice_id), None
                    )
                    if source_trade:
                        unrealized_reporting = self.pnl_calculator.convert_inventory_pnl(
                            unrealized_native, self.pair, snapshot.fx_rate
                        )

                        sample_attribution = TradePnLAttribution(
                            timestamp_ms=point.timestamp_ms,
                            event_type="sample",
                            source_trade_id=slice_id,
                            pair=self.pair,
                            native_currency=self.native_currency,
                            reporting_currency=self.config.reporting_currency,
                            fx_rate=snapshot.fx_rate,
                            metadata={
                                "order_id": source_trade.order_id,
                                "is_direct": source_trade.is_direct,
                                "path": source_trade.path,
                            },
                            execution_pnl_native=0.0,
                            execution_pnl_reporting=0.0,
                            inventory_pnl_native=0.0,
                            inventory_pnl_reporting=0.0,
                            hedge_pnl_native=0.0,
                            hedge_pnl_reporting=0.0,
                            unrealized_pnl_native=unrealized_native,
                            unrealized_pnl_reporting=unrealized_reporting,
                        )
                        event_attributions.append(sample_attribution)

            # Create PnL attribution record for this event
            if event_attributions:
                pnl_record = PnLAttributionRecord(
                    timestamp_ms=point.timestamp_ms,
                    event_type=point.event_type,
                    trade_attributions=event_attributions,
                    total_execution_pnl_reporting=sum(
                        a.execution_pnl_reporting for a in event_attributions
                    ),
                    total_inventory_pnl_reporting=sum(
                        a.inventory_pnl_reporting for a in event_attributions
                    ),
                    total_hedge_pnl_reporting=sum(
                        a.hedge_pnl_reporting for a in event_attributions
                    ),
                    total_unrealized_pnl_reporting=sum(
                        a.unrealized_pnl_reporting for a in event_attributions
                    ),
                )
                pnl_records.append(pnl_record)

            # Update state
            state.last_timestamp_ms = point.timestamp_ms
            state.last_mid = snapshot.mid

        # Step 5: Update cumulative PnL (in reporting currency)
        state.cumulative_execution_pnl = sum(
            r.total_execution_pnl_reporting for r in pnl_records
        )
        state.cumulative_inventory_pnl = sum(
            r.total_inventory_pnl_reporting for r in pnl_records
        )
        state.cumulative_hedge_pnl = sum(
            r.total_hedge_pnl_reporting for r in pnl_records
        )

        # Step 6: Convert FIFO queue back to state
        state.fifo_queue = self._numpy_to_state(self.fifo_matcher.queue)

        # Step 7: Calculate metrics
        metrics = self._calculate_metrics(pnl_records, state, client_trades, hedge_trades)

        return ShardResult(
            pair=self.pair,
            date=self.date,
            final_state=state,
            pnl_records=pnl_records,
            metrics=metrics,
        )

    def _state_to_numpy(self, fifo_queue: list[FIFOSlice]) -> np.ndarray:
        """Convert FIFOSlice list to numpy structured array.

        Args:
            fifo_queue: List of FIFOSlice objects

        Returns:
            Numpy structured array for Numba processing
        """
        if not fifo_queue:
            return np.array([], dtype=FIFO_SLICE_DTYPE)

        data = []
        for slice_ in fifo_queue:
            data.append((
                slice_.slice_id,
                slice_.open_timestamp_ms,
                slice_.side,
                slice_.qty,
                slice_.open_mid,
                slice_.source_type,
                slice_.source_trade_id,
            ))

        return np.array(data, dtype=FIFO_SLICE_DTYPE)

    def _numpy_to_state(self, queue: np.ndarray) -> list[FIFOSlice]:
        """Convert numpy structured array back to FIFOSlice list.

        Args:
            queue: Numpy structured array

        Returns:
            List of FIFOSlice objects
        """
        if len(queue) == 0:
            return []

        slices = []
        for i in range(len(queue)):
            row = queue[i]
            slices.append(FIFOSlice(
                slice_id=str(row['slice_id']),
                open_timestamp_ms=int(row['open_timestamp_ms']),
                side=int(row['side']),
                qty=float(row['qty']),
                open_mid=float(row['open_mid']),
                source_type=str(row['source_type']),
                source_trade_id=str(row['source_trade_id']),
            ))

        return slices

    def _calculate_metrics(
        self,
        pnl_records: list[PnLAttributionRecord],
        state: ShardState,
        client_trades: list[DecrossedTradeRecord],
        hedge_trades: list[dict],
    ) -> dict:
        """Calculate summary metrics for this shard.

        Args:
            pnl_records: PnL attribution records
            state: Final shard state
            client_trades: All client trades processed
            hedge_trades: All hedge trades executed

        Returns:
            Dict with metrics
        """
        # Volume metrics
        total_client_volume = sum(t.qty for t in client_trades)
        total_hedge_volume = sum(h["qty"] for h in hedge_trades)
        internalized_volume = total_client_volume - total_hedge_volume
        internalization_ratio = (
            internalized_volume / total_client_volume if total_client_volume > 0 else 0.0
        )

        # PnL metrics (in reporting currency)
        total_pnl = (
            state.cumulative_execution_pnl
            + state.cumulative_inventory_pnl
            + state.cumulative_hedge_pnl
        )

        # Time-to-close metrics
        if state.fifo_queue:
            times_open = [
                (state.last_timestamp_ms - slice_.open_timestamp_ms) / 1000.0
                for slice_ in state.fifo_queue
            ]
            avg_time_open = sum(times_open) / len(times_open)
            max_time_open = max(times_open)
        else:
            avg_time_open = 0.0
            max_time_open = 0.0

        return {
            # Volume metrics
            "total_client_volume": total_client_volume,
            "total_hedge_volume": total_hedge_volume,
            "internalized_volume": internalized_volume,
            "internalization_ratio": internalization_ratio,
            # PnL metrics (reporting currency)
            "total_pnl_reporting": total_pnl,
            "execution_pnl_reporting": state.cumulative_execution_pnl,
            "inventory_pnl_reporting": state.cumulative_inventory_pnl,
            "hedge_pnl_reporting": state.cumulative_hedge_pnl,
            # Position metrics
            "final_net_position": state.net_position,
            "open_slice_count": len(state.fifo_queue),
            # Time-to-close metrics
            "avg_time_open_seconds": avg_time_open,
            "max_time_open_seconds": max_time_open,
            # Trade counts
            "client_trade_count": len(client_trades),
            "hedge_trade_count": len(hedge_trades),
        }

    def _empty_result(self, prior_state: ShardState | None) -> ShardResult:
        """Create empty result when no trades to process.

        Args:
            prior_state: Prior state (if any)

        Returns:
            Empty ShardResult
        """
        state = prior_state if prior_state else ShardState(pair=self.pair, date=self.date)

        return ShardResult(
            pair=self.pair,
            date=self.date,
            final_state=state,
            pnl_records=[],
            metrics={
                "total_client_volume": 0.0,
                "total_hedge_volume": 0.0,
                "internalized_volume": 0.0,
                "internalization_ratio": 0.0,
                "total_pnl_reporting": 0.0,
                "execution_pnl_reporting": 0.0,
                "inventory_pnl_reporting": 0.0,
                "hedge_pnl_reporting": 0.0,
                "final_net_position": state.net_position,
                "open_slice_count": len(state.fifo_queue),
                "avg_time_open_seconds": 0.0,
                "max_time_open_seconds": 0.0,
                "client_trade_count": 0,
                "hedge_trade_count": 0,
            },
        )
