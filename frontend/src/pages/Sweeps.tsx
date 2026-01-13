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
  type ParameterRange,
} from '../api/sweeps'
import { listDatasets, type DatasetSummary } from '../api/datasets'
import { listTradeBooks, type TradeBookSummary } from '../api/tradebooks'

type View = 'list' | 'create' | 'progress'

interface ParameterEntry {
  name: string
  type: 'list' | 'range'
  values: string // Comma-separated for list
  min: number
  max: number
  step: number
}

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

  // Form state
  const [dataset, setDataset] = useState('')
  const [tradebook, setTradebook] = useState('')
  const [name, setName] = useState('')
  const [parameters, setParameters] = useState<ParameterEntry[]>([])

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

  const addParameter = (paramName: string) => {
    if (parameters.some(p => p.name === paramName)) return
    setParameters([
      ...parameters,
      { name: paramName, type: 'list', values: '', min: 0, max: 0, step: 1 }
    ])
  }

  const removeParameter = (paramName: string) => {
    setParameters(parameters.filter(p => p.name !== paramName))
  }

  const updateParameter = (paramName: string, updates: Partial<ParameterEntry>) => {
    setParameters(parameters.map(p =>
      p.name === paramName ? { ...p, ...updates } : p
    ))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dataset || !tradebook) return

    setSubmitting(true)
    setError(null)

    try {
      // Build parameter grid
      const parameterGrid: Record<string, unknown> = {}
      for (const param of parameters) {
        if (param.type === 'list') {
          const values = param.values.split(',').map(v => {
            const trimmed = v.trim()
            const num = Number(trimmed)
            return isNaN(num) ? trimmed : num
          }).filter(v => v !== '')
          if (values.length > 0) {
            parameterGrid[param.name] = values
          }
        } else {
          const range: ParameterRange = {
            min: param.min,
            max: param.max,
            step: param.step,
          }
          parameterGrid[param.name] = range
        }
      }

      const config: SweepConfig = {
        dataset,
        tradebook,
        name: name || undefined,
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

  const availableParams = [
    { name: 'risk_band_qty', label: 'Risk Band Qty' },
    { name: 'hedge_mode', label: 'Hedge Mode' },
    { name: 'hedge_policy', label: 'Hedge Policy' },
    { name: 'max_path_length', label: 'Max Path Length' },
    { name: 'min_leg_qty', label: 'Min Leg Qty' },
  ]

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

      <div className="form-section">
        <h3>Parameter Grid</h3>
        <p className="form-hint">
          Add parameters to sweep over. Each creates multiple configuration combinations.
        </p>

        <div className="param-buttons">
          {availableParams.map(p => (
            <button
              key={p.name}
              type="button"
              className="btn btn-sm"
              onClick={() => addParameter(p.name)}
              disabled={parameters.some(param => param.name === p.name)}
            >
              + {p.label}
            </button>
          ))}
        </div>

        {parameters.length > 0 && (
          <div className="param-list">
            {parameters.map(param => (
              <div key={param.name} className="param-entry">
                <div className="param-header">
                  <strong>{param.name}</strong>
                  <button
                    type="button"
                    className="btn btn-danger btn-xs"
                    onClick={() => removeParameter(param.name)}
                  >
                    Remove
                  </button>
                </div>

                <div className="param-type">
                  <label>
                    <input
                      type="radio"
                      checked={param.type === 'list'}
                      onChange={() => updateParameter(param.name, { type: 'list' })}
                    />
                    Explicit Values
                  </label>
                  <label>
                    <input
                      type="radio"
                      checked={param.type === 'range'}
                      onChange={() => updateParameter(param.name, { type: 'range' })}
                    />
                    Range
                  </label>
                </div>

                {param.type === 'list' ? (
                  <input
                    type="text"
                    placeholder="e.g., 1000000, 5000000, 10000000"
                    value={param.values}
                    onChange={e => updateParameter(param.name, { values: e.target.value })}
                  />
                ) : (
                  <div className="range-inputs">
                    <input
                      type="number"
                      placeholder="Min"
                      value={param.min || ''}
                      onChange={e => updateParameter(param.name, { min: Number(e.target.value) })}
                    />
                    <input
                      type="number"
                      placeholder="Max"
                      value={param.max || ''}
                      onChange={e => updateParameter(param.name, { max: Number(e.target.value) })}
                    />
                    <input
                      type="number"
                      placeholder="Step"
                      value={param.step || ''}
                      onChange={e => updateParameter(param.name, { step: Number(e.target.value) })}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {parameters.length === 0 && (
          <p className="empty-params">
            No parameters added. The sweep will run a single configuration.
          </p>
        )}
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

  useEffect(() => {
    if (autoStart && !started) {
      setStarted(true)
      startSweep(sweepId)
        .then(setStatus)
        .catch(e => setError(e instanceof Error ? e.message : 'Failed to start sweep'))
    }
  }, [sweepId, autoStart, started])

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

    // Initial fetch
    getSweepStatus(sweepId).then(setStatus).catch(() => {})

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
