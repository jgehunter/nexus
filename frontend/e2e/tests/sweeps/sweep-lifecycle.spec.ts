/**
 * E2E tests for the complete sweep lifecycle:
 * Create -> Start -> Monitor Progress -> View Results -> Delete
 */

import { test, expect } from '../../fixtures/base'

test.describe('Sweep Lifecycle', () => {
  test.beforeEach(async ({ page }) => {
    // Set up API mocks BEFORE any navigation
    // Mock datasets
    await page.route('**/api/v1/datasets', (route) =>
      route.fulfill({
        json: [{ name: 'TEST_DATASET', pairs: ['EURUSD', 'GBPUSD'], dates: ['2024-01-01', '2024-01-02'] }],
      })
    )
    // Mock tradebooks
    await page.route('**/api/v1/tradebooks', (route) =>
      route.fulfill({
        json: [{ name: 'TEST_BOOK', total_trades: 1000, dates: ['2024-01-01', '2024-01-02'] }],
      })
    )
  })

  test('should create a sweep with parameter grid', async ({ page, sweepsPage }) => {
    // Mock empty sweep list initially
    await page.route('**/api/v1/sweeps', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({ json: { sweeps: [] } })
      } else if (request.method() === 'POST') {
        route.fulfill({
          json: {
            sweep_id: 'sweep-test-123',
            status: 'pending',
            config_hash: 'abc12345',
            total_configs: 4,
            message: null,
          },
        })
      } else {
        route.continue()
      }
    })

    // Mock sweep start
    await page.route('**/api/v1/sweeps/sweep-test-123/start', (route) =>
      route.fulfill({
        json: {
          sweep_id: 'sweep-test-123',
          status: 'running',
          total_configs: 4,
          completed_configs: 0,
          progress_pct: 0,
        },
      })
    )

    // Mock sweep status
    await page.route('**/api/v1/sweeps/sweep-test-123/status', (route) =>
      route.fulfill({
        json: {
          sweep_id: 'sweep-test-123',
          status: 'running',
          total_configs: 4,
          completed_configs: 1,
          progress_pct: 25,
        },
      })
    )

    // Navigate to Sweeps page
    await sweepsPage.goto()

    // Click New Sweep button
    await sweepsPage.clickNewSweep()

    // Verify create form is visible
    await expect(sweepsPage.createForm).toBeVisible()

    // Fill in the form
    await sweepsPage.selectDataset('TEST_DATASET')
    await sweepsPage.selectTradebook('TEST_BOOK')
    await sweepsPage.setName('Test Sweep')

    // Add parameter (risk_band_qty)
    await sweepsPage.addParameter('Risk Band Qty')
    await sweepsPage.setParameterValues('risk_band_qty', '1000000, 5000000')

    // Submit the form
    await sweepsPage.submitCreateForm()

    // Verify progress view appears (sweep auto-starts after creation)
    await expect(sweepsPage.progressView).toBeVisible({ timeout: 10000 })
  })

  test('should monitor sweep progress through completion', async ({ page, sweepsPage }) => {
    // Mock sweep list with a pending sweep
    await page.route('**/api/v1/sweeps?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({
          json: {
            sweeps: [
              {
                sweep_id: 'sweep-monitor-test',
                status: 'pending',
                config_hash: 'def67890',
                total_configs: 4,
                completed_configs: 0,
                failed_configs: 0,
                skipped_configs: 0,
                progress_pct: 0,
                created_at_ms: Date.now(),
                name: 'Monitor Test',
                dataset: 'TEST_DATASET',
                tradebook: 'TEST_BOOK',
              },
            ],
          },
        })
      } else {
        route.continue()
      }
    })

    // Mock sweep start
    await page.route('**/api/v1/sweeps/sweep-monitor-test/start', (route) =>
      route.fulfill({
        json: {
          sweep_id: 'sweep-monitor-test',
          status: 'running',
          total_configs: 4,
          completed_configs: 0,
          failed_configs: 0,
          skipped_configs: 0,
          progress_pct: 0,
          current_run_id: 'run-001',
          error_message: null,
        },
      })
    )

    // Mock progressive status updates
    let statusCallCount = 0
    const statusResponses = [
      {
        sweep_id: 'sweep-monitor-test',
        status: 'running',
        total_configs: 4,
        completed_configs: 1,
        failed_configs: 0,
        skipped_configs: 0,
        progress_pct: 25,
        current_run_id: 'run-002',
        error_message: null,
      },
      {
        sweep_id: 'sweep-monitor-test',
        status: 'running',
        total_configs: 4,
        completed_configs: 2,
        failed_configs: 0,
        skipped_configs: 0,
        progress_pct: 50,
        current_run_id: 'run-003',
        error_message: null,
      },
      {
        sweep_id: 'sweep-monitor-test',
        status: 'running',
        total_configs: 4,
        completed_configs: 3,
        failed_configs: 0,
        skipped_configs: 0,
        progress_pct: 75,
        current_run_id: 'run-004',
        error_message: null,
      },
      {
        sweep_id: 'sweep-monitor-test',
        status: 'completed',
        total_configs: 4,
        completed_configs: 4,
        failed_configs: 0,
        skipped_configs: 0,
        progress_pct: 100,
        current_run_id: null,
        error_message: null,
      },
    ]

    await page.route('**/api/v1/sweeps/sweep-monitor-test/status', (route) => {
      const response = statusResponses[Math.min(statusCallCount++, statusResponses.length - 1)]
      route.fulfill({ json: response })
    })

    // Navigate to Sweeps page
    await sweepsPage.goto()

    // Find and start the sweep by looking for the name displayed in the card
    const card = page.locator('.sweep-card:has-text("Monitor Test")')
    await expect(card).toBeVisible()
    await card.getByRole('button', { name: 'Start' }).click()

    // Wait for progress view
    await expect(sweepsPage.progressView).toBeVisible({ timeout: 5000 })

    // Verify progress updates (wait for completion)
    await expect(sweepsPage.progressPercentage).toContainText('100', { timeout: 15000 })

    // Verify completion status - use specific locator to avoid matching "completed" status text
    const completedStat = page.locator('.progress-stat').filter({ has: page.locator('.label:text("Completed")') })
    await expect(completedStat.locator('.value')).toContainText('4')

    // Verify View Results button appears
    await expect(sweepsPage.viewResultsButton).toBeVisible()
  })

  test('should handle partial sweep completion with failures', async ({ page, sweepsPage }) => {
    // Mock sweep list with a running sweep
    await page.route('**/api/v1/sweeps?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({
          json: {
            sweeps: [
              {
                sweep_id: 'sweep-fail-test',
                status: 'running',
                config_hash: 'fail123',
                total_configs: 4,
                completed_configs: 0,
                failed_configs: 0,
                skipped_configs: 0,
                progress_pct: 0,
                created_at_ms: Date.now(),
                name: 'Fail Test',
                dataset: 'TEST_DATASET',
                tradebook: 'TEST_BOOK',
              },
            ],
          },
        })
      } else {
        route.continue()
      }
    })

    // Mock progressive status with failures
    let statusCallCount = 0
    const statusResponses = [
      {
        sweep_id: 'sweep-fail-test',
        status: 'running',
        total_configs: 4,
        completed_configs: 1,
        failed_configs: 0,
        skipped_configs: 0,
        progress_pct: 25,
        current_run_id: 'run-002',
        error_message: null,
      },
      {
        sweep_id: 'sweep-fail-test',
        status: 'partial',
        total_configs: 4,
        completed_configs: 2,
        failed_configs: 2,
        skipped_configs: 0,
        progress_pct: 100,
        current_run_id: null,
        error_message: 'Config 3 failed: timeout',
      },
    ]

    await page.route('**/api/v1/sweeps/sweep-fail-test/status', (route) => {
      const response = statusResponses[Math.min(statusCallCount++, statusResponses.length - 1)]
      route.fulfill({ json: response })
    })

    // Navigate to Sweeps page
    await sweepsPage.goto()

    // Find the running sweep and view progress
    const card = page.locator('.sweep-card:has-text("Fail Test")')
    await expect(card).toBeVisible()
    await card.getByRole('button', { name: 'View Progress' }).click()

    // Wait for progress view
    await expect(sweepsPage.progressView).toBeVisible()

    // Wait for partial completion
    await expect(sweepsPage.failedCount).toContainText('2', { timeout: 15000 })

    // Verify error message is shown
    await expect(page.locator('.error-message')).toContainText('timeout')
  })

  test('should navigate to compare page from completed sweep', async ({ page, sweepsPage }) => {
    // Mock completed sweep
    await page.route('**/api/v1/sweeps?*', (route, request) => {
      if (request.method() === 'GET') {
        route.fulfill({
          json: {
            sweeps: [
              {
                sweep_id: 'sweep-complete',
                status: 'completed',
                config_hash: 'comp123',
                total_configs: 4,
                completed_configs: 4,
                failed_configs: 0,
                skipped_configs: 0,
                progress_pct: 100,
                created_at_ms: Date.now(),
                name: 'Complete Sweep',
                dataset: 'TEST_DATASET',
                tradebook: 'TEST_BOOK',
              },
            ],
          },
        })
      } else {
        route.continue()
      }
    })

    // Navigate to Sweeps page
    await sweepsPage.goto()

    // Find the completed sweep card by name
    const card = page.locator('.sweep-card:has-text("Complete Sweep")')
    await expect(card).toBeVisible()

    // Click View Results (should navigate to compare page)
    await card.getByRole('button', { name: 'View Results' }).click()

    // Verify navigation to compare page
    await expect(page).toHaveURL(/\/compare\?sweep=sweep-complete/)
  })

  test('should delete a sweep', async ({ page, sweepsPage }) => {
    // Track whether delete has been called
    let deleteWasCalled = false

    // Mock sweep list - returns different data before and after delete
    await page.route('**/api/v1/sweeps?*', (route, request) => {
      if (request.method() === 'GET') {
        if (deleteWasCalled) {
          // After delete, return empty list
          route.fulfill({ json: { sweeps: [] } })
        } else {
          route.fulfill({
            json: {
              sweeps: [
                {
                  sweep_id: 'sweep-delete-test',
                  status: 'completed',
                  config_hash: 'del123',
                  total_configs: 2,
                  completed_configs: 2,
                  failed_configs: 0,
                  skipped_configs: 0,
                  progress_pct: 100,
                  created_at_ms: Date.now(),
                  name: 'Delete Test',
                  dataset: 'TEST_DATASET',
                  tradebook: 'TEST_BOOK',
                },
              ],
            },
          })
        }
      } else {
        route.continue()
      }
    })

    // Mock delete endpoint
    await page.route('**/api/v1/sweeps/sweep-delete-test*', (route, request) => {
      if (request.method() === 'DELETE') {
        deleteWasCalled = true
        route.fulfill({ status: 204 })
      } else {
        route.continue()
      }
    })

    // Navigate to Sweeps page
    await sweepsPage.goto()

    // Find the sweep card by name
    const card = page.locator('.sweep-card:has-text("Delete Test")')
    await expect(card).toBeVisible()

    // Set up dialog handler before clicking delete
    page.once('dialog', (dialog) => dialog.accept())

    // Delete the sweep
    await card.getByRole('button', { name: 'Delete' }).click()

    // Verify sweep is removed from list
    await expect(card).not.toBeVisible({ timeout: 5000 })
  })
})
