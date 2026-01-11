import { describe, it, expect, vi } from 'vitest'
import {
    listTradeBooks,
    getTradeBook,
    getTradeBookHealth,
    type TradeBookSummary,
    type TradeBookDetail,
    type TradeBookHealthReport
} from './tradebooks'

describe('Trade Books API', () => {
    describe('listTradeBooks', () => {
        it('should return list of trade books', async () => {
            const mockTradeBooks: TradeBookSummary[] = [
                {
                    name: 'MAD_GLD',
                    version_id: 'abc123',
                    dates: ['20240101', '20240102'],
                    total_files: 2,
                    total_trades: 10,
                    root_path: '/data/tradebooks/MAD_GLD',
                },
                {
                    name: 'MAD_SLV',
                    version_id: 'def456',
                    dates: ['20240101'],
                    total_files: 1,
                    total_trades: 5,
                    root_path: '/data/tradebooks/MAD_SLV',
                },
            ]

            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockTradeBooks),
            })

            const result = await listTradeBooks()

            expect(result).toEqual(mockTradeBooks)
            expect(result).toHaveLength(2)
            expect(result[0].name).toBe('MAD_GLD')
        })

        it('should handle empty list', async () => {
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve([]),
            })

            const result = await listTradeBooks()

            expect(result).toEqual([])
        })
    })

    describe('getTradeBook', () => {
        it('should return trade book detail', async () => {
            const mockDetail: TradeBookDetail = {
                name: 'MAD_GLD',
                version_id: 'abc123',
                dates: ['20240101', '20240102'],
                total_files: 2,
                total_trades: 10,
                root_path: '/data/tradebooks/MAD_GLD',
                date_files: [
                    { date: '20240101', trade_count: 5 },
                    { date: '20240102', trade_count: 5 },
                ],
            }

            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockDetail),
            })

            const result = await getTradeBook('MAD_GLD')

            expect(result).toEqual(mockDetail)
            expect(result.date_files).toHaveLength(2)
        })
    })

    describe('getTradeBookHealth', () => {
        it('should return health report', async () => {
            const mockHealth: TradeBookHealthReport = {
                book_name: 'MAD_GLD',
                version_id: 'abc123',
                has_issues: false,
                summary: {
                    total_trade_files: 2,
                    total_trades: 10,
                    total_schema_issues: 0,
                    dates_covered: 2,
                },
                trade_stats: [
                    {
                        date: '20240101',
                        has_data: true,
                        trade_count: 5,
                        first_timestamp_ms: 1704067200000,
                        last_timestamp_ms: 1704153600000,
                        duration_ms: 86400000,
                    },
                ],
            }

            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockHealth),
            })

            const result = await getTradeBookHealth('MAD_GLD')

            expect(result).toEqual(mockHealth)
            expect(result.book_name).toBe('MAD_GLD')
            expect(result.summary.total_trades).toBe(10)
        })

        it('should handle health with issues', async () => {
            const mockHealth: TradeBookHealthReport = {
                book_name: 'BAD_BOOK',
                version_id: 'xyz789',
                has_issues: true,
                summary: {
                    total_trade_files: 1,
                    total_trades: 0,
                    total_schema_issues: 2,
                    dates_covered: 0,
                },
                trade_stats: [],
            }

            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockHealth),
            })

            const result = await getTradeBookHealth('BAD_BOOK')

            expect(result.has_issues).toBe(true)
            expect(result.summary.total_schema_issues).toBe(2)
        })
    })
})
