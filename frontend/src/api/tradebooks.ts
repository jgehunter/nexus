/**
 * Trade Books API functions.
 *
 * Trade books are independent entities representing collections of trades
 * organized by date. The book name IS the entity identifier.
 */

import { apiGet } from './client'

export interface TradeBookSummary {
    name: string
    version_id: string
    dates: string[]
    total_files: number
    total_trades: number
    root_path: string
}

export interface TradeBookDetail extends TradeBookSummary {
    date_files: Array<{
        date: string
        trade_count: number
    }>
}

export interface TradeBookHealthReport {
    book_name: string
    version_id: string
    has_issues: boolean
    summary: {
        total_trade_files: number
        total_trades: number
        total_schema_issues: number
        dates_covered: number
    }
    trade_stats: Array<{
        date: string
        has_data: boolean
        trade_count: number
        first_timestamp_ms: number | null
        last_timestamp_ms: number | null
        duration_ms: number | null
    }>
}

/**
 * Get list of all trade books.
 */
export async function listTradeBooks(): Promise<TradeBookSummary[]> {
    return apiGet<TradeBookSummary[]>('/tradebooks')
}

/**
 * Get detailed information about a specific trade book.
 */
export async function getTradeBook(name: string): Promise<TradeBookDetail> {
    return apiGet<TradeBookDetail>(`/tradebooks/${name}`)
}

/**
 * Get health report for a trade book.
 */
export async function getTradeBookHealth(name: string): Promise<TradeBookHealthReport> {
    return apiGet<TradeBookHealthReport>(`/tradebooks/${name}/health`)
}

/**
 * Get list of dates in a trade book.
 */
export async function getTradeBookDates(name: string): Promise<string[]> {
    return apiGet<string[]>(`/tradebooks/${name}/dates`)
}
