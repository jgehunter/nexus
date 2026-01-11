/**
 * Runs API functions for creating and managing backtest runs.
 */

import { apiGet, apiPost, apiDelete } from './client'

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export type RunStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface HedgePolicyConfig {
  risk_band_qty: number
  hedge_mode: string
  pair_bands?: Record<string, number>
}

export interface SimulationConfig {
  dataset: string
  reporting_currency: string
  hedge_policy: string
  hedge_policy_config: HedgePolicyConfig
  sample_interval_seconds: number
}

export interface DecrossConfig {
  priority_currencies: string[]
  max_path_length: number
  use_banker_rounding: boolean
  min_leg_qty: number
}

export interface RunConfig {
  dataset: string
  tradebook: string | null
  pairs: string[]
  start_date: string | null
  end_date: string | null
  name: string | null
  description: string | null
  enable_decrossing: boolean
  decross_config?: DecrossConfig
  simulation_config: SimulationConfig | null
  mode?: 'backtest' | 'replay'
}

export interface FailedShardDetail {
  pair: string
  date: string
  error: string
  traceback: string | null
}

export interface RunListItem {
  run_id: string
  status: RunStatus
  config_hash: string
  config: RunConfig
  created_at_ms: number
  started_at_ms: number | null
  completed_at_ms: number | null
  total_shards: number
  completed_shards: number
  failed_shards: number
  progress_pct: number
  error_message: string | null
  failed_shard_details: FailedShardDetail[]
}

export interface RunListResponse {
  runs: RunListItem[]
  total: number
  limit: number
  offset: number
}

export interface RunCreateResponse {
  run_id: string
  status: RunStatus
  is_new: boolean
  config_hash: string
}

export interface RunStatusResponse {
  run_id: string
  status: RunStatus
  total_shards: number
  completed_shards: number
  failed_shards: number
  progress_pct: number
  started_at_ms: number | null
  error_message: string | null
}

export interface CancelResponse {
  run_id: string
  cancelled: boolean
  message: string | null
}

// -----------------------------------------------------------------------------
// API Functions
// -----------------------------------------------------------------------------

/**
 * List all runs with optional status filter.
 */
export async function listRuns(
  status?: RunStatus,
  limit: number = 100,
  offset: number = 0
): Promise<RunListResponse> {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  params.append('limit', limit.toString())
  params.append('offset', offset.toString())
  const query = params.toString()
  return apiGet<RunListResponse>(`/runs${query ? `?${query}` : ''}`)
}

/**
 * Create a new run (does NOT start execution).
 */
export async function createRun(
  config: RunConfig,
  idempotence: 'error' | 'reuse' | 'new' = 'error'
): Promise<RunCreateResponse> {
  return apiPost<RunConfig, RunCreateResponse>(`/runs?idempotence=${idempotence}`, config)
}

/**
 * Start execution of a created run.
 */
export async function startRun(runId: string): Promise<RunStatusResponse> {
  return apiPost<Record<string, never>, RunStatusResponse>(`/runs/${runId}/start`, {})
}

/**
 * Get current status and progress of a run.
 */
export async function getRunStatus(runId: string): Promise<RunStatusResponse> {
  return apiGet<RunStatusResponse>(`/runs/${runId}/status`)
}

/**
 * Get full details of a specific run.
 */
export async function getRunDetail(runId: string): Promise<RunListItem> {
  return apiGet<RunListItem>(`/runs/${runId}`)
}

/**
 * Request cancellation of a running run.
 */
export async function cancelRun(runId: string): Promise<CancelResponse> {
  return apiPost<Record<string, never>, CancelResponse>(`/runs/${runId}/cancel`, {})
}

/**
 * Delete a run and all its results.
 */
export async function deleteRun(runId: string): Promise<void> {
  return apiDelete(`/runs/${runId}`)
}
