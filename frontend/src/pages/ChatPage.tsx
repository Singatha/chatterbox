import {
  LogoutOutlined,
  MessageOutlined,
  PlusOutlined,
  SearchOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Avatar, Badge, Button, Empty, Input, List, Modal, Spin, Tooltip, message } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { authApi } from '../api/auth'
import { chatApi } from '../api/chat'
import { ApiError } from '../api/client'
import { useRealtimeChat } from '../hooks/useRealtimeChat'
import type { ErrorEvent } from '../realtime/events'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { conversationTitle, initials } from '../utils/chat'

function lastSeenLabel(value: string | null): string {
  if (!value) return 'Offline'
  return `Last seen ${new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

export function ChatPage() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const accessToken = useAuthStore((state) => state.accessToken)
  const refreshToken = useAuthStore((state) => state.refreshToken)
  const clearSession = useAuthStore((state) => state.clearSession)
  const selectedId = useChatStore((state) => state.selectedConversationId)
  const selectConversation = useChatStore((state) => state.selectConversation)
  const realtimeMessagesByConversation = useChatStore((state) => state.realtimeMessages)
  const presence = useChatStore((state) => state.presence)
  const typingUsers = useChatStore((state) => state.typingUsers)
  const receiptUpdates = useChatStore((state) => state.receiptUpdates)
  const clearRealtimeState = useChatStore((state) => state.clearRealtimeState)
  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState('')
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const typingConversationRef = useRef<string | null>(null)
  const lastReadRef = useRef<string | null>(null)

  const conversationsQuery = useQuery({
    queryKey: ['conversations'],
    queryFn: () => chatApi.listConversations(accessToken ?? ''),
    enabled: Boolean(accessToken),
  })
  const conversations = useMemo(
    () => conversationsQuery.data ?? [],
    [conversationsQuery.data],
  )
  const selected = conversations.find((conversation) => conversation.id === selectedId) ?? null

  useEffect(() => {
    if (!selectedId && conversations.length > 0) selectConversation(conversations[0].id)
  }, [conversations, selectConversation, selectedId])

  const messagesQuery = useInfiniteQuery({
    queryKey: ['messages', selectedId],
    queryFn: ({ pageParam }) => chatApi.listMessages(accessToken ?? '', selectedId!, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(selectedId && accessToken),
  })
  const messages = useMemo(() => {
    const persisted = messagesQuery.data?.pages.slice().reverse().flatMap((page) => page.items) ?? []
    const realtimeMessages = selectedId
      ? realtimeMessagesByConversation[selectedId] ?? []
      : []
    const unique = new Map([...persisted, ...realtimeMessages].map((item) => [item.id, item]))
    return [...unique.values()].sort((left, right) =>
      left.created_at === right.created_at
        ? left.id.localeCompare(right.id)
        : left.created_at.localeCompare(right.created_at),
    )
  }, [messagesQuery.data, realtimeMessagesByConversation, selectedId])

  const handleRealtimeError = useCallback(
    (event: ErrorEvent) => void message.error(event.error.message),
    [],
  )
  const {
    status: realtimeStatus,
    sendMessage: sendRealtimeMessage,
    sendTyping,
    markRead,
  } = useRealtimeChat(accessToken, handleRealtimeError)
  const peer = selected?.members.find((member) => member.user_id !== user?.id) ?? null
  const peerPresence = peer ? presence[peer.user_id] : undefined
  const peerOnline = peerPresence?.online ?? false
  const peerLastSeen = peerPresence?.lastSeen ?? peer?.last_seen ?? null
  const peerTyping = Boolean(
    selectedId && peer && (typingUsers[selectedId] ?? []).includes(peer.user_id),
  )

  const stopTyping = useCallback(() => {
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    typingTimerRef.current = null
    if (typingConversationRef.current) {
      sendTyping(typingConversationRef.current, false)
      typingConversationRef.current = null
    }
  }, [sendTyping])

  useEffect(() => () => stopTyping(), [selectedId, stopTyping])

  useEffect(() => {
    const latestInbound = [...messages].reverse().find((item) => item.sender_id !== user?.id)
    if (!selectedId || realtimeStatus !== 'connected' || !latestInbound) return
    const receipt = receiptUpdates[latestInbound.id]
      ?? latestInbound.receipts.find((item) => item.user_id === user?.id)
    if (receipt?.read_at || lastReadRef.current === latestInbound.id) return
    if (markRead(selectedId, latestInbound.id)) {
      lastReadRef.current = latestInbound.id
    }
  }, [markRead, messages, receiptUpdates, realtimeStatus, selectedId, user?.id])

  const usersQuery = useQuery({
    queryKey: ['users', search],
    queryFn: () => chatApi.searchUsers(accessToken ?? '', search),
    enabled: Boolean(searchOpen && accessToken),
  })

  const createConversation = useMutation({
    mutationFn: (participantId: string) => chatApi.createDirect(accessToken ?? '', participantId),
    onSuccess: async (conversation) => {
      await queryClient.invalidateQueries({ queryKey: ['conversations'] })
      selectConversation(conversation.id)
      setSearchOpen(false)
      setSearch('')
    },
    onError: (error) => void message.error(error instanceof ApiError ? error.message : 'Could not start conversation'),
  })

  const sendMessage = useMutation({
    mutationFn: (content: string) => chatApi.sendMessage(accessToken ?? '', selectedId!, content),
    onSuccess: async () => {
      setDraft('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['messages', selectedId] }),
        queryClient.invalidateQueries({ queryKey: ['conversations'] }),
      ])
    },
    onError: (error) => void message.error(error instanceof ApiError ? error.message : 'Message could not be sent'),
  })

  const logout = useMutation({
    mutationFn: () => refreshToken ? authApi.logout(refreshToken) : Promise.resolve(),
    onSettled: () => {
      queryClient.clear()
      selectConversation(null)
      clearRealtimeState()
      clearSession()
    },
  })

  if (!user || !accessToken) return null

  const submitMessage = () => {
    const content = draft.trim()
    if (!content || !selectedId || sendMessage.isPending) return
    stopTyping()
    if (realtimeStatus === 'connected' && sendRealtimeMessage(selectedId, content)) {
      setDraft('')
      return
    }
    sendMessage.mutate(content)
  }

  const updateDraft = (value: string) => {
    setDraft(value)
    if (!selectedId || realtimeStatus !== 'connected') return
    if (!value.trim()) {
      stopTyping()
      return
    }
    if (typingConversationRef.current !== selectedId) {
      stopTyping()
      if (sendTyping(selectedId, true)) typingConversationRef.current = selectedId
    }
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    typingTimerRef.current = setTimeout(stopTyping, 1500)
  }

  const connectionLabel = {
    connected: 'Live',
    connecting: 'Connecting',
    reconnecting: 'Reconnecting',
    disconnected: 'Offline',
  }[realtimeStatus]

  return (
    <main className="chat-shell">
      <aside className="chat-sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-logo"><MessageOutlined /></span>
          <strong>Chatterbox</strong>
        </div>
        <div className="current-user">
          <Avatar className="avatar purple">{initials(user.username)}</Avatar>
          <div><strong>{user.username}</strong><span className={`connection-state ${realtimeStatus}`}><i />{connectionLabel}</span></div>
          <Tooltip title="Sign out"><Button type="text" icon={<LogoutOutlined />} loading={logout.isPending} onClick={() => logout.mutate()} /></Tooltip>
        </div>
        <div className="conversation-heading">
          <span>Messages</span>
          <Tooltip title="New conversation"><Button type="text" icon={<PlusOutlined />} onClick={() => setSearchOpen(true)} /></Tooltip>
        </div>
        <div className="conversation-list">
          {conversationsQuery.isLoading ? <Spin className="center-spin" /> : conversations.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No conversations yet">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setSearchOpen(true)}>Start one</Button>
            </Empty>
          ) : conversations.map((conversation) => {
            const title = conversationTitle(conversation, user.id)
            const conversationPeer = conversation.members.find((member) => member.user_id !== user.id)
            const online = conversationPeer
              ? presence[conversationPeer.user_id]?.online ?? false
              : false
            return (
              <button key={conversation.id} type="button" className={`conversation-row ${selectedId === conversation.id ? 'active' : ''}`} onClick={() => selectConversation(conversation.id)}>
                <Badge dot color={online ? '#29b474' : '#b8b9c5'} offset={[-2, 30]}><Avatar className="avatar">{initials(title)}</Avatar></Badge>
                <span className="conversation-copy"><strong>{title}</strong><small>{conversation.last_message?.content ?? 'Start the conversation'}</small></span>
                {conversation.unread_count > 0 && <Badge count={conversation.unread_count} overflowCount={99} />}
              </button>
            )
          })}
        </div>
      </aside>

      <section className="chat-main">
        {!selected ? (
          <div className="chat-empty"><span className="empty-icon"><MessageOutlined /></span><h2>Your conversations live here</h2><p>Find someone and say hello.</p><Button type="primary" icon={<PlusOutlined />} onClick={() => setSearchOpen(true)}>New conversation</Button></div>
        ) : (
          <>
            <header className="chat-header">
              <Avatar className="avatar">{initials(conversationTitle(selected, user.id))}</Avatar>
              <div><strong>{conversationTitle(selected, user.id)}</strong><span>{peerOnline ? 'Online' : lastSeenLabel(peerLastSeen)}</span></div>
            </header>
            <div className="message-scroll">
              {messagesQuery.hasNextPage && <Button className="load-older" loading={messagesQuery.isFetchingNextPage} onClick={() => messagesQuery.fetchNextPage()}>Load older messages</Button>}
              {messagesQuery.isLoading ? <Spin className="center-spin" /> : messagesQuery.error ? <Alert type="error" message="Messages could not be loaded" /> : messages.length === 0 ? <div className="first-message"><Avatar size={58} className="avatar">{initials(conversationTitle(selected, user.id))}</Avatar><h3>Start your conversation with {conversationTitle(selected, user.id)}</h3><p>Messages are private to conversation members.</p></div> : messages.map((item) => {
                const own = item.sender_id === user.id
                const receipt = receiptUpdates[item.id] ?? item.receipts[0]
                const receiptLabel = receipt?.read_at ? 'Read' : receipt?.delivered_at ? 'Delivered' : 'Sent'
                return <div key={item.id} className={`message-line ${own ? 'own' : ''}`}><div className="message-meta"><strong>{own ? 'You' : item.sender_username}</strong><time>{new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div><div className="message-bubble">{item.content}</div>{own && <small className="receipt-state">{receiptLabel}</small>}</div>
              })}
              {peerTyping && <div className="typing-indicator"><i /><i /><i /><span>{peer?.username} is typing</span></div>}
            </div>
            <div className="composer">
              <Input.TextArea aria-label="Message" rows={1} value={draft} placeholder={`Message ${conversationTitle(selected, user.id)}`} onChange={(event) => updateDraft(event.target.value)} onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); submitMessage() } }} />
              <Button type="primary" shape="circle" aria-label="Send message" icon={<SendOutlined />} loading={sendMessage.isPending} disabled={!draft.trim()} onClick={submitMessage} />
            </div>
          </>
        )}
      </section>

      <Modal title="New conversation" open={searchOpen} footer={null} onCancel={() => setSearchOpen(false)} destroyOnHidden>
        <Input prefix={<SearchOutlined />} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by username or email" autoFocus />
        <List className="user-results" loading={usersQuery.isLoading} dataSource={usersQuery.data ?? []} locale={{ emptyText: search ? 'No people found' : 'Search for someone to message' }} renderItem={(person) => <List.Item actions={[<Button key="message" type="primary" icon={<MessageOutlined />} loading={createConversation.isPending} onClick={() => createConversation.mutate(person.id)}>Message</Button>]}><List.Item.Meta avatar={<Avatar icon={<UserOutlined />} />} title={person.username} /></List.Item>} />
      </Modal>
    </main>
  )
}
