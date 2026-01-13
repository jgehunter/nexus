/**
 * Smoke tests for basic navigation and health.
 * These tests verify that the app loads and basic navigation works.
 */

import { test, expect } from '@playwright/test'

test.describe('Smoke Tests - Navigation', () => {
  test('should load the dashboard', async ({ page }) => {
    await page.goto('/')

    // Verify page title or main heading
    await expect(page.locator('h1')).toBeVisible()
  })

  test('should navigate to Sweeps page', async ({ page }) => {
    await page.goto('/')

    // Click Sweeps nav link
    await page.getByRole('link', { name: 'Sweeps' }).click()

    // Verify URL
    await expect(page).toHaveURL(/\/sweeps/)

    // Verify page content
    await expect(page.locator('h1')).toContainText(/Sweep/i)
  })

  test('should navigate to Runs page', async ({ page }) => {
    await page.goto('/')

    // Click Runs nav link
    await page.getByRole('link', { name: 'Runs' }).click()

    // Verify URL
    await expect(page).toHaveURL(/\/runs/)
  })

  test('should navigate to Compare page', async ({ page }) => {
    await page.goto('/')

    // Click Compare nav link
    await page.getByRole('link', { name: 'Compare' }).click()

    // Verify URL
    await expect(page).toHaveURL(/\/compare/)
  })

  test('should navigate to Datasets page', async ({ page }) => {
    await page.goto('/')

    // Click Datasets nav link
    await page.getByRole('link', { name: 'Datasets' }).click()

    // Verify URL
    await expect(page).toHaveURL(/\/datasets/)
  })

  test('should navigate to Trade Books page', async ({ page }) => {
    await page.goto('/')

    // Click Trade Books nav link
    await page.getByRole('link', { name: 'Trade Books' }).click()

    // Verify URL
    await expect(page).toHaveURL(/\/tradebooks/)
  })

  test('should show connection status indicator', async ({ page }) => {
    await page.goto('/')

    // Verify connection dot is present
    await expect(page.locator('.connection-dot')).toBeVisible()
  })
})

test.describe('Smoke Tests - Page Load', () => {
  test('Sweeps page loads without errors', async ({ page }) => {
    await page.goto('/sweeps')

    // Should not have any console errors
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    // Wait for page to stabilize
    await page.waitForLoadState('networkidle')

    // Verify no critical errors (allow some third-party errors)
    const criticalErrors = errors.filter(
      (e) => !e.includes('favicon') && !e.includes('third-party')
    )
    expect(criticalErrors).toHaveLength(0)
  })

  test('Runs page loads without errors', async ({ page }) => {
    await page.goto('/runs')
    await page.waitForLoadState('networkidle')
    // Basic load test - page should render
    await expect(page.locator('body')).toBeVisible()
  })

  test('Compare page loads without errors', async ({ page }) => {
    await page.goto('/compare')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('body')).toBeVisible()
  })
})
