import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test } from 'vitest'
import { LoginPage } from './LoginPage'
import { RegisterPage } from './RegisterPage'

const renderWithQuery = (node: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>)

afterEach(async () => {
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
  cleanup()
})

test('login page validates required fields', async () => {
  renderWithQuery(<LoginPage onShowRegister={() => undefined} />)
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('Enter your email or username')).toBeInTheDocument()
  expect(await screen.findByText('Enter your password')).toBeInTheDocument()
})

test('registration page exposes account fields', () => {
  renderWithQuery(<RegisterPage onShowLogin={() => undefined} />)
  expect(screen.getByLabelText('Username')).toBeInTheDocument()
  expect(screen.getByLabelText('Email')).toBeInTheDocument()
  expect(screen.getByLabelText('Password')).toBeInTheDocument()
})
