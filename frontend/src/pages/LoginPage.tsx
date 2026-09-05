import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { Alert, Button, Form, Input } from 'antd'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthShell } from '../components/AuthShell'
import { useAuthStore } from '../stores/authStore'
import type { LoginPayload } from '../types/auth'

interface LoginPageProps {
  onShowRegister: () => void
}

export function LoginPage({ onShowRegister }: LoginPageProps) {
  const setSession = useAuthStore((state) => state.setSession)
  const mutation = useMutation({ mutationFn: authApi.login, onSuccess: setSession })

  return (
    <AuthShell>
      <div className="auth-card">
        <p className="eyebrow dark">Welcome back</p>
        <h2>Sign in to Chatterbox</h2>
        <p className="form-intro">Pick up where your conversations left off.</p>
        {mutation.error && (
          <Alert
            type="error"
            showIcon
            message={mutation.error instanceof ApiError ? mutation.error.message : 'Unable to sign in'}
          />
        )}
        <Form<LoginPayload> layout="vertical" requiredMark={false} onFinish={(values) => mutation.mutate(values)}>
          <Form.Item label="Email or username" name="login" rules={[{ required: true, message: 'Enter your email or username' }]}>
            <Input size="large" prefix={<UserOutlined />} autoComplete="username" placeholder="you@example.com" />
          </Form.Item>
          <Form.Item label="Password" name="password" rules={[{ required: true, message: 'Enter your password' }]}>
            <Input.Password size="large" prefix={<LockOutlined />} autoComplete="current-password" placeholder="Your password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={mutation.isPending}>Sign in</Button>
        </Form>
        <p className="switch-auth">New to Chatterbox? <button type="button" onClick={onShowRegister}>Create an account</button></p>
      </div>
    </AuthShell>
  )
}
