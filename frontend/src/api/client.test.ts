import { describe, it, expect, vi } from 'vitest'
import { apiGet, apiPost, apiDelete, ApiError } from './client'

describe('API Client', () => {
    describe('apiGet', () => {
        it('should make GET request and return JSON', async () => {
            const mockData = { id: 1, name: 'test' }
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockData),
            })

            const result = await apiGet<typeof mockData>('/test')

            expect(result).toEqual(mockData)
            expect(fetch).toHaveBeenCalledWith('/api/v1/test')
        })

        it('should throw ApiError on non-ok response', async () => {
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: false,
                status: 404,
                text: () => Promise.resolve('Not found'),
            })

            await expect(apiGet('/test')).rejects.toThrow(ApiError)
        })

        it('should include status code in ApiError', async () => {
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: false,
                status: 500,
                text: () => Promise.resolve('Server error'),
            })

            try {
                await apiGet('/test')
                expect.fail('Should have thrown')
            } catch (error) {
                expect(error).toBeInstanceOf(ApiError)
                expect((error as ApiError).status).toBe(500)
            }
        })
    })

    describe('apiPost', () => {
        it('should make POST request with JSON body', async () => {
            const mockData = { success: true }
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockData),
            })

            const result = await apiPost('/test', { data: 'value' })

            expect(result).toEqual(mockData)
            expect(fetch).toHaveBeenCalledWith('/api/v1/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ data: 'value' }),
            })
        })

        it('should throw ApiError on failure', async () => {
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: false,
                status: 400,
                text: () => Promise.resolve('Bad request'),
            })

            await expect(apiPost('/test', {})).rejects.toThrow(ApiError)
        })
    })

    describe('apiDelete', () => {
        it('should make DELETE request', async () => {
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: true,
            })

            await apiDelete('/test/1')

            expect(fetch).toHaveBeenCalledWith('/api/v1/test/1', {
                method: 'DELETE',
            })
        })

        it('should throw ApiError on failure', async () => {
            global.fetch = vi.fn().mockResolvedValueOnce({
                ok: false,
                status: 404,
                text: () => Promise.resolve('Not found'),
            })

            await expect(apiDelete('/test/1')).rejects.toThrow(ApiError)
        })
    })
})
