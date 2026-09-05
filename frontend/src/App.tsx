import { useState } from 'react'
import { ChatPage } from './pages/ChatPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { useAuthStore } from './stores/authStore'

export default function App() {
  const [screen, setScreen] = useState<'login' | 'register'>('login')
  const user = useAuthStore((state) => state.user)

  if (user) {
    return <ChatPage />
  }

  return screen === 'login' ? (
    <LoginPage onShowRegister={() => setScreen('register')} />
  ) : (
    <RegisterPage onShowLogin={() => setScreen('login')} />
  )
}
