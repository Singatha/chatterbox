import { MessageOutlined, SafetyCertificateOutlined, ThunderboltOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'

interface AuthShellProps {
  children: ReactNode
}

export function AuthShell({ children }: AuthShellProps) {
  return (
    <main className="auth-shell">
      <section className="brand-panel">
        <div className="brand-mark"><MessageOutlined /></div>
        <p className="eyebrow">Chatterbox</p>
        <h1>Conversation,<br />without the noise.</h1>
        <p className="brand-copy">
          A focused space for fast, private conversations with the people who matter.
        </p>
        <div className="feature-row">
          <span><ThunderboltOutlined /> Realtime</span>
          <span><SafetyCertificateOutlined /> Secure</span>
        </div>
      </section>
      <section className="form-panel">{children}</section>
    </main>
  )
}
