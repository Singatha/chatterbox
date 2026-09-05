import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { chatApi } from '../api/chat'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { ChatPage } from './ChatPage'

vi.mock('../api/chat', () => ({
  chatApi: {
    listConversations: vi.fn(),
    listMessages: vi.fn(),
    searchUsers: vi.fn(),
    createDirect: vi.fn(),
    sendMessage: vi.fn(),
  },
}))

vi.mock('../hooks/useRealtimeChat', () => ({
  useRealtimeChat: () => ({ status: 'disconnected', sendMessage: () => false }),
}))

const conversation = {
  id: 'conversation-1',
  type: 'direct' as const,
  name: null,
  created_by: 'user-1',
  created_at: '2026-09-05T12:00:00Z',
  updated_at: '2026-09-05T12:00:00Z',
  members: [
    { user_id: 'user-1', username: 'alice', role: 'member' },
    { user_id: 'user-2', username: 'bob', role: 'member' },
  ],
  last_message: null,
}

beforeEach(() => {
  useAuthStore.getState().setSession({
    access_token: 'access-token',
    refresh_token: 'refresh-token',
    token_type: 'bearer',
    user: {
      id: 'user-1',
      username: 'alice',
      email: 'alice@example.com',
      created_at: '2026-09-05T12:00:00Z',
      updated_at: '2026-09-05T12:00:00Z',
    },
  })
  useChatStore.getState().selectConversation(null)
  vi.mocked(chatApi.listConversations).mockResolvedValue([conversation])
  vi.mocked(chatApi.listMessages).mockResolvedValue({
    items: [
      {
        id: 'message-1',
        conversation_id: conversation.id,
        sender_id: 'user-2',
        sender_username: 'bob',
        content: 'Hello Alice',
        created_at: '2026-09-05T12:01:00Z',
        edited_at: null,
        cursor: 'cursor-1',
      },
    ],
    next_cursor: null,
  })
  vi.mocked(chatApi.searchUsers).mockResolvedValue([])
  vi.mocked(chatApi.sendMessage).mockResolvedValue({
    id: 'message-2',
    conversation_id: conversation.id,
    sender_id: 'user-1',
    sender_username: 'alice',
    content: 'Hi Bob',
    created_at: '2026-09-05T12:02:00Z',
    edited_at: null,
    cursor: 'cursor-2',
  })
})

afterEach(() => {
  useAuthStore.getState().clearSession()
  vi.clearAllMocks()
})

test('loads a conversation and sends a persisted message', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><ChatPage /></QueryClientProvider>)

  expect(await screen.findByText('Hello Alice')).toBeInTheDocument()
  expect((await screen.findAllByText('bob')).length).toBeGreaterThan(0)

  await userEvent.type(screen.getByLabelText('Message'), 'Hi Bob')
  await userEvent.click(screen.getByRole('button', { name: 'Send message' }))

  await waitFor(() => {
    expect(chatApi.sendMessage).toHaveBeenCalledWith(
      'access-token',
      conversation.id,
      'Hi Bob',
    )
  })
})
