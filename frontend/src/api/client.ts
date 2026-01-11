/**
 * API client for backend communication.
 */

const API_BASE = '/api/v1'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Make a GET request to the API.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`)

  if (!response.ok) {
    const text = await response.text()
    throw new ApiError(response.status, text || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Make a POST request to the API.
 */
export async function apiPost<T, R>(path: string, body: T): Promise<R> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new ApiError(response.status, text || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Make a DELETE request to the API.
 */
export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const text = await response.text()
    throw new ApiError(response.status, text || `HTTP ${response.status}`)
  }
}
