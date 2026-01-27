/**
 * RunCreateForm component - multi-step form for creating a new run.
 */

import { useState, useEffect } from 'react'
import { listDatasets, getDataset, type DatasetSummary } from '../../api/datasets'
import { listTradeBooks, type TradeBookSummary } from '../../api/tradebooks'
import {
  createRun,
  type RunConfig,
  type SimulationConfig,
  type GeneralConfig,
  type HedgingRuleSet,
} from '../../api/runs'
import { HedgingRuleBuilder } from './HedgingRuleBuilder'

type Step = 'data' | 'config' | 'simulation' | 'review'

interface RunCreateFormProps {
  onCreated: (runId: string) => void
  onCancel: () => void
}

const REPORTING_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY']

// Default hedging rule set: no hedge for 0-1000, full hedge above
const DEFAULT_HEDGING_RULES: HedgingRuleSet = {
  groups: [],
  rules: [
    {
      pair_or_group: 'ALL',
      amount_type: 'absolute',
      from_amount: 0,
      to_amount: 1000,
      action: { action_type: 'no_hedge' },
    },
    {
      pair_or_group: 'ALL',
      amount_type: 'absolute',
      from_amount: 1000,
      to_amount: Infinity,
      action: { action_type: 'hedge_percentage', hedge_percentage: 1.0 },
    },
  ],
}

/**
 * Convert date from YYYYMMDD to YYYY-MM-DD format for API submission.
 */
function formatDateForApi(date: string): string {
  if (date.length === 8 && !date.includes('-')) {
    return `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`
  }
  return date
}

