import { useState } from 'react'
import { GoogleLogin } from '@react-oauth/google'
import { verifyGoogleToken } from '../api'
import type { AuthUser } from '../types'

interface Props {
  onLogin: (user: AuthUser) => void
}

const SESSION_TTL = 8 * 60 * 60 * 1000

export default function LoginOverlay({ onLogin }: Props) {
  const [error, setError] = useState('')

  async function handleSuccess(credentialResponse: { credential?: string }) {
    if (!credentialResponse.credential) return
    try {
      const user = await verifyGoogleToken(credentialResponse.credential)
      const session: AuthUser = { ...user, exp: Date.now() + SESSION_TTL }
      localStorage.setItem('procurement_auth', JSON.stringify(session))
      onLogin(session)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Erro de autenticação.'
      setError(msg)
    }
  }

  return (
    <div className="login-overlay">
      <div className="login-card">
        <img src="/vtex-logo-rebel.svg" className="vtex-logo-login" alt="VTEX" />
        <h1>PO Orders</h1>
        <p className="subtitle">Acesso restrito a colaboradores VTEX</p>

        <div className="login-divider" />

        <div className="google-btn-wrapper">
          <GoogleLogin
            onSuccess={handleSuccess}
            onError={() => setError('Falha ao autenticar com o Google.')}
            width="320"
          />
        </div>

        {error && (
          <div className="alert alert-danger mt-3" style={{ fontSize: '.85rem' }}>
            {error}
          </div>
        )}

        <p className="login-hint">
          Use sua conta <strong>@vtex.com</strong> para entrar
        </p>
      </div>
    </div>
  )
}
