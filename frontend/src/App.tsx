import { useMutation } from '@tanstack/react-query'
import { Button, message } from 'antd'
import { useState } from 'react'
import { authApi } from './api/auth'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { useAuthStore } from './stores/authStore'

export default function App() {
  const [screen, setScreen] = useState<'login' | 'register'>('login')
  const user = useAuthStore((state) => state.user)
  const refreshToken = useAuthStore((state) => state.refreshToken)
  const clearSession = useAuthStore((state) => state.clearSession)
  const logout = useMutation({
    mutationFn: () => refreshToken ? authApi.logout(refreshToken) : Promise.resolve(),
    onSettled: clearSession,
    onError: () => void message.warning('Your local session was cleared.'),
  })

  if (user) {
    return (
      <main className="placeholder-shell">
        <div className="placeholder-card">
          <div className="brand-mark small">R</div>
          <p className="eyebrow dark">Signed in</p>
          <h2>Welcome, {user.username}</h2>
          <p>Your account foundation is ready. Conversations arrive in the next increment.</p>
          <Button loading={logout.isPending} onClick={() => logout.mutate()}>Sign out</Button>
        </div>
      </main>
    )
  }

  return screen === 'login' ? (
    <LoginPage onShowRegister={() => setScreen('register')} />
  ) : (
    <RegisterPage onShowLogin={() => setScreen('login')} />
  )
}
