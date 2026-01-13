/**
 * Extended Playwright test fixtures with page objects and API mocking helpers.
 */

import { test as base, Page } from '@playwright/test'
import { SweepsPage } from '../pages/sweeps.page'
import { RunsPage } from '../pages/runs.page'
import { ComparePage } from '../pages/compare.page'

/**
 * Helper class for mocking API responses in E2E tests.
 * Provides methods for common API mocking patterns.
 */
export class MockApiHelper {
  constructor(private page: Page) {}

  /**
   * Mock the datasets list endpoint.
   */
  async mockDatasets(data: unknown) {
    await this.page.route('**/api/v1/datasets', (route) =>
      route.fulfill({ json: data })
    )
  }

  /**
   * Mock the tradebooks list endpoint.
   */
  async mockTradebooks(data: unknown) {
    await this.page.route('**/api/v1/tradebooks', (route) =>
      route.fulfill({ json: data })
    )
  }

  /**
   * Mock the sweeps list endpoint.
   */
  async mockSweepsList(data: unknown) {
    await this.page.route('**/api/v1/sweeps', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({ json: data })
      } else {
        route.continue()
      }
    })
  }

  /**
   * Mock sweep creation endpoint.
   */
  async mockSweepCreate(response: unknown) {
    await this.page.route('**/api/v1/sweeps', (route, request) => {
      if (request.method() === 'POST') {
        route.fulfill({ json: response })
      } else {
        route.continue()
      }
    })
  }

  /**
   * Mock sweep start endpoint.
   */
  async mockSweepStart(sweepId: string, response: unknown) {
    await this.page.route(`**/api/v1/sweeps/${sweepId}/start`, (route) =>
      route.fulfill({ json: response })
    )
  }

  /**
   * Mock sweep status with progressive responses.
   * Each call returns the next response in the array, staying on the last one.
   */
  async mockSweepProgress(sweepId: string, responses: unknown[]) {
    let callIndex = 0
    await this.page.route(`**/api/v1/sweeps/${sweepId}/status`, (route) => {
      const response = responses[Math.min(callIndex++, responses.length - 1)]
      route.fulfill({ json: response })
    })
  }

  /**
   * Mock sweep detail endpoint.
   */
  async mockSweepDetail(sweepId: string, response: unknown) {
    await this.page.route(`**/api/v1/sweeps/${sweepId}`, (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({ json: response })
      } else {
        route.continue()
      }
    })
  }

  /**
   * Mock frontier endpoint.
   */
  async mockFrontier(sweepId: string, response: unknown) {
    await this.page.route(`**/api/v1/sweeps/${sweepId}/frontier*`, (route) =>
      route.fulfill({ json: response })
    )
  }

  /**
   * Mock runs list endpoint.
   */
  async mockRunsList(data: unknown) {
    await this.page.route('**/api/v1/runs*', (route, request) => {
      if (request.method() === 'GET' && !request.url().includes('/status')) {
        route.fulfill({ json: data })
      } else {
        route.continue()
      }
    })
  }

  /**
   * Mock run creation endpoint.
   */
  async mockRunCreate(response: unknown) {
    await this.page.route('**/api/v1/runs', (route, request) => {
      if (request.method() === 'POST') {
        route.fulfill({ json: response })
      } else {
        route.continue()
      }
    })
  }

  /**
   * Mock run start endpoint.
   */
  async mockRunStart(runId: string, response: unknown) {
    await this.page.route(`**/api/v1/runs/${runId}/start`, (route) =>
      route.fulfill({ json: response })
    )
  }

  /**
   * Mock run status with progressive responses.
   */
  async mockRunProgress(runId: string, responses: unknown[]) {
    let callIndex = 0
    await this.page.route(`**/api/v1/runs/${runId}/status`, (route) => {
      const response = responses[Math.min(callIndex++, responses.length - 1)]
      route.fulfill({ json: response })
    })
  }

  /**
   * Mock dataset detail endpoint.
   */
  async mockDatasetDetail(name: string, response: unknown) {
    await this.page.route(`**/api/v1/datasets/${name}`, (route) =>
      route.fulfill({ json: response })
    )
  }
}

// Define fixture types
type Fixtures = {
  sweepsPage: SweepsPage
  runsPage: RunsPage
  comparePage: ComparePage
  mockApi: MockApiHelper
}

/**
 * Extended test with page objects and mock API helper.
 */
export const test = base.extend<Fixtures>({
  sweepsPage: async ({ page }, use) => {
    await use(new SweepsPage(page))
  },
  runsPage: async ({ page }, use) => {
    await use(new RunsPage(page))
  },
  comparePage: async ({ page }, use) => {
    await use(new ComparePage(page))
  },
  mockApi: async ({ page }, use) => {
    await use(new MockApiHelper(page))
  },
})

export { expect } from '@playwright/test'
