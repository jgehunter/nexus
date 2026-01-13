/**
 * Page Object Model for the Sweeps page.
 * Encapsulates selectors and actions for sweep management.
 */

import { Page, Locator } from '@playwright/test'

export class SweepsPage {
  readonly page: Page

  // Main view selectors
  readonly newSweepButton: Locator
  readonly sweepList: Locator
  readonly createForm: Locator
  readonly progressView: Locator

  // Form elements
  readonly datasetSelect: Locator
  readonly tradebookSelect: Locator
  readonly nameInput: Locator
  readonly parameterButtons: Locator
  readonly createButton: Locator
  readonly cancelButton: Locator

  // Progress elements
  readonly progressBar: Locator
  readonly progressPercentage: Locator
  readonly statusBadge: Locator
  readonly completedCount: Locator
  readonly failedCount: Locator
  readonly skippedCount: Locator
  readonly viewResultsButton: Locator
  readonly backToListButton: Locator

  constructor(page: Page) {
    this.page = page

    // Main view selectors
    this.newSweepButton = page.getByRole('button', { name: 'New Sweep' })
    this.sweepList = page.locator('.sweep-list')
    this.createForm = page.locator('.sweep-create-form')
    this.progressView = page.locator('.sweep-progress-view')

    // Form selectors
    this.datasetSelect = page.locator('select#dataset, [data-testid="dataset-select"]')
    this.tradebookSelect = page.locator('select#tradebook, [data-testid="tradebook-select"]')
    this.nameInput = page.locator('input#name, [data-testid="sweep-name-input"]')
    this.parameterButtons = page.locator('.param-buttons button')
    this.createButton = page.getByRole('button', { name: 'Create Sweep' })
    this.cancelButton = page.getByRole('button', { name: 'Cancel' })

    // Progress selectors
    this.progressBar = page.locator('.progress-bar-large .progress-fill')
    this.progressPercentage = page.locator('.progress-pct, [data-testid="progress-pct"]')
    this.statusBadge = page.locator('[data-testid="sweep-status"], .progress-stat .value').first()
    // Use label selector to get the value after the "Completed" label specifically
    this.completedCount = page.locator('[data-testid="completed-count"], .progress-stat .label:text("Completed") + .value')
    this.failedCount = page.locator('[data-testid="failed-count"], .progress-stat:has-text("Failed") .value')
    this.skippedCount = page.locator('[data-testid="skipped-count"], .progress-stat:has-text("Skipped") .value')
    this.viewResultsButton = page.getByRole('button', { name: 'View Results' })
    this.backToListButton = page.getByRole('button', { name: 'Back to List' })
  }

  /**
   * Navigate to the Sweeps page.
   */
  async goto() {
    await this.page.goto('/sweeps')
  }

  /**
   * Click the New Sweep button to open the create form.
   */
  async clickNewSweep() {
    await this.newSweepButton.click()
    await this.createForm.waitFor({ state: 'visible' })
  }

  /**
   * Select a dataset from the dropdown.
   */
  async selectDataset(name: string) {
    await this.datasetSelect.selectOption(name)
  }

  /**
   * Select a tradebook from the dropdown.
   */
  async selectTradebook(name: string) {
    await this.tradebookSelect.selectOption(name)
  }

  /**
   * Set the sweep name.
   */
  async setName(name: string) {
    await this.nameInput.fill(name)
  }

  /**
   * Add a parameter to the sweep by clicking its button.
   */
  async addParameter(paramName: string) {
    await this.page.getByRole('button', { name: new RegExp(`\\+ ${paramName}`, 'i') }).click()
  }

  /**
   * Set parameter values (comma-separated for list mode).
   */
  async setParameterValues(paramName: string, values: string) {
    const paramEntry = this.page.locator(`.param-entry:has-text("${paramName}")`)
    await paramEntry.locator('input[type="text"]').fill(values)
  }

  /**
   * Toggle parameter mode between list and range.
   */
  async setParameterMode(paramName: string, mode: 'list' | 'range') {
    const paramEntry = this.page.locator(`.param-entry:has-text("${paramName}")`)
    await paramEntry.locator(`input[value="${mode}"]`).check()
  }

  /**
   * Set range parameter values (min, max, step).
   */
  async setParameterRange(paramName: string, min: number, max: number, step: number) {
    const paramEntry = this.page.locator(`.param-entry:has-text("${paramName}")`)
    await paramEntry.locator('input[placeholder*="Min"]').fill(String(min))
    await paramEntry.locator('input[placeholder*="Max"]').fill(String(max))
    await paramEntry.locator('input[placeholder*="Step"]').fill(String(step))
  }

  /**
   * Submit the create form.
   */
  async submitCreateForm() {
    await this.createButton.click()
  }

  /**
   * Wait for the progress view to show completion status.
   */
  async waitForProgressComplete(timeout = 60000) {
    await this.page.waitForFunction(
      () => {
        const statusEl = document.querySelector('[data-testid="sweep-status"], .progress-stat .value')
        const text = statusEl?.textContent?.toLowerCase()
        return text === 'completed' || text === 'partial'
      },
      { timeout }
    )
  }

  /**
   * Get the current progress percentage.
   */
  async getProgressPercentage(): Promise<number> {
    const text = await this.progressPercentage.textContent()
    return parseFloat(text?.replace('%', '') || '0')
  }

  /**
   * Get a sweep card by its ID.
   */
  getSweepCard(sweepId: string): Locator {
    return this.page.locator(`.sweep-card:has-text("${sweepId}")`)
  }

  /**
   * Start a sweep from its card.
   */
  async startSweep(sweepId: string) {
    const card = this.getSweepCard(sweepId)
    await card.getByRole('button', { name: 'Start' }).click()
  }

  /**
   * View progress of a running sweep.
   */
  async viewProgress(sweepId: string) {
    const card = this.getSweepCard(sweepId)
    await card.getByRole('button', { name: /View Progress|Monitor/i }).click()
  }

  /**
   * Delete a sweep (with confirmation).
   */
  async deleteSweep(sweepId: string) {
    const card = this.getSweepCard(sweepId)
    this.page.once('dialog', (dialog) => dialog.accept())
    await card.getByRole('button', { name: 'Delete' }).click()
  }

  /**
   * Click View Results button.
   */
  async clickViewResults() {
    await this.viewResultsButton.click()
  }

  /**
   * Click Back to List button.
   */
  async clickBackToList() {
    await this.backToListButton.click()
  }
}
