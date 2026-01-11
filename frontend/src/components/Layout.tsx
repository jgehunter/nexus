import { ReactNode } from 'react'
import { Navbar } from './Navbar'
import type { ConnectionState } from '../api/health'

interface LayoutProps {
  children: ReactNode
  healthState: ConnectionState & { retry: () => void }
}

export function Layout({ children, healthState }: LayoutProps) {
  const { status } = healthState

  return (
    <div className="layout">
      <Navbar connectionStatus={status} />
      <main className="main">
        {children}
      </main>
    </div>
  )
}
