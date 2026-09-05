import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef } from 'react'
import { chatApi } from '../api/chat'
import { RealtimeClient } from '../realtime/client'
import type { ErrorEvent, ServerEvent } from '../realtime/events'
import { useChatStore } from '../stores/chatStore'
import type { Message, MessagePage } from '../types/chat'

function newestMessage(messages: Message[]): Message | undefined {
  const sorted = messages.slice().sort((left, right) =>
    left.created_at === right.created_at
      ? left.id.localeCompare(right.id)
      : left.created_at.localeCompare(right.created_at),
  )
  return sorted[sorted.length - 1]
}

async function recoverLoadedConversations(
  queryClient: QueryClient,
  accessToken: string,
  addMessage: (message: Message) => void,
): Promise<void> {
  const loaded = queryClient.getQueriesData<InfiniteData<MessagePage>>({
    queryKey: ['messages'],
  })
  await Promise.all(loaded.map(async ([queryKey, data]) => {
    const conversationId = String(queryKey[1] ?? '')
    const cached = data?.pages.flatMap((page) => page.items) ?? []
    const realtime = useChatStore.getState().realtimeMessages[conversationId] ?? []
    let cursor = newestMessage([...cached, ...realtime])?.cursor
    if (!conversationId || !cursor) return
    for (let pageNumber = 0; pageNumber < 20; pageNumber += 1) {
      const page = await chatApi.recoverMessages(accessToken, conversationId, cursor)
      page.items.forEach(addMessage)
      if (!page.next_cursor) break
      cursor = page.next_cursor
    }
  }))
  await queryClient.invalidateQueries({ queryKey: ['conversations'] })
}

export function useRealtimeChat(accessToken: string | null, onError: (event: ErrorEvent) => void) {
  const queryClient = useQueryClient()
  const clientRef = useRef<RealtimeClient | null>(null)
  const errorHandlerRef = useRef(onError)
  const addMessage = useChatStore((state) => state.addRealtimeMessage)
  const setStatus = useChatStore((state) => state.setConnectionStatus)
  const status = useChatStore((state) => state.connectionStatus)

  useEffect(() => { errorHandlerRef.current = onError }, [onError])

  useEffect(() => {
    if (!accessToken) return
    const handleEvent = (event: ServerEvent) => {
      if (event.type === 'message.created') {
        addMessage(event.data)
        void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      } else if (event.type === 'error') {
        errorHandlerRef.current(event)
      }
    }
    const client = new RealtimeClient({
      accessToken,
      onEvent: handleEvent,
      onStatus: setStatus,
      onOpen: (reconnected) => {
        if (reconnected) {
          void recoverLoadedConversations(queryClient, accessToken, addMessage)
        }
      },
    })
    clientRef.current = client
    client.connect()
    return () => {
      client.disconnect()
      clientRef.current = null
    }
  }, [accessToken, addMessage, queryClient, setStatus])

  const sendMessage = useCallback(
    (conversationId: string, content: string) =>
      clientRef.current?.sendMessage(conversationId, content) ?? false,
    [],
  )
  return { status, sendMessage }
}
