import type { ConnectionStatus } from '../stores/chatStore'
import type { MessageSendEvent, ServerEvent } from './events'
import { isServerEvent } from './events'

interface RealtimeClientOptions {
  accessToken: string
  onEvent: (event: ServerEvent) => void
  onStatus: (status: ConnectionStatus) => void
  onOpen?: (reconnected: boolean) => void
}

function websocketUrl(): string {
  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  return `${apiUrl.replace(/^http/, 'ws').replace(/\/$/, '')}/ws`
}

export class RealtimeClient {
  private socket: WebSocket | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private retryAttempt = 0
  private stopped = true
  private hasConnected = false

  constructor(private readonly options: RealtimeClientOptions) {}

  connect(): void {
    if (!this.stopped) return
    this.stopped = false
    this.open()
  }

  disconnect(): void {
    this.stopped = true
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.retryTimer = null
    this.socket?.close(1000, 'Client disconnected')
    this.socket = null
    this.options.onStatus('disconnected')
  }

  sendMessage(conversationId: string, content: string): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return false
    const event: MessageSendEvent = {
      type: 'message.send',
      request_id: crypto.randomUUID(),
      conversation_id: conversationId,
      content,
    }
    this.socket.send(JSON.stringify(event))
    return true
  }

  private open(): void {
    this.options.onStatus(this.hasConnected ? 'reconnecting' : 'connecting')
    const socket = new WebSocket(websocketUrl(), ['access_token', this.options.accessToken])
    this.socket = socket

    socket.onopen = () => {
      const reconnected = this.hasConnected
      this.hasConnected = true
      this.retryAttempt = 0
      this.options.onStatus('connected')
      this.options.onOpen?.(reconnected)
    }
    socket.onmessage = (message) => {
      try {
        const event: unknown = JSON.parse(String(message.data))
        if (isServerEvent(event)) this.options.onEvent(event)
      } catch {
        // Ignore malformed server frames and keep the connection alive.
      }
    }
    socket.onerror = () => socket.close()
    socket.onclose = (event) => {
      if (this.socket === socket) this.socket = null
      if (this.stopped) return
      if (event.code === 1008) {
        this.stopped = true
        this.options.onStatus('disconnected')
        return
      }
      this.options.onStatus('reconnecting')
      const delay = Math.min(1000 * 2 ** this.retryAttempt, 30_000)
      this.retryAttempt += 1
      this.retryTimer = setTimeout(() => this.open(), delay)
    }
  }
}
