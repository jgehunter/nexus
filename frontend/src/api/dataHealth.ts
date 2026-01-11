/**
 * Data health API functions.
 */

import { apiGet } from './client'

export interface TickCoverageStats {
    pair: string
    date: string
    has_data: boolean
    tick_count: number
    first_timestamp_ms: number | null
    last_timestamp_ms: number | null
    duration_ms: number | null
    avg_gap_ms: number | null
    max_gap_ms: number | null
    gaps_over_1min: number
    gaps_over_5min: number
    gaps_over_15min: number
}

export interface TradeCoverageStats {
    pair: string
    date: string
    has_data: boolean
    trade_count: number
    first_timestamp_ms: number | null
    last_timestamp_ms: number | null
    duration_ms: number | null
    total_volume: number
    avg_trade_size: number
}

export interface DataHealthReport {
    dataset_name: string
    version_id: string
    has_issues: boolean
    summary: {
        total_tick_files?: number
        total_trade_files?: number
        total_ticks?: number
        total_trades?: number
        total_volume?: number
        gaps_over_1min?: number
        gaps_over_5min?: number
        gaps_over_15min?: number
        total_schema_issues?: number
        pairs_with_ticks?: number
        pairs_with_trades?: number
    }
    tick_coverage: TickCoverageStats[]
    trade_coverage: TradeCoverageStats[]
}

/**
 * Get health report for a dataset.
 */
export async function getDataHealth(
    datasetName: string,
    validateSchemas: boolean = true
): Promise<DataHealthReport> {
    const params = new URLSearchParams({
        dataset: datasetName,
        validate_schemas: validateSchemas.toString()
    })
    return apiGet<DataHealthReport>(`/data-health?${params}`)
}

/**
 * Get health report for a dataset using path parameter.
 */
export async function getDatasetHealth(
    datasetName: string,
    validateSchemas: boolean = true
): Promise<DataHealthReport> {
    const params = new URLSearchParams({
        validate_schemas: validateSchemas.toString()
    })
    return apiGet<DataHealthReport>(`/data-health/${datasetName}?${params}`)
}