export function RunCreateForm({ onCreated, onCancel }: RunCreateFormProps) {
  // Step state
  const [step, setStep] = useState<Step>('data')

  // Data loading state
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [tradebooks, setTradebooks] = useState<TradeBookSummary[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [loadingDatasetDetails, setLoadingDatasetDetails] = useState(false)

  // Form values - Data Selection
  const [selectedDataset, setSelectedDataset] = useState<string>('')
  const [selectedTradebook, setSelectedTradebook] = useState<string>('')
  const [availablePairs, setAvailablePairs] = useState<string[]>([])
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')

  // Form values - General Config (defaults to all pairs from selected dataset)
  const [directPairs, setDirectPairs] = useState<string[]>([])

  // Form values - Simulation Settings
  const [reportingCurrency, setReportingCurrency] = useState('USD')
  const [sampleInterval, setSampleInterval] = useState(60)
  const [hedgingRules, setHedgingRules] = useState<HedgingRuleSet>(DEFAULT_HEDGING_RULES)
  const [hedgeDelayMs, setHedgeDelayMs] = useState(0)

  // Form values - Review
  const [runName, setRunName] = useState('')
  const [runDescription, setRunDescription] = useState('')

  // Submission state
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load datasets and tradebooks on mount
  useEffect(() => {
    async function loadData() {
      try {
        const [datasetsRes, tradebooksRes] = await Promise.all([
          listDatasets(),
          listTradeBooks(),
        ])
        setDatasets(datasetsRes)
        setTradebooks(tradebooksRes)

        // Auto-select first dataset if available
        if (datasetsRes.length > 0) {
          setSelectedDataset(datasetsRes[0].name)
        }
        // Auto-select first tradebook if available
        if (tradebooksRes.length > 0) {
          setSelectedTradebook(tradebooksRes[0].name)
        }
      } catch (err) {
        console.error('Failed to load data:', err)
        setError('Failed to load datasets and tradebooks')
      } finally {
        setLoadingData(false)
      }
    }
    loadData()
  }, [])

  // Load dataset details when selection changes
  useEffect(() => {
    if (!selectedDataset) {
      setAvailablePairs([])
      setAvailableDates([])
      setDirectPairs([])
      return
    }

    async function loadDatasetDetails() {
      setLoadingDatasetDetails(true)
      try {
        const details = await getDataset(selectedDataset)
        setAvailablePairs(details.pairs)
        setAvailableDates(details.dates)

        // Default ALL dataset pairs as direct pairs (they have market data)
        setDirectPairs(details.pairs)

        // Auto-select full date range
        if (details.dates.length > 0) {
          setStartDate(details.dates[0])
          setEndDate(details.dates[details.dates.length - 1])
        }
      } catch (err) {
        console.error('Failed to load dataset details:', err)
      } finally {
        setLoadingDatasetDetails(false)
      }
    }

    loadDatasetDetails()
  }, [selectedDataset])

  const handleDirectPairToggle = (pair: string) => {
    setDirectPairs((prev) =>
      prev.includes(pair) ? prev.filter((p) => p !== pair) : [...prev, pair]
    )
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)

    // Prepare hedging rules - convert Infinity to a large number for JSON serialization
    const serializableRules = hedgingRules.rules.map((rule) => ({
      ...rule,
      to_amount: isFinite(rule.to_amount) ? rule.to_amount : 1e18,
    }))

    const simConfig: SimulationConfig = {
      dataset: selectedDataset,
      reporting_currency: reportingCurrency,
      sample_interval_seconds: sampleInterval,
      hedging_rules: {
        groups: hedgingRules.groups,
        rules: serializableRules,
      },
      hedge_delay_ms: hedgeDelayMs,
    }

    const generalConfig: GeneralConfig = {
      direct_pairs: directPairs,
    }

    const config: RunConfig = {
      dataset: selectedDataset,
      tradebook: selectedTradebook,
      start_date: startDate ? formatDateForApi(startDate) : null,
      end_date: endDate ? formatDateForApi(endDate) : null,
      name: runName || null,
      description: runDescription || null,
      general_config: generalConfig,
      simulation_config: simConfig,
    }

    try {
      const response = await createRun(config, 'new')
      onCreated(response.run_id)
    } catch (err) {
      console.error('Failed to create run:', err)
      setError(err instanceof Error ? err.message : 'Failed to create run')
      setSubmitting(false)
    }
  }

  const canProceedToConfig = selectedDataset && selectedTradebook
  const canProceedToSimulation = true // General config has defaults
  const canProceedToReview = true // Simulation settings have defaults
  const canSubmit = !submitting

  if (loadingData) {
    return (
      <div className="run-create-form">
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading datasets and tradebooks...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="run-create-form">
      <div className="form-header">
        <button className="btn btn-ghost back-btn" onClick={onCancel}>
          &larr; Cancel
        </button>
        <h2>Create New Run</h2>
      </div>

      {/* Step Indicator */}
      <div className="step-indicator">
        <div className={`step ${step === 'data' ? 'active' : ''}`}>
          <span className="step-number">1</span>
          <span className="step-label">Data Selection</span>
        </div>
        <div className="step-divider" />
        <div className={`step ${step === 'config' ? 'active' : step === 'simulation' || step === 'review' ? 'completed' : ''}`}>
          <span className="step-number">2</span>
          <span className="step-label">General Config</span>
        </div>
        <div className="step-divider" />
        <div className={`step ${step === 'simulation' ? 'active' : step === 'review' ? 'completed' : ''}`}>
          <span className="step-number">3</span>
          <span className="step-label">Simulation Settings</span>
        </div>
        <div className="step-divider" />
        <div className={`step ${step === 'review' ? 'active' : ''}`}>
          <span className="step-number">4</span>
          <span className="step-label">Review & Create</span>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Step 1: Data Selection */}
      {step === 'data' && (
        <div className="form-step">
          <div className="form-section">
            <h3>Market Dataset</h3>
            <select
              className="form-select"
              value={selectedDataset}
              onChange={(e) => setSelectedDataset(e.target.value)}
            >
              <option value="">Select a dataset...</option>
              {datasets.map((ds) => (
                <option key={ds.name} value={ds.name}>
                  {ds.name} ({ds.pairs.length} pairs, {ds.dates.length} dates)
                </option>
              ))}
            </select>
            <p className="form-hint">
              Market data provides price ticks for simulation.
            </p>
          </div>

          <div className="form-section">
            <h3>Trade Book</h3>
            <select
              className="form-select"
              value={selectedTradebook}
              onChange={(e) => setSelectedTradebook(e.target.value)}
            >
              <option value="">Select a tradebook...</option>
              {tradebooks.map((tb) => (
                <option key={tb.name} value={tb.name}>
                  {tb.name} ({tb.total_trades} trades)
                </option>
              ))}
            </select>
            <p className="form-hint">
              Trade book contains the client trades to simulate. All currency pairs in the trades will be processed.
            </p>
          </div>

          {selectedDataset && (
            <div className="form-section">
              <h3>Date Range</h3>
              {loadingDatasetDetails ? (
                <p>Loading dates...</p>
              ) : (
                <div className="date-range-inputs">
                  <div className="form-field">
                    <label>Start Date</label>
                    <select
                      className="form-select"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                    >
                      {availableDates.map((date) => (
                        <option key={date} value={date}>
                          {date}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>End Date</label>
                    <select
                      className="form-select"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                    >
                      {availableDates.map((date) => (
                        <option key={date} value={date}>
                          {date}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
            </div>
          )}

          {selectedDataset && !loadingDatasetDetails && (
            <div className="form-section info-section">
              <h4>Available Pairs in Dataset</h4>
              <p className="pairs-preview">
                {availablePairs.join(', ') || 'No pairs found'}
              </p>
            </div>
          )}

          <div className="form-actions">
            <button className="btn btn-secondary" onClick={onCancel}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              disabled={!canProceedToConfig}
              onClick={() => setStep('config')}
            >
              Next: General Config
            </button>
          </div>
        </div>
      )}

      {/* Step 2: General Config */}
      {step === 'config' && (
        <div className="form-step">
          <div className="form-section">
            <h3>Direct Pairs</h3>
            <p className="form-hint">
              Direct pairs can be hedged externally in the market. Cross pairs will be decomposed into direct pair legs.
            </p>
            <div className="pair-grid">
              {availablePairs.map((pair) => (
                <label key={pair} className="pair-checkbox">
                  <input
                    type="checkbox"
                    checked={directPairs.includes(pair)}
                    onChange={() => handleDirectPairToggle(pair)}
                  />
                  <span>{pair}</span>
                </label>
              ))}
            </div>
            <p className="form-hint">
              Selected as direct: {directPairs.length > 0 ? directPairs.join(', ') : 'None'}
            </p>
          </div>

          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => setStep('data')}>
              Back
            </button>
            <button
              className="btn btn-primary"
              disabled={!canProceedToSimulation}
              onClick={() => setStep('simulation')}
            >
              Next: Simulation Settings
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Simulation Settings */}
      {step === 'simulation' && (
        <div className="form-step">
          <div className="form-row">
            <div className="form-field">
              <label>Reporting Currency</label>
              <select
                className="form-select"
                value={reportingCurrency}
                onChange={(e) => setReportingCurrency(e.target.value)}
              >
                {REPORTING_CURRENCIES.map((ccy) => (
                  <option key={ccy} value={ccy}>
                    {ccy}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-field">
              <label>Sample Interval</label>
              <select
                className="form-select"
                value={sampleInterval}
                onChange={(e) => setSampleInterval(Number(e.target.value))}
              >
                <option value={30}>30 seconds</option>
                <option value={60}>1 minute</option>
                <option value={300}>5 minutes</option>
              </select>
            </div>

            <div className="form-field">
              <label>Hedge Delay (ms)</label>
              <input
                type="number"
                className="form-input"
                value={hedgeDelayMs}
                onChange={(e) => setHedgeDelayMs(Math.max(0, Number(e.target.value)))}
                min={0}
                step={10}
                placeholder="0"
              />
              <p className="form-hint">
                Delay before hedge execution (0 = immediate). Use to visualize position changes.
              </p>
            </div>
          </div>

          <div className="form-section">
            <h3>Hedging Configuration</h3>
            <HedgingRuleBuilder
              ruleSet={hedgingRules}
              availablePairs={availablePairs}
              onChange={setHedgingRules}
            />
          </div>

          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => setStep('config')}>
              Back
            </button>
            <button
              className="btn btn-primary"
              disabled={!canProceedToReview}
              onClick={() => setStep('review')}
            >
              Next: Review
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Review & Create */}
      {step === 'review' && (
        <div className="form-step">
          <div className="form-section">
            <h3>Run Details (optional)</h3>
            <div className="form-field">
              <label>Run Name</label>
              <input
                type="text"
                className="form-input"
                value={runName}
                onChange={(e) => setRunName(e.target.value)}
                placeholder="e.g., Aggressive hedge test"
              />
            </div>
            <div className="form-field">
              <label>Description</label>
              <textarea
                className="form-textarea"
                value={runDescription}
                onChange={(e) => setRunDescription(e.target.value)}
                placeholder="Optional notes about this run..."
                rows={3}
              />
            </div>
          </div>

          <div className="form-section">
            <h3>Configuration Summary</h3>
            <div className="config-summary">
              <div className="summary-row">
                <span className="summary-label">Dataset:</span>
                <span className="summary-value">{selectedDataset}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Tradebook:</span>
                <span className="summary-value">{selectedTradebook}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Date Range:</span>
                <span className="summary-value">{startDate} to {endDate}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Direct Pairs:</span>
                <span className="summary-value">{directPairs.join(', ') || 'None'}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Reporting Currency:</span>
                <span className="summary-value">{reportingCurrency}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Sample Interval:</span>
                <span className="summary-value">{sampleInterval}s</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Hedge Delay:</span>
                <span className="summary-value">{hedgeDelayMs}ms{hedgeDelayMs === 0 ? ' (immediate)' : ''}</span>
              </div>
              {hedgingRules.groups.length > 0 && (
                <div className="summary-row">
                  <span className="summary-label">Pair Groups:</span>
                  <span className="summary-value">
                    {hedgingRules.groups.map((g) => `${g.name} (${g.pairs.join(', ')})`).join('; ')}
                  </span>
                </div>
              )}
              <div className="summary-row">
                <span className="summary-label">Hedging Rules:</span>
                <span className="summary-value">{hedgingRules.rules.length} rule(s)</span>
              </div>
              <div className="rules-summary">
                {hedgingRules.rules.map((rule, idx) => (
                  <div key={idx} className="rule-summary-item">
                    <span className="rule-target">{rule.pair_or_group}</span>
                    <span className="rule-range">
                      {rule.from_amount.toLocaleString()} - {isFinite(rule.to_amount) ? rule.to_amount.toLocaleString() : '∞'}
                    </span>
                    <span className="rule-action">
                      {rule.action.action_type === 'no_hedge' && 'No Hedge'}
                      {rule.action.action_type === 'hedge_to_target' &&
                        `Target ${((rule.action as { target_percentage: number }).target_percentage * 100).toFixed(0)}%`}
                      {rule.action.action_type === 'hedge_percentage' &&
                        `Hedge ${((rule.action as { hedge_percentage: number }).hedge_percentage * 100).toFixed(0)}%`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => setStep('simulation')}>
              Back
            </button>
            <button
              className="btn btn-primary"
              disabled={!canSubmit}
              onClick={handleSubmit}
            >
              {submitting ? 'Creating...' : 'Create & Start Run'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
