export interface User {
  id: string
  username: string
  email: string
  created_at: string
  updated_at: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  user: User
}

export interface RegisterPayload {
  username: string
  email: string
  password: string
}

export interface LoginPayload {
  login: string
  password: string
}

