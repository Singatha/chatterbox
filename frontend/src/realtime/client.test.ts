import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { useChatStore } from '../stores/chatStore'
import type { Message } from '../types/chat'
import { RealtimeClient } from './client'
import type { ServerEvent } from './events'

class MockWebSocket {
  static readonly OPEN = 1
  static instances: MockWebSocket[] = []

  readonly url: string
  readonly protocols: string[]
  readyState = 0
  sent: string[] = []
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(url: string, protocols: string[]) {
    this.url = url
    this.protocols = protocols
    MockWebSocket.instances.push(this)
  }

  send(payload: string): void {
    this.sent.push(payload)
  }

  close(): void {
    this.readyState = 3
    this.onclose?.(new CloseEvent('close'))
  }

  open(): void {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  receive(event: ServerEvent | object): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(event) }))
  }
}

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('authenticates, emits message events, and validates server frames', () => {
  const events: ServerEvent[] = []
  const statuses: string[] = []
  const client = new RealtimeClient({
    accessToken: 'signed-token',
    onEvent: (event) => events.push(event),
    onStatus: (status) => statuses.push(status),
  })
  client.connect()
  const socket = MockWebSocket.instances[0]
  expect(socket.protocols).toEqual(['access_token', 'signed-token'])
  socket.open()

  expect(client.sendMessage('conversation-1', 'Hello')).toBe(true)
  expect(JSON.parse(socket.sent[0])).toMatchObject({
    type: 'message.send',
    conversation_id: 'conversation-1',
    content: 'Hello',
  })
  expect(client.sendTyping('conversation-1', true)).toBe(true)
  expect(client.markRead('conversation-1', 'message-1')).toBe(true)
  expect(JSON.parse(socket.sent[1])).toEqual({
    type: 'typing.start',
    conversation_id: 'conversation-1',
  })
  expect(JSON.parse(socket.sent[2])).toMatchObject({
    type: 'message.read',
    conversation_id: 'conversation-1',
    message_id: 'message-1',
  })
  socket.receive({ type: 'message.created', data: { id: 'incomplete' } })
  socket.receive({
    type: 'connection.ready',
    data: { user_id: 'user-1', online_user_ids: [] },
  })

  expect(events).toHaveLength(1)
  expect(events[0].type).toBe('connection.ready')
  expect(statuses).toEqual(['connecting', 'connected'])
  client.disconnect()
})

test('reconnects with backoff and marks subsequent opens as recovered', () => {
  const opens: boolean[] = []
  const statuses: string[] = []
  const client = new RealtimeClient({
    accessToken: 'signed-token',
    onEvent: () => undefined,
    onStatus: (status) => statuses.push(status),
    onOpen: (reconnected) => opens.push(reconnected),
  })
  client.connect()
  MockWebSocket.instances[0].open()
  MockWebSocket.instances[0].close()

  vi.advanceTimersByTime(999)
  expect(MockWebSocket.instances).toHaveLength(1)
  vi.advanceTimersByTime(1)
  expect(MockWebSocket.instances).toHaveLength(2)
  MockWebSocket.instances[1].open()

  expect(opens).toEqual([false, true])
  expect(statuses).toContain('reconnecting')
  client.disconnect()
})

test('realtime store deduplicates messages by durable id', () => {
  useChatStore.getState().clearRealtimeState()
  const message: Message = {
    id: 'message-1',
    conversation_id: 'conversation-1',
    sender_id: 'user-1',
    sender_username: 'alice',
    content: 'Once only',
    created_at: '2026-09-05T12:00:00Z',
    edited_at: null,
    cursor: 'cursor-1',
    receipts: [],
  }
  useChatStore.getState().addRealtimeMessage(message)
  useChatStore.getState().addRealtimeMessage(message)

  expect(useChatStore.getState().realtimeMessages['conversation-1']).toEqual([message])
})

test('realtime store tracks presence, typing, and receipt transitions', () => {
  const store = useChatStore.getState()
  store.clearRealtimeState()
  store.setPresenceSnapshot(['user-2'])
  store.setTyping('conversation-1', 'user-2', true)
  store.updateReceipt({
    message_id: 'message-1',
    conversation_id: 'conversation-1',
    user_id: 'user-2',
    delivered_at: '2026-09-05T12:01:00Z',
    read_at: null,
  })

  expect(useChatStore.getState().presence['user-2'].online).toBe(true)
  expect(useChatStore.getState().typingUsers['conversation-1']).toEqual(['user-2'])
  expect(useChatStore.getState().receiptUpdates['message-1'].delivered_at).not.toBeNull()

  useChatStore.getState().setTyping('conversation-1', 'user-2', false)
  useChatStore.getState().setPresence(
    'user-2',
    false,
    '2026-09-05T12:02:00Z',
  )
  expect(useChatStore.getState().typingUsers['conversation-1']).toEqual([])
  expect(useChatStore.getState().presence['user-2']).toEqual({
    online: false,
    lastSeen: '2026-09-05T12:02:00Z',
  })
})
