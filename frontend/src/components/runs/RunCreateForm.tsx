/**
 * RunCreateForm component - multi-step form for creating a new run.
 */

import { useState, useEffect } from 'react'
import { listDatasets, getDataset, type DatasetSummary } from '../../api/datasets'
import { listTradeBooks, type TradeBookSummary } from '../../api/tradebooks'
import { createRun, type RunConfig, type SimulationConfig } from '../../api/runs'

type Step = 'data' | 'simulation' | 'review'

interface RunCreateFormProps {
  onCreated: (runId: string) => void
  onCancel: () => void
}

const HEDGE_POLICIES = [
  { value: 'aggressive', label: 'Aggressive', description: 'Hedge immediately when position exceeds band' },
  { value: 'passive', label: 'Passive', description: 'Wait for natural offsetting flow' },
]

const HEDGE_MODES = [
  { value: 'full', label: 'Full', description: 'Hedge entire excess position' },
  { value: 'partial', label: 'Partial', description: 'Hedge down to band edge only' },
]

const REPORTING_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY']

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
  const [selectedPairs, setSelectedPairs] = useState<string[]>([])
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')

  // Form values - Simulation Settings
  const [hedgePolicy, setHedgePolicy] = useState('aggressive')
  const [hedgeMode, setHedgeMode] = useState('full')
  const [riskBandQty, setRiskBandQty] = useState(1000)
  const [reportingCurrency, setReportingCurrency] = useState('USD')
  const [sampleInterval, setSampleInterval] = useState(60)
  const [enablePairBands, setEnablePairBands] = useState(false)
  const [pairBands, setPairBands] = useState<Record<string, number>>({})

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
      return
    }

    async function loadDatasetDetails() {
      setLoadingDatasetDetails(true)
      try {
        const details = await getDataset(selectedDataset)
        setAvailablePairs(details.pairs)
        setAvailableDates(details.dates)

        // Auto-select all pairs and full date range
        setSelectedPairs(details.pairs)
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

  const handlePairToggle = (pair: string) => {
    setSelectedPairs((prev) =>
      prev.includes(pair) ? prev.filter((p) => p !== pair) : [...prev, pair]
    )
  }

  const handleSelectAllPairs = () => {
    setSelectedPairs(availablePairs)
  }

  const handleDeselectAllPairs = () => {
    setSelectedPairs([])
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)

    // Build pair_bands object with only non-default values
    const effectivePairBands: Record<string, number> = {}
    if (enablePairBands) {
      for (const pair of selectedPairs) {
        const pairBand = pairBands[pair]
        if (pairBand !== undefined && pairBand !== riskBandQty) {
          effectivePairBands[pair] = pairBand
        }
      }
    }

    const simConfig: SimulationConfig = {
      dataset: selectedDataset,
      reporting_currency: reportingCurrency,
      hedge_policy: hedgePolicy,
      hedge_policy_config: {
        risk_band_qty: riskBandQty,
        hedge_mode: hedgeMode,
        ...(Object.keys(effectivePairBands).length > 0 && { pair_bands: effectivePairBands }),
      },
      sample_interval_seconds: sampleInterval,
    }

    const config: RunConfig = {
      dataset: selectedDataset,
      tradebook: selectedTradebook || null,
      pairs: selectedPairs,
      start_date: startDate ? formatDateForApi(startDate) : null,
      end_date: endDate ? formatDateForApi(endDate) : null,
      name: runName || null,
      description: runDescription || null,
      enable_decrossing: !!selectedTradebook,
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

  const canProceedToSimulation = selectedDataset && selectedPairs.length > 0
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
        <div className={`step ${step === 'simulation' ? 'active' : step === 'review' ? 'completed' : ''}`}>
          <span className="step-number">2</span>
          <span className="step-label">Simulation Settings</span>
        </div>
        <div className="step-divider" />
        <div className={`step ${step === 'review' ? 'active' : ''}`}>
          <span className="step-number">3</span>
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
            <h3>Dataset</h3>
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
          </div>

          <div className="form-section">
            <h3>Tradebook (optional)</h3>
            <select
              className="form-select"
              value={selectedTradebook}
              onChange={(e) => setSelectedTradebook(e.target.value)}
            >
              <option value="">No tradebook (simulation only)</option>
              {tradebooks.map((tb) => (
                <option key={tb.name} value={tb.name}>
                  {tb.name} ({tb.total_trades} trades)
                </option>
              ))}
            </select>
            <p className="form-hint">
              Select a tradebook to run simulation with client trades. Leave empty for market data only.
            </p>
          </div>

          {selectedDataset && (
            <>
              <div className="form-section">
                <h3>Currency Pairs</h3>
                {loadingDatasetDetails ? (
                  <p>Loading pairs...</p>
                ) : (
                  <>
                    <div className="pair-select-actions">
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={handleSelectAllPairs}
                      >
                        Select All
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={handleDeselectAllPairs}
                      >
                        Deselect All
                      </button>
                      <span className="pair-count">
                        {selectedPairs.length} of {availablePairs.length} selected
                      </span>
                    </div>
                    <div className="pair-grid">
                      {availablePairs.map((pair) => (
                        <label key={pair} className="pair-checkbox">
                          <input
                            type="checkbox"
                            checked={selectedPairs.includes(pair)}
                            onChange={() => handlePairToggle(pair)}
                          />
                          <span>{pair}</span>
                        </label>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <div className="form-section">
                <h3>Date Range</h3>
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
              </div>
            </>
          )}

          <div className="form-actions">
            <button className="btn btn-secondary" onClick={onCancel}>
              Cancel
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

      {/* Step 2: Simulation Settings */}
      {step === 'simulation' && (
        <div className="form-step">
          <div className="form-section">
            <h3>Hedge Policy</h3>
            <div className="radio-group">
              {HEDGE_POLICIES.map((policy) => (
                <label key={policy.value} className="radio-option">
                  <input
                    type="radio"
                    name="hedgePolicy"
                    value={policy.value}
                    checked={hedgePolicy === policy.value}
                    onChange={(e) => setHedgePolicy(e.target.value)}
                  />
                  <div className="radio-content">
                    <span className="radio-label">{policy.label}</span>
                    <span className="radio-description">{policy.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="form-section">
            <h3>Hedge Mode</h3>
            <div className="radio-group">
              {HEDGE_MODES.map((mode) => (
                <label key={mode.value} className="radio-option">
                  <input
                    type="radio"
                    name="hedgeMode"
                    value={mode.value}
                    checked={hedgeMode === mode.value}
                    onChange={(e) => setHedgeMode(e.target.value)}
                  />
                  <div className="radio-content">
                    <span className="radio-label">{mode.label}</span>
                    <span className="radio-description">{mode.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="form-row">
            <div className="form-field">
              <label>Risk Band Quantity</label>
              <input
                type="number"
                className="form-input"
                value={riskBandQty}
                onChange={(e) => setRiskBandQty(Number(e.target.value))}
                min={0}
                step={100}
              />
              <span className="form-hint">Base currency units</span>
            </div>

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
          </div>

          <div className="form-section">
            <label className="checkbox-option">
              <input
                type="checkbox"
                checked={enablePairBands}
                onChange={(e) => {
                  setEnablePairBands(e.target.checked)
                  if (e.target.checked && Object.keys(pairBands).length === 0) {
                    // Initialize all pairs with global default
                    const initialBands: Record<string, number> = {}
                    for (const pair of selectedPairs) {
                      initialBands[pair] = riskBandQty
                    }
                    setPairBands(initialBands)
                  }
                }}
              />
              <span>Configure per-pair bands</span>
            </label>
            {enablePairBands && (
              <div className="pair-bands-table">
                <div className="pair-bands-header">
                  <span>Pair</span>
                  <span>Band Qty (base currency)</span>
                </div>
                {selectedPairs.map((pair) => (
                  <div key={pair} className="pair-bands-row">
                    <span className="pair-name">{pair}</span>
                    <input
                      type="number"
                      className="form-input"
                      value={pairBands[pair] ?? riskBandQty}
                      onChange={(e) =>
                        setPairBands((prev) => ({
                          ...prev,
                          [pair]: Number(e.target.value),
                        }))
                      }
                      min={0}
                      step={100}
                    />
                  </div>
                ))}
                <p className="form-hint">
                  Pairs using the global default ({riskBandQty.toLocaleString()}) are not included in the config.
                </p>
              </div>
            )}
          </div>

          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => setStep('data')}>
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

      {/* Step 3: Review & Create */}
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
              {selectedTradebook && (
                <div className="summary-row">
                  <span className="summary-label">Tradebook:</span>
                  <span className="summary-value">{selectedTradebook}</span>
                </div>
              )}
              <div className="summary-row">
                <span className="summary-label">Pairs:</span>
                <span className="summary-value">{selectedPairs.join(', ')}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Date Range:</span>
                <span className="summary-value">{startDate} to {endDate}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Hedge Policy:</span>
                <span className="summary-value">{hedgePolicy} / {hedgeMode}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Risk Band:</span>
                <span className="summary-value">
                  {riskBandQty.toLocaleString()} units
                  {enablePairBands && ' (global default)'}
                </span>
              </div>
              {enablePairBands && Object.entries(pairBands).filter(([, val]) => val !== riskBandQty).length > 0 && (
                <div className="summary-row">
                  <span className="summary-label">Per-Pair Bands:</span>
                  <span className="summary-value">
                    {Object.entries(pairBands)
                      .filter(([, val]) => val !== riskBandQty)
                      .map(([pair, val]) => `${pair}: ${val.toLocaleString()}`)
                      .join(', ')}
                  </span>
                </div>
              )}
              <div className="summary-row">
                <span className="summary-label">Reporting Currency:</span>
                <span className="summary-value">{reportingCurrency}</span>
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
