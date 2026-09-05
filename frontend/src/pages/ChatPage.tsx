import {
  LogoutOutlined,
  MessageOutlined,
  PlusOutlined,
  SearchOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Avatar, Button, Empty, Input, List, Modal, Spin, Tooltip, message } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { authApi } from '../api/auth'
import { chatApi } from '../api/chat'
import { ApiError } from '../api/client'
import { useRealtimeChat } from '../hooks/useRealtimeChat'
import type { ErrorEvent } from '../realtime/events'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { conversationTitle, initials } from '../utils/chat'

export function ChatPage() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const accessToken = useAuthStore((state) => state.accessToken)
  const refreshToken = useAuthStore((state) => state.refreshToken)
  const clearSession = useAuthStore((state) => state.clearSession)
  const selectedId = useChatStore((state) => state.selectedConversationId)
  const selectConversation = useChatStore((state) => state.selectConversation)
  const realtimeMessagesByConversation = useChatStore((state) => state.realtimeMessages)
  const clearRealtimeState = useChatStore((state) => state.clearRealtimeState)
  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState('')

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
  const realtime = useRealtimeChat(accessToken, handleRealtimeError)

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
    if (realtime.status === 'connected' && realtime.sendMessage(selectedId, content)) {
      setDraft('')
      return
    }
    sendMessage.mutate(content)
  }

  const connectionLabel = {
    connected: 'Live',
    connecting: 'Connecting',
    reconnecting: 'Reconnecting',
    disconnected: 'Offline',
  }[realtime.status]

  return (
    <main className="chat-shell">
      <aside className="chat-sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-logo"><MessageOutlined /></span>
          <strong>Chatterbox</strong>
        </div>
        <div className="current-user">
          <Avatar className="avatar purple">{initials(user.username)}</Avatar>
          <div><strong>{user.username}</strong><span className={`connection-state ${realtime.status}`}><i />{connectionLabel}</span></div>
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
            return (
              <button key={conversation.id} type="button" className={`conversation-row ${selectedId === conversation.id ? 'active' : ''}`} onClick={() => selectConversation(conversation.id)}>
                <Avatar className="avatar">{initials(title)}</Avatar>
                <span className="conversation-copy"><strong>{title}</strong><small>{conversation.last_message?.content ?? 'Start the conversation'}</small></span>
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
              <div><strong>{conversationTitle(selected, user.id)}</strong><span>Direct message · {connectionLabel}</span></div>
            </header>
            <div className="message-scroll">
              {messagesQuery.hasNextPage && <Button className="load-older" loading={messagesQuery.isFetchingNextPage} onClick={() => messagesQuery.fetchNextPage()}>Load older messages</Button>}
              {messagesQuery.isLoading ? <Spin className="center-spin" /> : messagesQuery.error ? <Alert type="error" message="Messages could not be loaded" /> : messages.length === 0 ? <div className="first-message"><Avatar size={58} className="avatar">{initials(conversationTitle(selected, user.id))}</Avatar><h3>Start your conversation with {conversationTitle(selected, user.id)}</h3><p>Messages are private to conversation members.</p></div> : messages.map((item) => {
                const own = item.sender_id === user.id
                return <div key={item.id} className={`message-line ${own ? 'own' : ''}`}><div className="message-meta"><strong>{own ? 'You' : item.sender_username}</strong><time>{new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div><div className="message-bubble">{item.content}</div></div>
              })}
            </div>
            <div className="composer">
              <Input.TextArea aria-label="Message" rows={1} value={draft} placeholder={`Message ${conversationTitle(selected, user.id)}`} onChange={(event) => setDraft(event.target.value)} onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); submitMessage() } }} />
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
