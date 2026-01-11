/**
 * Runs page - create and manage backtest runs.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RunList, RunCreateForm, RunProgress } from '../components/runs'

type View = 'list' | 'create' | 'progress'

export function Runs() {
  const navigate = useNavigate()
  const [view, setView] = useState<View>('list')
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [autoStartRun, setAutoStartRun] = useState(false)

  const handleViewProgress = (runId: string) => {
    setActiveRunId(runId)
    setAutoStartRun(false)
    setView('progress')
  }

  const handleViewResults = (runId: string) => {
    navigate(`/results?run=${runId}`)
  }

  const handleStartRun = async (runId: string) => {
    setActiveRunId(runId)
    setAutoStartRun(true)
    setView('progress')
  }

  const handleRunCreated = (runId: string) => {
    setActiveRunId(runId)
    setAutoStartRun(true)
    setView('progress')
  }

  const handleComplete = (runId: string) => {
    navigate(`/results?run=${runId}`)
  }

  const handleBack = () => {
    setView('list')
    setActiveRunId(null)
    setAutoStartRun(false)
  }

  return (
    <div className="page runs-page">
      <div className="page-header">
        <div className="page-header-main">
          <h1>Runs</h1>
          <p className="page-description">
            Configure and execute backtest simulations
          </p>
        </div>

        {view === 'list' && (
          <button className="btn btn-primary" onClick={() => setView('create')}>
            New Run
          </button>
        )}
      </div>

      {view === 'list' && (
        <RunList
          onViewProgress={handleViewProgress}
          onViewResults={handleViewResults}
          onStartRun={handleStartRun}
        />
      )}

      {view === 'create' && (
        <RunCreateForm onCreated={handleRunCreated} onCancel={handleBack} />
      )}

      {view === 'progress' && activeRunId && (
        <RunProgress
          runId={activeRunId}
          autoStart={autoStartRun}
          onBack={handleBack}
          onComplete={handleComplete}
        />
      )}
    </div>
  )
}
