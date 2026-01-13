import { NavLink } from 'react-router-dom'
import type { ConnectionStatus } from '../api/health'

interface NavbarProps {
  connectionStatus: ConnectionStatus
}

export function Navbar({ connectionStatus }: NavbarProps) {
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="brand-text">eFX Backtester</span>
        <div
          className={`connection-dot connection-dot-${connectionStatus}`}
          title={`Backend: ${connectionStatus}`}
        />
      </div>
      <ul className="navbar-menu">
        <li>
          <NavLink to="/" className={({ isActive }) => isActive ? 'active' : ''}>
            Dashboard
          </NavLink>
        </li>
        <li>
          <NavLink to="/datasets" className={({ isActive }) => isActive ? 'active' : ''}>
            Datasets
          </NavLink>
        </li>
        <li>
          <NavLink to="/tradebooks" className={({ isActive }) => isActive ? 'active' : ''}>
            Trade Books
          </NavLink>
        </li>
        <li>
          <NavLink to="/runs" className={({ isActive }) => isActive ? 'active' : ''}>
            Runs
          </NavLink>
        </li>
        <li>
          <NavLink to="/results" className={({ isActive }) => isActive ? 'active' : ''}>
            Results
          </NavLink>
        </li>
        <li>
          <NavLink to="/sweeps" className={({ isActive }) => isActive ? 'active' : ''}>
            Sweeps
          </NavLink>
        </li>
        <li>
          <NavLink to="/compare" className={({ isActive }) => isActive ? 'active' : ''}>
            Compare
          </NavLink>
        </li>
      </ul>
    </nav>
  )
}
