/**
 * Sweeps API client for parameter sweep operations.
 */

import { apiGet, apiPost, apiDelete } from './client'

// -----------------------------------------------------------------------------
// Type Definitions
// -----------------------------------------------------------------------------

export type SweepStatus = 'pending' | 'running' | 'completed' | 'partial' | 'cancelled'

export interface ParameterRange {
  min: number
  max: number
  step: number
}

export interface SweepParameterGrid {
  risk_band_qty?: number[] | ParameterRange
  hedge_mode?: string[]
  hedge_policy?: string[]
  reporting_currency?: string[]
  sample_interval_seconds?: number[] | ParameterRange
  max_path_length?: number[] | ParameterRange
  min_leg_qty?: number[] | ParameterRange
  priority_currencies?: string[][]
}

export interface SweepConfig {
  dataset: string
  tradebook: string
  start_date?: string | null
  end_date?: string | null
  base_simulation_config?: Record<string, unknown>
  base_decross_config?: Record<string, unknown>
  base_general_config?: Record<string, unknown>
  parameter_grid: SweepParameterGrid
  name?: string | null
  description?: string | null
}

export interface SweepCreateResponse {
  sweep_id: string
  status: SweepStatus
  config_hash: string
  total_configs: number
  message: string | null
}

export interface SweepStatusResponse {
  sweep_id: string
  status: SweepStatus
  total_configs: number
  completed_configs: number
  failed_configs: number
  skipped_configs: number
  progress_pct: number
  current_run_id: string | null
  error_message: string | null
}

export interface SweepListItem {
  sweep_id: string
  status: SweepStatus
  config_hash: string
  name: string | null
  dataset: string
  tradebook: string
  total_configs: number
  completed_configs: number
  failed_configs: number
  skipped_configs: number
  progress_pct: number
  created_at_ms: number
  completed_at_ms: number | null
}

export interface SweepListResponse {
  sweeps: SweepListItem[]
  total: number
  limit: number
  offset: number
}

export interface SweepDetailResponse {
  sweep_id: string
  status: SweepStatus
  config_hash: string
  config: SweepConfig
  created_at_ms: number
  started_at_ms: number | null
  completed_at_ms: number | null
  total_configs: number
  completed_configs: number
  failed_configs: number
  skipped_configs: number
  progress_pct: number
  member_run_ids: string[]
  error_message: string | null
}

export interface FrontierConstraint {
  metric: string
  operator: 'lt' | 'le' | 'gt' | 'ge' | 'eq'
  value: number
}

export interface FrontierConfig {
  run_id: string
  config_hash: string
  parameters: Record<string, unknown>
  total_pnl: number
  pnl_per_volume_bps: number
  max_drawdown_pct: number
  inventory_risk_score: number
  risk_adjusted_return: number
  internalization_ratio: number
  total_client_volume: number
  hedge_count: number
  is_pareto_optimal: boolean
}

export interface FrontierTableResponse {
  sweep_id: string
  configs: FrontierConfig[]
  total_configs: number
  filtered_count: number
  pareto_count: number
  x_axis: string
  y_axis: string
}

export interface BestConfigsRequest {
  constraints: FrontierConstraint[]
  sort_by?: string
  limit?: number
}

export interface BestConfigsResponse {
  sweep_id: string
  constraints: FrontierConstraint[]
  sort_by: string
  configs: FrontierConfig[]
  count: number
}

// -----------------------------------------------------------------------------
// API Functions
// -----------------------------------------------------------------------------

/**
 * List all sweeps with optional status filter.
 */
export async function listSweeps(
  status?: SweepStatus,
  limit = 100,
  offset = 0
): Promise<SweepListResponse> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return apiGet<SweepListResponse>(`/sweeps?${params.toString()}`)
}

/**
 * Create a new sweep (does NOT start execution).
 */
export async function createSweep(config: SweepConfig): Promise<SweepCreateResponse> {
  return apiPost<SweepConfig, SweepCreateResponse>('/sweeps', config)
}

/**
 * Get full details of a sweep.
 */
export async function getSweepDetail(sweepId: string): Promise<SweepDetailResponse> {
  return apiGet<SweepDetailResponse>(`/sweeps/${sweepId}`)
}

/**
 * Start execution of a created sweep.
 */
export async function startSweep(sweepId: string): Promise<SweepStatusResponse> {
  return apiPost<Record<string, never>, SweepStatusResponse>(`/sweeps/${sweepId}/start`, {})
}

/**
 * Get current status and progress of a sweep.
 */
export async function getSweepStatus(sweepId: string): Promise<SweepStatusResponse> {
  return apiGet<SweepStatusResponse>(`/sweeps/${sweepId}/status`)
}

/**
 * Delete a sweep and optionally its member runs.
 */
export async function deleteSweep(sweepId: string, deleteRuns = false): Promise<void> {
  const params = new URLSearchParams()
  if (deleteRuns) params.set('delete_runs', 'true')
  return apiDelete(`/sweeps/${sweepId}?${params.toString()}`)
}

/**
 * Get frontier table with optional constraints.
 */
export async function getFrontier(
  sweepId: string,
  maxRisk?: number,
  minInternalization?: number,
  maxDrawdown?: number
): Promise<FrontierTableResponse> {
  const params = new URLSearchParams()
  if (maxRisk !== undefined) params.set('max_risk', String(maxRisk))
  if (minInternalization !== undefined) params.set('min_internalization', String(minInternalization))
  if (maxDrawdown !== undefined) params.set('max_drawdown', String(maxDrawdown))
  const query = params.toString()
  return apiGet<FrontierTableResponse>(`/sweeps/${sweepId}/frontier${query ? `?${query}` : ''}`)
}

/**
 * Get best configurations satisfying all constraints.
 */
export async function getBestConfigs(
  sweepId: string,
  request: BestConfigsRequest
): Promise<BestConfigsResponse> {
  return apiPost<BestConfigsRequest, BestConfigsResponse>(`/sweeps/${sweepId}/best`, request)
}
