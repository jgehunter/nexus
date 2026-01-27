/**
 * Sweeps page - create and manage parameter sweeps.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  listSweeps,
  createSweep,
  startSweep,
  deleteSweep,
  getSweepStatus,
  type SweepListItem,
  type SweepConfig,
  type SweepStatus,
  type SweepStatusResponse,
} from '../api/sweeps'
import { listDatasets, type DatasetSummary, getDataset } from '../api/datasets'
import { listTradeBooks, type TradeBookSummary } from '../api/tradebooks'
import type { HedgingRuleSet, HedgingRule } from '../api/runs'
import { HedgingRuleBuilder } from '../components/runs/HedgingRuleBuilder'

type View = 'list' | 'create' | 'progress'

// Format timestamp for display
function formatTimestamp(ms: number): string {
  return new Date(ms).toLocaleString()
}

// Get status badge color
function getStatusColor(status: SweepStatus): string {
  switch (status) {
    case 'completed': return 'var(--color-success)'
    case 'running': return 'var(--color-accent)'
    case 'partial': return 'var(--color-warning)'
    case 'pending': return 'var(--color-text-muted)'
    case 'cancelled': return 'var(--color-error)'
    default: return 'var(--color-text-muted)'
  }
}

// Sweep card component
function SweepCard({
  sweep,
  onStart,
  onViewProgress,
  onViewResults,
  onDelete,
}: {
  sweep: SweepListItem
  onStart: (id: string) => void
  onViewProgress: (id: string) => void
  onViewResults: (id: string) => void
  onDelete: (id: string) => void
}) {
  const isRunning = sweep.status === 'running'
  const canStart = sweep.status === 'pending'
  const hasResults = sweep.status === 'completed' || sweep.status === 'partial'

  return (
    <div className="sweep-card">
      <div className="sweep-card-header">
        <div className="sweep-card-title">
          <span className="sweep-name">{sweep.name || sweep.sweep_id}</span>
          <span
            className="sweep-status"
            style={{ backgroundColor: getStatusColor(sweep.status) }}
          >
            {sweep.status}
          </span>
        </div>
        <span className="sweep-hash">{sweep.config_hash.slice(0, 8)}</span>
      </div>

      <div className="sweep-card-meta">
        <div>Dataset: <strong>{sweep.dataset}</strong></div>
        <div>Tradebook: <strong>{sweep.tradebook}</strong></div>
        <div>Configs: <strong>{sweep.total_configs}</strong></div>
        <div>Created: {formatTimestamp(sweep.created_at_ms)}</div>
      </div>

      {(isRunning || sweep.progress_pct > 0) && (
        <div className="sweep-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${sweep.progress_pct}%` }}
            />
          </div>
          <span className="progress-text">
            {sweep.completed_configs + sweep.skipped_configs}/{sweep.total_configs}
            {sweep.failed_configs > 0 && ` (${sweep.failed_configs} failed)`}
          </span>
        </div>
      )}

      <div className="sweep-card-actions">
        {canStart && (
          <button className="btn btn-primary btn-sm" onClick={() => onStart(sweep.sweep_id)}>
            Start
          </button>
        )}
        {isRunning && (
          <button className="btn btn-secondary btn-sm" onClick={() => onViewProgress(sweep.sweep_id)}>
            View Progress
          </button>
        )}
        {hasResults && (
          <button className="btn btn-primary btn-sm" onClick={() => onViewResults(sweep.sweep_id)}>
            View Results
          </button>
        )}
        <button
          className="btn btn-danger btn-sm"
          onClick={() => onDelete(sweep.sweep_id)}
          disabled={isRunning}
        >
          Delete
        </button>
      </div>
    </div>
  )
}

// Sweep list component
function SweepList({
  onStart,
  onViewProgress,
  onViewResults,
}: {
  onStart: (id: string) => void
  onViewProgress: (id: string) => void
  onViewResults: (id: string) => void
}) {
  const [sweeps, setSweeps] = useState<SweepListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadSweeps = useCallback(async () => {
    try {
      setLoading(true)
      const response = await listSweeps()
      setSweeps(response.sweeps)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sweeps')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSweeps()
  }, [loadSweeps])

  const handleDelete = async (sweepId: string) => {
    if (!confirm('Are you sure you want to delete this sweep?')) return
    try {
      await deleteSweep(sweepId, false)
      loadSweeps()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete sweep')
    }
  }

  if (loading) {
    return <div className="loading">Loading sweeps...</div>
  }

  if (error) {
    return <div className="error-banner">{error}</div>
  }

  if (sweeps.length === 0) {
    return (
      <div className="empty-state">
        <p>No sweeps found. Create a new sweep to get started.</p>
      </div>
    )
  }

  return (
    <div className="sweep-list">
      {sweeps.map((sweep) => (
        <SweepCard
          key={sweep.sweep_id}
          sweep={sweep}
          onStart={onStart}
          onViewProgress={onViewProgress}
          onViewResults={onViewResults}
          onDelete={handleDelete}
        />
      ))}
    </div>
  )
}

// Large number to represent infinity for JSON serialization
const INFINITY_SUBSTITUTE = 1e18

// Sanitize a rule set for JSON serialization (convert Infinity to large number)
function sanitizeRuleSetForApi(ruleSet: HedgingRuleSet): HedgingRuleSet {
  return {
    ...ruleSet,
    rules: ruleSet.rules.map(rule => ({
      ...rule,
      from_amount: Number.isFinite(rule.from_amount) ? rule.from_amount : INFINITY_SUBSTITUTE,
      to_amount: Number.isFinite(rule.to_amount) ? rule.to_amount : INFINITY_SUBSTITUTE,
    })),
  }
}

// Create a default hedging rule set
function createDefaultRuleSet(name: string): HedgingRuleSet {
  return {
    name,
    groups: [],
    rules: [
      {
        pair_or_group: 'ALL',
        amount_type: 'absolute',
        from_amount: 0,
        to_amount: Infinity,
        action: { action_type: 'no_hedge' },
      } as HedgingRule,
    ],
  }
}

// Preset templates for common hedging strategies
const HEDGING_TEMPLATES: { name: string; create: () => HedgingRuleSet }[] = [
  {
    name: 'No Hedge',
    create: () => ({
      name: 'No Hedge',
      groups: [],
      rules: [
        {
          pair_or_group: 'ALL',
          amount_type: 'absolute',
          from_amount: 0,
          to_amount: Infinity,
          action: { action_type: 'no_hedge' },
        } as HedgingRule,
      ],
    }),
  },
  {
    name: 'Hedge 100% Above 1M',
    create: () => ({
      name: 'Hedge 100% Above 1M',
      groups: [],
      rules: [
        {
          pair_or_group: 'ALL',
          amount_type: 'absolute',
          from_amount: 0,
          to_amount: 1000000,
          action: { action_type: 'no_hedge' },
        } as HedgingRule,
        {
          pair_or_group: 'ALL',
          amount_type: 'absolute',
          from_amount: 1000000,
          to_amount: Infinity,
          action: { action_type: 'hedge_percentage', hedge_percentage: 1.0 },
        } as HedgingRule,
      ],
    }),
  },
  {
    name: 'Hedge to 50% Above 1M',
    create: () => ({
      name: 'Hedge to 50% Above 1M',
      groups: [],
      rules: [
        {
          pair_or_group: 'ALL',
          amount_type: 'absolute',
          from_amount: 0,
          to_amount: 1000000,
          action: { action_type: 'no_hedge' },
        } as HedgingRule,
        {
          pair_or_group: 'ALL',
          amount_type: 'absolute',
          from_amount: 1000000,
          to_amount: Infinity,
          action: { action_type: 'hedge_to_target', target_percentage: 0.5 },
        } as HedgingRule,
      ],
    }),
  },
]

// Sweep create form component
function SweepCreateForm({
  onCreated,
  onCancel,
}: {
  onCreated: (id: string) => void
  onCancel: () => void
}) {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [tradebooks, setTradebooks] = useState<TradeBookSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [availablePairs, setAvailablePairs] = useState<string[]>([])

  // Form state
  const [dataset, setDataset] = useState('')
  const [tradebook, setTradebook] = useState('')
  const [name, setName] = useState('')

  // Simulation config (fixed for all runs in sweep)
  const [hedgeDelayMs, setHedgeDelayMs] = useState(0)
  const [sampleIntervalSeconds, setSampleIntervalSeconds] = useState(60)

  // Hedging rule presets state
  const [hedgingPresets, setHedgingPresets] = useState<HedgingRuleSet[]>([])
  const [expandedPresetIndex, setExpandedPresetIndex] = useState<number | null>(null)

  useEffect(() => {
    async function loadData() {
      try {
        const [ds, tb] = await Promise.all([listDatasets(), listTradeBooks()])
        setDatasets(ds)
        setTradebooks(tb)
        if (ds.length > 0) setDataset(ds[0].name)
        if (tb.length > 0) setTradebook(tb[0].name)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load data')
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  // Load available pairs when dataset changes
  useEffect(() => {
    async function loadPairs() {
      if (!dataset) return
      try {
        const detail = await getDataset(dataset)
        setAvailablePairs(detail.pairs || [])
      } catch {
        setAvailablePairs([])
      }
    }
    loadPairs()
  }, [dataset])

  // Hedging preset management
  const addPresetFromTemplate = (template: typeof HEDGING_TEMPLATES[0]) => {
    setHedgingPresets([...hedgingPresets, template.create()])
  }

  const addCustomPreset = () => {
    const presetNum = hedgingPresets.length + 1
    setHedgingPresets([...hedgingPresets, createDefaultRuleSet(`Preset ${presetNum}`)])
    setExpandedPresetIndex(hedgingPresets.length)
  }

  const removePreset = (index: number) => {
    setHedgingPresets(hedgingPresets.filter((_, i) => i !== index))
    if (expandedPresetIndex === index) {
      setExpandedPresetIndex(null)
    } else if (expandedPresetIndex !== null && expandedPresetIndex > index) {
      setExpandedPresetIndex(expandedPresetIndex - 1)
    }
  }

  const updatePreset = (index: number, ruleSet: HedgingRuleSet) => {
    setHedgingPresets(hedgingPresets.map((p, i) => (i === index ? ruleSet : p)))
  }

  const updatePresetName = (index: number, newName: string) => {
    setHedgingPresets(
      hedgingPresets.map((p, i) => (i === index ? { ...p, name: newName } : p))
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dataset || !tradebook) return

    setSubmitting(true)
    setError(null)

    try {
      // Build parameter grid - only hedging_rules_index if multiple presets
      const parameterGrid: Record<string, unknown> = {}
      if (hedgingPresets.length > 1) {
        parameterGrid['hedging_rules_index'] = hedgingPresets.map((_, i) => i)
      }

      // Determine hedging presets to use and sanitize for API
      const presetsToUse = hedgingPresets.length > 0
        ? hedgingPresets.map(sanitizeRuleSetForApi)
        : [sanitizeRuleSetForApi(createDefaultRuleSet('No Hedge'))]

      const config: SweepConfig = {
        dataset,
        tradebook,
        name: name || undefined,
        hedging_rules_presets: presetsToUse,
        base_simulation_config: {
          hedge_delay_ms: hedgeDelayMs,
          sample_interval_seconds: sampleIntervalSeconds,
        },
        parameter_grid: parameterGrid as SweepConfig['parameter_grid'],
      }

      const result = await createSweep(config)
      onCreated(result.sweep_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create sweep')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="loading">Loading...</div>
  }

  return (
    <form className="sweep-create-form" onSubmit={handleSubmit}>
      <h2>Create Parameter Sweep</h2>

      {error && <div className="error-banner">{error}</div>}

      <div className="form-group">
        <label htmlFor="name">Sweep Name (optional)</label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="My Sweep"
        />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="dataset">Dataset</label>
          <select
            id="dataset"
            value={dataset}
            onChange={e => setDataset(e.target.value)}
            required
          >
            {datasets.map(d => (
              <option key={d.name} value={d.name}>{d.name}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="tradebook">Tradebook</label>
          <select
            id="tradebook"
            value={tradebook}
            onChange={e => setTradebook(e.target.value)}
            required
          >
            {tradebooks.map(t => (
              <option key={t.name} value={t.name}>{t.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Hedging Rule Presets Section */}
      <div className="form-section">
        <h3>Hedging Rule Presets</h3>
        <p className="form-hint">
          Define different hedging strategies to compare. The sweep will test each preset.
        </p>

        {/* Template buttons */}
        <div className="preset-templates">
          <span className="template-label">Quick add:</span>
          {HEDGING_TEMPLATES.map((template) => (
            <button
              key={template.name}
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => addPresetFromTemplate(template)}
            >
              {template.name}
            </button>
          ))}
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={addCustomPreset}
          >
            + Custom
          </button>
        </div>

        {/* Preset list */}
        {hedgingPresets.length > 0 && (
          <div className="presets-list">
            {hedgingPresets.map((preset, index) => (
              <div key={index} className="preset-card">
                <div className="preset-header">
                  <input
                    type="text"
                    className="preset-name-input"
                    value={preset.name || `Preset ${index + 1}`}
                    onChange={(e) => updatePresetName(index, e.target.value)}
                    placeholder={`Preset ${index + 1}`}
                  />
                  <div className="preset-actions">
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      onClick={() =>
                        setExpandedPresetIndex(expandedPresetIndex === index ? null : index)
                      }
                    >
                      {expandedPresetIndex === index ? 'Collapse' : 'Edit'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost btn-danger-text"
                      onClick={() => removePreset(index)}
                    >
                      Remove
                    </button>
                  </div>
                </div>

                {/* Summary when collapsed */}
                {expandedPresetIndex !== index && (
                  <div className="preset-summary">
                    {preset.rules.length} rule{preset.rules.length !== 1 ? 's' : ''}
                    {preset.groups.length > 0 && `, ${preset.groups.length} group${preset.groups.length !== 1 ? 's' : ''}`}
                  </div>
                )}

                {/* Expanded rule builder */}
                {expandedPresetIndex === index && (
                  <div className="preset-expanded">
                    <HedgingRuleBuilder
                      ruleSet={preset}
                      availablePairs={availablePairs}
                      onChange={(ruleSet) => updatePreset(index, ruleSet)}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {hedgingPresets.length === 0 && (
          <p className="empty-presets">
            No presets defined. A default "No Hedge" preset will be used.
          </p>
        )}

        {hedgingPresets.length > 1 && (
          <p className="sweep-info">
            The sweep will run {hedgingPresets.length} configurations, one for each preset.
          </p>
        )}
      </div>

      {/* Simulation Settings */}
      <div className="form-section">
        <h3>Simulation Settings</h3>
        <p className="form-hint">
          Configure simulation parameters that apply to all runs in the sweep.
        </p>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="hedgeDelay">Hedge Delay (ms)</label>
            <input
              id="hedgeDelay"
              type="number"
              min={0}
              step={1}
              value={hedgeDelayMs}
              onChange={e => setHedgeDelayMs(Number(e.target.value) || 0)}
            />
            <span className="form-help">Delay before hedge execution (0 = immediate)</span>
          </div>

          <div className="form-group">
            <label htmlFor="sampleInterval">Sample Interval (seconds)</label>
            <input
              id="sampleInterval"
              type="number"
              min={1}
              step={1}
              value={sampleIntervalSeconds}
              onChange={e => setSampleIntervalSeconds(Number(e.target.value) || 60)}
            />
            <span className="form-help">How often to sample positions for metrics</span>
          </div>
        </div>
      </div>

      <div className="form-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create Sweep'}
        </button>
      </div>
    </form>
  )
}

// Sweep progress component
function SweepProgress({
  sweepId,
  autoStart,
  onBack,
  onComplete,
}: {
  sweepId: string
  autoStart: boolean
  onBack: () => void
  onComplete: (sweepId: string) => void
}) {
  const [status, setStatus] = useState<SweepStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [started, setStarted] = useState(false)

  // Auto-start sweep if needed (only if status is pending)
  useEffect(() => {
    if (!autoStart || started) return

    async function maybeStart() {
      try {
        const currentStatus = await getSweepStatus(sweepId)
        setStatus(currentStatus)

        // Only start if pending
        if (currentStatus.status === 'pending') {
          setStarted(true)
          const newStatus = await startSweep(sweepId)
          setStatus(newStatus)
        } else {
          // Already running or completed, just mark as started to prevent retries
          setStarted(true)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to start sweep')
      }
    }

    maybeStart()
  }, [sweepId, autoStart, started])

  // Poll for status updates
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const s = await getSweepStatus(sweepId)
        setStatus(s)
        if (s.status === 'completed' || s.status === 'partial') {
          clearInterval(interval)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to get status')
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [sweepId])

  const isComplete = status?.status === 'completed' || status?.status === 'partial'

  return (
    <div className="sweep-progress-view">
      <h2>Sweep Progress</h2>

      {error && <div className="error-banner">{error}</div>}

      {status && (
        <div className="progress-details">
          <div className="progress-stat">
            <span className="label">Status</span>
            <span
              className="value"
              style={{ color: getStatusColor(status.status) }}
            >
              {status.status}
            </span>
          </div>
          <div className="progress-stat">
            <span className="label">Completed</span>
            <span className="value">{status.completed_configs}</span>
          </div>
          <div className="progress-stat">
            <span className="label">Skipped</span>
            <span className="value">{status.skipped_configs}</span>
          </div>
          <div className="progress-stat">
            <span className="label">Failed</span>
            <span className="value">{status.failed_configs}</span>
          </div>
          <div className="progress-stat">
            <span className="label">Total</span>
            <span className="value">{status.total_configs}</span>
          </div>

          {status.current_run_id && (
            <div className="progress-stat">
              <span className="label">Current Run</span>
              <span className="value">{status.current_run_id}</span>
            </div>
          )}

          <div className="progress-bar-large">
            <div
              className="progress-fill"
              style={{ width: `${status.progress_pct}%` }}
            />
          </div>
          <div className="progress-pct">{status.progress_pct.toFixed(1)}%</div>

          {status.error_message && (
            <div className="error-message">
              <strong>Error:</strong> {status.error_message}
            </div>
          )}
        </div>
      )}

      <div className="progress-actions">
        <button className="btn btn-secondary" onClick={onBack}>
          Back to List
        </button>
        {isComplete && (
          <button className="btn btn-primary" onClick={() => onComplete(sweepId)}>
            View Results
          </button>
        )}
      </div>
    </div>
  )
}

// Main Sweeps page
export function Sweeps() {
  const navigate = useNavigate()
  const [view, setView] = useState<View>('list')
  const [activeSweepId, setActiveSweepId] = useState<string | null>(null)
  const [autoStartSweep, setAutoStartSweep] = useState(false)

  const handleStart = async (sweepId: string) => {
    setActiveSweepId(sweepId)
    setAutoStartSweep(true)
    setView('progress')
  }

  const handleViewProgress = (sweepId: string) => {
    setActiveSweepId(sweepId)
    setAutoStartSweep(false)
    setView('progress')
  }

  const handleViewResults = (sweepId: string) => {
    navigate(`/compare?sweep=${sweepId}`)
  }

  const handleSweepCreated = (sweepId: string) => {
    setActiveSweepId(sweepId)
    setAutoStartSweep(true)
    setView('progress')
  }

  const handleComplete = (sweepId: string) => {
    navigate(`/compare?sweep=${sweepId}`)
  }

  const handleBack = () => {
    setView('list')
    setActiveSweepId(null)
    setAutoStartSweep(false)
  }

  return (
    <div className="page sweeps-page">
      <div className="page-header">
        <div className="page-header-main">
          <h1>Parameter Sweeps</h1>
          <p className="page-description">
            Run parameter sweeps to find optimal configurations
          </p>
        </div>

        {view === 'list' && (
          <button className="btn btn-primary" onClick={() => setView('create')}>
            New Sweep
          </button>
        )}
      </div>

      {view === 'list' && (
        <SweepList
          onStart={handleStart}
          onViewProgress={handleViewProgress}
          onViewResults={handleViewResults}
        />
      )}

      {view === 'create' && (
        <SweepCreateForm onCreated={handleSweepCreated} onCancel={handleBack} />
      )}

      {view === 'progress' && activeSweepId && (
        <SweepProgress
          sweepId={activeSweepId}
          autoStart={autoStartSweep}
          onBack={handleBack}
          onComplete={handleComplete}
        />
      )}
    </div>
  )
}
