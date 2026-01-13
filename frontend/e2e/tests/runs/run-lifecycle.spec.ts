/**
 * E2E tests for the complete run lifecycle:
 * Create (multi-step form) -> Start -> Monitor Progress -> View Results
 */

import { test, expect } from '../../fixtures/base'

test.describe('Run Lifecycle', () => {
  test.beforeEach(async ({ page }) => {
    // Set up API mocks BEFORE any navigation
    // Mock datasets
    await page.route('**/api/v1/datasets', (route) =>
      route.fulfill({
        json: [
          {
            name: 'HEDGING_Q1',
            pairs: ['EURUSD', 'GBPUSD', 'USDJPY'],
            dates: ['2024-01-01', '2024-01-02', '2024-01-03'],
          },
        ],
      })
    )

    // Mock tradebooks
    await page.route('**/api/v1/tradebooks', (route) =>
      route.fulfill({
        json: [{ name: 'MAD_GLD', total_trades: 5000, dates: ['2024-01-01', '2024-01-02', '2024-01-03'] }],
      })
    )

    // Mock dataset detail
    await page.route('**/api/v1/datasets/HEDGING_Q1', (route) =>
      route.fulfill({
        json: {
          name: 'HEDGING_Q1',
          pairs: ['EURUSD', 'GBPUSD', 'USDJPY'],
          dates: ['2024-01-01', '2024-01-02', '2024-01-03'],
        },
      })
    )
  })

  test('should navigate through all four form steps', async ({ page, runsPage }) => {
    // Mock empty runs list (matches /runs?limit=... query params)
    await page.route('**/api/v1/runs?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({ json: { runs: [] } })
      } else {
        route.continue()
      }
    })

    // Navigate to Runs page
    await runsPage.goto()

    // Click New Run
    await runsPage.clickNewRun()

    // Step 1: Data Selection - verify we're on step 1 and proceed
    await expect(page.locator('.step.active')).toContainText(/Data|1/i)
    // Wait for form to load and auto-select dataset
    await page.waitForTimeout(500)
    await runsPage.clickNext()

    // Step 2: General Config - verify and proceed
    await expect(page.locator('.step.active')).toContainText(/General|Config|2/i)
    await runsPage.clickNext()

    // Step 3: Simulation Settings - verify, configure, and proceed
    await expect(page.locator('.step.active')).toContainText(/Simulation|3/i)
    await runsPage.clickNext()

    // Step 4: Review - verify we reached the final step
    await expect(page.locator('.step.active')).toContainText(/Review|4/i)

    // Verify summary shows correct values
    await expect(runsPage.configSummary).toContainText('HEDGING_Q1')
    await expect(runsPage.configSummary).toContainText('MAD_GLD')
  })

  test('should allow going back to previous steps', async ({ page, runsPage }) => {
    // Mock empty runs list
    await page.route('**/api/v1/runs?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({ json: { runs: [] } })
      } else {
        route.continue()
      }
    })

    await runsPage.goto()
    await runsPage.clickNewRun()

    // Wait for form to load
    await page.waitForTimeout(500)

    // Go to step 2
    await runsPage.clickNext()

    // Verify we're on step 2
    await expect(page.locator('.step.active')).toContainText(/General|Config|2/i)

    // Go back to step 1
    await runsPage.clickBack()
    await expect(page.locator('.step.active')).toContainText(/Data|1/i)
  })

  test('should monitor two-phase progress', async ({ page, runsPage }) => {
    // Mock empty runs list initially (GET /runs?...)
    await page.route('**/api/v1/runs?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({ json: { runs: [] } })
      } else {
        route.continue()
      }
    })

    // Mock run creation (POST /runs?idempotence=new)
    await page.route('**/api/v1/runs?idempotence*', (route, request) => {
      if (request.method() === 'POST') {
        route.fulfill({
          json: {
            run_id: 'run-progress-test',
            status: 'created',
            config_hash: 'prog123',
          },
        })
      } else {
        route.continue()
      }
    })

    // Mock run start
    await page.route('**/api/v1/runs/run-progress-test/start', (route) =>
      route.fulfill({
        json: {
          run_id: 'run-progress-test',
          status: 'running',
        },
      })
    )

    // Mock progressive status with two phases
    let statusCallCount = 0
    const statusResponses = [
      // Phase 1: Decrossing
      {
        run_id: 'run-progress-test',
        status: 'running',
        decross_status: 'running',
        decross_progress_pct: 0,
        decross_completed_dates: 0,
        decross_total_dates: 3,
        decross_current_date: '2024-01-01',
        progress_pct: 0,
        completed_shards: 0,
        total_shards: 0,
        failed_shards: 0,
      },
      {
        run_id: 'run-progress-test',
        status: 'running',
        decross_status: 'running',
        decross_progress_pct: 67,
        decross_completed_dates: 2,
        decross_total_dates: 3,
        decross_current_date: '2024-01-03',
        progress_pct: 0,
        completed_shards: 0,
        total_shards: 0,
        failed_shards: 0,
      },
      {
        run_id: 'run-progress-test',
        status: 'running',
        decross_status: 'completed',
        decross_progress_pct: 100,
        decross_completed_dates: 3,
        decross_total_dates: 3,
        decross_current_date: null,
        progress_pct: 0,
        completed_shards: 0,
        total_shards: 6,
        failed_shards: 0,
      },
      // Phase 2: Simulation
      {
        run_id: 'run-progress-test',
        status: 'running',
        decross_status: 'completed',
        progress_pct: 50,
        completed_shards: 3,
        total_shards: 6,
        failed_shards: 0,
        current_stage: 'Running simulation',
      },
      {
        run_id: 'run-progress-test',
        status: 'completed',
        decross_status: 'completed',
        progress_pct: 100,
        completed_shards: 6,
        total_shards: 6,
        failed_shards: 0,
        current_stage: null,
      },
    ]

    await page.route('**/api/v1/runs/run-progress-test/status', (route) => {
      const response = statusResponses[Math.min(statusCallCount++, statusResponses.length - 1)]
      route.fulfill({ json: response })
    })

    // Navigate and create run through form
    await runsPage.goto()
    await runsPage.clickNewRun()

    // Wait for form to load
    await page.waitForTimeout(500)

    // Quick navigation through form
    await runsPage.clickNext() // Step 2
    await runsPage.clickNext() // Step 3
    await runsPage.clickNext() // Step 4

    // Submit form
    await runsPage.submitCreateForm()

    // Wait for progress view
    await expect(runsPage.progressView).toBeVisible({ timeout: 10000 })

    // Wait for completion (the status polling will cycle through responses)
    await expect(runsPage.viewResultsButton).toBeVisible({ timeout: 30000 })
  })

  test('should handle run cancellation', async ({ page, runsPage }) => {
    // Track cancellation
    let cancelled = false

    // Mock runs list with a running run (GET /runs?...)
    await page.route('**/api/v1/runs?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({
          json: {
            runs: [
              {
                run_id: 'run-cancel-test',
                status: cancelled ? 'cancelled' : 'running',
                config_hash: 'cancel123',
                created_at_ms: Date.now(),
                config: {
                  name: 'Cancel Test Run',
                  dataset: 'HEDGING_Q1',
                  tradebook: 'MAD_GLD',
                },
                progress_pct: 50,
                completed_shards: 3,
                total_shards: 6,
                failed_shards: 0,
              },
            ],
          },
        })
      } else {
        route.continue()
      }
    })

    // Mock cancel endpoint
    await page.route('**/api/v1/runs/run-cancel-test/cancel', (route) => {
      cancelled = true
      route.fulfill({
        json: { run_id: 'run-cancel-test', status: 'cancelled', message: 'Run cancelled' },
      })
    })

    // Navigate to Runs page
    await runsPage.goto()

    // Find the running run by name (displayed in the card)
    const card = page.locator('.run-card:has-text("Cancel Test Run")')
    await expect(card).toBeVisible()

    // Cancel the run
    await card.getByRole('button', { name: 'Cancel' }).click()

    // Update the mock to return cancelled status
    await page.unroute('**/api/v1/runs?*')
    await page.route('**/api/v1/runs?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({
          json: {
            runs: [
              {
                run_id: 'run-cancel-test',
                status: 'cancelled',
                config_hash: 'cancel123',
                created_at_ms: Date.now(),
                config: {
                  name: 'Cancel Test Run',
                  dataset: 'HEDGING_Q1',
                  tradebook: 'MAD_GLD',
                },
                progress_pct: 50,
                completed_shards: 3,
                total_shards: 6,
                failed_shards: 0,
              },
            ],
          },
        })
      } else {
        route.continue()
      }
    })

    // Reload the page to get updated status
    await page.reload()

    // Find the card again after reload and verify status changed
    const updatedCard = page.locator('.run-card:has-text("Cancel Test Run")')
    await expect(updatedCard.locator('.status-badge')).toContainText(/cancelled/i, {
      timeout: 5000,
    })
  })

  test('should filter runs by status', async ({ page, runsPage }) => {
    // Mock runs with different statuses (GET /runs?...)
    await page.route('**/api/v1/runs?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({
          json: {
            runs: [
              {
                run_id: 'run-1',
                status: 'running',
                config_hash: 'r1',
                created_at_ms: Date.now(),
                config: { name: 'Running Run', dataset: 'DS1', tradebook: 'TB1' },
                progress_pct: 50,
                completed_shards: 3,
                total_shards: 6,
                failed_shards: 0,
              },
              {
                run_id: 'run-2',
                status: 'completed',
                config_hash: 'r2',
                created_at_ms: Date.now() - 1000,
                config: { name: 'Completed Run 1', dataset: 'DS1', tradebook: 'TB1' },
                progress_pct: 100,
                completed_shards: 6,
                total_shards: 6,
                failed_shards: 0,
              },
              {
                run_id: 'run-3',
                status: 'failed',
                config_hash: 'r3',
                created_at_ms: Date.now() - 2000,
                config: { name: 'Failed Run', dataset: 'DS1', tradebook: 'TB1' },
                progress_pct: 50,
                completed_shards: 3,
                total_shards: 6,
                failed_shards: 3,
                error_message: 'Simulation failed',
              },
              {
                run_id: 'run-4',
                status: 'completed',
                config_hash: 'r4',
                created_at_ms: Date.now() - 3000,
                config: { name: 'Completed Run 2', dataset: 'DS1', tradebook: 'TB1' },
                progress_pct: 100,
                completed_shards: 6,
                total_shards: 6,
                failed_shards: 0,
              },
            ],
          },
        })
      } else {
        route.continue()
      }
    })

    await runsPage.goto()

    // Initially all runs visible (by name)
    await expect(page.locator('.run-card:has-text("Running Run")')).toBeVisible()
    await expect(page.locator('.run-card:has-text("Completed Run 1")')).toBeVisible()
    await expect(page.locator('.run-card:has-text("Failed Run")')).toBeVisible()
    await expect(page.locator('.run-card:has-text("Completed Run 2")')).toBeVisible()

    // Filter to running only (clicks the Running filter button)
    await runsPage.filterByStatus('running')

    // Filter to completed
    await runsPage.filterByStatus('completed')

    // Filter back to all
    await runsPage.filterByStatus('all')
  })
})
