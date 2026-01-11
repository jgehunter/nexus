/**
 * Dataset API functions.
 */

import { apiGet } from './client'

export interface DatasetSummary {
    name: string
    version_id: string
    pairs: string[]
    dates: string[]
    total_market_files: number
    root_path: string
}

export interface DatasetDetail extends DatasetSummary {
    pair_dates: Array<{
        pair: string
        date: string
        row_count: number
    }>
}

/**
 * Get list of all datasets.
 */
export async function listDatasets(): Promise<DatasetSummary[]> {
    return apiGet<DatasetSummary[]>('/datasets')
}

/**
 * Get detailed information about a specific dataset.
 */
export async function getDataset(name: string): Promise<DatasetDetail> {
    return apiGet<DatasetDetail>(`/datasets/${name}`)
}

/**
 * Get list of pairs in a dataset.
 */
export async function getDatasetPairs(name: string): Promise<string[]> {
    return apiGet<string[]>(`/datasets/${name}/pairs`)
}

/**
 * Get list of dates in a dataset.
 */
export async function getDatasetDates(name: string): Promise<string[]> {
    return apiGet<string[]>(`/datasets/${name}/dates`)
}
