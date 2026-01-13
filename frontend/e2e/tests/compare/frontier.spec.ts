/**
 * E2E tests for the Compare page (Efficient Frontier visualization).
 * Tests scatter plot, constraint filters, and table sorting.
 */

import { test, expect } from '../../fixtures/base'

// Mock frontier data for tests
const mockFrontierData = {
  sweep_id: 'sweep-frontier-test',
  configs: [
    {
      run_id: 'run-1',
      config_hash: 'cfg001',
      parameters: { risk_band_qty: 1000000 },
      pnl_per_volume_bps: 2.5,
      inventory_risk_score: 0.3,
      max_drawdown_pct: 5.2,
      internalization_ratio: 0.85,
      risk_adjusted_return: 1.8,
      is_pareto_optimal: true,
      total_client_volume: 50000000,
      hedge_count: 120,
    },
    {
      run_id: 'run-2',
      config_hash: 'cfg002',
      parameters: { risk_band_qty: 5000000 },
      pnl_per_volume_bps: 1.8,
      inventory_risk_score: 0.15,
      max_drawdown_pct: 2.1,
      internalization_ratio: 0.72,
      risk_adjusted_return: 2.1,
      is_pareto_optimal: true,
    },
    {
      run_id: 'run-3',
      config_hash: 'cfg003',
      parameters: { risk_band_qty: 3000000 },
      pnl_per_volume_bps: 2.0,
      inventory_risk_score: 0.25,
      max_drawdown_pct: 4.0,
      internalization_ratio: 0.78,
      risk_adjusted_return: 1.5,
      is_pareto_optimal: false,
    },
    {
      run_id: 'run-4',
      config_hash: 'cfg004',
      parameters: { risk_band_qty: 10000000 },
      pnl_per_volume_bps: 1.2,
      inventory_risk_score: 0.1,
      max_drawdown_pct: 1.5,
      internalization_ratio: 0.65,
      risk_adjusted_return: 2.5,
      is_pareto_optimal: true,
    },
  ],
  total_configs: 4,
  filtered_count: 4,
  pareto_count: 3,
  x_axis: 'inventory_risk_score',
  y_axis: 'pnl_per_volume_bps',
}

test.describe('Compare Page - Scatter Plot', () => {
  test.beforeEach(async ({ mockApi }) => {
    // Mock sweep detail
    await mockApi.mockSweepDetail('sweep-frontier-test', {
      sweep_id: 'sweep-frontier-test',
      status: 'completed',
      config: { name: 'Test Sweep', dataset: 'DS1', tradebook: 'TB1' },
      total_configs: 4,
      completed_configs: 4,
      failed_configs: 0,
      skipped_configs: 0,
    })

    // Mock frontier data
    await mockApi.mockFrontier('sweep-frontier-test', mockFrontierData)
  })

  test('should render scatter chart with data points', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')

    // Wait for chart to load
    await comparePage.waitForChartLoad()

    // Verify correct number of scatter points
    const pointCount = await comparePage.getScatterPointCount()
    expect(pointCount).toBe(4)
  })

  test('should show tooltip on point hover', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')
    await comparePage.waitForChartLoad()

    // Hover over first scatter point
    await comparePage.hoverScatterPoint(0)

    // Verify tooltip appears
    expect(await comparePage.isTooltipVisible()).toBe(true)

    // Verify tooltip contains expected data
    const tooltipContent = await comparePage.getTooltipContent()
    expect(tooltipContent).toContain('cfg')
  })

  test('should display chart legend', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')
    await comparePage.waitForChartLoad()

    // Verify legend is visible
    await expect(comparePage.chartLegend).toBeVisible()

    // Verify legend contains expected items
    await expect(comparePage.chartLegend).toContainText(/Internalization|Pareto/i)
  })
})

