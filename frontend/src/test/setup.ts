import '@testing-library/jest-dom'

// Mock fetch for API tests
global.fetch = vi.fn()

// Helper to mock fetch responses
export function mockFetchResponse(data: unknown, status = 200) {
    return (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(data),
        text: () => Promise.resolve(JSON.stringify(data)),
    })
}

// Helper to mock fetch errors
export function mockFetchError(message: string) {
    return (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error(message)
    )
}

// Reset mocks after each test
afterEach(() => {
    vi.clearAllMocks()
})
