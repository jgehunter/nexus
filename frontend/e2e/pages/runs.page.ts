/**
 * Page Object Model for the Runs page.
 * Encapsulates selectors and actions for run management.
 */

import { Page, Locator } from '@playwright/test'

export class RunsPage {
  readonly page: Page

  // Main view selectors
  readonly newRunButton: Locator
  readonly runList: Locator
  readonly createForm: Locator
  readonly progressView: Locator

  // Filter tabs
  readonly filterAll: Locator
  readonly filterRunning: Locator
  readonly filterCompleted: Locator
  readonly filterFailed: Locator

  // Multi-step form navigation
  readonly nextButton: Locator
  readonly backButton: Locator
  readonly createAndStartButton: Locator

  // Step 1: Data Selection
  readonly datasetSelect: Locator
  readonly tradebookSelect: Locator
  readonly startDateSelect: Locator
  readonly endDateSelect: Locator

  // Step 2: General Config
  readonly directPairsCheckboxes: Locator

  // Step 3: Simulation Settings
  readonly hedgePolicyAggressive: Locator
  readonly hedgePolicyPassive: Locator
  readonly hedgeModeFull: Locator
  readonly hedgeModePartial: Locator
  readonly riskBandQtyInput: Locator
  readonly reportingCurrencySelect: Locator

  // Step 4: Review
  readonly configSummary: Locator
  readonly runNameInput: Locator

  // Progress view elements
  readonly decrossPhase: Locator
  readonly simulationPhase: Locator
  readonly decrossProgressBar: Locator
  readonly simulationProgressBar: Locator
  readonly progressPercentage: Locator
  readonly elapsedTime: Locator
  readonly statusBadge: Locator
  readonly currentStage: Locator
  readonly completionMessage: Locator
  readonly viewResultsButton: Locator
  readonly cancelRunButton: Locator

  constructor(page: Page) {
    this.page = page

    // Main view selectors
    this.newRunButton = page.getByRole('button', { name: 'New Run' })
    this.runList = page.locator('.run-list')
    this.createForm = page.locator('.run-create-form, .create-run-form')
    this.progressView = page.locator('.run-progress-view, .run-progress')

    // Filter tabs
    this.filterAll = page.getByRole('button', { name: 'All' })
    this.filterRunning = page.getByRole('button', { name: 'Running' })
    this.filterCompleted = page.getByRole('button', { name: 'Completed' })
    this.filterFailed = page.getByRole('button', { name: 'Failed' })

    // Form navigation
    this.nextButton = page.getByRole('button', { name: 'Next' })
    this.backButton = page.getByRole('button', { name: 'Back' })
    this.createAndStartButton = page.getByRole('button', { name: /Create.*Start|Start Run/i })

    // Step 1: Data Selection
    this.datasetSelect = page.locator('select#dataset, [data-testid="dataset-select"]')
    this.tradebookSelect = page.locator('select#tradebook, [data-testid="tradebook-select"]')
    this.startDateSelect = page.locator('select#startDate, [data-testid="start-date-select"]')
    this.endDateSelect = page.locator('select#endDate, [data-testid="end-date-select"]')

    // Step 2: General Config
    this.directPairsCheckboxes = page.locator('.direct-pairs-section input[type="checkbox"]')

    // Step 3: Simulation Settings
    this.hedgePolicyAggressive = page.locator('input[value="aggressive"], [data-testid="hedge-policy-aggressive"]')
    this.hedgePolicyPassive = page.locator('input[value="passive"], [data-testid="hedge-policy-passive"]')
    this.hedgeModeFull = page.locator('input[value="full"], [data-testid="hedge-mode-full"]')
    this.hedgeModePartial = page.locator('input[value="partial"], [data-testid="hedge-mode-partial"]')
    this.riskBandQtyInput = page.locator('input#riskBandQty, [data-testid="risk-band-qty"]')
    this.reportingCurrencySelect = page.locator('select#reportingCurrency, [data-testid="reporting-currency"]')

    // Step 4: Review
    this.configSummary = page.locator('.config-summary')
    this.runNameInput = page.locator('input#name, [data-testid="run-name-input"]')

    // Progress view
    this.decrossPhase = page.locator('[data-testid="decross-phase"], h4:text("Decrossing")')
    this.simulationPhase = page.locator('[data-testid="simulation-phase"], h4:text("Simulation")')
    this.decrossProgressBar = page.locator('.decross-fill, [data-testid="decross-progress"]')
    this.simulationProgressBar = page.locator('.simulation-fill, [data-testid="simulation-progress"]')
    this.progressPercentage = page.locator('.progress-pct, [data-testid="progress-pct"]')
    this.elapsedTime = page.locator('.elapsed-time, [data-testid="elapsed-time"]')
    this.statusBadge = page.locator('[data-testid="run-status"], .status-badge')
    this.currentStage = page.locator('.current-stage, [data-testid="current-stage"]')
    this.completionMessage = page.locator('.completion-message')
    this.viewResultsButton = page.getByRole('button', { name: 'View Results' })
    this.cancelRunButton = page.getByRole('button', { name: 'Cancel Run' })
  }

