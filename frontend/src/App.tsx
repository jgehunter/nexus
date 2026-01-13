import { Routes, Route } from 'react-router-dom'
import { useHealthMonitor } from './hooks/useHealthMonitor'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Datasets } from './pages/Datasets'
import { TradeBooks } from './pages/TradeBooks'
import { Runs } from './pages/Runs'
import { Results } from './pages/Results'
import { Sweeps } from './pages/Sweeps'
import { Compare } from './pages/Compare'

function App() {
  const healthState = useHealthMonitor()

  return (
    <Layout healthState={healthState}>
      <Routes>
        <Route path="/" element={<Dashboard healthState={healthState} />} />
        <Route path="/datasets" element={<Datasets />} />
        <Route path="/tradebooks" element={<TradeBooks />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/results" element={<Results />} />
        <Route path="/sweeps" element={<Sweeps />} />
        <Route path="/compare" element={<Compare />} />
      </Routes>
    </Layout>
  )
}

export default App
