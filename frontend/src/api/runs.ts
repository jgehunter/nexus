/**
 * Runs API functions for creating and managing backtest runs.
 */

import { apiGet, apiPost, apiDelete } from './client'

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export type RunStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled'

// === EXTENSIBLE ACTION SYSTEM ===
// To add a new action:
// 1. Create a new interface with action_type literal
// 2. Add it to the ActionParams union type
// 3. Update HedgingRuleBuilder component to handle new action

export interface NoHedgeParams {
  action_type: 'no_hedge'
}

export interface HedgeToTargetParams {
  action_type: 'hedge_to_target'
  target_percentage: number // 0.0 - 1.0
}

export interface HedgePercentageParams {
  action_type: 'hedge_percentage'
  hedge_percentage: number // 0.0 - 1.0
}

// Discriminated union for all action types
export type ActionParams = NoHedgeParams | HedgeToTargetParams | HedgePercentageParams

export type AmountType = 'absolute' | 'signed'

export interface PairGroup {
  name: string
  pairs: string[]
}

export interface HedgingRule {
  pair_or_group: string
  amount_type: AmountType
  from_amount: number
  to_amount: number
  action: ActionParams // Discriminated union
}

export interface HedgingRuleSet {
  groups: PairGroup[]
  rules: HedgingRule[]
}

export interface SimulationConfig {
  dataset: string
  reporting_currency: string
  sample_interval_seconds: number
  use_mid_for_unrealized?: boolean
  hedging_rules: HedgingRuleSet // REQUIRED - replaces hedge_policy + hedge_policy_config
  hedge_delay_ms?: number // Delay in ms before hedge execution (0 = immediate)
}

export interface DecrossConfig {
  priority_currencies: string[]
  max_path_length: number
  use_banker_rounding: boolean
  min_leg_qty: number
}

export interface GeneralConfig {
  direct_pairs: string[]
}

export interface RunConfig {
  dataset: string
  tradebook: string
  start_date: string | null
  end_date: string | null
  name: string | null
  description: string | null
  decross_config?: DecrossConfig
  general_config?: GeneralConfig
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

export type DecrossStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface RunStatusResponse {
  run_id: string
  status: RunStatus
  // Decrossing progress
  decross_status: DecrossStatus
  decross_progress_pct: number
  decross_total_dates: number
  decross_completed_dates: number
  decross_current_date: string | null
  // Shard progress
  total_shards: number
  completed_shards: number
  failed_shards: number
  progress_pct: number
  started_at_ms: number | null
  current_stage: string | null
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
