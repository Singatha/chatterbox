import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { Alert, Button, Form, Input } from 'antd'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthShell } from '../components/AuthShell'
import { useAuthStore } from '../stores/authStore'
import type { RegisterPayload } from '../types/auth'

interface RegisterPageProps {
  onShowLogin: () => void
}

export function RegisterPage({ onShowLogin }: RegisterPageProps) {
  const setSession = useAuthStore((state) => state.setSession)
  const mutation = useMutation({ mutationFn: authApi.register, onSuccess: setSession })

  return (
    <AuthShell>
      <div className="auth-card">
        <p className="eyebrow dark">Start talking</p>
        <h2>Create your account</h2>
        <p className="form-intro">One minute from your first conversation.</p>
        {mutation.error && (
          <Alert type="error" showIcon message={mutation.error instanceof ApiError ? mutation.error.message : 'Unable to register'} />
        )}
        <Form<RegisterPayload> layout="vertical" requiredMark={false} onFinish={(values) => mutation.mutate(values)}>
          <Form.Item label="Username" name="username" rules={[{ required: true }, { min: 3 }, { pattern: /^[A-Za-z0-9_]+$/, message: 'Use letters, numbers, and underscores only' }]}>
            <Input size="large" prefix={<UserOutlined />} autoComplete="username" placeholder="alex_river" />
          </Form.Item>
          <Form.Item label="Email" name="email" rules={[{ required: true }, { type: 'email' }]}>
            <Input size="large" prefix={<MailOutlined />} autoComplete="email" placeholder="you@example.com" />
          </Form.Item>
          <Form.Item label="Password" name="password" rules={[{ required: true }, { min: 8, message: 'Use at least 8 characters' }]}>
            <Input.Password size="large" prefix={<LockOutlined />} autoComplete="new-password" placeholder="At least 8 characters" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={mutation.isPending}>Create account</Button>
        </Form>
        <p className="switch-auth">Already have an account? <button type="button" onClick={onShowLogin}>Sign in</button></p>
      </div>
    </AuthShell>
  )
}

