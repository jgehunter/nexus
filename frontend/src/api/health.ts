/**
 * Health check API with connection status tracking.
 */

import { apiGet } from './client'

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  timestamp_ms: number
  version: string
  checks: Record<string, boolean>
}

export interface DetailedHealthResponse extends HealthResponse {
  system: {
    cpu_percent: number
    memory_percent: number
    memory_available_mb: number
    duckdb_version: string
  }
}

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'error'

export interface ConnectionState {
  status: ConnectionStatus
  health: DetailedHealthResponse | null
  error: string | null
  lastChecked: number | null
  retryCount: number
}

/**
 * Get basic health status.
 */
export async function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health')
}

/**
 * Get detailed health status with system metrics.
 */
export async function getDetailedHealth(): Promise<DetailedHealthResponse> {
  return apiGet<DetailedHealthResponse>('/health/detailed')
}
