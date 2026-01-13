/**
 * Page Object Model for the Compare page.
 * Encapsulates selectors and actions for frontier visualization.
 */

import { Page, Locator } from '@playwright/test'

export class ComparePage {
  readonly page: Page

  // Page header
  readonly pageTitle: Locator
  readonly pageDescription: Locator

  // Constraint filters
  readonly filterPanel: Locator
  readonly maxRiskInput: Locator
  readonly minInternalizationInput: Locator
  readonly maxDrawdownInput: Locator
  readonly clearFiltersButton: Locator

  // Scatter chart
  readonly chartSection: Locator
  readonly chartContainer: Locator
  readonly scatterPoints: Locator
  readonly chartTooltip: Locator
  readonly chartLegend: Locator

  // Configs table
  readonly tableSection: Locator
  readonly configsTable: Locator
  readonly tableHeaders: Locator
  readonly tableRows: Locator
  readonly paretoRows: Locator

  constructor(page: Page) {
    this.page = page

    // Page header
    this.pageTitle = page.locator('h1')
    this.pageDescription = page.locator('.page-description')

    // Constraint filters
    this.filterPanel = page.locator('.filter-panel')
    this.maxRiskInput = page.locator('.filter-input:has-text("Max Risk") input')
    this.minInternalizationInput = page.locator('.filter-input:has-text("Min Internalization") input')
    this.maxDrawdownInput = page.locator('.filter-input:has-text("Max Drawdown") input')
    this.clearFiltersButton = page.getByRole('button', { name: 'Clear' })

    // Scatter chart
    this.chartSection = page.locator('.frontier-chart-section')
    this.chartContainer = page.locator('.chart-container')
    this.scatterPoints = page.locator('.recharts-scatter-symbol, .recharts-symbols circle')
    this.chartTooltip = page.locator('.frontier-tooltip')
    this.chartLegend = page.locator('.chart-legend')

    // Configs table
    this.tableSection = page.locator('.table-section')
    this.configsTable = page.locator('.configs-table')
    this.tableHeaders = page.locator('.configs-table th')
    this.tableRows = page.locator('.configs-table tbody tr')
    this.paretoRows = page.locator('.configs-table tbody tr.pareto-row')
  }

  /**
   * Navigate to the Compare page for a specific sweep.
   */
  async goto(sweepId: string) {
    await this.page.goto(`/compare?sweep=${sweepId}`)
  }

  /**
   * Navigate to the Compare page without a sweep (for manual selection).
   */
  async gotoEmpty() {
    await this.page.goto('/compare')
  }

  /**
   * Set the maximum risk score filter.
   */
  async setMaxRisk(value: number) {
    await this.maxRiskInput.fill(String(value))
  }

  /**
   * Set the minimum internalization ratio filter.
   */
  async setMinInternalization(value: number) {
    await this.minInternalizationInput.fill(String(value))
  }

  /**
   * Set the maximum drawdown filter.
   */
  async setMaxDrawdown(value: number) {
    await this.maxDrawdownInput.fill(String(value))
  }

  /**
   * Clear all filters.
   */
  async clearFilters() {
    await this.clearFiltersButton.click()
  }

  /**
   * Get the number of scatter points on the chart.
   */
  async getScatterPointCount(): Promise<number> {
    return await this.scatterPoints.count()
  }

  /**
   * Hover over a scatter point by index.
   */
  async hoverScatterPoint(index: number) {
    await this.scatterPoints.nth(index).hover()
  }

  /**
   * Check if the tooltip is visible.
   */
  async isTooltipVisible(): Promise<boolean> {
    return await this.chartTooltip.isVisible()
  }

  /**
   * Get tooltip content.
   */
  async getTooltipContent(): Promise<string> {
    return (await this.chartTooltip.textContent()) || ''
  }

  /**
   * Sort the table by clicking a column header.
   */
  async sortByColumn(columnName: string) {
    await this.page.locator(`th:text("${columnName}")`).click()
  }

  /**
   * Get the sort indicator for a column.
   */
  async getSortIndicator(columnName: string): Promise<string> {
    const header = this.page.locator(`th:text("${columnName}")`)
    const text = (await header.textContent()) || ''
    if (text.includes('\u25B2')) return 'asc'
    if (text.includes('\u25BC')) return 'desc'
    return 'none'
  }

  /**
   * Get the number of table rows.
   */
  async getTableRowCount(): Promise<number> {
    return await this.tableRows.count()
  }

  /**
   * Get the number of Pareto-optimal rows.
   */
  async getParetoRowCount(): Promise<number> {
    return await this.paretoRows.count()
  }

  /**
   * Get a specific cell value by row index and column name.
   */
  async getCellValue(rowIndex: number, columnIndex: number): Promise<string> {
    const cell = this.tableRows.nth(rowIndex).locator('td').nth(columnIndex)
    return (await cell.textContent()) || ''
  }

  /**
   * Get all values from a specific column.
   */
  async getColumnValues(columnIndex: number): Promise<string[]> {
    const cells = this.tableRows.locator(`td:nth-child(${columnIndex + 1})`)
    const count = await cells.count()
    const values: string[] = []
    for (let i = 0; i < count; i++) {
      values.push((await cells.nth(i).textContent()) || '')
    }
    return values
  }

  /**
   * Wait for the chart to load.
   */
  async waitForChartLoad(timeout = 10000) {
    await this.scatterPoints.first().waitFor({ state: 'visible', timeout })
  }

  /**
   * Wait for the table to load.
   */
  async waitForTableLoad(timeout = 10000) {
    await this.tableRows.first().waitFor({ state: 'visible', timeout })
  }

  /**
   * Take a screenshot of the chart section.
   */
  async screenshotChart(name: string) {
    await this.chartSection.screenshot({ path: `screenshots/${name}.png` })
  }

  /**
   * Check if a config hash is in the table.
   */
  async hasConfigHash(hash: string): Promise<boolean> {
    const row = this.page.locator(`.configs-table tr:has-text("${hash}")`)
    return await row.isVisible()
  }

  /**
   * Check if a config is marked as Pareto optimal.
   */
  async isConfigPareto(hash: string): Promise<boolean> {
    const row = this.page.locator(`.configs-table tr:has-text("${hash}")`)
    const paretoCell = row.locator('.pareto-cell')
    const text = await paretoCell.textContent()
    return text?.includes('\u2713') || text?.includes('Yes') || false
  }
}
