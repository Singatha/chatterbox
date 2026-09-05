import type { Message } from '../types/chat'

export interface ConnectionReadyEvent {
  type: 'connection.ready'
  data: { user_id: string; online_user_ids: string[] }
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

export interface ReceiptEventData {
  message_id: string
  conversation_id: string
  user_id: string
  delivered_at: string | null
  read_at: string | null
}

export interface MessageDeliveredEvent {
  type: 'message.delivered'
  data: ReceiptEventData
}

export interface MessageReadEvent {
  type: 'message.read'
  request_id: string | null
  data: ReceiptEventData
}

export interface TypingEvent {
  type: 'typing.start' | 'typing.stop'
  data: { conversation_id: string; user_id: string }
}

export interface PresenceOnlineEvent {
  type: 'presence.online'
  data: { user_id: string }
}

export interface PresenceOfflineEvent {
  type: 'presence.offline'
  data: { user_id: string; last_seen: string }
}

export type ServerEvent =
  | ConnectionReadyEvent
  | MessageCreatedEvent
  | MessageDeliveredEvent
  | MessageReadEvent
  | TypingEvent
  | PresenceOnlineEvent
  | PresenceOfflineEvent
  | ErrorEvent

export interface MessageSendEvent {
  type: 'message.send'
  request_id: string
  conversation_id: string
  content: string
}

export interface MessageReadRequest {
  type: 'message.read'
  request_id: string
  conversation_id: string
  message_id: string
}

export interface TypingRequest {
  type: 'typing.start' | 'typing.stop'
  conversation_id: string
}

function hasStringData(event: Record<string, unknown>, ...keys: string[]): boolean {
  const data = event.data as Record<string, unknown> | undefined
  return keys.every((key) => typeof data?.[key] === 'string')
}

export function isServerEvent(value: unknown): value is ServerEvent {
  if (!value || typeof value !== 'object' || !('type' in value)) return false
  const event = value as Record<string, unknown>
  if (event.type === 'connection.ready') {
    const data = event.data as Record<string, unknown> | undefined
    return typeof data?.user_id === 'string'
      && Array.isArray(data.online_user_ids)
      && data.online_user_ids.every((id) => typeof id === 'string')
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
  if (event.type === 'message.delivered' || event.type === 'message.read') {
    return hasStringData(event, 'message_id', 'conversation_id', 'user_id')
  }
  if (event.type === 'typing.start' || event.type === 'typing.stop') {
    return hasStringData(event, 'conversation_id', 'user_id')
  }
  if (event.type === 'presence.online') return hasStringData(event, 'user_id')
  if (event.type === 'presence.offline') return hasStringData(event, 'user_id', 'last_seen')
  return false
}
