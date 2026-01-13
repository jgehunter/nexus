/**
 * Results API client for Phase 5 reporting outputs.
 */

import { apiGet } from './client'

// -----------------------------------------------------------------------------
// Type Definitions
// -----------------------------------------------------------------------------

export interface PositionTimeseriesPoint {
  timestamp_ms: number
  position: number
  position_usd: number
}

export interface PairPositionTimeseries {
  pair: string
  points: PositionTimeseriesPoint[]
  max_position: number
  max_position_usd: number
}

export interface AggregatePositionTimeseriesPoint {
  timestamp_ms: number
  total_abs_position_usd: number
}

export interface AggregatePositionTimeseries {
  points: AggregatePositionTimeseriesPoint[]
  max_total_abs_position_usd: number
}

export interface RiskMetrics {
  max_abs_inventory: number
  inventory_p95: number
  inventory_p99: number
  max_drawdown: number
  max_drawdown_pct: number
  worst_interval_pnl: number
  worst_interval_start_ms: number
  cvar_95: number
  pair_risk: Record<string, unknown>[]
  position_timeseries: PairPositionTimeseries[]
  aggregate_position_timeseries: AggregatePositionTimeseries | null
}

export interface OpsMetrics {
  hedge_count: number
  total_hedge_volume: number
  hedge_volume_ratio: number
  avg_hedge_size: number
  total_client_volume: number
  pair_ops: Record<string, unknown>[]
}

export interface DirectPairInternalization {
  pair: string
  client_volume_usd: number
  internalized_volume_usd: number
  externalized_volume_usd: number
  internalization_ratio: number
}

export interface InternalizationMetrics {
  // USD-normalized aggregate metrics
  total_client_volume_usd: number
  total_internalized_volume_usd: number
  total_externalized_volume_usd: number
  internalization_ratio: number
  // Legacy fields (base currency)
  total_client_volume: number
  total_internalized_volume: number
  total_externalized_volume: number
  // Direct pair breakdown (USD-normalized)
  direct_pair_breakdown: DirectPairInternalization[]
  // Legacy pair breakdown
  pair_breakdown: Record<string, unknown>[]
}

export interface EfficientFrontierScores {
  total_pnl: number
  pnl_per_volume_bps: number
  max_drawdown_pct: number
  inventory_risk_score: number
  risk_adjusted_return: number
}

export interface RunSummary {
  run_id: string
  status: string
  pairs: string[]
  date_range: [string, string] | null
  total_shards: number
  total_execution_pnl: number
  total_inventory_pnl: number
  total_hedge_pnl: number
  total_pnl: number
  total_client_volume: number
  total_internalized_volume: number
  total_externalized_volume: number
  internalization_ratio: number
  pair_summaries: Record<string, unknown>[]
  risk_metrics: RiskMetrics | null
  ops_metrics: OpsMetrics | null
  internalization_metrics: InternalizationMetrics | null
  frontier_scores: EfficientFrontierScores | null
}

export interface TimeseriesPoint {
  timestamp_ms: number
  cumulative_pnl: number
  net_position: number
  unrealized_pnl: number
}

export interface TimeseriesResponse {
  run_id: string
  sample_points: number
  points: TimeseriesPoint[]
}

export interface PnLBreakdownEntry {
  group: string
  execution_pnl: number
  inventory_pnl: number
  hedge_pnl: number
  total_pnl: number
}

export interface PnLBreakdownResponse {
  run_id: string
  group_by: string
  breakdown: PnLBreakdownEntry[]
}

export interface RiskMetricsResponse {
  run_id: string
  risk: RiskMetrics | null
  ops: OpsMetrics | null
}

export interface InternalizationResponse {
  run_id: string
  metrics: InternalizationMetrics | null
}

export interface TradeRecord {
  timestamp_ms: number
  pair: string
  event_type: string
  side: number
  qty: number
  price: number
  execution_pnl: number
  inventory_pnl: number
  hedge_pnl: number
  source_trade_id: string | null
}

export interface TradesResponse {
  run_id: string
  trades: TradeRecord[]
  total: number
  limit: number
  offset: number
}

export interface KPIDefinition {
  id: string
  name: string
  category: string
  description: string
  formula: string | null
  unit: string
  interpretation: 'higher_better' | 'lower_better' | 'neutral'
}

export interface KPIDefinitionsResponse {
  definitions: KPIDefinition[]
}

export interface RunComparisonResponse {
  runs: EfficientFrontierScores[]
  run_ids: string[]
}

export interface RunListItem {
  run_id: string
  status: string
  created_at_ms: number
  completed_at_ms: number | null
  total_shards: number
  completed_shards: number
  progress_pct: number
}

export interface RunListResponse {
  runs: RunListItem[]
  total: number
  limit: number
  offset: number
}

// -----------------------------------------------------------------------------
// API Functions
// -----------------------------------------------------------------------------

/**
 * List all runs.
 */
export async function listRuns(
  status?: string,
  limit = 100,
  offset = 0
): Promise<RunListResponse> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return apiGet<RunListResponse>(`/runs?${params.toString()}`)
}

/**
 * Get summary results for a completed run.
 */
export async function getRunSummary(runId: string): Promise<RunSummary> {
  return apiGet<RunSummary>(`/results/${runId}`)
}

/**
 * Get time series data for visualization.
 */
export async function getTimeseries(
  runId: string,
  samplePoints = 500
): Promise<TimeseriesResponse> {
  return apiGet<TimeseriesResponse>(
    `/results/${runId}/timeseries?sample_points=${samplePoints}`
  )
}

/**
 * Get PnL breakdown by grouping level.
 */
export async function getPnLBreakdown(
  runId: string,
  groupBy: 'total' | 'pair' | 'date' = 'total'
): Promise<PnLBreakdownResponse> {
  return apiGet<PnLBreakdownResponse>(`/results/${runId}/pnl?by=${groupBy}`)
}

/**
 * Get risk metrics for a run.
 */
export async function getRiskMetrics(runId: string): Promise<RiskMetricsResponse> {
  return apiGet<RiskMetricsResponse>(`/results/${runId}/risk`)
}

/**
 * Get internalization metrics for a run.
 */
export async function getInternalizationMetrics(
  runId: string
): Promise<InternalizationResponse> {
  return apiGet<InternalizationResponse>(`/results/${runId}/internalization`)
}

/**
 * Get paginated trade-level data.
 */
export async function getTrades(
  runId: string,
  limit = 100,
  offset = 0,
  pair?: string
): Promise<TradesResponse> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  if (pair) params.set('pair', pair)
  return apiGet<TradesResponse>(`/results/${runId}/trades?${params.toString()}`)
}

/**
 * Get KPI definitions for tooltips.
 */
export async function getKPIDefinitions(): Promise<KPIDefinitionsResponse> {
  return apiGet<KPIDefinitionsResponse>('/kpi/definitions')
}

/**
 * Compare multiple runs.
 */
export async function compareRuns(runIds: string[]): Promise<RunComparisonResponse> {
  const params = new URLSearchParams()
  runIds.forEach((id) => params.append('run_ids', id))
  return apiGet<RunComparisonResponse>(`/kpi/compare?${params.toString()}`)
}
