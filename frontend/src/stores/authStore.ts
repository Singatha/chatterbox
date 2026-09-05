import { create } from 'zustand'
import type { AuthResponse, User } from '../types/auth'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  setSession: (session: AuthResponse) => void
  clearSession: () => void
}

const STORAGE_KEY = 'chatterbox-auth'

function readStoredSession(): Pick<AuthState, 'user' | 'accessToken' | 'refreshToken'> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      return JSON.parse(raw) as Pick<AuthState, 'user' | 'accessToken' | 'refreshToken'>
    }
  } catch {
    sessionStorage.removeItem(STORAGE_KEY)
  }
  return { user: null, accessToken: null, refreshToken: null }
}

export const useAuthStore = create<AuthState>((set) => ({
  ...readStoredSession(),
  setSession: (session) => {
    const stored = {
      user: session.user,
      accessToken: session.access_token,
      refreshToken: session.refresh_token,
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
    set(stored)
  },
  clearSession: () => {
    sessionStorage.removeItem(STORAGE_KEY)
    set({ user: null, accessToken: null, refreshToken: null })
  },
}))
