import { describe, it, expect, vi } from 'vitest'
import {
    listDatasets,
    getDataset,
    type DatasetSummary,
    type DatasetDetail
} from './datasets'

describe('Datasets API', () => {
    describe('listDatasets', () => {
        it('should return list of datasets', async () => {
            const mockDatasets: DatasetSummary[] = [
                {
                    name: 'sample_efx_2024_market',
                    version_id: 'abc123',
                    pairs: ['MAD_GLD', 'MAD_SLV'],
                    dates: ['20240101', '20240102'],
                    total_market_files: 4,
                    root_path: '/data/datasets/sample_efx_2024_market',
                },
            ]

            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockDatasets),
            })

            const result = await listDatasets()

            expect(result).toEqual(mockDatasets)
            expect(result).toHaveLength(1)
            expect(result[0].name).toBe('sample_efx_2024_market')
        })

        it('should handle empty list', async () => {
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve([]),
            })

            const result = await listDatasets()

            expect(result).toEqual([])
        })
    })

    describe('getDataset', () => {
        it('should return dataset detail', async () => {
            const mockDetail: DatasetDetail = {
                name: 'sample_efx_2024_market',
                version_id: 'abc123',
                pairs: ['MAD_GLD', 'MAD_SLV'],
                dates: ['20240101', '20240102'],
                total_market_files: 4,
                root_path: '/data/datasets/sample_efx_2024_market',
                pair_dates: [
                    { pair: 'MAD_GLD', date: '20240101', row_count: 1000 },
                    { pair: 'MAD_GLD', date: '20240102', row_count: 1200 },
                    { pair: 'MAD_SLV', date: '20240101', row_count: 800 },
                    { pair: 'MAD_SLV', date: '20240102', row_count: 900 },
                ],
            }

            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockDetail),
            })

            const result = await getDataset('sample_efx_2024_market')

            expect(result).toEqual(mockDetail)
            expect(result.pair_dates).toHaveLength(4)
        })
    })
})