test.describe('Compare Page - Constraint Filters', () => {
  test.beforeEach(async ({ page, mockApi }) => {
    await mockApi.mockSweepDetail('sweep-frontier-test', {
      sweep_id: 'sweep-frontier-test',
      status: 'completed',
      config: { name: 'Test Sweep', dataset: 'DS1', tradebook: 'TB1' },
      total_configs: 4,
      completed_configs: 4,
    })

    // Initial mock returns all configs
    await mockApi.mockFrontier('sweep-frontier-test', mockFrontierData)

    // Mock filtered responses based on query params
    await page.route('**/api/v1/sweeps/sweep-frontier-test/frontier*max_risk*', (route) => {
      // Return filtered data when max_risk filter is applied
      route.fulfill({
        json: {
          ...mockFrontierData,
          configs: mockFrontierData.configs.filter((c) => c.inventory_risk_score < 0.2),
          filtered_count: 2,
        },
      })
    })
  })

  test('should apply max risk filter', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')
    await comparePage.waitForTableLoad()

    // Get initial row count
    const initialCount = await comparePage.getTableRowCount()
    expect(initialCount).toBe(4)

    // Apply max risk filter
    await comparePage.setMaxRisk(0.2)

    // Wait for table to update (filters trigger API call)
    await comparePage.page.waitForTimeout(500)

    // Verify filtered results
    const filteredCount = await comparePage.getTableRowCount()
    expect(filteredCount).toBe(2)
  })

  test('should clear all filters', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')
    await comparePage.waitForTableLoad()

    // Apply a filter
    await comparePage.setMaxRisk(0.2)
    await comparePage.page.waitForTimeout(500)

    // Clear filters
    await comparePage.clearFilters()

    // Verify filter inputs are cleared
    await expect(comparePage.maxRiskInput).toHaveValue('')
  })
})

test.describe('Compare Page - Table Sorting', () => {
  test.beforeEach(async ({ mockApi }) => {
    await mockApi.mockSweepDetail('sweep-frontier-test', {
      sweep_id: 'sweep-frontier-test',
      status: 'completed',
      config: { name: 'Test Sweep', dataset: 'DS1', tradebook: 'TB1' },
    })
    await mockApi.mockFrontier('sweep-frontier-test', mockFrontierData)
  })

  test('should sort table by PnL/Volume column', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')
    await comparePage.waitForTableLoad()

    // Click PnL/Vol header to sort descending (higher is better)
    await comparePage.sortByColumn('PnL/Vol')

    // Verify sort indicator
    const sortDir = await comparePage.getSortIndicator('PnL/Vol')
    expect(sortDir).toBe('desc')

    // Click again to toggle to ascending
    await comparePage.sortByColumn('PnL/Vol')

    const newSortDir = await comparePage.getSortIndicator('PnL/Vol')
    expect(newSortDir).toBe('asc')
  })

  test('should sort table by Risk Score column (ascending by default)', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')
    await comparePage.waitForTableLoad()

    // Click Risk Score header (lower is better, so ascending)
    await comparePage.sortByColumn('Risk Score')

    const sortDir = await comparePage.getSortIndicator('Risk Score')
    expect(sortDir).toBe('asc')
  })

  test('should highlight Pareto-optimal rows', async ({ comparePage }) => {
    await comparePage.goto('sweep-frontier-test')
    await comparePage.waitForTableLoad()

    // Verify Pareto rows are highlighted
    const paretoCount = await comparePage.getParetoRowCount()
    expect(paretoCount).toBe(3) // Based on mock data
  })
})

test.describe('Compare Page - Error States', () => {
  test('should show error when no sweep ID provided', async ({ comparePage }) => {
    await comparePage.gotoEmpty()

    // Verify error message is shown
    await expect(comparePage.page.locator('.error-banner')).toContainText(/No sweep ID|Select a sweep/i)
  })

  test('should show error for invalid sweep ID', async ({ page, comparePage }) => {
    // Mock 404 response
    await page.route('**/api/v1/sweeps/invalid-sweep*', (route) =>
      route.fulfill({
        status: 404,
        json: { detail: 'Sweep not found' },
      })
    )

    await comparePage.goto('invalid-sweep')

    // Verify error message
    await expect(page.locator('.error-banner')).toBeVisible()
  })
})