  /**
   * Navigate to the Runs page.
   */
  async goto() {
    await this.page.goto('/runs')
  }

  /**
   * Click the New Run button to start the creation form.
   */
  async clickNewRun() {
    await this.newRunButton.click()
  }

  /**
   * Click the Next button to advance to the next step.
   */
  async clickNext() {
    await this.nextButton.click()
  }

  /**
   * Click the Back button to go to the previous step.
   */
  async clickBack() {
    await this.backButton.click()
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
   * Select the start date.
   */
  async selectStartDate(date: string) {
    await this.startDateSelect.selectOption(date)
  }

  /**
   * Select the end date.
   */
  async selectEndDate(date: string) {
    await this.endDateSelect.selectOption(date)
  }

  /**
   * Toggle a direct pair checkbox.
   */
  async toggleDirectPair(pair: string) {
    await this.page.locator(`input[type="checkbox"]:near(:text("${pair}"))`).click()
  }

  /**
   * Select hedge policy (aggressive or passive).
   */
  async selectHedgePolicy(policy: 'aggressive' | 'passive') {
    if (policy === 'aggressive') {
      await this.hedgePolicyAggressive.check()
    } else {
      await this.hedgePolicyPassive.check()
    }
  }

  /**
   * Select hedge mode (full or partial).
   */
  async selectHedgeMode(mode: 'full' | 'partial') {
    if (mode === 'full') {
      await this.hedgeModeFull.check()
    } else {
      await this.hedgeModePartial.check()
    }
  }

  /**
   * Set the risk band quantity.
   */
  async setRiskBandQty(value: number) {
    await this.riskBandQtyInput.fill(String(value))
  }

  /**
   * Select the reporting currency.
   */
  async selectReportingCurrency(currency: string) {
    await this.reportingCurrencySelect.selectOption(currency)
  }

  /**
   * Set the run name.
   */
  async setRunName(name: string) {
    await this.runNameInput.fill(name)
  }

  /**
   * Submit the form to create and start the run.
   */
  async submitCreateForm() {
    await this.createAndStartButton.click()
  }

  /**
   * Get the current step indicator.
   */
  async getCurrentStep(): Promise<string> {
    const activeStep = this.page.locator('.step-indicator .step.active, [data-testid="current-step"]')
    return (await activeStep.textContent()) || ''
  }

  /**
   * Wait for progress to complete.
   */
  async waitForProgressComplete(timeout = 60000) {
    await this.page.waitForFunction(
      () => {
        const statusEl = document.querySelector('[data-testid="run-status"], .status-badge')
        const text = statusEl?.textContent?.toLowerCase()
        return text === 'completed' || text === 'failed' || text === 'cancelled'
      },
      { timeout }
    )
  }

  /**
   * Filter runs by status.
   */
  async filterByStatus(status: 'all' | 'running' | 'completed' | 'failed') {
    switch (status) {
      case 'all':
        await this.filterAll.click()
        break
      case 'running':
        await this.filterRunning.click()
        break
      case 'completed':
        await this.filterCompleted.click()
        break
      case 'failed':
        await this.filterFailed.click()
        break
    }
  }

  /**
   * Get a run card by its ID.
   */
  getRunCard(runId: string): Locator {
    return this.page.locator(`.run-card:has-text("${runId}")`)
  }

  /**
   * Start a run from its card.
   */
  async startRun(runId: string) {
    const card = this.getRunCard(runId)
    await card.getByRole('button', { name: 'Start' }).click()
  }

  /**
   * View progress of a running run.
   */
  async viewProgress(runId: string) {
    const card = this.getRunCard(runId)
    await card.getByRole('button', { name: /View Progress|Monitor/i }).click()
  }

  /**
   * Cancel a running run.
   */
  async cancelRun(runId: string) {
    const card = this.getRunCard(runId)
    await card.getByRole('button', { name: 'Cancel' }).click()
  }

  /**
   * Delete a run.
   */
  async deleteRun(runId: string) {
    const card = this.getRunCard(runId)
    this.page.once('dialog', (dialog) => dialog.accept())
    await card.getByRole('button', { name: 'Delete' }).click()
  }

  /**
   * Click View Results button.
   */
  async clickViewResults() {
    await this.viewResultsButton.click()
  }
}
