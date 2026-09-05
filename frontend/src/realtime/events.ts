import type { Message } from '../types/chat'

export interface ConnectionReadyEvent {
  type: 'connection.ready'
  data: { user_id: string }
}

export interface MessageCreatedEvent {
  type: 'message.created'
  request_id: string | null
  data: Message
}

export interface ErrorEvent {
  type: 'error'
  request_id: string | null
  error: { code: string; message: string }
}

export type ServerEvent = ConnectionReadyEvent | MessageCreatedEvent | ErrorEvent

export interface MessageSendEvent {
  type: 'message.send'
  request_id: string
  conversation_id: string
  content: string
}

export function isServerEvent(value: unknown): value is ServerEvent {
  if (!value || typeof value !== 'object' || !('type' in value)) return false
  const event = value as Record<string, unknown>
  if (event.type === 'connection.ready') {
    const data = event.data as Record<string, unknown> | undefined
    return typeof data?.user_id === 'string'
  }
  if (event.type === 'message.created') {
    const data = event.data as Record<string, unknown> | undefined
    return typeof data?.id === 'string'
      && typeof data.conversation_id === 'string'
      && typeof data.content === 'string'
      && typeof data.cursor === 'string'
  }
  if (event.type === 'error') {
    const error = event.error as Record<string, unknown> | undefined
    return typeof error?.code === 'string' && typeof error.message === 'string'
  }
  return false
}
